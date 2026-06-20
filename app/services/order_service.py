import logging
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.guest import Guest
from app.models.menu import MenuItem
from app.models.order import Order, OrderItem, Visit
from app.models.venue import Venue
from app.schemas.order import OrderCreate
from app.services.points_service import add_points, calculate_points_earned

logger = logging.getLogger(__name__)

VALID_TRANSITIONS = {
    "new": ["confirmed", "cancelled"],
    "confirmed": ["preparing", "cancelled"],
    "preparing": ["ready", "cancelled"],
    "ready": ["done", "cancelled"],
    "done": [],
    "cancelled": [],
}


async def create_order(data: OrderCreate, guest: Guest, db: AsyncSession) -> Order:
    item_ids = [i.menu_item_id for i in data.items]
    result = await db.execute(
        select(MenuItem).where(MenuItem.id.in_(item_ids), MenuItem.venue_id == data.venue_id)
    )
    menu_items = {m.id: m for m in result.scalars().all()}

    total = Decimal("0")
    order_items = []
    for item_data in data.items:
        menu_item = menu_items.get(item_data.menu_item_id)
        if not menu_item or not menu_item.is_available:
            raise ValueError(f"Позиция {item_data.menu_item_id} недоступна")
        subtotal = menu_item.price * item_data.quantity
        total += subtotal
        order_items.append(
            OrderItem(
                id=uuid.uuid4(),
                menu_item_id=menu_item.id,
                quantity=item_data.quantity,
                price=menu_item.price,
                name=menu_item.name,
            )
        )

    points = calculate_points_earned(total)
    order = Order(
        id=uuid.uuid4(),
        venue_id=data.venue_id,
        guest_id=guest.id,
        status="new",
        total_amount=total,
        points_earned=points,
        notes=data.notes,
        items=order_items,
    )
    db.add(order)
    await db.flush()

    visit = Visit(id=uuid.uuid4(), guest_id=guest.id, venue_id=data.venue_id, order_id=order.id)
    db.add(visit)
    guest.total_visits += 1

    await add_points(guest, data.venue_id, points, f"Заказ #{order.id}", db)
    await db.commit()
    await db.refresh(order)
    return order


async def update_order_status(order_id: uuid.UUID, new_status: str, db: AsyncSession) -> Order:
    result = await db.execute(
        select(Order).options(selectinload(Order.items), selectinload(Order.guest)).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise ValueError("Заказ не найден")
    if new_status not in VALID_TRANSITIONS.get(order.status, []):
        raise ValueError(f"Нельзя перевести заказ из {order.status} в {new_status}")

    order.status = new_status
    await db.commit()
    await db.refresh(order)
    logger.info("Order %s status -> %s", order_id, new_status)
    return order


async def get_order_with_items(order_id: uuid.UUID, db: AsyncSession) -> Order | None:
    result = await db.execute(
        select(Order)
        .options(selectinload(Order.items), selectinload(Order.guest))
        .where(Order.id == order_id)
    )
    return result.scalar_one_or_none()
