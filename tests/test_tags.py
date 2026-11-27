"""The managed tag list: admin CRUD, picking tags on images, bulk tagging, filters and the legacy migration."""

import re

from fastapi.testclient import TestClient

from app import db as dbmod
from app import tags
from app.db import Image, Tag
from app.main import app

from .conftest import login, png_bytes


def _upload(client: TestClient, name: str, tag_text: str = "") -> tuple[int, str]:
    r = client.post("/images/upload", files=[("files", (name, png_bytes(), "image/png"))], data={"tags": tag_text})
    assert r.status_code == 200
    return int(re.findall(r'name="ids" value="(\d+)"', r.text)[0]), r.text


def _tag_id(client: TestClient, name: str) -> int:
    page = client.get("/admin/tags").text
    m = re.search(rf'action="/admin/tags/(\d+)" class="row">\s*<input name="name" value="{re.escape(name)}"', page)
    assert m, f"tag {name} not listed"
    return int(m.group(1))


def test_name_parsing():
    assert tags.clean_name("  Retro   look  ") == "Retro look"
    assert tags.split_names("cats, Cats,\nsummer ,, ") == ["cats", "summer"]
    assert len(tags.clean_name("x" * 100)) == tags.MAX_LEN


def test_admin_manages_tag_list(admin_client):
    r = admin_client.post("/admin/tags", data={"names": "Cats\nSummer, retro", "color": "#ff0000"})
    assert "Added 3 tag(s)" in r.text
    r = admin_client.post("/admin/tags", data={"names": "cats, Winter"})
    assert "Added 1 tag(s)" in r.text and "Already on the list: cats" in r.text
    cats, winter = _tag_id(admin_client, "Cats"), _tag_id(admin_client, "Winter")
    assert "Tag saved" in admin_client.post(f"/admin/tags/{winter}", data={"name": "Wintertime", "color": "#00f"}).text
    r = admin_client.post(f"/admin/tags/{winter}", data={"name": "CATS"})
    assert "already exists" in r.text
    assert "needs a name" in admin_client.post(f"/admin/tags/{winter}", data={"name": " , "}).text
    assert admin_client.post("/admin/tags/9999", data={"name": "x"}).status_code == 404
    assert admin_client.post("/admin/tags/9999/delete").status_code == 404
    assert "Tag deleted." in admin_client.post(f"/admin/tags/{winter}/delete").text
    assert "Wintertime" not in admin_client.get("/admin/tags").text
    assert cats
    assert "Tags" in admin_client.get("/admin").text


def test_images_only_take_listed_tags(admin_client):
    admin_client.post("/admin/tags", data={"names": "space, neon"})
    img, text = _upload(admin_client, "tagged.png", "Space, made-up")
    assert "Uploaded 1 file(s)" in text and "Not on the tag list, so not added: made-up" in text

    detail = admin_client.get(f"/images/{img}").text
    assert 'name="tags" value="space"' in detail and "data-tagpick" in detail and '<option value="neon"' in detail

    r = admin_client.post(f"/images/{img}", data={"title": "T", "tags": "neon, NEON, bogus", "outcome": "unknown"})
    assert "Saved." in r.text and "not added: bogus" in r.text
    assert 'name="tags" value="neon"' in r.text

    listing = admin_client.get("/images?tag=NEON").text
    assert f'name="ids" value="{img}"' in listing and 'class="badge tag"' in listing
    assert f'name="ids" value="{img}"' not in admin_client.get("/images?tag=space").text
    assert f'name="ids" value="{img}"' in admin_client.get("/images?q=neo").text


def test_bulk_tagging_and_merge_on_delete(admin_client):
    admin_client.post("/admin/tags", data={"names": "bulk-a, bulk-b"})
    a, b = _tag_id(admin_client, "bulk-a"), _tag_id(admin_client, "bulk-b")
    one, _ = _upload(admin_client, "one.png")
    two, _ = _upload(admin_client, "two.png", "bulk-b")

    r = admin_client.post("/images/bulk", data={"action": "add_tag", "tag_id": str(a), "ids": [one, two]})
    assert "Updated 2 image(s)" in r.text
    assert "Choose a tag" in admin_client.post("/images/bulk", data={"action": "add_tag", "ids": [one]}).text
    admin_client.post("/images/bulk", data={"action": "add_tag", "tag_id": str(a), "ids": [one]})  # no duplicate
    usage = admin_client.get("/admin/tags").text
    assert re.search(r"/images\?tag=bulk-a\">2<", usage)

    admin_client.post("/images/bulk", data={"action": "remove_tag", "tag_id": str(a), "ids": [two]})
    admin_client.post("/images/bulk", data={"action": "remove_tag", "tag_id": str(a), "ids": [two]})  # already gone
    assert 'name="tags" value="bulk-b"' in admin_client.get(f"/images/{two}").text

    # Deleting bulk-b and merging it into bulk-a moves image two over.
    r = admin_client.post(f"/admin/tags/{b}/delete", data={"move_to": str(a)})
    assert "Its images now have “bulk-a”" in r.text
    admin_client.post("/images/bulk", data={"action": "add_tag", "tag_id": str(a), "ids": [two]})
    assert 'name="tags" value="bulk-a"' in admin_client.get(f"/images/{two}").text


def test_merge_keeps_single_link_and_renders_inherit_tags(admin_client):
    admin_client.post("/admin/tags", data={"names": "keep, drop-me"})
    keep, gone = _tag_id(admin_client, "keep"), _tag_id(admin_client, "drop-me")
    img, _ = _upload(admin_client, "both.png", "keep, drop-me")
    admin_client.post(f"/admin/tags/{gone}/delete", data={"move_to": str(keep)})
    assert 'name="tags" value="keep"' in admin_client.get(f"/images/{img}").text

    r = admin_client.post(f"/images/{img}/export", data={"format": "png", "action": "save"})
    assert "Saved as a new image" in r.text and 'name="tags" value="keep"' in r.text


def test_non_admin_picks_but_cannot_manage():
    with TestClient(app) as admin:
        login(admin)
        admin.post(
            "/admin/users", data={"username": "dave", "password": "dave-pass-12", "role": "user", "is_active": "1"}
        )
        admin.post("/admin/tags", data={"names": "user-ok"})
    with TestClient(app) as c:
        login(c, "dave", "dave-pass-12")
        assert c.get("/admin/tags").status_code == 403
        assert c.post("/admin/tags", data={"names": "sneaky"}).status_code == 403
        img, text = _upload(c, "dave.png", "user-ok, sneaky")
        assert "not added: sneaky" in text
        assert 'name="tags" value="user-ok"' in c.get(f"/images/{img}").text
        assert "Manage tags" not in c.get(f"/images/{img}").text


def test_legacy_free_form_tags_are_migrated():
    with dbmod.session_factory()() as s:
        s.add(Tag(name="Legacy"))
        s.commit()
        img = Image(original_filename="old.png", stored_filename="old.png", legacy_tags="legacy, Brand New , brand new")
        s.add(img)
        s.commit()
        assert tags.migrate_legacy_tags(s) == 1
        assert tags.migrate_legacy_tags(s) == 0  # idempotent
        s.refresh(img)
        assert img.legacy_tags == ""
        assert img.tag_list == ["Brand New", "Legacy"]
        assert img.tags_text == "Brand New, Legacy"
        assert tags.find(s, "brand  new") is not None
