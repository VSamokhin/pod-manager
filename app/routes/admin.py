import json

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import render
from ..auth import admin_user, hash_password
from ..db import Drop, DropState, GoodsType, Image, Template, User, get_db
from ..web import flash, page, redirect
from .images import _params_from_form

router = APIRouter(prefix="/admin")


def _save(request: Request, db: Session, ok_msg: str) -> bool:
    try:
        db.commit()
        flash(request, ok_msg)
        return True
    except IntegrityError:
        db.rollback()
        flash(request, "That name is already taken.", "error")
        return False


@router.get("")
def admin_home(request: Request, user: User = Depends(admin_user), db: Session = Depends(get_db)):
    counts = {
        "Images": db.scalar(select(func.count(Image.id))),
        "Drops": db.scalar(select(func.count(Drop.id))),
        "Templates": db.scalar(select(func.count(Template.id))),
        "Goods types": db.scalar(select(func.count(GoodsType.id))),
        "Users": db.scalar(select(func.count(User.id))),
    }
    return page(request, "admin/home.html", counts=counts)


# ------------------------------------------------------------------ drop states


@router.get("/states")
def states(request: Request, user: User = Depends(admin_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(DropState).order_by(DropState.sort_order, DropState.name)).all()
    usage = dict(db.execute(select(Drop.state_id, func.count(Drop.id)).group_by(Drop.state_id)).all())
    return page(request, "admin/states.html", states=rows, usage=usage)


@router.post("/states")
def state_save(
    request: Request,
    id: str = Form(""),
    name: str = Form(...),
    color: str = Form("#888888"),
    sort_order: int = Form(0),
    is_default: str = Form(""),
    user: User = Depends(admin_user),
    db: Session = Depends(get_db),
):
    st = db.get(DropState, int(id)) if id.isdigit() else DropState()
    if not st.id:
        db.add(st)
    st.name, st.color, st.sort_order = name.strip()[:64], render._color(color, "#888888"), sort_order
    if is_default:
        for other in db.scalars(select(DropState)).all():
            other.is_default = False
        st.is_default = True
    else:
        st.is_default = False
    _save(request, db, "State saved.")
    return redirect("/admin/states")


@router.post("/states/{state_id}/delete")
def state_delete(
    request: Request, state_id: int, move_to: str = Form(""), user: User = Depends(admin_user), db: Session = Depends(get_db)
):
    st = db.get(DropState, state_id)
    if not st:
        raise HTTPException(404)
    target = int(move_to) if move_to.isdigit() and int(move_to) != state_id else None
    for d in db.scalars(select(Drop).where(Drop.state_id == state_id)).all():
        d.state_id = target
    db.delete(st)
    db.commit()
    flash(request, "State deleted.")
    return redirect("/admin/states")


# ------------------------------------------------------------------ goods types


@router.get("/goods")
def goods(request: Request, user: User = Depends(admin_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(GoodsType).order_by(GoodsType.name)).all()
    return page(request, "admin/goods.html", goods=rows)


def _float(v: str) -> float | None:
    try:
        return float(v) if v.strip() else None
    except ValueError:
        return None


@router.post("/goods")
def goods_save(
    request: Request,
    id: str = Form(""),
    name: str = Form(...),
    description: str = Form(""),
    print_width_mm: str = Form(""),
    print_height_mm: str = Form(""),
    active: str = Form(""),
    user: User = Depends(admin_user),
    db: Session = Depends(get_db),
):
    g = db.get(GoodsType, int(id)) if id.isdigit() else GoodsType()
    if not g.id:
        db.add(g)
    g.name, g.description = name.strip()[:100], description
    g.print_width_mm, g.print_height_mm = _float(print_width_mm), _float(print_height_mm)
    g.active = bool(active)
    _save(request, db, "Goods type saved.")
    return redirect("/admin/goods")


@router.post("/goods/{goods_id}/delete")
def goods_delete(request: Request, goods_id: int, user: User = Depends(admin_user), db: Session = Depends(get_db)):
    g = db.get(GoodsType, goods_id)
    if g:
        db.delete(g)
        db.commit()
        flash(request, "Goods type deleted.")
    return redirect("/admin/goods")


# ------------------------------------------------------------------ templates


@router.get("/templates")
def templates_list(request: Request, user: User = Depends(admin_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Template).order_by(Template.name)).all()
    sample = db.scalar(select(Image).where(Image.has_preview.is_(True)).order_by(Image.id.desc()))
    return page(request, "admin/templates.html", templates=rows, sample=sample)


@router.get("/templates/{tpl_id}")
def template_edit(
    request: Request, tpl_id: str, sample: int | None = None, user: User = Depends(admin_user), db: Session = Depends(get_db)
):
    tpl = None if tpl_id == "new" else db.get(Template, int(tpl_id)) if tpl_id.isdigit() else None
    if tpl_id != "new" and not tpl:
        raise HTTPException(404)
    samples = db.scalars(select(Image).where(Image.has_preview.is_(True)).order_by(Image.parent_id.is_not(None)).order_by(Image.id.desc()).limit(100)).all()
    img = db.get(Image, sample) if sample else (samples[0] if samples else None)
    params = render.normalize(tpl.params if tpl else {})
    return page(request, "admin/template_edit.html", tpl=tpl, params=params, img=img, samples=samples)


@router.post("/templates/{tpl_id}")
async def template_save(request: Request, tpl_id: str, user: User = Depends(admin_user), db: Session = Depends(get_db)):
    form = await request.form()
    tpl = Template() if tpl_id == "new" else db.get(Template, int(tpl_id)) if tpl_id.isdigit() else None
    if tpl is None:
        raise HTTPException(404)
    if not tpl.id:
        db.add(tpl)
    tpl.name = (form.get("name") or "").strip()[:100] or "Untitled template"
    tpl.description = form.get("description") or ""
    tpl.params_json = json.dumps(render.normalize(_params_from_form(form)))
    if not _save(request, db, "Template saved."):
        return redirect(f"/admin/templates/{tpl_id}")
    return redirect(f"/admin/templates/{tpl.id}")


@router.post("/templates/{tpl_id}/duplicate")
def template_duplicate(request: Request, tpl_id: int, user: User = Depends(admin_user), db: Session = Depends(get_db)):
    tpl = db.get(Template, tpl_id)
    if not tpl:
        raise HTTPException(404)
    base, n = f"{tpl.name} copy", 1
    name = base
    while db.scalar(select(Template).where(Template.name == name)):
        n += 1
        name = f"{base} {n}"
    new = Template(name=name, description=tpl.description, params_json=tpl.params_json)
    db.add(new)
    db.commit()
    flash(request, "Template duplicated.")
    return redirect(f"/admin/templates/{new.id}")


@router.post("/templates/{tpl_id}/delete")
def template_delete(request: Request, tpl_id: int, user: User = Depends(admin_user), db: Session = Depends(get_db)):
    tpl = db.get(Template, tpl_id)
    if tpl:
        db.delete(tpl)
        db.commit()
        flash(request, "Template deleted.")
    return redirect("/admin/templates")


# ------------------------------------------------------------------ users


@router.get("/users")
def users(request: Request, user: User = Depends(admin_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(User).order_by(User.username)).all()
    return page(request, "admin/users.html", users=rows)


@router.post("/users")
def user_save(
    request: Request,
    id: str = Form(""),
    username: str = Form(...),
    password: str = Form(""),
    role: str = Form("user"),
    is_active: str = Form(""),
    user: User = Depends(admin_user),
    db: Session = Depends(get_db),
):
    u = db.get(User, int(id)) if id.isdigit() else None
    if u is None:
        if len(password) < 8:
            flash(request, "New users need a password of at least 8 characters.", "error")
            return redirect("/admin/users")
        u = User(password_hash="")
        db.add(u)
    if password:
        if len(password) < 8:
            flash(request, "Password must be at least 8 characters.", "error")
            return redirect("/admin/users")
        u.password_hash = hash_password(password)
    new_role = role if role in ("admin", "user") else "user"
    new_active = bool(is_active)
    if u.id == user.id and (new_role != "admin" or not new_active):
        flash(request, "You can't remove your own admin rights or deactivate yourself.", "error")
        return redirect("/admin/users")
    u.username = username.strip()[:64]
    u.role, u.is_active = new_role, new_active
    _save(request, db, "User saved.")
    return redirect("/admin/users")


@router.post("/users/{user_id}/delete")
def user_delete(request: Request, user_id: int, user: User = Depends(admin_user), db: Session = Depends(get_db)):
    if user_id == user.id:
        flash(request, "You can't delete yourself.", "error")
        return redirect("/admin/users")
    u = db.get(User, user_id)
    if u:
        db.delete(u)
        db.commit()
        flash(request, "User deleted.")
    return redirect("/admin/users")
