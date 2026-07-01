import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.guest import Guest
from app.models.order import Order
from app.models.user import User
from app.models.venue import Venue
from app.routers.bot_api import _require_bot_secret
from app.routers.deps import get_current_user_dep, get_accessible_venue_ids
from app.schemas.order import OrderCreate, OrderOut, OrderStatusUpdate
from app.services.order_service import create_order, update_order_status, cancel_order, get_order_with_items

router = APIRouter(prefix="/api/orders", tags=["orders"])
logger = logging.getLogger(__name__)


@router.get("/live", response_model=list[OrderOut])
async def live_orders(
    venue_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        accessible_ids = await get_accessible_venue_ids(current_user, db)
        filter_ids = [venue_id] if venue_id and venue_id in accessible_ids else accessible_ids
        stmt = (
            select(Order)
            .options(selectinload(Order.items), selectinload(Order.guest))
            .where(Order.venue_id.in_(filter_ids), Order.status.in_(["new", "confirmed", "preparing", "ready"]))
            .order_by(Order.created_at.desc())
        )
        result = await db.execute(stmt)
        return result.scalars().all()
    except Exception as e:
        logger.error("Live orders error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка загрузки заказов")


@router.get("/", response_model=list[OrderOut])
async def list_orders(
    venue_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    telegram_id: int | None = Query(None),
    limit: int = Query(50, le=200),
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        accessible_ids = await get_accessible_venue_ids(current_user, db)
        filter_ids = [venue_id] if venue_id and venue_id in accessible_ids else accessible_ids
        stmt = (
            select(Order)
            .options(selectinload(Order.items))
            .where(Order.venue_id.in_(filter_ids))
            .order_by(Order.created_at.desc())
            .limit(limit)
        )
        if status:
            stmt = stmt.where(Order.status == status)
        if telegram_id is not None:
            stmt = stmt.join(Guest, Order.guest_id == Guest.id).where(Guest.telegram_id == telegram_id)
        result = await db.execute(stmt)
        return result.scalars().all()
    except Exception as e:
        logger.error("List orders error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка загрузки заказов")


@router.get("/guest/history", response_model=list[OrderOut], dependencies=[Depends(_require_bot_secret)])
async def guest_order_history(
    telegram_id: int = Query(...),
    network_id: uuid.UUID = Query(...),
    limit: int = Query(10, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Bot-internal endpoint (shared-secret gated) — returns a guest's order
    history scoped to one network, by telegram_id."""
    try:
        stmt = (
            select(Order)
            .options(selectinload(Order.items))
            .join(Guest, Order.guest_id == Guest.id)
            .where(Guest.telegram_id == telegram_id, Guest.network_id == network_id)
            .order_by(Order.created_at.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        return result.scalars().all()
    except Exception as e:
        logger.error("Guest history error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка загрузки истории")


@router.post("/", response_model=OrderOut)
async def place_order(
    data: OrderCreate,
    telegram_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        venue = (await db.execute(select(Venue).where(Venue.id == data.venue_id))).scalar_one_or_none()
        if not venue:
            raise HTTPException(status_code=404, detail="Заведение не найдено")
        # Resolve the guest within the venue's own network — the same Telegram
        # account can have a separate Guest row per network, so a bare
        # telegram_id lookup would be ambiguous (and could match a guest of an
        # unrelated network) without this scope.
        guest = (await db.execute(
            select(Guest).where(Guest.telegram_id == telegram_id, Guest.network_id == venue.network_id)
        )).scalar_one_or_none()
        if not guest:
            raise HTTPException(status_code=404, detail="Гость не найден")
        order = await create_order(data, guest, db)
        return order
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Place order error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка создания заказа")


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(
    order_id: uuid.UUID,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await db.execute(
            select(Order)
            .options(selectinload(Order.items), selectinload(Order.guest))
            .join(Venue)
            .where(Order.id == order_id, Venue.network_id == current_user.network_id)
        )
        order = result.scalar_one_or_none()
        if not order:
            raise HTTPException(status_code=404, detail="Заказ не найден")
        return order
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get order error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка загрузки заказа")


@router.patch("/{order_id}/status", response_model=OrderOut)
async def change_order_status(
    order_id: uuid.UUID,
    data: OrderStatusUpdate,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        # Verify order belongs to current user's network before mutating
        check = (await db.execute(
            select(Order).join(Venue).where(Order.id == order_id, Venue.network_id == current_user.network_id)
        )).scalar_one_or_none()
        if not check:
            raise HTTPException(status_code=404, detail="Заказ не найден")
        order = await update_order_status(order_id, data.status, db, changed_by=current_user.email)
        return order
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Status update error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка обновления статуса")


@router.post("/{order_id}/cancel", response_model=OrderOut)
async def cancel_order_endpoint(
    order_id: uuid.UUID,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Staff can always cancel; guests get 10-min window via bot."""
    try:
        # Verify order belongs to current user's network before mutating
        check = (await db.execute(
            select(Order).join(Venue).where(Order.id == order_id, Venue.network_id == current_user.network_id)
        )).scalar_one_or_none()
        if not check:
            raise HTTPException(status_code=404, detail="Заказ не найден")
        order = await cancel_order(order_id, db, changed_by=current_user.email, allow_always=True)
        return order
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Cancel order error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка отмены заказа")


@router.post("/{order_id}/cancel/guest", response_model=OrderOut)
async def guest_cancel_order(
    order_id: uuid.UUID,
    telegram_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint — guest self-cancel within 10 min."""
    try:
        # Match the order's actual guest by telegram_id directly (a standalone
        # Guest lookup by telegram_id alone is ambiguous now that the same
        # Telegram account can have a separate Guest row per network).
        guest_id = (await db.execute(
            select(Guest.id)
            .join(Order, Order.guest_id == Guest.id)
            .where(Order.id == order_id, Guest.telegram_id == telegram_id)
        )).scalar_one_or_none()
        if not guest_id:
            raise HTTPException(status_code=404, detail="Заказ не найден")
        # Pass guest_id into cancel_order so ownership is checked atomically — no TOCTOU
        order = await cancel_order(order_id, db, changed_by=f"guest:{telegram_id}", allow_always=False, guest_id=guest_id)
        return order
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Guest cancel error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка отмены заказа")

