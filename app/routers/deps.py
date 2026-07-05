from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status, Request
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


# ── Role-based access ─────────────────────────────────────────────────────
# One linear hierarchy: each level includes everything below it.
#   waiter/kitchen/cashier — floor jobs (level 1). Same API rights: orders,
#                    cash shifts, stock intake/write-off, stop-list. They
#                    differ in WHICH SCREEN they live on (see JOB_HOME):
#                    each job role is locked to its own workstation screen.
#   manager        — + menu editing, guests, analytics, staff & schedules,
#                    goods receipts (invoices)
#   administrator  — + finances (P&L, expenses, CSV), broadcasts
#   owner          — + settings: venues, users, promos, API, billing
ROLE_LEVEL = {"waiter": 1, "kitchen": 1, "cashier": 1, "manager": 2, "administrator": 3, "owner": 4}

# Workstation lock: a job-role account opens ONLY its screen (plus what the
# job genuinely needs). Any other page silently redirects home — a tablet at
# the register can't wander into the back office by a stray tap.
JOB_HOME = {"cashier": "/pos", "waiter": "/waiter", "kitchen": "/kitchen"}
JOB_ALLOWED_PREFIXES = {
    # the register also serves/collects payment from the orders board
    "cashier": ("/pos", "/orders", "/waiter", "/kitchen", "/partials"),
    "waiter": ("/waiter",),
    "kitchen": ("/kitchen", "/partials"),
}


def _job_screen_gate(user: User, request: Request) -> None:
    """For job roles, redirect any HTML page outside their workstation back
    to their home screen. APIs are untouched (guarded by _wants_html)."""
    home = JOB_HOME.get(user.role)
    if not home or not _wants_html(request):
        return
    path = request.url.path
    allowed = JOB_ALLOWED_PREFIXES[user.role]
    # receipts/tickets print from any station
    if path.endswith("/receipt") or path.startswith(allowed) or path.startswith("/auth"):
        return
    raise HTTPException(status_code=status.HTTP_307_TEMPORARY_REDIRECT, headers={"Location": home})


def role_at_least(user: User, min_role: str) -> bool:
    return ROLE_LEVEL.get(user.role, 0) >= ROLE_LEVEL[min_role]


def require_role(min_role: str):
    """Dependency factory: `Depends(require_role("manager"))` returns the
    current user or raises 403. HTML requests get redirected home instead of
    a bare error page."""
    async def _dep(
        request: Request,
        db: AsyncSession = Depends(get_db),
    ) -> User:
        user = await get_current_user_dep(request, db)
        if not role_at_least(user, min_role):
            if _wants_html(request):
                raise HTTPException(status_code=status.HTTP_307_TEMPORARY_REDIRECT, headers={"Location": "/dashboard"})
            raise HTTPException(status_code=403, detail="Недостаточно прав для этого раздела")
        return user
    return _dep


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
    _job_screen_gate(user, request)
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
