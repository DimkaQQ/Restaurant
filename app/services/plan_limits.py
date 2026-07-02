"""Plan-tier limits (venues/staff seats) — enforces what the billing page
advertises. Trials are left unrestricted so a prospect can fully evaluate
the product before choosing a plan; limits only bite once a paid
subscription is active, so upgrading a struggling tenant is the fix rather
than a hard wall during evaluation.
"""
import uuid

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subscription import Subscription
from app.models.user import User
from app.models.venue import Venue

# None means unlimited.
PLAN_LIMITS = {
    "starter": {"max_venues": 1, "max_staff": 3},
    "pro": {"max_venues": 5, "max_staff": None},
    "enterprise": {"max_venues": None, "max_staff": None},
}


async def _get_active_subscription(network_id: uuid.UUID, db: AsyncSession) -> Subscription | None:
    sub = (await db.execute(
        select(Subscription).where(Subscription.network_id == network_id)
    )).scalar_one_or_none()
    if not sub or sub.status == "trial":
        return None
    return sub


async def check_venue_limit(network_id: uuid.UUID, db: AsyncSession) -> None:
    sub = await _get_active_subscription(network_id, db)
    if not sub:
        return
    max_venues = PLAN_LIMITS.get(sub.plan, PLAN_LIMITS["starter"])["max_venues"]
    if max_venues is None:
        return
    count = (await db.execute(
        select(func.count(Venue.id)).where(Venue.network_id == network_id)
    )).scalar_one()
    if count >= max_venues:
        raise HTTPException(
            status_code=402,
            detail=f"Достигнут лимит заведений для тарифа «{sub.plan}» ({max_venues}). "
                   f"Перейдите на другой тариф в разделе «Оплата», чтобы добавить ещё.",
        )


async def check_staff_limit(network_id: uuid.UUID, db: AsyncSession) -> None:
    sub = await _get_active_subscription(network_id, db)
    if not sub:
        return
    max_staff = PLAN_LIMITS.get(sub.plan, PLAN_LIMITS["starter"])["max_staff"]
    if max_staff is None:
        return
    count = (await db.execute(
        select(func.count(User.id)).where(User.network_id == network_id)
    )).scalar_one()
    if count >= max_staff:
        raise HTTPException(
            status_code=402,
            detail=f"Достигнут лимит сотрудников для тарифа «{sub.plan}» ({max_staff}). "
                   f"Перейдите на другой тариф в разделе «Оплата», чтобы добавить ещё.",
        )
