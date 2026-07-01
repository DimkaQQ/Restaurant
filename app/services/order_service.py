import logging
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.guest import Guest
from app.models.inventory import Ingredient, WriteOff
from app.models.menu import MenuItem
from app.models.order import Order, OrderItem, OrderStatusLog, Visit
from app.models.points import PointsTransaction
from app.models.recipe import Recipe
from app.models.table import Table
from app.schemas.order import OrderCreate
from app.services.points_service import add_points, calculate_points_earned

ACTIVE_ORDER_STATUSES = ("new", "confirmed", "preparing", "ready")


async def _sync_table_status(table_id: uuid.UUID, db: AsyncSession) -> None:
    """Free a table once it has no more active orders; occupy it otherwise.
    Reserved tables are left alone — that status is set/cleared manually."""
    table = (await db.execute(select(Table).where(Table.id == table_id).with_for_update())).scalar_one_or_none()
    if not table or table.status == "reserved":
        return
    has_active = (await db.execute(
        select(Order.id).where(Order.table_id == table_id, Order.status.in_(ACTIVE_ORDER_STATUSES)).limit(1)
    )).first()
    table.status = "occupied" if has_active else "free"

logger = logging.getLogger(__name__)

VALID_TRANSITIONS = {
    "new": ["confirmed", "cancelled"],
    "confirmed": ["preparing", "new", "cancelled"],
    "preparing": ["ready", "confirmed"],
    "ready": ["done", "preparing"],
    "done": [],
    "cancelled": [],
}


WALKIN_MARKER = "__walkin__"


async def get_or_create_walkin_guest(network_id: uuid.UUID, db: AsyncSession) -> Guest:
    """Anonymous guest bucket for POS orders placed by staff without a real customer
    (walk-ins, takeaway at the counter) — keeps Order.guest_id NOT NULL without
    forcing every in-house sale through the Telegram loyalty flow."""
    existing = (await db.execute(
        select(Guest).where(Guest.network_id == network_id, Guest.phone == WALKIN_MARKER)
    )).scalar_one_or_none()
    if existing:
        return existing

    guest = Guest(
        id=uuid.uuid4(),
        network_id=network_id,
        name="Гость (касса)",
        phone=WALKIN_MARKER,
    )
    db.add(guest)
    await db.flush()
    return guest


async def create_order(data: OrderCreate, guest: Guest, db: AsyncSession, changed_by: str = "bot") -> Order:
    table = None
    table_id = getattr(data, 'table_id', None)
    if table_id:
        table = (await db.execute(
            select(Table).where(Table.id == table_id, Table.venue_id == data.venue_id)
        )).scalar_one_or_none()
        if not table:
            raise ValueError("Стол не найден в этом заведении")

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

    is_walkin = guest.phone == WALKIN_MARKER
    points = 0 if is_walkin else calculate_points_earned(total)
    order = Order(
        id=uuid.uuid4(),
        venue_id=data.venue_id,
        guest_id=guest.id,
        status="new",
        total_amount=total,
        points_earned=points,
        notes=data.notes,
        table_number=table.label if table else getattr(data, 'table_number', None),
        table_id=table.id if table else None,
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

    # The shared walk-in guest bucket doesn't earn loyalty visits/points —
    # those only make sense for real, identifiable customers.
    if not is_walkin:
        visit = Visit(id=uuid.uuid4(), guest_id=guest.id, venue_id=data.venue_id, order_id=order.id)
        db.add(visit)
        guest.total_visits += 1
        await add_points(guest, data.venue_id, points, f"Заказ #{order.id}", db)

    if table:
        await _sync_table_status(table.id, db)

    await db.commit()
    # Plain db.refresh() only reloads the order's own columns; OrderOut also
    # serializes .items/.guest, which are lazy-loaded relationships that can't
    # be touched implicitly once we're back in FastAPI's response-serialization
    # code (raises MissingGreenlet) — so eagerly reload them here instead.
    result = await db.execute(
        select(Order).options(selectinload(Order.items), selectinload(Order.guest)).where(Order.id == order.id)
    )
    return result.scalar_one()


async def _deduct_inventory_for_order(order: Order, db: AsyncSession) -> None:
    """Auto-deduct ingredient stock per the tech card (Recipe) when an order completes.
    Best-effort: goes negative rather than blocking order completion on missing stock."""
    menu_item_ids = [i.menu_item_id for i in order.items if i.menu_item_id]
    if not menu_item_ids:
        return

    recipes = (await db.execute(
        select(Recipe).where(Recipe.menu_item_id.in_(menu_item_ids))
    )).scalars().all()
    if not recipes:
        return

    recipes_by_item: dict[uuid.UUID, list[Recipe]] = {}
    for r in recipes:
        recipes_by_item.setdefault(r.menu_item_id, []).append(r)

    needed: dict[uuid.UUID, Decimal] = {}
    for item in order.items:
        for recipe in recipes_by_item.get(item.menu_item_id, []):
            needed[recipe.ingredient_id] = needed.get(recipe.ingredient_id, Decimal("0")) + recipe.quantity * item.quantity

    if not needed:
        return

    # Lock the ingredient rows so two orders completing concurrently with a
    # shared ingredient serialize instead of one deduction clobbering the other.
    ingredients = (await db.execute(
        select(Ingredient).where(Ingredient.id.in_(needed.keys())).with_for_update()
    )).scalars().all()

    for ingredient in ingredients:
        amount = needed[ingredient.id]
        ingredient.quantity = (ingredient.quantity or Decimal("0")) - amount
        db.add(WriteOff(
            id=uuid.uuid4(),
            ingredient_id=ingredient.id,
            quantity=amount,
            reason="usage",
            note=f"Автосписание по заказу #{str(order.id)[:8].upper()}",
        ))


async def update_order_status(
    order_id: uuid.UUID,
    new_status: str,
    db: AsyncSession,
    changed_by: str = "staff",
) -> Order:
    # Lock the order row for the duration of the transition so two concurrent
    # requests (double-click, racing clients) can't both pass the
    # VALID_TRANSITIONS check and both trigger inventory deduction on "done".
    result = await db.execute(
        select(Order)
        .options(selectinload(Order.items), selectinload(Order.guest))
        .where(Order.id == order_id)
        .with_for_update()
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

    if new_status == "done":
        await _deduct_inventory_for_order(order, db)

    if order.table_id and new_status in ("done", "cancelled"):
        await _sync_table_status(order.table_id, db)

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
    guest_id: uuid.UUID | None = None,
) -> Order:
    """Cancel order. Guests can cancel only within 10 min; staff/manager can always cancel.
    Pass guest_id to enforce ownership check atomically inside the service."""
    result = await db.execute(
        select(Order).options(selectinload(Order.items), selectinload(Order.guest)).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise ValueError("Заказ не найден")
    # Ownership check — prevents TOCTOU if called with guest_id
    if guest_id is not None and order.guest_id != guest_id:
        raise ValueError("Заказ не найден")
    if order.status == "cancelled":
        raise ValueError("Заказ уже отменён")
    if order.status == "done":
        raise ValueError("Нельзя отменить завершённый заказ")
    if order.status in ("preparing", "ready") and not allow_always:
        raise ValueError("Заказ уже готовится — отмена возможна только через менеджера")

    if not allow_always:
        created_at_utc = order.created_at if order.created_at.tzinfo else order.created_at.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - created_at_utc
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

    # Reverse points earned on this order to prevent farming
    if order.points_earned and order.points_earned > 0 and order.guest:
        guest = order.guest
        points_to_reverse = min(order.points_earned, guest.total_points or 0)
        if points_to_reverse > 0:
            guest.total_points -= points_to_reverse
            db.add(PointsTransaction(
                id=uuid.uuid4(),
                guest_id=guest.id,
                venue_id=order.venue_id,
                amount=-points_to_reverse,
                reason=f"Отмена заказа #{str(order.id)[:8].upper()}",
            ))
            logger.info("Reversed %d points for guest %s on order cancellation", points_to_reverse, guest.id)

    # Reverse visit counter — cancelled orders shouldn't count as visits
    if order.guest:
        visit = (await db.execute(select(Visit).where(Visit.order_id == order_id))).scalar_one_or_none()
        if visit:
            await db.delete(visit)
            if order.guest.total_visits and order.guest.total_visits > 0:
                order.guest.total_visits -= 1

    if order.table_id:
        await _sync_table_status(order.table_id, db)

    await db.commit()
    # db.refresh() expires the eagerly-loaded items/guest relationships too;
    # reload with selectinload so OrderOut can serialize them without an
    # implicit lazy-load outside the request's greenlet context.
    result = await db.execute(
        select(Order).options(selectinload(Order.items), selectinload(Order.guest)).where(Order.id == order_id)
    )
    return result.scalar_one()


async def get_order_with_items(order_id: uuid.UUID, db: AsyncSession) -> Order | None:
    result = await db.execute(
        select(Order)
        .options(selectinload(Order.items), selectinload(Order.guest))
        .where(Order.id == order_id)
    )
    return result.scalar_one_or_none()
