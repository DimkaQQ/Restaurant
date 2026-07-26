"""Render a friendly upsell page when a tenant's paid plan doesn't include a
feature. Trials/un-billed tenants pass through (evaluation) — see plan_limits.
"""
from fastapi import Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.plan_limits import (
    FEATURE_LABELS, FEATURE_MIN_PLAN, network_has_feature,
)
from app.templates_env import templates


async def feature_gate(request: Request, feature: str, user: User, db: AsyncSession) -> HTMLResponse | None:
    """Return an upsell page (HTTP 402) if `user`'s plan lacks `feature`, else
    None so the caller renders its normal page."""
    if await network_has_feature(user.network_id, feature, db):
        return None
    plan = FEATURE_MIN_PLAN.get(feature, "pro").capitalize()
    return templates.TemplateResponse(
        "upsell.html",
        {"request": request, "user": user,
         "feature": FEATURE_LABELS.get(feature, feature), "plan": plan},
        status_code=402,
    )
