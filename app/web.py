"""Shared helpers for route modules."""

from pathlib import Path
from typing import Any

from fastapi import Request, Response
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.datastructures import FormData

from . import config

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.globals["FONTS"] = config.FONTS
templates.env.globals["APP_VERSION"] = config.APP_VERSION


def flash(request: Request, message: str, kind: str = "ok") -> None:
    request.session.setdefault("flash", []).append([kind, message])


def form_str(form: FormData, key: str, default: str = "") -> str:
    """A text field from a parsed form (uploads and missing keys give `default`)."""
    value = form.get(key)
    return value if isinstance(value, str) else default


def page(request: Request, name: str, **ctx: Any) -> Response:
    messages = request.session.pop("flash", [])
    return templates.TemplateResponse(
        request,
        name,
        {"user": getattr(request.state, "user", None), "messages": messages, **ctx},
    )


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)
