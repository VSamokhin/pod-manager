import re
from collections.abc import Sequence
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session, selectinload
from starlette.datastructures import FormData

from .. import autotag, config, imaging, printfit, render, tags
from ..auth import current_user
from ..db import Drop, DropImage, GoodsType, Image, Tag, Template, User, get_db
from ..web import flash, form_str, page, redirect

router = APIRouter()

OUTCOMES = ("unknown", "successful", "unsuccessful")


def get_image(db: Session, image_id: int) -> Image:
    img = db.get(Image, image_id)
    if not img:
        raise HTTPException(404, "Image not found")
    return img


def create_image(db: Session, data: bytes, filename: str, user: User | None, **extra: Any) -> Image:
    kind, mime = imaging.classify(filename)
    stored = imaging.store_original(data, filename)
    stem = re.sub(r"[_\-]+", " ", filename.rsplit(".", 1)[0]).strip()
    img = Image(
        title=extra.pop("title", None) or stem[:255],
        original_filename=filename[:255],
        stored_filename=stored,
        mime=mime,
        kind=kind,
        size_bytes=len(data),
        uploaded_by=user,
        **extra,
    )
    db.add(img)
    db.flush()
    if kind in ("raster", "vector"):
        try:
            img.width, img.height = imaging.make_derivatives(img.id, kind, imaging.original_path(stored))
            img.has_preview = True
        except Exception as exc:  # noqa: BLE001 - Pillow/Cairo raise many types on corrupt files; keep the file
            img.kind = "other"
            img.notes = f"Could not read image: {exc}"[:500]
    autotag.apply(db, img)
    return img


def delete_image_files(img: Image) -> None:
    for p in (imaging.original_path(img.stored_filename), imaging.thumb_path(img.id), imaging.preview_path(img.id)):
        p.unlink(missing_ok=True)


# ------------------------------------------------------------------ list / upload


@router.get("/images")
def list_images(
    request: Request,
    q: str = "",
    kind: str = "",
    flag: str = "",
    tag: str = "",
    drop: str = "",
    sort: str = "new",
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    stmt = select(Image).options(selectinload(Image.drop_links), selectinload(Image.tags))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                Image.title.ilike(like),
                Image.original_filename.ilike(like),
                Image.notes.ilike(like),
                Image.tags.any(Tag.name.ilike(like)),
            )
        )
    if kind in ("raster", "vector", "other"):
        stmt = stmt.where(Image.kind == kind)
    if flag == "interesting":
        stmt = stmt.where(Image.interesting.is_(True))
    elif flag in OUTCOMES:
        stmt = stmt.where(Image.outcome == flag)
    elif flag == "renders":
        stmt = stmt.where(Image.parent_id.is_not(None))
    elif flag == "originals":
        stmt = stmt.where(Image.parent_id.is_(None))
    if tag:
        stmt = stmt.where(Image.tags.any(func.lower(Tag.name) == tag.strip().lower()))
    if drop == "none":
        stmt = stmt.where(~Image.drop_links.any())
    elif drop.isdigit():
        stmt = stmt.where(Image.drop_links.any(DropImage.drop_id == int(drop)))
    orders: dict[str, ColumnElement[Any]] = {"old": Image.id.asc(), "title": Image.title.asc(), "new": Image.id.desc()}
    order = orders.get(sort, orders["new"])
    stmt = stmt.order_by(order)
    images = db.scalars(stmt).all()
    drops = db.scalars(select(Drop).options(selectinload(Drop.state)).order_by(Drop.id.desc())).all()
    return page(
        request,
        "images.html",
        images=images,
        drops=drops,
        all_tags=tags.all_tags(db),
        f={"q": q, "kind": kind, "flag": flag, "tag": tag, "drop": drop, "sort": sort},
        accept=",".join(sorted(imaging.ALLOWED_EXT)),
    )


@router.post("/images/upload")
async def upload(
    request: Request,
    files: list[UploadFile] = File(...),
    tag_input: str = Form("", alias="tags"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    ok, errors = 0, []
    batch_tags, unknown = tags.resolve(db, tag_input)
    limit = config.MAX_UPLOAD_MB * 1024 * 1024
    for f in files:
        if not f.filename:
            continue
        data = await f.read()
        if len(data) > limit:
            errors.append(f"{f.filename}: larger than {config.MAX_UPLOAD_MB} MB")
            continue
        try:
            create_image(db, data, f.filename, user, tags=list(batch_tags))
            ok += 1
        except imaging.IngestError as exc:
            errors.append(f"{f.filename}: {exc}")
    db.commit()
    if ok:
        flash(request, f"Uploaded {ok} file(s).")
    if unknown:
        flash(request, tags.unknown_message(unknown), "error")
    for e in errors:
        flash(request, e, "error")
    return redirect("/images")


@router.post("/images/bulk")
def bulk(
    request: Request,
    action: str = Form(...),
    ids: list[int] = Form(default=[]),
    drop_id: str = Form(""),
    tag_id: str = Form(""),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    images = db.scalars(select(Image).where(Image.id.in_(ids))).all() if ids else []
    if not images:
        flash(request, "Select at least one image.", "error")
        return redirect(request.headers.get("referer") or "/images")
    if action == "add_to_drop":
        if not drop_id.isdigit() or not (drop := db.get(Drop, int(drop_id))):
            flash(request, "Choose a drop.", "error")
            return redirect(request.headers.get("referer") or "/images")
        added = add_images_to_drop(db, drop, images)
        db.commit()
        flash(request, f"Added {added} image(s) to “{drop.name}”.")
        return redirect(f"/drops/{drop.id}")
    if action in ("add_tag", "remove_tag"):
        if not tag_id.isdigit() or not (tag := db.get(Tag, int(tag_id))):
            flash(request, "Choose a tag.", "error")
            return redirect(request.headers.get("referer") or "/images")
        _bulk_tag(images, tag, add=action == "add_tag")
    elif action in ("interesting", "not_interesting"):
        for img in images:
            img.interesting = action == "interesting"
    elif action in OUTCOMES:
        for img in images:
            img.outcome = action
    elif action == "delete":
        if not user.is_admin:
            raise HTTPException(403, "Admins only")
        for img in images:
            delete_image_files(img)
            db.delete(img)
    else:
        raise HTTPException(400, "Unknown action")
    db.commit()
    flash(request, f"Updated {len(images)} image(s).")
    return redirect(request.headers.get("referer") or "/images")


def _bulk_tag(images: Sequence[Image], tag: Tag, *, add: bool) -> None:
    for img in images:
        if add and tag not in img.tags:
            img.tags.append(tag)
        elif not add and tag in img.tags:
            img.tags.remove(tag)


def add_images_to_drop(db: Session, drop: Drop, images: Sequence[Image]) -> int:
    existing = {it.image_id for it in drop.items}
    pos = max((it.position for it in drop.items), default=0)
    added = 0
    for img in images:
        if img.id in existing:
            continue
        pos += 1
        drop.items.append(DropImage(image=img, position=pos))
        added += 1
    return added


# ------------------------------------------------------------------ detail


@router.get("/images/{image_id}")
def image_detail(
    request: Request, image_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> Response:
    img = get_image(db, image_id)
    drops = db.scalars(select(Drop).order_by(Drop.id.desc())).all()
    tpls = db.scalars(select(Template).order_by(Template.name)).all()
    return page(
        request,
        "image_detail.html",
        img=img,
        drops=drops,
        templates=tpls,
        outcomes=OUTCOMES,
        all_tags=tags.all_tags(db),
        print_hints=printfit.suggest(img.width, img.height, img.kind),
        min_dpi=printfit.MIN_DPI,
    )


@router.post("/images/{image_id}")
def image_update(
    request: Request,
    image_id: int,
    title: str = Form(""),
    tag_input: str = Form("", alias="tags"),
    notes: str = Form(""),
    interesting: str = Form(""),
    outcome: str = Form("unknown"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    img = get_image(db, image_id)
    img.title = title.strip()[:255]
    img.tags, unknown = tags.resolve(db, tag_input)
    img.notes = notes
    img.interesting = bool(interesting)
    img.outcome = outcome if outcome in OUTCOMES else "unknown"
    db.commit()
    flash(request, "Saved.")
    if unknown:
        flash(request, tags.unknown_message(unknown), "error")
    return redirect(f"/images/{image_id}")


@router.post("/images/{image_id}/add-to-drop")
def image_add_to_drop(
    request: Request,
    image_id: int,
    drop_id: int = Form(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    img = get_image(db, image_id)
    drop = db.get(Drop, drop_id)
    if not drop:
        raise HTTPException(404)
    n = add_images_to_drop(db, drop, [img])
    db.commit()
    flash(request, f"Added to “{drop.name}”." if n else "Already in that drop.")
    return redirect(f"/images/{image_id}")


@router.post("/images/{image_id}/delete")
def image_delete(
    request: Request, image_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> Response:
    if not user.is_admin:
        raise HTTPException(403, "Admins only")
    img = get_image(db, image_id)
    delete_image_files(img)
    db.delete(img)
    db.commit()
    flash(request, "Image deleted.")
    return redirect("/images")


# ------------------------------------------------------------------ media


@router.get("/media/{image_id}/{variant}")
def media(
    image_id: int, variant: str, download: int = 0, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> Response:
    img = get_image(db, image_id)
    headers = {"Cache-Control": "private, max-age=86400"}
    if variant == "thumb" and img.has_preview:
        return FileResponse(imaging.thumb_path(img.id), media_type="image/webp", headers=headers)
    if variant == "preview" and img.has_preview:
        return FileResponse(imaging.preview_path(img.id), media_type="image/webp", headers=headers)
    if variant == "original":
        # Never let an uploaded SVG run scripts in our origin.
        headers["Content-Security-Policy"] = "default-src 'none'; img-src data:; style-src 'unsafe-inline'; sandbox"
        headers["X-Content-Type-Options"] = "nosniff"
        return FileResponse(
            imaging.original_path(img.stored_filename),
            media_type=img.mime,
            filename=img.original_filename,
            content_disposition_type="attachment" if download or img.kind == "other" else "inline",
            headers=headers,
        )
    raise HTTPException(404)


# ------------------------------------------------------------------ templates applied to images


def _params_from_form(form: FormData) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for key in render.DEFAULT_PARAMS:
        if key in render.BOOLEAN:
            params[key] = form.get(key) in ("on", "1", "true")
        elif key in form:
            params[key] = form.get(key)
    return params


@router.get("/images/{image_id}/apply")
def apply_page(
    request: Request,
    image_id: int,
    template_id: int | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    img = get_image(db, image_id)
    if not img.has_preview:
        flash(request, "Templates can only be applied to raster or SVG images.", "error")
        return redirect(f"/images/{image_id}")
    tpls = db.scalars(select(Template).order_by(Template.name)).all()
    tpl = db.get(Template, template_id) if template_id else (tpls[0] if tpls else None)
    goods = db.scalars(select(GoodsType).where(GoodsType.active.is_(True)).order_by(GoodsType.name)).all()
    params = render.normalize(tpl.params if tpl else {})
    return page(request, "apply.html", img=img, templates=tpls, tpl=tpl, params=params, goods=goods)


@router.post("/api/preview")
async def api_preview(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    form = await request.form()
    image_id = form_str(form, "image_id")
    img = get_image(db, int(image_id) if image_id.isdigit() else 0)
    if not img.has_preview:
        raise HTTPException(400, "No preview for this file type")
    svg, w, h = render.compose_svg(
        img, _params_from_form(form), href=f"/media/{img.id}/preview", title=img.display_title
    )
    return Response(svg, media_type="image/svg+xml", headers={"X-Size": f"{w:.0f}x{h:.0f}"})


@router.post("/images/{image_id}/export")
async def export(
    request: Request, image_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> Response:
    form = await request.form()
    img = get_image(db, image_id)
    params = _params_from_form(form)
    fmt = form_str(form, "format", "png")
    if fmt not in ("png", "pdf", "svg"):
        raise HTTPException(400, "Unknown format")
    try:
        width_mm = float(form_str(form, "width_mm") or 0) or None
        dpi = int(form_str(form, "dpi") or 300)
    except ValueError:
        raise HTTPException(400, "Invalid size") from None
    href = imaging.embed_data_uri(img.kind, img.mime, imaging.original_path(img.stored_filename))
    svg, w, h = render.compose_svg(img, params, href=href, title=img.display_title)

    if form_str(form, "action") == "save":
        tpl_id = form_str(form, "template_id")
        tpl = db.get(Template, int(tpl_id)) if tpl_id.isdigit() else None
        name = f"{img.display_title} ({tpl.name})" if tpl else f"{img.display_title} (render)"
        # Keep px units so the render keeps its full resolution when reused.
        new = create_image(
            db,
            svg.encode(),
            re.sub(r"[^\w\-. ]", "_", img.display_title)[:80] + "-render.svg",
            user,
            title=name[:255],
            parent_id=img.id,
            template_id=tpl.id if tpl else None,
            tags=list(img.tags),
        )
        db.commit()
        flash(request, "Saved as a new image. It keeps a link to the original.")
        return redirect(f"/images/{new.id}")

    data, mime = render.export(svg, w, h, fmt, width_mm, dpi)
    safe = re.sub(r"[^\w\-]+", "_", img.display_title).strip("_")[:60] or f"image{img.id}"
    return Response(
        data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{safe}-print.{fmt}"'}
    )
