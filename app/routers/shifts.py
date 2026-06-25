from app.templates_env import templates
import logging
import uuid
from datetime import datetime, timezone, date, timedelta, time

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.shift import Shift
from app.models.staff import Staff
from app.models.venue import Venue
from app.models.user import User
from app.routers.deps import get_current_user_dep, get_accessible_venue_ids

router = APIRouter(tags=["shifts"])
logger = logging.getLogger(__name__)


class ShiftCreate(BaseModel):
    staff_id: uuid.UUID
    venue_id: uuid.UUID
    shift_date: date
    start_time: time
    end_time: time
    notes: str | None = None


class ShiftStatusUpdate(BaseModel):
    status: str


@router.get("/shifts", response_class=HTMLResponse)
async def shifts_page(
    request: Request,
    venue_id: uuid.UUID | None = Query(None),
    week_offset: int = Query(0),
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        accessible_ids = await get_accessible_venue_ids(current_user, db)
        venues = (await db.execute(
            select(Venue).where(Venue.id.in_(accessible_ids), Venue.is_active == True).order_by(Venue.name)
        )).scalars().all()

        filter_ids = [venue_id] if venue_id and venue_id in accessible_ids else accessible_ids
        selected_venue_id = str(venue_id) if venue_id and venue_id in accessible_ids else ""

        # Week range
        today = datetime.now(timezone.utc).date()
        week_start = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
        week_days = [week_start + timedelta(days=i) for i in range(7)]

        # Shifts for the week
        shifts = (await db.execute(
            select(Shift)
            .options(selectinload(Shift.staff), selectinload(Shift.venue))
            .where(
                Shift.venue_id.in_(filter_ids),
                Shift.shift_date >= week_days[0],
                Shift.shift_date <= week_days[-1],
            )
            .order_by(Shift.shift_date, Shift.start_time)
        )).scalars().all()

        # Group by date
        shifts_by_day: dict[date, list] = {d: [] for d in week_days}
        for s in shifts:
            if s.shift_date in shifts_by_day:
                shifts_by_day[s.shift_date].append(s)

        # All staff for the modal
        all_staff = (await db.execute(
            select(Staff)
            .where(Staff.venue_id.in_(filter_ids), Staff.is_active == True)
            .options(selectinload(Staff.venue))
            .order_by(Staff.name)
        )).scalars().all()

        # Today's working staff count
        today_shifts = shifts_by_day.get(today, [])
        active_today = [s for s in today_shifts if s.status in ("planned", "active")]

        return templates.TemplateResponse("shifts.html", {
            "request": request,
            "user": current_user,
            "venues": venues,
            "selected_venue_id": selected_venue_id,
            "week_days": week_days,
            "shifts_by_day": shifts_by_day,
            "today": today,
            "week_offset": week_offset,
            "all_staff": all_staff,
            "active_today_count": len(active_today),
        })
    except Exception as e:
        logger.error("Shifts page error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка загрузки смен")


@router.post("/api/shifts")
async def create_shift(
    data: ShiftCreate,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        accessible_ids = await get_accessible_venue_ids(current_user, db)
        if data.venue_id not in accessible_ids:
            raise HTTPException(status_code=403, detail="Нет доступа к заведению")

        # Verify staff belongs to the target venue specifically
        staff = (await db.execute(
            select(Staff).where(Staff.id == data.staff_id, Staff.venue_id == data.venue_id)
        )).scalar_one_or_none()
        if not staff:
            raise HTTPException(status_code=404, detail="Сотрудник не найден или не принадлежит этому заведению")

        if data.end_time <= data.start_time:
            raise HTTPException(status_code=400, detail="Время окончания должно быть позже начала")

        shift = Shift(id=uuid.uuid4(), **data.model_dump())
        db.add(shift)
        await db.commit()
        return {"id": str(shift.id)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Create shift error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка создания смены")


@router.patch("/api/shifts/{shift_id}")
async def update_shift_status(
    shift_id: uuid.UUID,
    data: ShiftStatusUpdate,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        if data.status not in ("planned", "active", "done", "cancelled"):
            raise HTTPException(status_code=400, detail="Неверный статус")

        accessible_ids = await get_accessible_venue_ids(current_user, db)
        shift = (await db.execute(
            select(Shift).where(Shift.id == shift_id, Shift.venue_id.in_(accessible_ids))
        )).scalar_one_or_none()
        if not shift:
            raise HTTPException(status_code=404, detail="Смена не найдена")

        shift.status = data.status
        await db.commit()
        return {"status": shift.status}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Update shift error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка обновления смены")


@router.delete("/api/shifts/{shift_id}")
async def delete_shift(
    shift_id: uuid.UUID,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        accessible_ids = await get_accessible_venue_ids(current_user, db)
        shift = (await db.execute(
            select(Shift).where(Shift.id == shift_id, Shift.venue_id.in_(accessible_ids))
        )).scalar_one_or_none()
        if not shift:
            raise HTTPException(status_code=404, detail="Смена не найдена")
        await db.delete(shift)
        await db.commit()
        return {"message": "Удалено"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Delete shift error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка удаления смены")
