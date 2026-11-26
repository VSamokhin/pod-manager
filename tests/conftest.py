import io
import os
import tempfile

import pytest
from PIL import Image as PILImage
from PIL import ImageDraw

# Configure an isolated data dir before the app module is imported anywhere.
os.environ["POD_DATA_DIR"] = tempfile.mkdtemp(prefix="pod-test-")
os.environ["POD_ADMIN_USERNAME"] = "admin"
os.environ["POD_ADMIN_PASSWORD"] = "admin-pass-123"

from fastapi.testclient import TestClient

from app.main import app

ADMIN = ("admin", "admin-pass-123")


def png_bytes(alpha: bool = True, size: tuple[int, int] = (300, 200)) -> bytes:
    im = PILImage.new("RGBA" if alpha else "RGB", size, (0, 0, 0, 0) if alpha else (255, 255, 255))
    ImageDraw.Draw(im).ellipse((40, 30, 200, 170), fill=(200, 30, 30, 255) if alpha else (200, 30, 30))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def login(client: TestClient, user: str = ADMIN[0], pw: str = ADMIN[1]) -> None:
    r = client.post("/login", data={"username": user, "password": pw}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/images"


@pytest.fixture(scope="session")
def admin_client():
    with TestClient(app) as c:
        login(c)
        yield c
