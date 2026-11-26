import logging
import os
import secrets

import bcrypt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import DropState, GoodsType, Template, User, get_db

log = logging.getLogger("pod")


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode()[:72], hashed.encode())
    except ValueError:
        return False


class LoginRequired(Exception):
    pass


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    uid = request.session.get("uid")
    user = db.get(User, uid) if uid else None
    if not user or not user.is_active:
        request.session.clear()
        raise LoginRequired()
    request.state.user = user
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admins only")
    return user


DEFAULT_STATES = [
    ("Future", "#3b82f6", 10, True),
    ("Released", "#16a34a", 20, False),
    ("Parked", "#9ca3af", 30, False),
]

DEFAULT_GOODS = [
    ("T-shirt", 300, 400),
    ("Hoodie", 300, 400),
    ("Poster A3", 297, 420),
    ("Mug", 200, 85),
    ("Sticker", 100, 100),
    ("Tote bag", 300, 350),
]

DEFAULT_TEMPLATES = {
    "Clean white border": {"padding": 6, "background": "#ffffff", "border_width": 0},
    "Rounded card with title": {
        "padding": 5,
        "background": "#ffffff",
        "image_radius": 4,
        "frame_radius": 6,
        "border_width": 1.5,
        "border_color": "#111111",
        "title_text": "{title}",
        "title_position": "bottom",
        "title_size": 7,
    },
    "Die-cut sticker": {
        "padding": 0,
        "background_transparent": True,
        "outline_mode": "contour",
        "outline_width": 4,
        "outline_color": "#ffffff",
        "cutline": True,
    },
    "Polaroid": {
        "padding": 5,
        "padding_bottom_extra": 18,
        "background": "#fbfbf8",
        "title_text": "{title}",
        "title_position": "bottom",
        "title_size": 6,
        "title_font": "DejaVu Serif",
        "title_weight": "normal",
    },
}


def seed(db: Session) -> None:
    import json

    if not db.scalar(select(User).limit(1)):
        username = os.environ.get("POD_ADMIN_USERNAME", "admin")
        password = os.environ.get("POD_ADMIN_PASSWORD")
        if not password:
            password = secrets.token_urlsafe(12)
            log.warning("=" * 60)
            log.warning("Created initial admin user '%s' with password: %s", username, password)
            log.warning("Change it after first login (Admin > Users).")
            log.warning("=" * 60)
        db.add(User(username=username, password_hash=hash_password(password), role="admin"))
    if not db.scalar(select(DropState).limit(1)):
        for name, color, order, default in DEFAULT_STATES:
            db.add(DropState(name=name, color=color, sort_order=order, is_default=default))
    if not db.scalar(select(GoodsType).limit(1)):
        for name, w, h in DEFAULT_GOODS:
            db.add(GoodsType(name=name, print_width_mm=w, print_height_mm=h))
    if not db.scalar(select(Template).limit(1)):
        for name, params in DEFAULT_TEMPLATES.items():
            db.add(Template(name=name, params_json=json.dumps(params)))
    db.commit()
