from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..auth import current_user
from ..db import Drop, DropImage, DropState, GoodsType, Image, User, get_db
from ..web import flash, page, redirect
from .images import add_images_to_drop

router = APIRouter()


def get_drop(db: Session, drop_id: int) -> Drop:
    drop = db.get(Drop, drop_id)
    if not drop:
        raise HTTPException(404, "Drop not found")
    return drop


@router.get("/drops")
def list_drops(request: Request, state: str = "", user: User = Depends(current_user), db: Session = Depends(get_db)):
    states = db.scalars(select(DropState).order_by(DropState.sort_order, DropState.name)).all()
    stmt = select(Drop).options(selectinload(Drop.items).selectinload(DropImage.image), selectinload(Drop.state))
    if state.isdigit():
        stmt = stmt.where(Drop.state_id == int(state))
    drops = db.scalars(stmt.order_by(Drop.planned_date.desc(), Drop.id.desc())).all()
    groups = [(s, [d for d in drops if d.state_id == s.id]) for s in states]
    no_state = [d for d in drops if d.state_id is None]
    if no_state:
        groups.append((None, no_state))
    return page(request, "drops.html", groups=groups, states=states, state_filter=state)


@router.post("/drops")
def create_drop(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    planned_date: str = Form(""),
    state_id: str = Form(""),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if state_id.isdigit():
        sid = int(state_id)
    else:
        default = db.scalar(select(DropState).where(DropState.is_default.is_(True))) or db.scalar(
            select(DropState).order_by(DropState.sort_order)
        )
        sid = default.id if default else None
    drop = Drop(name=name.strip()[:200] or "Untitled drop", description=description, planned_date=planned_date[:10], state_id=sid)
    db.add(drop)
    db.commit()
    flash(request, "Drop created.")
    return redirect(f"/drops/{drop.id}")


@router.get("/drops/{drop_id}")
def drop_detail(request: Request, drop_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    drop = get_drop(db, drop_id)
    states = db.scalars(select(DropState).order_by(DropState.sort_order, DropState.name)).all()
    goods = db.scalars(select(GoodsType).order_by(GoodsType.name)).all()
    in_drop = {it.image_id for it in drop.items}
    candidates = [i for i in db.scalars(select(Image).order_by(Image.interesting.desc(), Image.id.desc())).all() if i.id not in in_drop]
    goods_count: dict[str, int] = {}
    for it in drop.items:
        for g in it.goods:
            goods_count[g.name] = goods_count.get(g.name, 0) + 1
    return page(
        request, "drop_detail.html", drop=drop, states=states, goods=goods, candidates=candidates, goods_count=goods_count
    )


@router.post("/drops/{drop_id}")
def update_drop(
    request: Request,
    drop_id: int,
    name: str = Form(...),
    description: str = Form(""),
    planned_date: str = Form(""),
    state_id: str = Form(""),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    drop = get_drop(db, drop_id)
    drop.name = name.strip()[:200] or drop.name
    drop.description = description
    drop.planned_date = planned_date[:10]
    drop.state_id = int(state_id) if state_id.isdigit() and db.get(DropState, int(state_id)) else None
    db.commit()
    flash(request, "Drop saved.")
    return redirect(f"/drops/{drop_id}")


@router.post("/drops/{drop_id}/state")
def set_state(request: Request, drop_id: int, state_id: int = Form(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    drop = get_drop(db, drop_id)
    state = db.get(DropState, state_id)
    if not state:
        raise HTTPException(404)
    drop.state_id = state.id
    db.commit()
    flash(request, f"“{drop.name}” is now {state.name}.")
    return redirect(request.headers.get("referer") or f"/drops/{drop_id}")


@router.post("/drops/{drop_id}/delete")
def delete_drop(request: Request, drop_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not user.is_admin:
        raise HTTPException(403, "Admins only")
    drop = get_drop(db, drop_id)
    db.delete(drop)
    db.commit()
    flash(request, "Drop deleted. Its images were kept.")
    return redirect("/drops")


@router.post("/drops/{drop_id}/add")
def add_to_drop(
    request: Request, drop_id: int, ids: list[int] = Form(default=[]), user: User = Depends(current_user), db: Session = Depends(get_db)
):
    drop = get_drop(db, drop_id)
    images = db.scalars(select(Image).where(Image.id.in_(ids))).all() if ids else []
    n = add_images_to_drop(db, drop, images)
    db.commit()
    flash(request, f"Added {n} image(s).")
    return redirect(f"/drops/{drop_id}")


@router.post("/drops/{drop_id}/items/{item_id}")
def update_item(
    request: Request,
    drop_id: int,
    item_id: int,
    goods: list[int] = Form(default=[]),
    notes: str = Form(""),
    position: int = Form(0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    item = db.get(DropImage, item_id)
    if not item or item.drop_id != drop_id:
        raise HTTPException(404)
    item.goods = db.scalars(select(GoodsType).where(GoodsType.id.in_(goods))).all() if goods else []
    item.notes = notes
    item.position = position
    db.commit()
    flash(request, f"Saved “{item.image.display_title}”.")
    return redirect(f"/drops/{drop_id}#item-{item_id}")


@router.post("/drops/{drop_id}/items/{item_id}/remove")
def remove_item(request: Request, drop_id: int, item_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = db.get(DropImage, item_id)
    if not item or item.drop_id != drop_id:
        raise HTTPException(404)
    db.delete(item)
    db.commit()
    flash(request, "Removed from drop.")
    return redirect(f"/drops/{drop_id}")
