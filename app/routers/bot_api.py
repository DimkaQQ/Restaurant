import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.broadcast import Broadcast
from app.models.guest import Guest
from app.models.menu import MenuItem
from app.models.venue import Venue
from app.schemas.venue import VenueOut

router = APIRouter(prefix="/api/bot", tags=["bot"])
logger = logging.getLogger(__name__)


class GuestPatch(BaseModel):
    language: str | None = None
    preferred_venue_id: uuid.UUID | None = None


@router.get("/venues", response_model=list[VenueOut])
async def bot_venues(network_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Venue)
        .where(Venue.network_id == network_id, Venue.is_active == True)
        .order_by(Venue.city, Venue.name)
    )
    return result.scalars().all()


@router.get("/menu")
async def bot_menu(venue_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    result = await db.execute(
        select(MenuItem)
        .where(MenuItem.venue_id == venue_id, MenuItem.is_available == True)
        .order_by(MenuItem.category, MenuItem.name)
    )
    items = result.scalars().all()
    return [
        {
            "id": str(item.id),
            "name": item.name,
            "description": item.description,
            "price": float(item.price),
            "category": item.category,
            "is_available": item.is_available,
            "image_url": item.image_url,
        }
        for item in items
    ]


@router.patch("/guest/{telegram_id}")
async def bot_update_guest(
    telegram_id: int,
    data: GuestPatch,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Guest).where(Guest.telegram_id == telegram_id))
    guest = result.scalar_one_or_none()
    if not guest:
        raise HTTPException(status_code=404, detail="Гость не найден")
    if data.language is not None:
        guest.language = data.language
    if data.preferred_venue_id is not None:
        guest.preferred_venue_id = data.preferred_venue_id
    await db.commit()
    await db.refresh(guest)
    return {"id": str(guest.id), "language": guest.language, "preferred_venue_id": str(guest.preferred_venue_id) if guest.preferred_venue_id else None}


@router.get("/broadcasts")
async def get_broadcasts(
    network_id: uuid.UUID,
    lang: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    stmt = select(Broadcast).where(
        Broadcast.network_id == network_id,
        Broadcast.sent_at == None,
    )
    result = await db.execute(stmt)
    broadcasts = result.scalars().all()

    now = datetime.now(timezone.utc)
    output = []
    for b in broadcasts:
        if b.lang_filter is not None and lang is not None and b.lang_filter != lang:
            continue
        b.sent_at = now
        b.sent_count += 1
        output.append({
            "id": str(b.id),
            "message": b.message,
            "lang_filter": b.lang_filter,
        })

    if output:
        await db.commit()

    return output


@router.get("/guest-ids")
async def get_guest_telegram_ids(
    network_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[int]:
    result = await db.execute(
        select(Guest.telegram_id)
        .where(Guest.network_id == network_id, Guest.telegram_id != None)
    )
    return [row[0] for row in result.all()]
