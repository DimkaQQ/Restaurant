import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.broadcast import Broadcast
from app.models.guest import Guest
from app.models.menu import MenuItem
from app.models.order import Order
from app.models.review import Review
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


class ReviewCreate(BaseModel):
    order_id: uuid.UUID
    guest_telegram_id: int
    overall_rating: int  # 1-5
    comment: str | None = None


@router.post("/review")
async def submit_review(data: ReviewCreate, db: AsyncSession = Depends(get_db)):
    # 1. Find guest by telegram_id
    guest_result = await db.execute(select(Guest).where(Guest.telegram_id == data.guest_telegram_id))
    guest = guest_result.scalar_one_or_none()
    if not guest:
        raise HTTPException(status_code=404, detail="Гость не найден")

    # 2. Find order, verify it belongs to guest
    order_result = await db.execute(
        select(Order).where(Order.id == data.order_id, Order.guest_id == guest.id)
    )
    order = order_result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    # 3. Get venue for gis_url
    venue_result = await db.execute(select(Venue).where(Venue.id == order.venue_id))
    venue = venue_result.scalar_one_or_none()

    # 4. Create Review record
    review = Review(
        id=uuid.uuid4(),
        venue_id=order.venue_id,
        order_id=order.id,
        guest_id=guest.id,
        overall_rating=max(1, min(5, data.overall_rating)),
        comment=data.comment,
        source="bot",
    )
    db.add(review)

    # 5. Award +50 points to guest
    guest.total_points = (guest.total_points or 0) + 50

    await db.commit()

    return {
        "ok": True,
        "venue_gis_url": venue.gis_url if venue else None,
        "venue_name": venue.name if venue else None,
        "venue_id": str(venue.id) if venue else None,
        "manager_telegram_id": venue.manager_telegram_id if venue else None,
        "points_awarded": 50,
    }


@router.get("/orders-for-review")
async def orders_needing_review(
    network_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    cutoff_min = now - timedelta(minutes=30)
    cutoff_max = now - timedelta(hours=24)

    # Find orders: status=done, review_sent_at IS NULL, 30min..24h ago, guest has telegram_id
    stmt = (
        select(Order, Guest, Venue)
        .join(Guest, Guest.id == Order.guest_id)
        .join(Venue, Venue.id == Order.venue_id)
        .where(
            Venue.network_id == network_id,
            Order.status == "done",
            Order.review_sent_at == None,
            Order.created_at <= cutoff_min,
            Order.created_at >= cutoff_max,
            Guest.telegram_id != None,
        )
    )
    rows = (await db.execute(stmt)).all()

    output = []
    for order, guest, venue in rows:
        order.review_sent_at = now
        output.append({
            "order_id": str(order.id),
            "guest_telegram_id": guest.telegram_id,
            "venue_name": venue.name,
            "guest_name": guest.name or "",
            "guest_lang": guest.language or "ru",
        })

    if output:
        await db.commit()

    return output
