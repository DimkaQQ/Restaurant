import logging
from app.config import settings
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
from app.services.fiscal.service import issue_fiscal_check
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
    forcing every in-house sale through the loyalty flow."""
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


async def create_order(
    data: OrderCreate,
    guest: Guest,
    db: AsyncSession,
    changed_by: str = "bot",
    waiter_user_id: uuid.UUID | None = None,
    waiter_name: str | None = None,
) -> Order:
    table = None
    table_id = getattr(data, 'table_id', None)
    if table_id:
        table = (await db.execute(
            select(Table).where(Table.id == table_id, Table.venue_id == data.venue_id)
        )).scalar_one_or_none()
        if not table:
            raise ValueError("Стол не найден в этом заведении")

    item_ids = [i.menu_item_id for i in data.items if i.menu_item_id]
    result = await db.execute(
        select(MenuItem).where(MenuItem.id.in_(item_ids), MenuItem.venue_id == data.venue_id)
    )
    menu_items = {m.id: m for m in result.scalars().all()}

    # Resolve all chosen modifier options in one query, then validate each
    # against its item — never trust client-supplied price deltas.
    all_option_ids = [oid for i in data.items for oid in getattr(i, 'modifier_option_ids', [])]
    options_by_id = {}
    if all_option_ids:
        from app.models.menu import ModifierOption, ModifierGroup
        rows = (await db.execute(
            select(ModifierOption, ModifierGroup.menu_item_id)
            .join(ModifierGroup, ModifierOption.group_id == ModifierGroup.id)
            .where(ModifierOption.id.in_(all_option_ids))
        )).all()
        options_by_id = {opt.id: (opt, mi_id) for opt, mi_id in rows}

    total = Decimal("0")
    order_items = []
    for item_data in data.items:
        if item_data.menu_item_id is None:
            # Free-form line ("Прочее"): staff-entered name and price, for
            # things not in the menu. Guest-facing endpoints require a real
            # menu_item_id in their schemas and can never reach this branch.
            if data.source not in ("pos", "staff"):
                raise ValueError("Произвольные позиции доступны только персоналу")
            free_name = (item_data.name or "").strip()
            if not free_name or item_data.price is None:
                raise ValueError("Для произвольной позиции нужны название и цена")
            line_price = Decimal(item_data.price)
            total += line_price * item_data.quantity
            order_items.append(OrderItem(
                id=uuid.uuid4(),
                menu_item_id=None,
                quantity=item_data.quantity,
                price=line_price,
                name=free_name,
                comment=getattr(item_data, 'comment', None),
            ))
            continue
        menu_item = menu_items.get(item_data.menu_item_id)
        if not menu_item or not menu_item.is_available:
            raise ValueError(f"Позиция {item_data.menu_item_id} недоступна")
        line_price = menu_item.price
        chosen_names = []
        for oid in getattr(item_data, 'modifier_option_ids', []):
            resolved = options_by_id.get(oid)
            if not resolved or resolved[1] != menu_item.id:
                raise ValueError(f"Модификатор не относится к позиции «{menu_item.name}»")
            opt = resolved[0]
            line_price += opt.price_delta
            chosen_names.append(opt.name)
        subtotal = line_price * item_data.quantity
        total += subtotal
        order_items.append(
            OrderItem(
                id=uuid.uuid4(),
                menu_item_id=menu_item.id,
                quantity=item_data.quantity,
                price=line_price,
                name=menu_item.name,
                comment=getattr(item_data, 'comment', None),
                modifiers=" · ".join(chosen_names) if chosen_names else None,
            )
        )

    # ── Discounts ────────────────────────────────────────────────────────
    # Two mutually exclusive paths: a staff-applied discount (POS) or a
    # guest promo code. Amounts are always recomputed server-side.
    subtotal = total
    discount_type = getattr(data, 'discount_type', None)
    discount_value = getattr(data, 'discount_value', None)
    promo_code_used = None

    raw_promo = (getattr(data, 'promo_code', None) or "").strip().upper()
    if raw_promo and discount_type:
        # Two discount paths at once would silently override each other —
        # make the caller pick one so the receipt is unambiguous.
        raise ValueError("Укажите либо скидку, либо промокод — не оба сразу")
    if raw_promo:
        from app.models.promo import PromoCode
        from app.models.venue import Venue as VenueModel
        network_id = (await db.execute(
            select(VenueModel.network_id).where(VenueModel.id == data.venue_id)
        )).scalar_one()
        promo = (await db.execute(
            select(PromoCode)
            .where(PromoCode.network_id == network_id, PromoCode.code == raw_promo)
            .with_for_update()
        )).scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if (not promo or not promo.active
                or (promo.expires_at is not None and promo.expires_at < now)
                or (promo.max_uses is not None and promo.used_count >= promo.max_uses)):
            raise ValueError("Промокод недействителен")
        discount_type, discount_value = promo.type, promo.value
        promo.used_count += 1
        promo_code_used = promo.code

    if discount_type:
        if discount_type not in ("percent", "amount") or not discount_value or discount_value <= 0:
            raise ValueError("Неверная скидка")
        if discount_type == "percent":
            if discount_value > 100:
                raise ValueError("Скидка не может превышать 100%")
            off = (subtotal * discount_value / Decimal("100")).quantize(Decimal("0.01"))
        else:
            off = min(discount_value, subtotal)
        total = subtotal - off

    is_walkin = guest.phone == WALKIN_MARKER
    points = 0 if is_walkin else calculate_points_earned(total)
    # Gratuity rides on top of the goods total — never folded into total_amount,
    # so revenue reporting stays clean and points are earned on goods only.
    tip_amount = getattr(data, 'tip_amount', None) or Decimal("0")
    if tip_amount < 0:
        tip_amount = Decimal("0")
    order = Order(
        id=uuid.uuid4(),
        venue_id=data.venue_id,
        guest_id=guest.id,
        status="new",
        total_amount=total,
        tip_amount=tip_amount,
        subtotal_amount=subtotal if discount_type else None,
        discount_type=discount_type,
        discount_value=discount_value,
        promo_code=promo_code_used,
        points_earned=points,
        notes=data.notes,
        table_number=table.label if table else getattr(data, 'table_number', None),
        table_id=table.id if table else None,
        source=getattr(data, 'source', None) or 'bot',
        client_order_id=getattr(data, 'client_order_id', None),
        waiter_user_id=waiter_user_id,
        waiter_name=waiter_name,
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


async def move_order_table(
    order_id: uuid.UUID,
    db: AsyncSession,
    table_id: uuid.UUID | None = None,
    table_number: str | None = None,
    changed_by: str = "staff",
) -> Order:
    """Move an active order to another table (guests changed seats, or the
    waiter picked the wrong table). Frees the old table if nothing else is
    on it and occupies the new one."""
    order = (await db.execute(
        select(Order)
        .options(selectinload(Order.items), selectinload(Order.guest))
        .where(Order.id == order_id)
        .with_for_update()
    )).scalar_one_or_none()
    if not order:
        raise ValueError("Заказ не найден")
    if order.status == "cancelled" or (order.status == "done" and order.payment_status == "paid"):
        raise ValueError("Закрытый заказ нельзя перенести")

    old_table_id = order.table_id
    if table_id:
        table = (await db.execute(
            select(Table).where(Table.id == table_id, Table.venue_id == order.venue_id)
        )).scalar_one_or_none()
        if not table:
            raise ValueError("Стол не найден в этом заведении")
        order.table_id = table.id
        order.table_number = table.label
    else:
        order.table_id = None
        # the column is String(20) — truncate rather than 500 on long input
        order.table_number = (table_number or "").strip()[:20] or None

    if old_table_id:
        await _sync_table_status(old_table_id, db)
    if order.table_id:
        await _sync_table_status(order.table_id, db)
    logger.info("Order %s moved to table %s by %s", order.id, order.table_number, changed_by)
    await db.commit()
    # commit expires ORM state — reload eagerly for response serialization
    return (await db.execute(
        select(Order).options(selectinload(Order.items), selectinload(Order.guest)).where(Order.id == order_id)
    )).scalar_one()


async def split_order(
    order_id: uuid.UUID,
    item_ids: list[uuid.UUID],
    db: AsyncSession,
    changed_by: str = "staff",
) -> tuple[Order, Order]:
    """Split selected lines into a separate order (guests at one table paying
    apart). Only for unpaid, undiscounted orders — a discount makes the money
    split ambiguous. Loyalty points move proportionally, no double credit."""
    order = (await db.execute(
        select(Order)
        .options(selectinload(Order.items), selectinload(Order.guest))
        .where(Order.id == order_id)
        .with_for_update()
    )).scalar_one_or_none()
    if not order:
        raise ValueError("Заказ не найден")
    if order.payment_status != "unpaid":
        raise ValueError("Оплаченный заказ нельзя разделить")
    if order.status == "cancelled":
        raise ValueError("Отменённый заказ нельзя разделить")
    if order.discount_type or order.promo_code:
        raise ValueError("Заказ со скидкой нельзя разделить — сначала уберите скидку")

    wanted = set(item_ids)
    moving = [i for i in order.items if i.id in wanted]
    if not moving:
        raise ValueError("Выберите позиции для отделения")
    if len(moving) == len(order.items):
        raise ValueError("Нельзя отделить все позиции — в чеке должно что-то остаться")

    new_total = sum((i.price * i.quantity for i in moving), Decimal("0"))
    old_total = order.total_amount

    # Points were credited at creation from the full total: move a
    # proportional share to the new order so a later cancellation of either
    # part reverses the right amount. The guest's balance doesn't change.
    new_points = 0
    if order.points_earned and old_total > 0:
        new_points = int(order.points_earned * new_total / old_total)

    new_order = Order(
        id=uuid.uuid4(),
        venue_id=order.venue_id,
        guest_id=order.guest_id,
        status=order.status,
        total_amount=new_total,
        points_earned=new_points,
        notes=order.notes,
        table_number=order.table_number,
        table_id=order.table_id,
        source=order.source,
    )
    db.add(new_order)
    await db.flush()
    for i in moving:
        i.order_id = new_order.id
    order.total_amount = old_total - new_total
    order.points_earned = (order.points_earned or 0) - new_points

    db.add(OrderStatusLog(
        id=uuid.uuid4(), order_id=new_order.id, old_status=None,
        new_status=order.status, changed_by=f"split:{changed_by}",
    ))
    logger.info("Order %s split by %s: %s %s moved to %s", order.id, changed_by, new_total, settings.CURRENCY, new_order.id)
    await db.commit()

    async def _reload(oid):
        return (await db.execute(
            select(Order).options(selectinload(Order.items), selectinload(Order.guest)).where(Order.id == oid)
        )).scalar_one()
    return await _reload(order.id), await _reload(new_order.id)


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


def _apply_cancellation_side_effects(order: Order, changed_by: str, db: AsyncSession) -> None:
    """Everything that must happen whenever an order becomes cancelled,
    regardless of which endpoint did it: mark paid money as refunded and
    reverse loyalty points. (Visit reversal needs a query — see callers.)"""
    # A paid order that gets cancelled means the money went back to the
    # guest. Mark it refunded so revenue, Z-reports and analytics (which all
    # filter on payment_status == "paid") stop counting it.
    if order.payment_status == "paid":
        order.payment_status = "refunded"
        db.add(OrderStatusLog(
            id=uuid.uuid4(),
            order_id=order.id,
            old_status="paid",
            new_status="refunded",
            changed_by=changed_by,
        ))
        logger.info("Order %s marked refunded on cancellation by %s", order.id, changed_by)

    guest = order.guest
    if guest and guest.phone != WALKIN_MARKER and order.points_earned and order.points_earned > 0:
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


async def _remove_visit_for_order(order: Order, db: AsyncSession) -> None:
    """Cancelled orders shouldn't count as guest visits."""
    if not order.guest or order.guest.phone == WALKIN_MARKER:
        return
    visit = (await db.execute(select(Visit).where(Visit.order_id == order.id))).scalar_one_or_none()
    if visit:
        await db.delete(visit)
        if order.guest.total_visits and order.guest.total_visits > 0:
            order.guest.total_visits -= 1


async def update_order_status(
    order_id: uuid.UUID,
    new_status: str,
    db: AsyncSession,
    changed_by: str = "staff",
) -> Order:
    """Advance the order through its logistics lifecycle. Payment is a separate
    event (see pay_order) — "done" means the order was served, nothing more."""
    # Lock the order row for the duration of the transition so two concurrent
    # requests (double-click, racing clients) can't both pass the
    # VALID_TRANSITIONS check and both trigger inventory deduction on "done".
    result = await db.execute(
        select(Order)
        .options(selectinload(Order.items), selectinload(Order.guest), selectinload(Order.venue))
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

    if new_status == "cancelled":
        _apply_cancellation_side_effects(order, changed_by, db)
        await _remove_visit_for_order(order, db)

    if order.table_id and new_status in ("done", "cancelled"):
        await _sync_table_status(order.table_id, db)

    await db.commit()
    result = await db.execute(
        select(Order).options(selectinload(Order.items), selectinload(Order.guest)).where(Order.id == order_id)
    )
    order = result.scalar_one()
    logger.info("Order %s status %s → %s by %s", order_id, old_status, new_status, changed_by)
    return order


PAYMENT_METHODS = ("cash", "card", "mobile")


async def pay_order(
    order_id: uuid.UUID,
    method: str,
    db: AsyncSession,
    changed_by: str = "staff",
    tip_amount: Decimal | None = None,
) -> Order:
    """Record payment for an order. Independent of the logistics status: a
    coffee shop takes payment before preparing, a restaurant after the meal.
    The fiscal receipt is issued here — at the moment money changes hands."""
    if method not in PAYMENT_METHODS:
        raise ValueError("Неверный способ оплаты")
    result = await db.execute(
        select(Order)
        .options(selectinload(Order.items), selectinload(Order.guest), selectinload(Order.venue))
        .where(Order.id == order_id)
        .with_for_update()
    )
    order = result.scalar_one_or_none()
    if not order:
        raise ValueError("Заказ не найден")
    if order.status == "cancelled":
        raise ValueError("Нельзя принять оплату по отменённому заказу")
    if order.payment_status == "paid":
        raise ValueError("Заказ уже оплачен")

    # A tip entered when settling an open order (table service pays at the end).
    if tip_amount is not None and tip_amount > 0:
        order.tip_amount = tip_amount
    order.payment_status = "paid"
    order.payment_method = method
    order.paid_at = datetime.now(timezone.utc)
    db.add(OrderStatusLog(
        id=uuid.uuid4(),
        order_id=order.id,
        old_status=order.status,
        new_status=f"paid:{method}",
        changed_by=changed_by,
    ))
    await issue_fiscal_check(order, order.venue)

    await db.commit()
    result = await db.execute(
        select(Order).options(selectinload(Order.items), selectinload(Order.guest)).where(Order.id == order_id)
    )
    order = result.scalar_one()
    logger.info("Order %s paid (%s) by %s", order_id, method, changed_by)
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

    _apply_cancellation_side_effects(order, changed_by, db)
    await _remove_visit_for_order(order, db)

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
