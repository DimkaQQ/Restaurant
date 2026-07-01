from app.templates_env import templates
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.subscription import Subscription
from app.models.user import User
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/billing", tags=["billing"])
logger = logging.getLogger(__name__)


@router.get("", response_class=HTMLResponse)
async def billing_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    # get_current_user_dep would redirect back here on an expired subscription,
    # so this page authenticates the user directly without the subscription gate.
    token = request.cookies.get("access_token")
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
    current_user: User | None = await get_current_user(token, db) if token else None
    if not current_user:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/auth/login")

    sub = (await db.execute(
        select(Subscription).where(Subscription.network_id == current_user.network_id)
    )).scalar_one_or_none()

    days_left = None
    if sub and sub.status == "trial" and sub.trial_ends_at:
        delta = sub.trial_ends_at - datetime.now(timezone.utc)
        days_left = max(0, delta.days)

    return templates.TemplateResponse("billing.html", {
        "request": request,
        "user": current_user,
        "subscription": sub,
        "days_left": days_left,
    })
