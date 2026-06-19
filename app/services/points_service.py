import logging
import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.guest import Guest
from app.models.points import PointsTransaction

logger = logging.getLogger(__name__)

POINTS_PER_TENGE = Decimal("0.01")  # 10 points per 1000 tenge
POINTS_REDEEM_RATE = 5  # 100 points = 500 tenge => 5 tenge per point


def calculate_points_earned(total_amount: Decimal) -> int:
    return int(total_amount * POINTS_PER_TENGE)


async def add_points(
    guest: Guest,
    venue_id: uuid.UUID,
    amount: int,
    reason: str,
    db: AsyncSession,
) -> None:
    transaction = PointsTransaction(
        id=uuid.uuid4(),
        guest_id=guest.id,
        venue_id=venue_id,
        amount=amount,
        reason=reason,
    )
    db.add(transaction)
    guest.total_points += amount
    logger.info("Added %d points to guest %s (%s)", amount, guest.id, reason)


async def redeem_points(
    guest: Guest,
    venue_id: uuid.UUID,
    points: int,
    db: AsyncSession,
) -> Decimal:
    if guest.total_points < points:
        raise ValueError("Недостаточно баллов")
    discount = Decimal(points * POINTS_REDEEM_RATE)
    transaction = PointsTransaction(
        id=uuid.uuid4(),
        guest_id=guest.id,
        venue_id=venue_id,
        amount=-points,
        reason=f"Списание {points} баллов (скидка {discount} тг)",
    )
    db.add(transaction)
    guest.total_points -= points
    logger.info("Redeemed %d points for guest %s", points, guest.id)
    return discount
