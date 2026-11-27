"""Tags derived from the file itself (vector or raster, transparency, orientation).

Each rule is mapped to at most one tag from the managed list (Tag.auto_rule). Admins can point a rule at any tag
or switch it off by leaving it unassigned; deleting the tag switches the rule off too.
"""

from typing import cast

from PIL import Image as PILImage
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import imaging
from .db import AppMeta, Image, Tag
from .tags import DEFAULT_COLOR, find

# key -> (description shown to admins, tag name created on first start or None to leave the rule off)
RULES: dict[str, tuple[str, str | None]] = {
    "vector": ("Vector files (SVG)", "artwork"),
    "raster": ("Raster files (JPG, PNG, …)", "photo"),
    "transparent": ("Raster files with a transparent background", "transparent"),
    "landscape": ("Wider than tall", None),
    "portrait": ("Taller than wide", None),
    "square": ("Square (within 5 %)", None),
}
SEEDED_KEY = "auto_tags_seeded"


def has_transparency(image_id: int) -> bool:
    """True when the stored preview has pixels that are not (almost) fully opaque."""
    path = imaging.preview_path(image_id)
    if not path.exists():
        return False
    with PILImage.open(path) as im:
        if "A" not in im.getbands():
            return False
        lo, _hi = cast(tuple[int, int], im.getchannel("A").getextrema())
        return lo < 250


def matching_rules(img: Image) -> set[str]:
    if img.parent_id is not None:  # template renders inherit the original's tags instead
        return set()
    found: set[str] = set()
    if img.kind == "vector":
        found.add("vector")
    elif img.kind == "raster":
        found.add("raster")
        if img.has_preview and has_transparency(img.id):
            found.add("transparent")
    if img.width and img.height:
        ratio = img.width / img.height
        found.add("square" if abs(ratio - 1) <= 0.05 else "landscape" if ratio > 1 else "portrait")
    return found


def rule_tags(db: Session) -> dict[str, Tag]:
    return {t.auto_rule: t for t in db.scalars(select(Tag).where(Tag.auto_rule.is_not(None))).all() if t.auto_rule}


def apply(db: Session, img: Image, mapping: dict[str, Tag] | None = None) -> int:
    """Add the tags of all matching rules to the image. Returns how many were added."""
    mapping = rule_tags(db) if mapping is None else mapping
    added = 0
    for rule in sorted(matching_rules(img)):
        tag = mapping.get(rule)
        if tag is not None and tag not in img.tags:
            img.tags.append(tag)
            added += 1
    return added


def apply_all(db: Session) -> int:
    mapping = rule_tags(db)
    added = sum(apply(db, img, mapping) for img in db.scalars(select(Image)).all()) if mapping else 0
    db.commit()
    return added


def assign(db: Session, tag: Tag, rule: str) -> None:
    """Point `rule` at `tag` (moving it away from any other tag); an empty or unknown rule clears the tag's rule."""
    if rule not in RULES:
        tag.auto_rule = None
        return
    for other in db.scalars(select(Tag).where(Tag.auto_rule == rule, Tag.id != tag.id)).all():
        other.auto_rule = None
    tag.auto_rule = rule


def seed_once(db: Session) -> None:
    """On the first start with auto tags: create the default rule tags and tag the existing images once."""
    if db.get(AppMeta, SEEDED_KEY):
        return
    for rule, (_label, name) in RULES.items():
        if name is None:
            continue
        tag = find(db, name)
        if tag is None:
            tag = Tag(name=name, color=DEFAULT_COLOR)
            db.add(tag)
        if tag.auto_rule is None:
            tag.auto_rule = rule
    db.add(AppMeta(key=SEEDED_KEY, value="1"))
    db.flush()
    apply_all(db)
