import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.guest import Guest
from app.models.user import User
from app.routers.deps import get_current_user_dep
from app.schemas.guest import GuestCreate, GuestOut
from app.services.ai_service import get_guest_recommendation
from app.services.order_service import WALKIN_MARKER

router = APIRouter(prefix="/api/guests", tags=["guests"])
logger = logging.getLogger(__name__)


@router.get("/", response_model=list[GuestOut])
async def list_guests(
    search: str | None = Query(None),
    limit: int = Query(50, le=200),
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        stmt = (
            select(Guest)
            .where(Guest.network_id == current_user.network_id, Guest.phone != WALKIN_MARKER)
            .order_by(Guest.total_visits.desc())
            .limit(limit)
        )
        if search:
            stmt = stmt.where(
                Guest.name.ilike(f"%{search}%") | Guest.phone.ilike(f"%{search}%")
            )
        result = await db.execute(stmt)
        return result.scalars().all()
    except Exception as e:
        logger.error("List guests error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка загрузки гостей")


@router.get("/{guest_id}", response_model=GuestOut)
async def get_guest(
    guest_id: uuid.UUID,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await db.execute(
            select(Guest).where(Guest.id == guest_id, Guest.network_id == current_user.network_id)
        )
        guest = result.scalar_one_or_none()
        if not guest:
            raise HTTPException(status_code=404, detail="Гость не найден")
        return guest
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get guest error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка загрузки гостя")


@router.post("/", response_model=GuestOut)
async def create_or_get_guest(
    data: GuestCreate,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        if data.telegram_id:
            result = await db.execute(
                select(Guest).where(Guest.telegram_id == data.telegram_id, Guest.network_id == current_user.network_id)
            )
            existing = result.scalar_one_or_none()
            if existing:
                return existing

        guest = Guest(id=uuid.uuid4(), **{**data.model_dump(), "network_id": current_user.network_id})
        db.add(guest)
        await db.commit()
        await db.refresh(guest)
        return guest
    except Exception as e:
        logger.error("Create guest error: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{guest_id}/recommendation")
async def guest_recommendation(
    guest_id: uuid.UUID,
    venue_id: uuid.UUID = Query(...),
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        # Verify guest and venue both belong to current user's network
        guest = (await db.execute(
            select(Guest).where(Guest.id == guest_id, Guest.network_id == current_user.network_id)
        )).scalar_one_or_none()
        if not guest:
            raise HTTPException(status_code=404, detail="Гость не найден")
        text = await get_guest_recommendation(guest_id, venue_id, db)
        return {"recommendation": text}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("AI recommendation error: %s", e)
        return {"recommendation": "Добро пожаловать! Рады видеть вас."}
