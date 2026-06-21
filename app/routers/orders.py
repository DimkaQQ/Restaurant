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
from app.routers.deps import get_current_user_dep, get_accessible_venue_ids
from app.schemas.order import OrderCreate, OrderOut, OrderStatusUpdate
from app.services.order_service import create_order, update_order_status, get_order_with_items

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
        stmt = (
            select(Order)
            .options(selectinload(Order.items))
            .join(Venue)
            .where(Venue.network_id == current_user.network_id)
            .order_by(Order.created_at.desc())
            .limit(limit)
        )
        if venue_id:
            stmt = stmt.where(Order.venue_id == venue_id)
        if status:
            stmt = stmt.where(Order.status == status)
        if telegram_id is not None:
            stmt = stmt.join(Guest, Order.guest_id == Guest.id).where(Guest.telegram_id == telegram_id)
        result = await db.execute(stmt)
        return result.scalars().all()
    except Exception as e:
        logger.error("List orders error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка загрузки заказов")


@router.post("/", response_model=OrderOut)
async def place_order(
    data: OrderCreate,
    telegram_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        guest_result = await db.execute(select(Guest).where(Guest.telegram_id == telegram_id))
        guest = guest_result.scalar_one_or_none()
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


