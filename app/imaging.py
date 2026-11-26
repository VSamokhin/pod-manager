"""File ingestion, thumbnails/previews and silhouette (contour) tracing."""

import base64
import io
import mimetypes
import uuid
from functools import lru_cache
from pathlib import Path

import cairosvg
import numpy as np
from PIL import Image as PILImage
from PIL import ImageDraw, ImageFilter, ImageOps

from . import config, trace

PILImage.MAX_IMAGE_PIXELS = 400_000_000  # large print files are expected

RASTER_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff", ".bmp"}
VECTOR_EXT = {".svg"}
# Accepted and stored, but no preview / templating in the MVP.
OTHER_EXT = {".pdf", ".ai", ".eps", ".psd"}
ALLOWED_EXT = RASTER_EXT | VECTOR_EXT | OTHER_EXT


class IngestError(ValueError):
    pass


def original_path(stored: str) -> Path:
    return config.ORIGINALS_DIR / stored


def thumb_path(image_id: int) -> Path:
    return config.THUMBS_DIR / f"{image_id}.webp"


def preview_path(image_id: int) -> Path:
    return config.PREVIEWS_DIR / f"{image_id}.webp"


def classify(filename: str) -> tuple[str, str]:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise IngestError(f"Unsupported file type: {ext or 'no extension'}")
    kind = "raster" if ext in RASTER_EXT else "vector" if ext in VECTOR_EXT else "other"
    mime = mimetypes.types_map.get(ext) or {".svg": "image/svg+xml", ".webp": "image/webp"}.get(
        ext, "application/octet-stream"
    )
    return kind, mime


def store_original(data: bytes, filename: str) -> str:
    ext = Path(filename).suffix.lower()
    stored = f"{uuid.uuid4().hex}{ext}"
    original_path(stored).write_bytes(data)
    return stored


def _render_svg(data: bytes, width: int | None = None) -> PILImage.Image:
    png = cairosvg.svg2png(bytestring=data, output_width=width, unsafe=False)
    return PILImage.open(io.BytesIO(png))


def open_full(kind: str, path: Path) -> PILImage.Image:
    """Full-resolution PIL image with EXIF orientation applied."""
    if kind == "vector":
        return _render_svg(path.read_bytes())
    im = PILImage.open(path)
    im = ImageOps.exif_transpose(im)
    if im.mode not in ("RGB", "RGBA", "L", "LA"):
        im = im.convert("RGBA" if "A" in im.getbands() or im.info.get("transparency") is not None else "RGB")
    return im


def make_derivatives(image_id: int, kind: str, path: Path) -> tuple[int, int]:
    """Create thumbnail + preview; returns (width, height) of the original."""
    if kind == "vector":
        data = path.read_bytes()
        base = _render_svg(data)
        w, h = base.size
        if max(w, h) < config.PREVIEW_SIZE:
            scale_w = round(w * config.PREVIEW_SIZE / max(w, h))
            base = _render_svg(data, width=scale_w)
    else:
        base = open_full(kind, path)
        w, h = base.size
    base.load()
    if base.mode not in ("RGB", "RGBA"):
        base = base.convert("RGBA")
    prev = base.copy()
    prev.thumbnail((config.PREVIEW_SIZE, config.PREVIEW_SIZE))
    prev.save(preview_path(image_id), "WEBP", quality=88)
    th = base.copy()
    th.thumbnail((config.THUMB_SIZE, config.THUMB_SIZE))
    th.save(thumb_path(image_id), "WEBP", quality=80)
    return w, h


def embed_data_uri(kind: str, mime: str, path: Path) -> str:
    """Data URI of the original suitable for <image href> in SVG (cairosvg + browsers)."""
    if kind == "vector":
        return "data:image/svg+xml;base64," + base64.b64encode(path.read_bytes()).decode()
    if mime in ("image/png", "image/jpeg"):
        with PILImage.open(path) as im:
            orientation = im.getexif().get(0x0112, 1)
        if orientation == 1:
            return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()
    im = open_full(kind, path)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def preview_data_uri(image_id: int) -> str:
    return "data:image/webp;base64," + base64.b64encode(preview_path(image_id).read_bytes()).decode()


# ---------------------------------------------------------------- contour tracing

MASK_MAX = 900  # working resolution for silhouette tracing


def _alpha_mask(img: PILImage.Image) -> PILImage.Image:
    if img.mode in ("RGBA", "LA"):
        return img.getchannel("A").point(lambda v: 255 if v > 24 else 0)
    return PILImage.new("L", img.size, 255)


@lru_cache(maxsize=64)
def contour_path(image_id: int, cache_key: str, width: int, height: int, dilate: float, smooth: float = 1.0) -> str:
    """SVG path data (image-local coordinates) of the image silhouette grown by `dilate` px.

    Holes are filled, so the result is the outer die-cut shape of each island.
    `cache_key` should change when the source file changes.
    """
    src = PILImage.open(preview_path(image_id))
    src.load()
    mask = _alpha_mask(src)
    scale = min(1.0, MASK_MAX / max(mask.size))
    if scale < 1.0:
        mask = mask.resize((max(1, round(mask.width * scale)), max(1, round(mask.height * scale))), PILImage.BILINEAR)
        mask = mask.point(lambda v: 255 if v > 127 else 0)
    k = mask.width / width  # mask px per image px
    r = max(0.0, dilate * k)
    pad = int(r) + 4
    padded = PILImage.new("L", (mask.width + 2 * pad, mask.height + 2 * pad), 0)
    padded.paste(mask, (pad, pad))

    # Dilate: repeated 3x3 max filters (alternating square / approx-cross ≈ octagon), then round off.
    steps = int(round(r))
    for i in range(steps):
        padded = padded.filter(ImageFilter.MaxFilter(3))
        if i % 2:
            padded = padded.filter(ImageFilter.GaussianBlur(0.5)).point(lambda v: 255 if v > 90 else 0)
    if r > 1:
        padded = padded.filter(ImageFilter.GaussianBlur(max(1.0, r / 6) * smooth)).point(
            lambda v: 255 if v > 127 else 0
        )

    # Fill holes: flood the outside, everything else becomes solid.
    ImageDraw.floodfill(padded, (0, 0), 128)
    solid = padded.point(lambda v: 0 if v == 128 else 255)

    arr = np.array(solid) > 127
    if not arr.any():
        return ""

    def fmt(p) -> str:
        return f"{(p[0] - pad) / k:.2f},{(p[1] - pad) / k:.2f}"

    return " ".join(trace.smooth_path(poly, fmt) for poly in trace.trace(arr))
