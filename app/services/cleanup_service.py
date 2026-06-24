"""Background cleanup: auto-cancel orders stuck in 'new'/'confirmed' for too long.

Orders that are never acted on (app crash, missed notification, network issue)
would permanently hold awarded loyalty points. This loop reverses them.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.order import Order
from app.services.order_service import cancel_order

logger = logging.getLogger(__name__)

# Orders in new/confirmed older than this are auto-cancelled.
# 'preparing' and 'ready' are left for staff to resolve manually.
STALE_HOURS = 2


async def cancel_stale_orders() -> int:
    """Find orders stuck in new/confirmed for > STALE_HOURS and cancel them.
    Returns the number of orders cancelled."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=STALE_HOURS)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Order.id).where(
                Order.status.in_(["new", "confirmed"]),
                Order.created_at <= cutoff,
            )
        )
        stale_ids = list(result.scalars().all())

    if not stale_ids:
        return 0

    cancelled = 0
    for order_id in stale_ids:
        try:
            async with AsyncSessionLocal() as db:
                await cancel_order(
                    order_id,
                    db,
                    changed_by="system:stale",
                    allow_always=True,
                )
                cancelled += 1
        except ValueError as e:
            # Already cancelled or completed between the query and now — fine
            logger.debug("Skipping stale order %s: %s", order_id, e)
        except Exception as e:
            logger.error("Auto-cancel failed for order %s: %s", order_id, e)

    if cancelled:
        logger.info(
            "Auto-cancelled %d stale order(s) (stuck > %dh in new/confirmed)",
            cancelled, STALE_HOURS,
        )
    return cancelled


async def stale_order_cleanup_loop(interval_seconds: int = 3600) -> None:
    """Run stale-order cleanup every interval_seconds. Starts after a 90s delay."""
    await asyncio.sleep(90)  # let the app fully start before first run
    while True:
        try:
            await cancel_stale_orders()
        except Exception as e:
            logger.error("Stale order cleanup loop error: %s", e)
        await asyncio.sleep(interval_seconds)
