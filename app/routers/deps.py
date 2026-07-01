from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.subscription import Subscription
from app.services.auth_service import get_current_user

# Paths reachable even when a subscription is expired/suspended, so the
# owner can always get to the billing page (and log out) to fix it.
_BILLING_EXEMPT_PREFIXES = ("/billing", "/auth")


def _wants_html(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "text/html" in accept


async def _check_subscription(user: User, request: Request, db: AsyncSession) -> None:
    if any(request.url.path.startswith(p) for p in _BILLING_EXEMPT_PREFIXES):
        return

    sub = (await db.execute(
        select(Subscription).where(Subscription.network_id == user.network_id)
    )).scalar_one_or_none()

    if not sub:
        return  # no subscription row yet (e.g. legacy/manually-created network) — don't lock anyone out

    # past_due is shown as blocked in billing.html, so it must actually be
    # blocked here too — otherwise a failed card charge never cuts off access.
    blocked = sub.status in ("past_due", "suspended", "cancelled")
    if sub.status == "trial" and sub.trial_ends_at and datetime.now(timezone.utc) > sub.trial_ends_at:
        blocked = True

    if blocked:
        if _wants_html(request):
            raise HTTPException(status_code=status.HTTP_307_TEMPORARY_REDIRECT, headers={"Location": "/billing"})
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Подписка неактивна")


def _extract_token(request: Request) -> str | None:
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:]
    return request.cookies.get("access_token")


async def get_user_from_request(request: Request, db: AsyncSession) -> User | None:
    """Auth without the subscription gate — for billing/admin pages that must
    stay reachable even when a subscription is expired/suspended."""
    token = _extract_token(request)
    if not token:
        return None
    return await get_current_user(token, db)


async def get_current_user_dep(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    token = _extract_token(request)

    if not token:
        if _wants_html(request):
            raise HTTPException(status_code=status.HTTP_307_TEMPORARY_REDIRECT, headers={"Location": "/auth/login"})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Не авторизован")

    user = await get_current_user(token, db)
    if not user:
        if _wants_html(request):
            raise HTTPException(status_code=status.HTTP_307_TEMPORARY_REDIRECT, headers={"Location": "/auth/login"})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Недействительный токен")

    await _check_subscription(user, request, db)
    return user


async def get_current_user_optional(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User | None:
    try:
        return await get_current_user_dep(request, db)
    except HTTPException:
        return None


async def get_accessible_venue_ids(user: User, db: AsyncSession) -> list:
    from sqlalchemy import select
    from app.models.venue import Venue
    stmt = select(Venue.id).where(Venue.network_id == user.network_id, Venue.is_active == True)
    # Non-owner with an assigned venue: restrict to that venue only.
    # Non-owner without a venue assignment: access all network venues (network-wide manager/admin).
    if user.role != "owner" and user.venue_id:
        stmt = stmt.where(Venue.id == user.venue_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())
