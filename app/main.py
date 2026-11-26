import logging
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from . import config, db
from .auth import LoginRequired, current_user, hash_password, seed, verify_password
from .db import User, get_db
from .routes import admin, drops, images
from .web import flash, page, redirect

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(db_url: str | None = None) -> FastAPI:
    db.init_engine(db_url)
    with db.SessionLocal() as s:
        seed(s)

    app = FastAPI(title="POD Manager", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(
        SessionMiddleware,
        secret_key=config.secret_key(),
        session_cookie="pod_session",
        max_age=60 * 60 * 24 * 14,
        same_site="lax",
        https_only=config.SECURE_COOKIES,
    )
    app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

    @app.exception_handler(LoginRequired)
    async def _login_required(request: Request, exc: LoginRequired):
        if request.url.path.startswith("/api/") or request.url.path.startswith("/media/"):
            return PlainTextResponse("Login required", status_code=401)
        return redirect(f"/login?next={request.url.path}")

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/")
    def home(user: User = Depends(current_user)):
        return redirect("/images")

    @app.get("/login")
    def login_form(request: Request, next: str = "/images"):
        return page(request, "login.html", next=next)

    @app.post("/login")
    def login(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
        next: str = Form("/images"),
        session: Session = Depends(get_db),
    ):
        user = session.scalar(select(User).where(User.username == username.strip()))
        if not user or not user.is_active or not verify_password(password, user.password_hash):
            flash(request, "Wrong username or password.", "error")
            return redirect("/login")
        request.session.clear()
        request.session["uid"] = user.id
        return redirect(next if next.startswith("/") and not next.startswith("//") else "/images")

    @app.post("/logout")
    def logout(request: Request):
        request.session.clear()
        return redirect("/login")

    @app.get("/account")
    def account(request: Request, user: User = Depends(current_user)):
        return page(request, "account.html")

    @app.post("/account/password")
    def change_password(
        request: Request,
        current: str = Form(...),
        new: str = Form(...),
        user: User = Depends(current_user),
        session: Session = Depends(get_db),
    ):
        u = session.get(User, user.id)
        if not verify_password(current, u.password_hash):
            flash(request, "Current password is wrong.", "error")
        elif len(new) < 8:
            flash(request, "New password must be at least 8 characters.", "error")
        else:
            u.password_hash = hash_password(new)
            session.commit()
            flash(request, "Password changed.")
        return redirect("/account")

    app.include_router(images.router)
    app.include_router(drops.router)
    app.include_router(admin.router)
    return app


app = create_app()
