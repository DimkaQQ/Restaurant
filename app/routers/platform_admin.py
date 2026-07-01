from app.templates_env import templates
import logging
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models.network import Network
from app.models.subscription import Subscription
from app.models.user import User
from app.models.venue import Venue
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/platform/admin", tags=["platform-admin"])
logger = logging.getLogger(__name__)


async def _require_platform_admin(request: Request, db: AsyncSession) -> User:
    if not settings.PLATFORM_ADMIN_EMAIL:
        raise HTTPException(status_code=404)
    token = request.cookies.get("access_token")
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
    user = await get_current_user(token, db) if token else None
    if not user or user.email.lower() != settings.PLATFORM_ADMIN_EMAIL.lower():
        raise HTTPException(status_code=404)
    return user


@router.get("", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    await _require_platform_admin(request, db)

    networks = (await db.execute(
        select(Network)
        .options(selectinload(Network.subscription), selectinload(Network.users))
    )).scalars().all()

    venue_counts = dict((await db.execute(
        select(Venue.network_id, func.count(Venue.id)).group_by(Venue.network_id)
    )).all())

    rows = []
    plan_price = {"starter": 30, "pro": 60, "enterprise": 150}
    mrr = 0
    for net in networks:
        sub = net.subscription
        owner = next((u for u in net.users if u.role == "owner"), None)
        if sub and sub.status == "active":
            mrr += plan_price.get(sub.plan, 0)
        rows.append({
            "id": net.id,
            "name": net.name,
            "slug": net.slug,
            "owner_email": owner.email if owner else "—",
            "venue_count": venue_counts.get(net.id, 0),
            "plan": sub.plan if sub else "—",
            "status": sub.status if sub else "нет подписки",
            "trial_ends_at": sub.trial_ends_at if sub else None,
            "created_at": net.created_at,
        })
    rows.sort(key=lambda r: r["created_at"], reverse=True)

    return templates.TemplateResponse("platform_admin.html", {
        "request": request,
        "rows": rows,
        "mrr": mrr,
        "total_networks": len(networks),
        "active_count": sum(1 for r in rows if r["status"] == "active"),
        "trial_count": sum(1 for r in rows if r["status"] == "trial"),
    })


@router.post("/subscription/{network_id}")
async def update_subscription(
    network_id: uuid.UUID,
    request: Request,
    plan: str = Form(...),
    status: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    await _require_platform_admin(request, db)

    sub = (await db.execute(
        select(Subscription).where(Subscription.network_id == network_id)
    )).scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Подписка не найдена")

    sub.plan = plan
    sub.status = status
    await db.commit()
    logger.info("Platform admin set network %s to plan=%s status=%s", network_id, plan, status)
    return RedirectResponse(url="/platform/admin", status_code=303)
