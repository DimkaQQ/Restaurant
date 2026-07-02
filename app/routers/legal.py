from datetime import date

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.i18n import get_translator
from app.templates_env import templates

router = APIRouter(prefix="/legal", tags=["legal"])

_UPDATED = date(2026, 7, 2).isoformat()


def _response(request: Request, template: str):
    gettext_fn, locale = get_translator(request)
    response = templates.TemplateResponse(
        template, {"request": request, "updated": _UPDATED, "_": gettext_fn, "locale": locale}
    )
    if request.query_params.get("lang") in ("ru", "en"):
        response.set_cookie("lang", request.query_params["lang"], max_age=60 * 60 * 24 * 365)
    return response


@router.get("/terms", response_class=HTMLResponse)
async def terms(request: Request):
    return _response(request, "legal/terms.html")


@router.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request):
    return _response(request, "legal/privacy.html")
