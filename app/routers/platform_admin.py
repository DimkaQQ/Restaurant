from app.templates_env import templates
import logging
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models.audit_log import AdminAuditLog
from app.models.network import Network
from app.models.subscription import Subscription
from app.models.user import User
from app.models.venue import Venue
from app.routers.deps import get_user_from_request
from app.services.auth_service import create_access_token, create_refresh_token

router = APIRouter(prefix="/platform/admin", tags=["platform-admin"])
logger = logging.getLogger(__name__)

_VALID_PLANS = ("starter", "pro", "enterprise")
_VALID_STATUSES = ("trial", "active", "past_due", "suspended", "cancelled")
_PLAN_PRICE_USD = {"starter": 30, "pro": 60, "enterprise": 150}
_COOKIE_SECURE = settings.PUBLIC_URL.startswith("https://")


async def _require_platform_admin(request: Request, db: AsyncSession) -> User:
    if not settings.PLATFORM_ADMIN_EMAIL:
        raise HTTPException(status_code=404)
    user = await get_user_from_request(request, db)
    if not user or user.email.lower() != settings.PLATFORM_ADMIN_EMAIL.lower():
        raise HTTPException(status_code=404)
    return user


async def _log_admin_action(admin: User, action: str, network_id, detail: str, db: AsyncSession) -> None:
    db.add(AdminAuditLog(
        id=uuid.uuid4(), admin_email=admin.email, action=action, network_id=network_id, detail=detail,
    ))
    await db.commit()
    logger.info("Platform admin %s: %s (network=%s) — %s", admin.email, action, network_id, detail)


@router.get("", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    await _require_platform_admin(request, db)

    networks = (await db.execute(
        select(Network).options(selectinload(Network.subscription))
    )).scalars().all()

    venue_counts = dict((await db.execute(
        select(Venue.network_id, func.count(Venue.id)).group_by(Venue.network_id)
    )).all())

    owner_emails = dict((await db.execute(
        select(User.network_id, User.email).where(User.role == "owner")
    )).all())

    rows = []
    mrr = 0
    for net in networks:
        sub = net.subscription
        if sub and sub.status == "active":
            mrr += _PLAN_PRICE_USD.get(sub.plan, 0)
        rows.append({
            "id": net.id,
            "name": net.name,
            "slug": net.slug,
            "owner_email": owner_emails.get(net.id, "—"),
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
    reason: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    admin = await _require_platform_admin(request, db)

    if plan not in _VALID_PLANS or status not in _VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Неверный план или статус")

    sub = (await db.execute(
        select(Subscription).where(Subscription.network_id == network_id)
    )).scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Подписка не найдена")

    old_plan, old_status = sub.plan, sub.status
    sub.plan = plan
    sub.status = status
    await db.commit()

    detail = f"plan {old_plan}→{plan}, status {old_status}→{status}"
    if reason.strip():
        detail += f" — причина: {reason.strip()}"
    await _log_admin_action(admin, "subscription_update", network_id, detail, db)
    return RedirectResponse(url="/platform/admin", status_code=303)


@router.post("/impersonate/{network_id}")
async def impersonate_owner(network_id: uuid.UUID, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """Log in as a tenant's owner for support/debugging — every use is
    written to the audit log with the acting admin's email."""
    admin = await _require_platform_admin(request, db)

    owner = (await db.execute(
        select(User).where(User.network_id == network_id, User.role == "owner")
    )).scalar_one_or_none()
    if not owner:
        raise HTTPException(status_code=404, detail="Владелец не найден")

    await _log_admin_action(admin, "impersonate", network_id, f"as {owner.email}", db)

    access_token = create_access_token({"sub": str(owner.id)})
    refresh_token = create_refresh_token({"sub": str(owner.id)})
    redirect = RedirectResponse(url="/dashboard", status_code=303)
    redirect.set_cookie(
        key="access_token", value=access_token, httponly=True, samesite="lax",
        secure=_COOKIE_SECURE, max_age=60 * settings.ACCESS_TOKEN_EXPIRE_MINUTES,
    )
    redirect.set_cookie(
        key="refresh_token", value=refresh_token, httponly=True, samesite="lax",
        secure=_COOKIE_SECURE, max_age=60 * 60 * 24 * 30,
    )
    return redirect


@router.get("/audit", response_class=HTMLResponse)
async def audit_log_page(request: Request, db: AsyncSession = Depends(get_db)):
    await _require_platform_admin(request, db)
    entries = (await db.execute(
        select(AdminAuditLog).order_by(AdminAuditLog.created_at.desc()).limit(200)
    )).scalars().all()
    return templates.TemplateResponse("platform_admin_audit.html", {"request": request, "entries": entries})
