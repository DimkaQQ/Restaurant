"""Re-anchor demo data to "today" so a live demo never shows a date gap.

Seed data is generated relative to when `seed_data.py` ran, so a week later
the dashboard's "today", the P&L "this month", NPS "this month" and the
kitchen's elapsed-time all look empty or absurd (orders "21000 min" old).

This script shifts every time column forward by one delta — the gap between
the newest order and now — preserving the whole 30/180-day distribution but
landing the freshest data on today. It also backfills what the demo needs to
look complete: tables per venue and tech cards (recipes) for popular items.

Idempotent: re-run before each demo; it re-anchors to the current moment.

    python scripts/refresh_demo_data.py            # shift + backfill
    make refresh                                    # same, in docker
"""
import asyncio
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select, func, text

from app.database import AsyncSessionLocal
from app.models.menu import MenuItem
from app.models.table import Table
from app.models.inventory import Ingredient
from app.models.recipe import Recipe


# (table, timestamp-with-tz column) pairs to shift by the same delta.
_TS_COLUMNS = [
    ("orders", "created_at"), ("orders", "updated_at"), ("orders", "paid_at"),
    ("order_items", None),  # no ts
    ("visits", "created_at"),
    ("reviews", "created_at"),
    ("cash_shifts", "opened_at"), ("cash_shifts", "closed_at"),
    ("expenses", "created_at"),
    ("write_offs", "created_at"),
    ("points_transactions", "created_at"),
    ("guests", "created_at"),
    ("purchase_invoices", "created_at"),
]
# date-only columns (no tz) shifted by whole days
_DATE_COLUMNS = [
    ("expenses", "expense_date"),
    ("shifts", "shift_date"),
    ("purchase_invoices", "invoice_date"),
]


async def _column_exists(db, table: str, column: str) -> bool:
    row = (await db.execute(text(
        "SELECT 1 FROM information_schema.columns WHERE table_name=:t AND column_name=:c"
    ), {"t": table, "c": column})).first()
    return row is not None


async def shift_dates(db) -> timedelta | None:
    """Shift every timestamp so the newest data point sits ~now.

    The anchor is the max across *every* column we shift — not just
    orders.created_at — otherwise later timestamps (an order's updated_at /
    paid_at, a review or visit made after the last order) would be pushed
    past "now" into the future and read as negative elapsed time."""
    newest = None
    for table, col in _TS_COLUMNS:
        if col is None or not await _column_exists(db, table, col):
            continue
        m = (await db.execute(text(f"SELECT max({col}) FROM {table}"))).scalar()
        if m is not None and (newest is None or m > newest):
            newest = m
    if newest is None:
        print("No timestamped rows — nothing to shift.")
        return None
    now = datetime.now(timezone.utc)
    # land the freshest row a few minutes ago (so it reads as "just now")
    delta = now - newest - timedelta(minutes=5)
    if abs(delta.total_seconds()) < 3600:
        print(f"Data already fresh (newest row {newest.isoformat()}). Skipping shift.")
        return timedelta(0)

    seconds = int(delta.total_seconds())
    # keep date-only columns aligned with their timestamp siblings: round to
    # the nearest day instead of truncating, so expense_date matches created_at.
    days = round(seconds / 86400)
    for table, col in _TS_COLUMNS:
        if col is None or not await _column_exists(db, table, col):
            continue
        await db.execute(text(
            f"UPDATE {table} SET {col} = {col} + make_interval(secs => :s) WHERE {col} IS NOT NULL"
        ), {"s": seconds})
    for table, col in _DATE_COLUMNS:
        if not await _column_exists(db, table, col):
            continue
        await db.execute(text(
            f"UPDATE {table} SET {col} = {col} + make_interval(days => :d) WHERE {col} IS NOT NULL"
        ), {"d": days})
    await db.commit()
    print(f"Shifted all dates forward by {days} days ({seconds}s). Newest order now ~today.")
    return delta


async def ensure_paid_consistency(db):
    """A 'done' order that somehow has no paid_at won't count as today's
    revenue after the shift — give served orders a paid_at so the P&L and
    dashboard 'today' populate on demo."""
    await db.execute(text(
        "UPDATE orders SET payment_status='paid', paid_at=COALESCE(paid_at, updated_at, created_at) "
        "WHERE status='done' AND payment_status <> 'refunded'"
    ))
    await db.commit()
    print("Ensured served (done) orders are marked paid.")


async def ensure_tables(db):
    """Every venue should have a floor plan for the demo (Касса/Официант use it)."""
    venue_ids = [v for (v,) in (await db.execute(text("SELECT id FROM venues"))).all()]
    created = 0
    for vid in venue_ids:
        existing = (await db.execute(
            select(func.count(Table.id)).where(Table.venue_id == vid)
        )).scalar() or 0
        if existing:
            continue
        n = random.randint(8, 15)
        for i in range(1, n + 1):
            db.add(Table(id=uuid.uuid4(), venue_id=vid, label=str(i),
                         seats=random.choice([2, 2, 4, 4, 4, 6]), status="free"))
        # a couple of bar seats
        for b in ("Бар 1", "Бар 2"):
            db.add(Table(id=uuid.uuid4(), venue_id=vid, label=b, seats=1, status="free"))
        created += n + 2
    await db.commit()
    print(f"Ensured tables: created {created} across {len(venue_ids)} venues.")


async def ensure_recipes(db):
    """Give some menu items a tech card so Menu-engineering shows a margin
    instead of '—'. Uses whatever ingredients the venue already has."""
    made = 0
    venue_ids = [v for (v,) in (await db.execute(text("SELECT id FROM venues"))).all()]
    for vid in venue_ids:
        ings = (await db.execute(
            select(Ingredient.id).where(Ingredient.venue_id == vid).limit(12)
        )).scalars().all()
        if not ings:
            continue
        items = (await db.execute(
            select(MenuItem.id).where(MenuItem.venue_id == vid).limit(15)
        )).scalars().all()
        for item_id in items:
            has = (await db.execute(
                select(func.count(Recipe.id)).where(Recipe.menu_item_id == item_id)
            )).scalar() or 0
            if has:
                continue
            for ing_id in random.sample(ings, k=min(len(ings), random.randint(2, 4))):
                db.add(Recipe(id=uuid.uuid4(), menu_item_id=item_id, ingredient_id=ing_id,
                              quantity=round(random.uniform(0.02, 0.3), 3)))
                made += 1
    await db.commit()
    print(f"Ensured recipes: added {made} tech-card lines.")


async def main():
    async with AsyncSessionLocal() as db:
        await shift_dates(db)
        await ensure_paid_consistency(db)
        await ensure_tables(db)
        await ensure_recipes(db)
    print("✓ Demo data refreshed — ready to present.")


if __name__ == "__main__":
    asyncio.run(main())
