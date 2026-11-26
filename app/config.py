import os
import secrets
from pathlib import Path

DATA_DIR = Path(os.environ.get("POD_DATA_DIR", "./data")).resolve()
FILES_DIR = DATA_DIR / "files"
ORIGINALS_DIR = FILES_DIR / "originals"
THUMBS_DIR = FILES_DIR / "thumbs"
PREVIEWS_DIR = FILES_DIR / "previews"
DB_PATH = DATA_DIR / "pod.db"

MAX_UPLOAD_MB = int(os.environ.get("POD_MAX_UPLOAD_MB", "200"))
THUMB_SIZE = 400
PREVIEW_SIZE = 1600

# Secure cookies only when served over HTTPS (set POD_SECURE_COOKIES=1 behind a TLS proxy).
SECURE_COOKIES = os.environ.get("POD_SECURE_COOKIES", "0") == "1"

FONTS = [
    "DejaVu Sans",
    "DejaVu Serif",
    "DejaVu Sans Mono",
    "Liberation Sans",
    "Liberation Serif",
    "Liberation Mono",
]


def ensure_dirs() -> None:
    for d in (DATA_DIR, ORIGINALS_DIR, THUMBS_DIR, PREVIEWS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def secret_key() -> str:
    """Session secret: from env, else persisted in the data dir so sessions survive restarts."""
    env = os.environ.get("POD_SECRET_KEY")
    if env:
        return env
    ensure_dirs()
    path = DATA_DIR / "secret.key"
    if not path.exists():
        path.write_text(secrets.token_urlsafe(48))
        path.chmod(0o600)
    return path.read_text().strip()
