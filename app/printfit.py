"""Print-size hints: which common print formats an image fills well, given its pixel size."""

from dataclasses import dataclass

# Common photo, poster and paper sizes in cm (short side first).
FORMATS: list[tuple[str, float, float]] = [
    ("20 × 20 cm", 20, 20),
    ("30 × 30 cm", 30, 30),
    ("40 × 40 cm", 40, 40),
    ("50 × 50 cm", 50, 50),
    ("10 × 15 cm", 10, 15),
    ("13 × 18 cm", 13, 18),
    ("15 × 20 cm", 15, 20),
    ("18 × 24 cm", 18, 24),
    ("A4", 21, 29.7),
    ("20 × 30 cm", 20, 30),
    ("24 × 30 cm", 24, 30),
    ("30 × 40 cm", 30, 40),
    ("A3", 29.7, 42),
    ("30 × 45 cm", 30, 45),
    ("40 × 50 cm", 40, 50),
    ("40 × 60 cm", 40, 60),
    ("A2", 42, 59.4),
    ("50 × 70 cm", 50, 70),
    ("60 × 90 cm", 60, 90),
    ("70 × 100 cm", 70, 100),
]
MIN_DPI = 150  # below this, prints look soft at normal viewing distance
GOOD_DPI = 240
MAX_CROP = 0.12  # formats that would cut off more than this are only shown as a fallback


@dataclass(frozen=True)
class Hint:
    name: str
    width_cm: float  # oriented like the image
    height_cm: float
    dpi: int | None  # None for vector files
    crop: float  # share of the image cut off to fill the format (0..1)
    role: str = ""  # why it is suggested, e.g. "largest sharp size"

    @property
    def quality(self) -> str:
        if self.dpi is None:
            return "sharp at any size"
        if self.dpi >= GOOD_DPI:
            return "excellent"
        return "good" if self.dpi >= MIN_DPI else "soft"

    @property
    def size(self) -> str:
        return f"{self.width_cm:g} × {self.height_cm:g} cm"

    @property
    def label(self) -> str:
        return self.size if self.name.endswith("cm") else f"{self.name} ({self.size})"


def _candidates(w: int, h: int, vector: bool) -> list[Hint]:
    out = []
    for name, short, long in FORMATS:
        fw, fh = (long, short) if w >= h else (short, long)
        img_ratio, fmt_ratio = w / h, fw / fh
        crop = 1 - min(img_ratio / fmt_ratio, fmt_ratio / img_ratio)
        # Filling the format means scaling until both sides are covered; the tighter side sets the resolution.
        dpi = None if vector else int(min(w / (fw / 2.54), h / (fh / 2.54)))
        out.append(Hint(name, fw, fh, dpi, round(crop, 3)))
    return out


def _area(c: Hint) -> float:
    return c.width_cm * c.height_cm


def suggest(width: int | None, height: int | None, kind: str) -> list[Hint]:
    """Two or three formats that give an overall picture: the largest sharp size, the largest size at top quality
    and the format that matches the image's shape best. Formats needing a heavy crop are left out when possible."""
    if not width or not height or kind not in ("raster", "vector"):
        return []
    vector = kind == "vector"
    cands = _candidates(width, height, vector)
    fitting = [c for c in cands if c.crop <= MAX_CROP] or sorted(cands, key=lambda c: c.crop)[:3]
    if vector:
        best = sorted(fitting, key=lambda c: (c.crop, -_area(c)))
        return [_role(c, "fits the shape") for c in best[:3]]
    sharp = [c for c in fitting if (c.dpi or 0) >= MIN_DPI]
    if not sharp:  # too small: show the smallest format so the limit is visible
        return [_role(min(cands, key=_area), "smallest common size")]
    picks: list[Hint] = [_role(max(sharp, key=_area), "largest sharp size")]
    top = [c for c in sharp if (c.dpi or 0) >= GOOD_DPI]
    if top:
        picks.append(_role(max(top, key=_area), "largest at top quality"))
    picks.append(_role(min(sharp, key=lambda c: (c.crop, -_area(c))), "best fit for the shape"))
    unique: dict[str, Hint] = {}
    for p in picks:
        prev = unique.get(p.name)
        unique[p.name] = _role(p, f"{prev.role}, {p.role}") if prev else p
    return sorted(unique.values(), key=_area, reverse=True)


def _role(c: Hint, role: str) -> Hint:
    return Hint(c.name, c.width_cm, c.height_cm, c.dpi, c.crop, role)
