"""Cash register shifts: open with a counted drawer float, close with a
recount. The close computes a Z-report (cash/card sales during the shift,
expected drawer, difference) and snapshots it immutably."""
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.cash_shift import CashShift
from app.models.order import Order
from app.models.user import User
from app.routers.deps import get_current_user_dep, get_accessible_venue_ids

router = APIRouter(prefix="/api/cash-shifts", tags=["cash-shifts"])
logger = logging.getLogger(__name__)


class OpenShiftIn(BaseModel):
    venue_id: uuid.UUID
    opening_cash: Decimal = Field(0, ge=0)


class CloseShiftIn(BaseModel):
    closing_cash_actual: Decimal = Field(..., ge=0)
    notes: str | None = None


def _shift_out(s: CashShift) -> dict:
    return {
        "id": str(s.id),
        "venue_id": str(s.venue_id),
        "opened_by": s.opened_by,
        "opening_cash": float(s.opening_cash),
        "opened_at": s.opened_at.isoformat() if s.opened_at else None,
        "closed_by": s.closed_by,
        "closed_at": s.closed_at.isoformat() if s.closed_at else None,
        "closing_cash_actual": float(s.closing_cash_actual) if s.closing_cash_actual is not None else None,
        "cash_sales": float(s.cash_sales) if s.cash_sales is not None else None,
        "card_sales": float(s.card_sales) if s.card_sales is not None else None,
        "orders_count": s.orders_count,
        "expected_cash": float(s.expected_cash) if s.expected_cash is not None else None,
        "difference": float(s.difference) if s.difference is not None else None,
        "notes": s.notes,
    }


async def _check_venue(venue_id: uuid.UUID, user: User, db: AsyncSession) -> None:
    accessible = await get_accessible_venue_ids(user, db)
    if venue_id not in accessible:
        raise HTTPException(status_code=403, detail="Нет доступа к этому заведению")


@router.get("/current")
async def current_shift(
    venue_id: uuid.UUID = Query(...),
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    await _check_venue(venue_id, current_user, db)
    shift = (await db.execute(
        select(CashShift).where(CashShift.venue_id == venue_id, CashShift.closed_at.is_(None))
    )).scalar_one_or_none()
    return {"shift": _shift_out(shift) if shift else None}


@router.post("/open")
async def open_shift(
    data: OpenShiftIn,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    await _check_venue(data.venue_id, current_user, db)
    existing = (await db.execute(
        select(CashShift)
        .where(CashShift.venue_id == data.venue_id, CashShift.closed_at.is_(None))
        .with_for_update()
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Смена уже открыта")
    shift = CashShift(
        id=uuid.uuid4(), venue_id=data.venue_id,
        opened_by=current_user.email, opening_cash=data.opening_cash,
    )
    db.add(shift)
    await db.commit()
    await db.refresh(shift)
    logger.info("Cash shift opened at venue %s by %s", data.venue_id, current_user.email)
    return {"shift": _shift_out(shift)}


@router.post("/{shift_id}/close")
async def close_shift(
    shift_id: uuid.UUID,
    data: CloseShiftIn,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    shift = (await db.execute(
        select(CashShift).where(CashShift.id == shift_id).with_for_update()
    )).scalar_one_or_none()
    if not shift:
        raise HTTPException(status_code=404, detail="Смена не найдена")
    await _check_venue(shift.venue_id, current_user, db)
    if shift.closed_at is not None:
        raise HTTPException(status_code=400, detail="Смена уже закрыта")

    now = datetime.now(timezone.utc)

    async def _sales(method: str) -> Decimal:
        return (await db.execute(
            select(func.coalesce(func.sum(Order.total_amount), 0)).where(
                Order.venue_id == shift.venue_id,
                Order.payment_status == "paid",
                Order.payment_method == method,
                Order.paid_at >= shift.opened_at,
                Order.paid_at <= now,
            )
        )).scalar() or Decimal("0")

    cash_sales = await _sales("cash")
    card_sales = (await _sales("card")) + (await _sales("mobile"))
    orders_count = (await db.execute(
        select(func.count(Order.id)).where(
            Order.venue_id == shift.venue_id,
            Order.payment_status == "paid",
            Order.paid_at >= shift.opened_at,
            Order.paid_at <= now,
        )
    )).scalar() or 0

    shift.closed_by = current_user.email
    shift.closed_at = now
    shift.closing_cash_actual = data.closing_cash_actual
    shift.notes = data.notes
    shift.cash_sales = cash_sales
    shift.card_sales = card_sales
    shift.orders_count = orders_count
    shift.expected_cash = shift.opening_cash + cash_sales
    shift.difference = data.closing_cash_actual - shift.expected_cash
    await db.commit()
    await db.refresh(shift)
    logger.info(
        "Cash shift %s closed by %s: expected=%s actual=%s diff=%s",
        shift_id, current_user.email, shift.expected_cash, shift.closing_cash_actual, shift.difference,
    )
    return {"shift": _shift_out(shift)}


@router.get("")
async def list_shifts(
    venue_id: uuid.UUID | None = Query(None),
    limit: int = Query(30, le=100),
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    accessible = await get_accessible_venue_ids(current_user, db)
    filter_ids = [venue_id] if venue_id and venue_id in accessible else accessible
    shifts = (await db.execute(
        select(CashShift)
        .where(CashShift.venue_id.in_(filter_ids))
        .order_by(CashShift.opened_at.desc())
        .limit(limit)
    )).scalars().all()
    return {"shifts": [_shift_out(s) for s in shifts]}
