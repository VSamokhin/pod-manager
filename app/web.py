"""Shared helpers for route modules."""

from pathlib import Path

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from . import config

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.globals["FONTS"] = config.FONTS


def flash(request: Request, message: str, kind: str = "ok") -> None:
    request.session.setdefault("flash", []).append([kind, message])


def page(request: Request, name: str, **ctx):
    messages = request.session.pop("flash", [])
    return templates.TemplateResponse(
        request,
        name,
        {"user": getattr(request.state, "user", None), "messages": messages, **ctx},
    )


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)
