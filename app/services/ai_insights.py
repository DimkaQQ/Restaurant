"""AI-generated weekly insights for the owner: revenue trends, dead menu
items, low stock, weekday patterns — turned into 3-5 concrete actions in
plain Russian by Claude. Gated on ANTHROPIC_API_KEY; the numbers are
computed here (SQL), the model only interprets them, so it can't
hallucinate the underlying figures."""
import logging
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select, func, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.inventory import Ingredient
from app.models.menu import MenuItem
from app.models.order import Order, OrderItem

logger = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"


async def gather_stats(db: AsyncSession, venue_ids: list[uuid.UUID]) -> dict:
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=28)

    daily = (await db.execute(
        select(cast(Order.paid_at, Date).label("day"), func.sum(Order.total_amount).label("rev"))
        .where(Order.venue_id.in_(venue_ids), Order.payment_status == "paid", Order.paid_at >= since)
        .group_by("day").order_by("day")
    )).all()

    top = (await db.execute(
        select(OrderItem.name, func.sum(OrderItem.quantity).label("qty"))
        .join(Order)
        .where(Order.venue_id.in_(venue_ids), Order.created_at >= since, Order.status != "cancelled")
        .group_by(OrderItem.name).order_by(func.sum(OrderItem.quantity).desc()).limit(5)
    )).all()

    sold_names = {r[0] for r in (await db.execute(
        select(OrderItem.name).join(Order)
        .where(Order.venue_id.in_(venue_ids), Order.created_at >= since)
        .distinct()
    )).all()}
    all_items = (await db.execute(
        select(MenuItem.name).where(MenuItem.venue_id.in_(venue_ids), MenuItem.is_available == True)  # noqa: E712
    )).scalars().all()
    dead_items = [n for n in all_items if n not in sold_names][:10]

    low_stock = (await db.execute(
        select(Ingredient.name, Ingredient.quantity, Ingredient.min_quantity, Ingredient.unit)
        .where(Ingredient.venue_id.in_(venue_ids), Ingredient.min_quantity > 0,
               Ingredient.quantity <= Ingredient.min_quantity)
        .limit(10)
    )).all()

    weekday_rev: dict[int, list[float]] = {}
    for r in daily:
        wd = r.day.weekday()
        weekday_rev.setdefault(wd, []).append(float(r.rev))
    wd_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    weekday_avg = {wd_names[k]: round(sum(v) / len(v)) for k, v in sorted(weekday_rev.items())}

    return {
        "daily_revenue": [{"day": str(r.day), "revenue": float(r.rev)} for r in daily],
        "top_items": [{"name": r.name, "qty": int(r.qty)} for r in top],
        "dead_items": dead_items,
        "low_stock": [
            {"name": r.name, "quantity": float(r.quantity), "min": float(r.min_quantity), "unit": r.unit}
            for r in low_stock
        ],
        "weekday_avg_revenue": weekday_avg,
    }


async def generate_insights(db: AsyncSession, venue_ids: list[uuid.UUID]) -> str:
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("AI-инсайты не настроены (нет ANTHROPIC_API_KEY)")

    stats = await gather_stats(db, venue_ids)
    if not stats["daily_revenue"]:
        return "Пока недостаточно данных: нужны оплаченные заказы хотя бы за несколько дней."

    import json
    prompt = (
        "Ты — консультант по управлению кафе. Ниже статистика заведения за 28 дней (JSON). "
        "Дай владельцу 3–5 коротких конкретных рекомендаций на русском: что улучшить, что убрать из меню, "
        "что докупить, какие дни проседают. Пиши по делу, маркированным списком, без воды и приветствий. "
        "Опирайся только на эти цифры.\n\n" + json.dumps(stats, ensure_ascii=False)
    )

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            ANTHROPIC_URL,
            headers={
                "x-api-key": settings.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": MODEL,
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
    return "".join(block.get("text", "") for block in data.get("content", []))
