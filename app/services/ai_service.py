import logging
import uuid

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.guest import Guest
from app.models.menu import MenuItem
from app.models.order import Order

logger = logging.getLogger(__name__)


async def get_guest_recommendation(guest_id: uuid.UUID, venue_id: uuid.UUID, db: AsyncSession) -> str:
    guest_result = await db.execute(
        select(Guest).options(selectinload(Guest.orders)).where(Guest.id == guest_id)
    )
    guest = guest_result.scalar_one_or_none()
    if not guest:
        return "Добро пожаловать! Рады видеть вас у нас."

    orders_result = await db.execute(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.guest_id == guest_id)
        .order_by(Order.created_at.desc())
        .limit(10)
    )
    recent_orders = orders_result.scalars().all()

    menu_result = await db.execute(
        select(MenuItem).where(MenuItem.venue_id == venue_id, MenuItem.is_available == True)
    )
    menu_items = menu_result.scalars().all()

    order_history = []
    for order in recent_orders:
        items_str = ", ".join(f"{item.name} x{item.quantity}" for item in order.items)
        order_history.append(items_str)

    history_text = "; ".join(order_history) if order_history else "нет истории заказов"
    menu_text = ", ".join(f"{m.name} ({m.price} тг)" for m in menu_items[:20])

    prompt = (
        f"Ты персональный ассистент ресторана. Гость {guest.name or 'наш гость'} обычно заказывает: {history_text}. "
        f"Текущее меню: {menu_text}. "
        f"Напиши короткое (1-2 предложения) приветствие и рекомендацию. "
        f"На русском языке. Тепло и лично."
    )

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        message = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
    except Exception as e:
        logger.error("AI recommendation failed: %s", e)
        return f"Привет, {guest.name or 'дорогой гость'}! Рады видеть вас снова!"
