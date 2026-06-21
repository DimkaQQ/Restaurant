import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.venue import Venue
from app.routers.deps import get_current_user_dep
from app.schemas.venue import VenueCreate, VenueOut, VenueUpdate

router = APIRouter(prefix="/api/venues", tags=["venues"])
logger = logging.getLogger(__name__)


@router.get("/", response_model=list[VenueOut])
async def list_venues(
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await db.execute(select(Venue).where(Venue.network_id == current_user.network_id))
        return result.scalars().all()
    except Exception as e:
        logger.error("List venues error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка загрузки заведений")


@router.post("/", response_model=VenueOut)
async def create_venue(
    data: VenueCreate,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        if current_user.role != "owner":
            raise HTTPException(status_code=403, detail="Доступ запрещён: только для владельца")
        venue = Venue(id=uuid.uuid4(), network_id=current_user.network_id, **data.model_dump())
        db.add(venue)
        await db.commit()
        await db.refresh(venue)
        return venue
    except Exception as e:
        logger.error("Create venue error: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{venue_id}", response_model=VenueOut)
async def update_venue(
    venue_id: uuid.UUID,
    data: VenueUpdate,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        if current_user.role != "owner":
            raise HTTPException(status_code=403, detail="Доступ запрещён: только для владельца")
        result = await db.execute(
            select(Venue).where(Venue.id == venue_id, Venue.network_id == current_user.network_id)
        )
        venue = result.scalar_one_or_none()
        if not venue:
            raise HTTPException(status_code=404, detail="Заведение не найдено")
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(venue, field, value)
        await db.commit()
        await db.refresh(venue)
        return venue
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Update venue error: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
