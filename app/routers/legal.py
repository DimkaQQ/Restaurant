from datetime import date

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.templates_env import templates

router = APIRouter(prefix="/legal", tags=["legal"])

_UPDATED = date(2026, 7, 2).isoformat()


@router.get("/terms", response_class=HTMLResponse)
async def terms(request: Request):
    return templates.TemplateResponse("legal/terms.html", {"request": request, "updated": _UPDATED})


@router.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request):
    return templates.TemplateResponse("legal/privacy.html", {"request": request, "updated": _UPDATED})
