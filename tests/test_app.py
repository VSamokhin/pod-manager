import io
import os
import re
import tempfile

import pytest
from PIL import Image as PILImage
from PIL import ImageDraw

os.environ["POD_DATA_DIR"] = tempfile.mkdtemp(prefix="pod-test-")
os.environ["POD_ADMIN_USERNAME"] = "admin"
os.environ["POD_ADMIN_PASSWORD"] = "admin-pass-123"

from fastapi.testclient import TestClient

from app.main import app

SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">'
    b'<circle cx="50" cy="50" r="40" fill="red"/><script>alert(1)</script></svg>'
)


def png_bytes(alpha=True) -> bytes:
    im = PILImage.new("RGBA" if alpha else "RGB", (300, 200), (0, 0, 0, 0) if alpha else (255, 255, 255))
    ImageDraw.Draw(im).ellipse((40, 30, 200, 170), fill=(200, 30, 30, 255) if alpha else (200, 30, 30))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def login(client, user="admin", pw="admin-pass-123"):
    r = client.post("/login", data={"username": user, "password": pw}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/images"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def first_id(html: str, prefix: str) -> int:
    return int(re.search(rf'href="{prefix}/(\d+)"', html).group(1))


def test_requires_login():
    with TestClient(app) as c:
        r = c.get("/images", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"].startswith("/login")
        assert c.get("/media/1/thumb").status_code == 401
        r = c.post("/login", data={"username": "admin", "password": "wrong"}, follow_redirects=False)
        assert r.headers["location"] == "/login"


def test_upload_flag_and_drop_flow(client):
    login(client)
    r = client.post(
        "/images/upload",
        files=[
            ("files", ("red_planet.png", png_bytes(), "image/png")),
            ("files", ("logo.svg", SVG, "image/svg+xml")),
            ("files", ("notes.txt", b"x", "text/plain")),
            ("files", ("artwork.pdf", b"%PDF-1.4 fake", "application/pdf")),
        ],
        data={"tags": "space, test"},
    )
    assert r.status_code == 200
    assert "Uploaded 3 file(s)" in r.text and "Unsupported file type" in r.text
    assert "red planet" in r.text

    ids = [int(x) for x in re.findall(r'name="ids" value="(\d+)"', r.text)]
    assert len(ids) == 3
    pdf_id, svg_id, png_id = ids  # newest first

    assert client.get(f"/media/{png_id}/thumb").headers["content-type"] == "image/webp"
    assert client.get(f"/media/{svg_id}/preview").status_code == 200
    orig = client.get(f"/media/{svg_id}/original")
    assert "sandbox" in orig.headers["content-security-policy"]
    assert client.get(f"/media/{pdf_id}/thumb").status_code == 404

    # Flags
    r = client.post(
        f"/images/{png_id}",
        data={"title": "Red Planet", "tags": "space", "notes": "", "interesting": "1", "outcome": "successful"},
    )
    assert "Saved." in r.text
    r = client.get("/images?flag=interesting")
    assert "Red Planet" in r.text and 'title="logo"' not in r.text

    # Drop with default state
    r = client.post("/drops", data={"name": "Autumn"})
    assert "Future" in r.text
    drop_id = int(re.search(r'action="/drops/(\d+)/state"', r.text).group(1))
    r = client.post("/images/bulk", data={"action": "add_to_drop", "drop_id": str(drop_id), "ids": [png_id, svg_id]})
    assert "Added 2 image(s)" in r.text
    item_id = int(re.search(r'id="item-(\d+)"', r.text).group(1))
    goods_ids = re.findall(r'name="goods" value="(\d+)"', r.text)[:2]
    r = client.post(
        f"/drops/{drop_id}/items/{item_id}", data={"goods": goods_ids, "notes": "front print", "position": "1"}
    )
    assert "Planned goods" in r.text and "front print" in r.text

    released = re.search(r'name="state_id" value="(\d+)">\s*<button title="Move to Released"', r.text).group(1)
    r = client.post(f"/drops/{drop_id}/state", data={"state_id": released})
    assert "is now Released" in r.text


def test_templates_preview_and_export(client):
    login(client)
    r = client.get("/images?kind=raster")
    png_id = first_id(r.text, "/images")
    r = client.get(f"/images/{png_id}/apply")
    assert r.status_code == 200
    tpl_ids = re.findall(r'<option value="(\d+)"', r.text)
    assert tpl_ids

    base = {
        "image_id": str(png_id),
        "padding": "5",
        "border_width": "1",
        "frame_radius": "5",
        "image_radius": "3",
        "title_text": "{title}",
        "outline_mode": "contour",
        "outline_width": "4",
        "cutline": "on",
    }
    r = client.post("/api/preview", data=base)
    assert r.status_code == 200 and r.text.startswith("<svg") and "Red Planet" in r.text and "<path" in r.text

    for fmt, mime, magic in [
        ("png", "image/png", b"\x89PNG"),
        ("pdf", "application/pdf", b"%PDF"),
        ("svg", "image/svg+xml", b"<svg"),
    ]:
        r = client.post(
            f"/images/{png_id}/export",
            data={**base, "format": fmt, "dpi": "150", "width_mm": "100", "action": "download"},
        )
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith(mime) and r.content.startswith(magic)
    r = client.post(
        f"/images/{png_id}/export",
        data={**base, "format": "png", "dpi": "254", "width_mm": "100", "action": "download"},
    )
    png = PILImage.open(io.BytesIO(r.content))
    assert png.width == 1000  # 100 mm at 254 dpi

    r = client.post(
        f"/images/{png_id}/export", data={**base, "format": "png", "action": "save", "template_id": tpl_ids[0]}
    )
    assert "Saved as a new image" in r.text and "Made from" in r.text


def test_admin_and_roles(client):
    login(client)
    r = client.post(
        "/admin/users", data={"username": "alice", "password": "alice-pass-1", "role": "user", "is_active": "1"}
    )
    assert "User saved." in r.text
    r = client.post(
        "/admin/goods", data={"name": "Phone case", "print_width_mm": "70", "print_height_mm": "140", "active": "1"}
    )
    assert "Phone case" in r.text
    r = client.post("/admin/states", data={"name": "In review", "color": "#ff0000", "sort_order": "5"})
    assert "In review" in r.text
    r = client.post(
        "/admin/templates/new", data={"name": "Thick black", "border_width": "3", "border_color": "#000000"}
    )
    assert "Template saved." in r.text
    r = client.post("/admin/templates/new", data={"name": "Thick black"})
    assert "already taken" in r.text

    with TestClient(app) as c2:
        login(c2, "alice", "alice-pass-1")
        assert c2.get("/admin").status_code == 403
        assert c2.get("/images").status_code == 200
        assert c2.post("/images/1/delete").status_code == 403
        r = c2.post("/account/password", data={"current": "alice-pass-1", "new": "alice-pass-2"})
        assert "Password changed." in r.text
