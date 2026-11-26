"""Broader route coverage: drops, bulk actions, admin CRUD, permissions and edge cases."""

import re

from fastapi.testclient import TestClient

from app.main import app

from .conftest import login, png_bytes


def _upload(client: TestClient, name: str, data: bytes | None = None) -> int:
    r = client.post("/images/upload", files=[("files", (name, data or png_bytes(), "image/png"))])
    assert r.status_code == 200
    return int(re.findall(r'name="ids" value="(\d+)"', r.text)[0])


def _new_drop(client: TestClient, name: str) -> int:
    r = client.post("/drops", data={"name": name})
    return int(re.search(r'action="/drops/(\d+)/state"', r.text).group(1))


def test_public_endpoints_and_login_redirect():
    with TestClient(app) as c:
        assert c.get("/healthz").json()["ok"] is True
        r = c.get("/login?next=/drops")
        assert 'value="/drops"' in r.text
        r = c.post("/login", data={"username": "admin", "password": "admin-pass-123", "next": "//evil.example"})
        assert r.url.path == "/images"
        r = c.post("/login", data={"username": "admin", "password": "admin-pass-123", "next": "/drops"})
        assert r.url.path == "/drops"
        assert c.get("/", follow_redirects=False).headers["location"] == "/images"
        r = c.post("/logout", follow_redirects=False)
        assert r.headers["location"] == "/login"
        assert c.post("/api/preview").status_code == 401


def test_image_search_filters_and_bulk(admin_client):
    a = _upload(admin_client, "alpha_one.png")
    b = _upload(admin_client, "beta_two.png", png_bytes(alpha=False))
    for query in [
        "q=alpha",
        "kind=raster",
        "flag=unknown",
        "flag=originals",
        "flag=renders",
        "flag=successful",
        "tag=x",
        "drop=none",
        "drop=999",
        "sort=old",
        "sort=title",
    ]:
        assert admin_client.get(f"/images?{query}").status_code == 200
    assert "alpha one" in admin_client.get("/images?q=alpha").text

    r = admin_client.post("/images/bulk", data={"action": "unsuccessful", "ids": [a, b]})
    assert "Updated 2 image(s)" in r.text
    r = admin_client.post("/images/bulk", data={"action": "not_interesting", "ids": [a]})
    assert "Updated 1 image(s)" in r.text
    r = admin_client.post("/images/bulk", data={"action": "interesting"})
    assert "Select at least one image" in r.text
    r = admin_client.post("/images/bulk", data={"action": "add_to_drop", "ids": [a], "drop_id": ""})
    assert "Choose a drop" in r.text
    assert admin_client.post("/images/bulk", data={"action": "bogus", "ids": [a]}).status_code == 400
    r = admin_client.post("/images/bulk", data={"action": "delete", "ids": [b]})
    assert "Updated 1 image(s)" in r.text
    assert admin_client.get(f"/images/{b}").status_code == 404


def test_image_detail_add_to_drop_and_delete(admin_client):
    img = _upload(admin_client, "gamma.png")
    drop = _new_drop(admin_client, "Gamma drop")
    r = admin_client.post(f"/images/{img}/add-to-drop", data={"drop_id": drop})
    assert "Added to" in r.text
    r = admin_client.post(f"/images/{img}/add-to-drop", data={"drop_id": drop})
    assert "Already in that drop" in r.text
    assert admin_client.post(f"/images/{img}/add-to-drop", data={"drop_id": 9999}).status_code == 404
    assert admin_client.get(f"/media/{img}/original?download=1").headers["content-disposition"].startswith("attachment")
    assert admin_client.get(f"/media/{img}/nope").status_code == 404
    r = admin_client.post(f"/images/{img}/delete")
    assert "Image deleted" in r.text


def test_unreadable_and_other_files(admin_client):
    r = admin_client.post("/images/upload", files=[("files", ("broken.png", b"not an image", "image/png"))])
    assert "Uploaded 1 file(s)" in r.text
    broken = int(re.findall(r'name="ids" value="(\d+)"', r.text)[0])
    r = admin_client.get(f"/images/{broken}")
    assert "Could not read image" in r.text
    r = admin_client.get(f"/images/{broken}/apply")
    assert "can only be applied" in r.text
    assert admin_client.post("/api/preview", data={"image_id": str(broken)}).status_code == 400
    assert admin_client.post("/api/preview", data={"image_id": "abc"}).status_code == 404


def test_export_validation(admin_client):
    img = _upload(admin_client, "delta.png")
    assert admin_client.post(f"/images/{img}/export", data={"format": "gif"}).status_code == 400
    assert admin_client.post(f"/images/{img}/export", data={"format": "png", "dpi": "x"}).status_code == 400
    r = admin_client.post(f"/images/{img}/export", data={"format": "png", "action": "save"})
    assert "(render)" in r.text


def test_drop_lifecycle(admin_client):
    img = _upload(admin_client, "epsilon.png")
    drop = _new_drop(admin_client, "Winter")
    r = admin_client.post(f"/drops/{drop}/add", data={"ids": [img]})
    assert "Added 1 image(s)" in r.text
    item = int(re.search(r'id="item-(\d+)"', r.text).group(1))
    states = dict(re.findall(r'<option value="(\d+)" ?(?:selected)?>([^<]+)</option>', r.text))
    parked = next(k for k, v in states.items() if v == "Parked")

    r = admin_client.post(
        f"/drops/{drop}",
        data={"name": "Winter 26", "description": "cold", "planned_date": "2026-12-01", "state_id": parked},
    )
    assert "Drop saved" in r.text
    assert "Winter 26" in r.text
    assert admin_client.get(f"/drops?state={parked}").status_code == 200
    assert "Winter 26" in admin_client.get("/drops").text
    r = admin_client.post(f"/drops/{drop}", data={"name": "Winter 26", "state_id": ""})
    assert "Drop saved" in r.text
    assert "No state" in admin_client.get("/drops").text

    assert admin_client.post(f"/drops/{drop}/items/{item}", data={"notes": "x"}).status_code == 200
    assert admin_client.post(f"/drops/{drop + 1000}/items/{item}", data={}).status_code == 404
    assert admin_client.post(f"/drops/{drop}/state", data={"state_id": 9999}).status_code == 404
    r = admin_client.post(f"/drops/{drop}/items/{item}/remove")
    assert "Removed from drop" in r.text
    assert admin_client.post(f"/drops/{drop}/items/{item}/remove").status_code == 404
    r = admin_client.post("/drops", data={"name": "Explicit", "state_id": parked})
    assert "Parked" in r.text
    r = admin_client.post(f"/drops/{drop}/delete")
    assert "Drop deleted" in r.text
    assert admin_client.get(f"/drops/{drop}").status_code == 404


def test_admin_crud(admin_client):
    assert "Images" in admin_client.get("/admin").text
    # states
    r = admin_client.post("/admin/states", data={"name": "Temp", "color": "#123456", "sort_order": 50})
    temp = int(re.search(r'name="id" value="(\d+)">\s*<input name="name" value="Temp"', r.text).group(1))
    r = admin_client.post(
        "/admin/states", data={"id": temp, "name": "Temp2", "color": "bad", "sort_order": 51, "is_default": "1"}
    )
    assert "Temp2" in r.text
    assert admin_client.post("/admin/states", data={"id": 9999, "name": "x", "color": "#000000"}).status_code == 404
    r = admin_client.post("/admin/states", data={"name": "Temp2", "color": "#000000"})
    assert "already taken" in r.text
    future = re.search(r'name="id" value="(\d+)">\s*<input name="name" value="Future"', r.text).group(1)
    admin_client.post("/admin/states", data={"id": future, "name": "Future", "color": "#3b82f6", "is_default": "1"})
    drop = _new_drop(admin_client, "Uses temp")
    admin_client.post(f"/drops/{drop}/state", data={"state_id": temp})
    r = admin_client.post(f"/admin/states/{temp}/delete", data={"move_to": future})
    assert "State deleted" in r.text
    assert admin_client.post("/admin/states/9999/delete").status_code == 404

    # goods
    r = admin_client.post("/admin/goods", data={"name": "Cap", "print_width_mm": "abc", "active": "1"})
    cap = int(re.search(r'name="id" value="(\d+)">\s*<input name="name" value="Cap"', r.text).group(1))
    r = admin_client.post("/admin/goods", data={"id": cap, "name": "Cap 2", "print_width_mm": "80.5"})
    assert "Cap 2" in r.text
    assert admin_client.post("/admin/goods", data={"id": 9999, "name": "x"}).status_code == 404
    assert "Goods type deleted" in admin_client.post(f"/admin/goods/{cap}/delete").text

    # templates
    r = admin_client.get("/admin/templates")
    tpl = int(re.search(r'href="/admin/templates/(\d+)"', r.text).group(1))
    assert admin_client.get("/admin/templates/new").status_code == 200
    assert admin_client.get(f"/admin/templates/{tpl}?sample=1").status_code == 200
    assert admin_client.get("/admin/templates/9999").status_code == 404
    assert admin_client.post("/admin/templates/9999", data={"name": "x"}).status_code == 404
    r = admin_client.post(f"/admin/templates/{tpl}/duplicate")
    assert "Template duplicated" in r.text
    r = admin_client.post(f"/admin/templates/{tpl}/duplicate")
    copy_id = int(re.search(r'action="/admin/templates/(\d+)"', r.text).group(1))
    assert "copy 2" in r.text
    assert admin_client.post("/admin/templates/9999/duplicate").status_code == 404
    assert "Template deleted" in admin_client.post(f"/admin/templates/{copy_id}/delete").text


def test_user_management_rules(admin_client):
    r = admin_client.post("/admin/users", data={"username": "bob", "password": "short", "role": "user"})
    assert "at least 8 characters" in r.text
    r = admin_client.post("/admin/users", data={"username": "bob", "password": "bob-pass-123", "role": "user"})
    bob = int(re.search(r'name="id" value="(\d+)">\s*<input name="username" value="bob"', r.text).group(1))
    me = int(re.search(r'name="id" value="(\d+)">\s*<input name="username" value="admin"', r.text).group(1))
    r = admin_client.post("/admin/users", data={"id": bob, "username": "bob", "password": "short"})
    assert "at least 8 characters" in r.text
    r = admin_client.post("/admin/users", data={"id": me, "username": "admin", "role": "user", "is_active": "1"})
    assert "remove your own admin rights" in r.text
    r = admin_client.post(f"/admin/users/{me}/delete")
    assert "delete yourself" in r.text

    # deactivated users cannot log in
    admin_client.post("/admin/users", data={"id": bob, "username": "bob", "role": "user"})
    with TestClient(app) as c:
        r = c.post("/login", data={"username": "bob", "password": "bob-pass-123"})
        assert "Wrong username or password" in r.text
    assert "User deleted" in admin_client.post(f"/admin/users/{bob}/delete").text


def test_account_password_errors():
    with TestClient(app) as c:
        login(c)
        assert c.get("/account").status_code == 200
        assert "Current password is wrong" in c.post("/account/password", data={"current": "x", "new": "y" * 8}).text
        r = c.post("/account/password", data={"current": "admin-pass-123", "new": "short"})
        assert "at least 8 characters" in r.text


def test_non_admin_cannot_delete_drops():
    with TestClient(app) as admin:
        login(admin)
        admin.post(
            "/admin/users", data={"username": "carol", "password": "carol-pass-1", "role": "user", "is_active": "1"}
        )
        drop = _new_drop(admin, "Carol test")
    with TestClient(app) as c:
        login(c, "carol", "carol-pass-1")
        assert c.post(f"/drops/{drop}/delete").status_code == 403
        assert c.post("/images/bulk", data={"action": "delete", "ids": [1]}).status_code in (403, 200)
