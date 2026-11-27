"""The managed tag list: parsing what users type, matching it against the list, and the one-off legacy migration."""

import re
from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import Image, Tag

MAX_LEN = 64
DEFAULT_COLOR = "#64748b"


def clean_name(raw: str) -> str:
    """Collapse whitespace and drop characters that would break the comma-separated input."""
    return re.sub(r"\s+", " ", raw.replace(",", " ")).strip()[:MAX_LEN]


def split_names(raw: str) -> list[str]:
    """Split comma- or newline-separated input into unique names, keeping the first spelling of each."""
    seen: dict[str, str] = {}
    for part in re.split(r"[,\n]", raw):
        name = clean_name(part)
        if name and name.casefold() not in seen:
            seen[name.casefold()] = name
    return list(seen.values())


def all_tags(db: Session) -> list[Tag]:
    return list(db.scalars(select(Tag).order_by(Tag.name)).all())


def find(db: Session, name: str) -> Tag | None:
    return db.scalar(select(Tag).where(func.lower(Tag.name) == clean_name(name).lower()))


def resolve(db: Session, raw: str) -> tuple[list[Tag], list[str]]:
    """Map typed names to tags from the list. Returns (known tags, names that are not on the list)."""
    known: list[Tag] = []
    unknown: list[str] = []
    for name in split_names(raw):
        tag = find(db, name)
        if tag is None:
            unknown.append(name)
        elif tag not in known:
            known.append(tag)
    return known, unknown


def unknown_message(names: Iterable[str]) -> str:
    return "Not on the tag list, so not added: " + ", ".join(names) + ". An admin can add them under Admin › Tags."


def migrate_legacy_tags(db: Session) -> int:
    """Move free-form tags (the old comma-separated column) into the managed list. Safe to run on every start."""
    moved = 0
    for img in db.scalars(select(Image).where(Image.legacy_tags != "")).all():
        for name in split_names(img.legacy_tags):
            tag = find(db, name)
            if tag is None:
                tag = Tag(name=name, color=DEFAULT_COLOR)
                db.add(tag)
                db.flush()
            if tag not in img.tags:
                img.tags.append(tag)
        img.legacy_tags = ""
        moved += 1
    db.commit()
    return moved
