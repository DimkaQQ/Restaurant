import logging
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.guest import Guest
from app.models.menu import MenuItem
from app.models.order import Order, OrderItem, OrderStatusLog, Visit
from app.schemas.order import OrderCreate
from app.services.points_service import add_points, calculate_points_earned

logger = logging.getLogger(__name__)

VALID_TRANSITIONS = {
    "new": ["confirmed", "cancelled"],
    "confirmed": ["preparing", "new", "cancelled"],
    "preparing": ["ready", "confirmed"],
    "ready": ["done", "preparing"],
    "done": [],
    "cancelled": [],
}


async def create_order(data: OrderCreate, guest: Guest, db: AsyncSession, changed_by: str = "bot") -> Order:
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
                comment=getattr(item_data, 'comment', None),
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
        table_number=getattr(data, 'table_number', None),
        source=getattr(data, 'source', None) or 'bot',
        items=order_items,
    )
    db.add(order)
    await db.flush()

    db.add(OrderStatusLog(
        id=uuid.uuid4(),
        order_id=order.id,
        old_status=None,
        new_status="new",
        changed_by=changed_by,
    ))

    visit = Visit(id=uuid.uuid4(), guest_id=guest.id, venue_id=data.venue_id, order_id=order.id)
    db.add(visit)
    guest.total_visits += 1

    await add_points(guest, data.venue_id, points, f"Заказ #{order.id}", db)
    await db.commit()
    await db.refresh(order)
    return order


async def update_order_status(
    order_id: uuid.UUID,
    new_status: str,
    db: AsyncSession,
    changed_by: str = "staff",
) -> Order:
    result = await db.execute(
        select(Order).options(selectinload(Order.items), selectinload(Order.guest)).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise ValueError("Заказ не найден")
    if new_status not in VALID_TRANSITIONS.get(order.status, []):
        raise ValueError(f"Нельзя перевести заказ из {order.status} в {new_status}")

    old_status = order.status
    order.status = new_status
    db.add(OrderStatusLog(
        id=uuid.uuid4(),
        order_id=order.id,
        old_status=old_status,
        new_status=new_status,
        changed_by=changed_by,
    ))

    await db.commit()
    result = await db.execute(
        select(Order).options(selectinload(Order.items), selectinload(Order.guest)).where(Order.id == order_id)
    )
    order = result.scalar_one()
    logger.info("Order %s status %s → %s by %s", order_id, old_status, new_status, changed_by)
    return order


async def cancel_order(
    order_id: uuid.UUID,
    db: AsyncSession,
    changed_by: str = "guest",
    allow_always: bool = False,
) -> Order:
    """Cancel order. Guests can cancel only within 10 min; staff/manager can always cancel."""
    result = await db.execute(
        select(Order).options(selectinload(Order.items), selectinload(Order.guest)).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise ValueError("Заказ не найден")
    if order.status == "cancelled":
        raise ValueError("Заказ уже отменён")
    if order.status == "done":
        raise ValueError("Нельзя отменить завершённый заказ")
    if order.status in ("preparing", "ready") and not allow_always:
        raise ValueError("Заказ уже готовится — отмена возможна только через менеджера")

    if not allow_always:
        age = datetime.now(timezone.utc) - order.created_at.replace(tzinfo=timezone.utc)
        if age > timedelta(minutes=10):
            raise ValueError("Время для самостоятельной отмены истекло (10 мин)")

    old_status = order.status
    order.status = "cancelled"
    db.add(OrderStatusLog(
        id=uuid.uuid4(),
        order_id=order.id,
        old_status=old_status,
        new_status="cancelled",
        changed_by=changed_by,
    ))
    await db.commit()
    await db.refresh(order)
    return order


async def get_order_with_items(order_id: uuid.UUID, db: AsyncSession) -> Order | None:
    result = await db.execute(
        select(Order)
        .options(selectinload(Order.items), selectinload(Order.guest))
        .where(Order.id == order_id)
    )
    return result.scalar_one_or_none()
