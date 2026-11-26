"""Compose an image with a vector template into a self-contained SVG, and export it."""

import contextlib
import io
from html import escape
from typing import Any

import cairosvg

from . import imaging

DEFAULT_PARAMS: dict = {
    # All lengths are percentages of the image's shorter side, so templates work at any resolution.
    "padding": 5.0,
    "padding_bottom_extra": 0.0,
    "background": "#ffffff",
    "background_transparent": False,
    "image_radius": 0.0,
    "frame_radius": 0.0,
    "border_width": 0.0,
    "border_color": "#111111",
    "outline_mode": "none",  # none | rect | contour
    "outline_width": 2.0,
    "outline_offset": 0.0,
    "outline_color": "#ffffff",
    "cutline": False,  # thin cut line around the outer outline/contour (for die-cut stickers)
    "cutline_color": "#ff00ff",
    "title_text": "",
    "title_position": "bottom",  # top | bottom | overlay-top | overlay-bottom
    "title_size": 7.0,
    "title_color": "#111111",
    "title_font": "DejaVu Sans",
    "title_weight": "bold",
    "title_align": "middle",  # start | middle | end
}

NUMERIC = {
    "padding",
    "padding_bottom_extra",
    "image_radius",
    "frame_radius",
    "border_width",
    "outline_width",
    "outline_offset",
    "title_size",
}
BOOLEAN = {"background_transparent", "cutline"}
CHOICES = {
    "outline_mode": {"none", "rect", "contour"},
    "title_position": {"top", "bottom", "overlay-top", "overlay-bottom"},
    "title_align": {"start", "middle", "end"},
    "title_weight": {"normal", "bold"},
}


def _color(v: str, fallback: str) -> str:
    v = (v or "").strip()
    if v.startswith("#") and len(v) in (4, 7) and all(c in "0123456789abcdefABCDEF" for c in v[1:]):
        return v
    return fallback


def normalize(params: dict | None) -> dict:
    """Merge with defaults and coerce/validate every value (params may come from a form)."""
    out = dict(DEFAULT_PARAMS)
    for key, val in (params or {}).items():
        if key not in DEFAULT_PARAMS:
            continue
        if key in NUMERIC:
            with contextlib.suppress(TypeError, ValueError):
                out[key] = max(0.0, min(200.0, float(val)))
        elif key in BOOLEAN:
            out[key] = val in (True, 1, "1", "true", "on", "yes")
        elif key in CHOICES:
            if val in CHOICES[key]:
                out[key] = val
        elif key.endswith("_color") or key == "background":
            out[key] = _color(val, DEFAULT_PARAMS[key])
        else:
            out[key] = str(val)[:200]
    return out


def compose_svg(img: Any, params: dict, *, href: str, title: str = "") -> tuple[str, float, float]:
    """Return (svg, width, height) in px of the source image's coordinate system.

    `img` is a db Image (needs id, width, height, stored_filename); `href` is what <image> points to.
    """
    p = normalize(params)
    W, H = float(img.width), float(img.height)
    u = min(W, H) / 100.0

    pad = p["padding"] * u
    pad_b_extra = p["padding_bottom_extra"] * u
    bw = p["border_width"] * u
    img_r = min(p["image_radius"] * u, min(W, H) / 2)

    mode = p["outline_mode"]
    ow, oo = p["outline_width"] * u, p["outline_offset"] * u
    ext = {"none": 0.0, "rect": oo + ow, "contour": ow}[mode]
    cut_w = max(1.0, 0.15 * u) if p["cutline"] else 0.0
    ext_total = ext + cut_w

    text = p["title_text"].replace("{title}", title).strip()
    fs = p["title_size"] * u
    band = fs * 1.6 if text and p["title_position"] in ("top", "bottom") else 0.0

    content_w, content_h = W + 2 * ext_total, H + 2 * ext_total
    total_w = content_w + 2 * pad + 2 * bw
    total_h = content_h + 2 * pad + pad_b_extra + band + 2 * bw
    ix = bw + pad + ext_total
    iy = bw + pad + ext_total + (band if p["title_position"] == "top" else 0.0)
    frame_r = min(p["frame_radius"] * u, min(total_w, total_h) / 2)

    el: list[str] = []
    defs: list[str] = []

    if not p["background_transparent"]:
        el.append(
            f'<rect x="0" y="0" width="{total_w:.2f}" height="{total_h:.2f}" rx="{frame_r:.2f}" '
            f'fill="{p["background"]}"/>'
        )
    if bw > 0:
        el.append(
            f'<rect x="{bw / 2:.2f}" y="{bw / 2:.2f}" width="{total_w - bw:.2f}" height="{total_h - bw:.2f}" '
            f'rx="{max(0.0, frame_r - bw / 2):.2f}" fill="none" stroke="{p["border_color"]}" stroke-width="{bw:.2f}"/>'
        )

    if mode == "rect" and ow > 0:
        o = oo + ow / 2
        rx = img_r + o if img_r > 0 else 0
        el.append(
            f'<rect x="{ix - o:.2f}" y="{iy - o:.2f}" width="{W + 2 * o:.2f}" height="{H + 2 * o:.2f}" rx="{rx:.2f}" '
            f'fill="none" stroke="{p["outline_color"]}" stroke-width="{ow:.2f}"/>'
        )
        if cut_w:
            o2 = oo + ow + cut_w / 2
            el.append(
                f'<rect x="{ix - o2:.2f}" y="{iy - o2:.2f}" width="{W + 2 * o2:.2f}" height="{H + 2 * o2:.2f}" '
                f'rx="{(img_r + o2) if img_r > 0 else 0:.2f}" fill="none" '
                f'stroke="{p["cutline_color"]}" stroke-width="{cut_w:.2f}"/>'
            )
    elif mode == "contour":
        d = imaging.contour_path(img.id, img.stored_filename, int(W), int(H), round(ow, 1))
        if d:
            el.append(f'<path transform="translate({ix:.2f},{iy:.2f})" d="{d}" fill="{p["outline_color"]}"/>')
            if cut_w:
                el.append(
                    f'<path transform="translate({ix:.2f},{iy:.2f})" d="{d}" fill="none" '
                    f'stroke="{p["cutline_color"]}" stroke-width="{cut_w:.2f}"/>'
                )
    elif cut_w:
        # Cut line around the whole piece when no outline is used.
        el.append(
            f'<rect x="{cut_w / 2:.2f}" y="{cut_w / 2:.2f}" '
            f'width="{total_w - cut_w:.2f}" height="{total_h - cut_w:.2f}" '
            f'rx="{frame_r:.2f}" fill="none" stroke="{p["cutline_color"]}" stroke-width="{cut_w:.2f}"/>'
        )

    clip = ""
    if img_r > 0:
        defs.append(
            f'<clipPath id="imgclip"><rect x="{ix:.2f}" y="{iy:.2f}" width="{W:.2f}" height="{H:.2f}" '
            f'rx="{img_r:.2f}"/></clipPath>'
        )
        clip = ' clip-path="url(#imgclip)"'
    el.append(
        f'<image x="{ix:.2f}" y="{iy:.2f}" width="{W:.2f}" height="{H:.2f}" preserveAspectRatio="none" '
        f'href="{escape(href, quote=True)}" xlink:href="{escape(href, quote=True)}"{clip}/>'
    )

    if text:
        pos, align = p["title_position"], p["title_align"]
        tx = {"start": bw + pad, "middle": total_w / 2, "end": total_w - bw - pad}[align]
        if pos == "top":
            ty = bw + pad + band / 2 + fs * 0.35
        elif pos == "bottom":
            ty = iy + H + ext_total + band / 2 + fs * 0.35 + pad_b_extra / 2
        elif pos == "overlay-top":
            ty = iy + fs * 1.3
            tx = {"start": ix + fs * 0.5, "middle": ix + W / 2, "end": ix + W - fs * 0.5}[align]
        else:
            ty = iy + H - fs * 0.7
            tx = {"start": ix + fs * 0.5, "middle": ix + W / 2, "end": ix + W - fs * 0.5}[align]
        el.append(
            f'<text x="{tx:.2f}" y="{ty:.2f}" font-family="{escape(p["title_font"], quote=True)}" '
            f'font-size="{fs:.2f}" font-weight="{p["title_weight"]}" fill="{p["title_color"]}" '
            f'text-anchor="{align}">{escape(text)}</text>'
        )

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{total_w:.2f}" height="{total_h:.2f}" viewBox="0 0 {total_w:.2f} {total_h:.2f}">'
        f"<defs>{''.join(defs)}</defs>{''.join(el)}</svg>"
    )
    return svg, total_w, total_h


def with_physical_size(svg: str, w: float, h: float, width_mm: float | None, dpi: int) -> tuple[str, float, float]:
    """Set width/height in mm on the root element. Default size = source px at `dpi`."""
    wmm = width_mm if width_mm and width_mm > 0 else w / dpi * 25.4
    hmm = wmm * h / w
    head = f'width="{w:.2f}" height="{h:.2f}"'
    return svg.replace(head, f'width="{wmm:.3f}mm" height="{hmm:.3f}mm"', 1), wmm, hmm


def export(svg: str, w: float, h: float, fmt: str, width_mm: float | None, dpi: int) -> tuple[bytes, str]:
    dpi = max(36, min(1200, int(dpi or 300)))
    sized, wmm, hmm = with_physical_size(svg, w, h, width_mm, dpi)
    if fmt == "svg":
        return sized.encode(), "image/svg+xml"
    if fmt == "pdf":
        return cairosvg.svg2pdf(bytestring=sized.encode(), unsafe=False), "application/pdf"
    if fmt == "png":
        px_w = round(wmm / 25.4 * dpi)
        px_h = round(hmm / 25.4 * dpi)
        png = cairosvg.svg2png(bytestring=svg.encode(), output_width=px_w, output_height=px_h, unsafe=False)
        # Embed DPI metadata so print shops read the intended physical size.
        from PIL import Image as PILImage

        im = PILImage.open(io.BytesIO(png))
        buf = io.BytesIO()
        im.save(buf, "PNG", dpi=(dpi, dpi))
        return buf.getvalue(), "image/png"
    raise ValueError("Unknown format")
