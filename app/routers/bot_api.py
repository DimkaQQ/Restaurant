import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.broadcast import Broadcast
from app.models.guest import Guest
from app.models.menu import MenuItem
from app.models.order import Order, OrderItem
from app.models.review import Review
from app.models.user import User
from app.models.venue import Venue
from app.schemas.venue import VenueOut
from app.services.auth_service import verify_password
from app.services.order_service import create_order
from app.schemas.order import OrderCreate, OrderItemCreate

router = APIRouter(prefix="/api/bot", tags=["bot"])
logger = logging.getLogger(__name__)


# ── Guest endpoints ──────────────────────────────────────────────────────────

@router.get("/guest/{telegram_id}")
async def get_bot_guest(telegram_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    guest = (await db.execute(select(Guest).where(Guest.telegram_id == telegram_id))).scalar_one_or_none()
    if not guest:
        raise HTTPException(status_code=404, detail="Гость не найден")
    return {
        "id": str(guest.id),
        "network_id": str(guest.network_id),
        "telegram_id": guest.telegram_id,
        "name": guest.name,
        "phone": guest.phone,
        "total_points": guest.total_points,
        "total_visits": guest.total_visits,
        "language": guest.language or "ru",
        "preferred_venue_id": str(guest.preferred_venue_id) if guest.preferred_venue_id else None,
    }


class GuestCreate(BaseModel):
    network_id: uuid.UUID
    telegram_id: int
    name: str | None = None
    phone: str | None = None
    language: str = "ru"


@router.post("/guest")
async def create_bot_guest(data: GuestCreate, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    existing = (await db.execute(select(Guest).where(Guest.telegram_id == data.telegram_id))).scalar_one_or_none()
    if existing:
        # Update language if provided
        if data.language and data.language != existing.language:
            existing.language = data.language
        if data.name and not existing.name:
            existing.name = data.name
        if data.phone and not existing.phone:
            existing.phone = data.phone
        await db.commit()
        await db.refresh(existing)
        guest = existing
    else:
        guest = Guest(
            id=uuid.uuid4(),
            network_id=data.network_id,
            telegram_id=data.telegram_id,
            name=data.name,
            phone=data.phone,
            language=data.language,
        )
        db.add(guest)
        await db.commit()
        await db.refresh(guest)

    return {
        "id": str(guest.id),
        "network_id": str(guest.network_id),
        "telegram_id": guest.telegram_id,
        "name": guest.name,
        "phone": guest.phone,
        "total_points": guest.total_points,
        "total_visits": guest.total_visits,
        "language": guest.language or "ru",
        "preferred_venue_id": str(guest.preferred_venue_id) if guest.preferred_venue_id else None,
    }


class GuestPatch(BaseModel):
    language: str | None = None
    preferred_venue_id: uuid.UUID | None = None


@router.patch("/guest/{telegram_id}")
async def bot_update_guest(telegram_id: int, data: GuestPatch, db: AsyncSession = Depends(get_db)):
    guest = (await db.execute(select(Guest).where(Guest.telegram_id == telegram_id))).scalar_one_or_none()
    if not guest:
        raise HTTPException(status_code=404, detail="Гость не найден")
    if data.language is not None:
        guest.language = data.language
    if data.preferred_venue_id is not None:
        guest.preferred_venue_id = data.preferred_venue_id
    await db.commit()
    return {"ok": True, "language": guest.language, "preferred_venue_id": str(guest.preferred_venue_id) if guest.preferred_venue_id else None}


# ── Venue / menu endpoints ───────────────────────────────────────────────────

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
        for item in result.scalars().all()
    ]


# ── Staff endpoints ──────────────────────────────────────────────────────────

@router.get("/staff/{telegram_id}")
async def get_bot_staff(telegram_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    user = (await db.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    return {
        "id": str(user.id),
        "email": user.email,
        "role": user.role,
        "network_id": str(user.network_id),
        "venue_id": str(user.venue_id) if user.venue_id else None,
    }


class StaffLinkRequest(BaseModel):
    token: str
    telegram_id: int
    telegram_name: str | None = None


@router.post("/staff/link")
async def link_staff_bot(data: StaffLinkRequest, db: AsyncSession = Depends(get_db)):
    """Link a staff user's Telegram account via one-time token from dashboard."""
    user = (await db.execute(select(User).where(User.bot_link_token == data.token))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Токен недействителен или уже использован")
    # Check if telegram_id already taken
    existing = (await db.execute(select(User).where(User.telegram_id == data.telegram_id))).scalar_one_or_none()
    if existing and existing.id != user.id:
        raise HTTPException(status_code=409, detail="Этот Telegram аккаунт уже привязан")
    user.telegram_id = data.telegram_id
    user.bot_link_token = None  # consume token
    await db.commit()
    return {
        "ok": True,
        "role": user.role,
        "email": user.email,
        "venue_id": str(user.venue_id) if user.venue_id else None,
    }


class StaffLoginRequest(BaseModel):
    email: str
    password: str
    telegram_id: int


@router.post("/staff/login")
async def staff_bot_login(data: StaffLoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate staff via email/password and link Telegram account."""
    user = (await db.execute(select(User).where(User.email == data.email))).scalar_one_or_none()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    existing = (await db.execute(select(User).where(User.telegram_id == data.telegram_id))).scalar_one_or_none()
    if existing and existing.id != user.id:
        raise HTTPException(status_code=409, detail="Этот Telegram аккаунт уже привязан к другому сотруднику")
    user.telegram_id = data.telegram_id
    await db.commit()
    return {
        "ok": True,
        "role": user.role,
        "email": user.email,
        "network_id": str(user.network_id),
        "venue_id": str(user.venue_id) if user.venue_id else None,
    }


class StaffOrderItemCreate(BaseModel):
    menu_item_id: uuid.UUID
    quantity: int = 1
    comment: str | None = None


class StaffOrderCreate(BaseModel):
    venue_id: uuid.UUID
    items: list[StaffOrderItemCreate]
    table_number: str | None = None
    notes: str | None = None
    guest_phone: str | None = None
    guest_name: str | None = None


@router.post("/staff/order")
async def create_staff_order(
    data: StaffOrderCreate,
    telegram_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Staff creates order for a table. Guest is found/created by phone or anonymous."""
    staff = (await db.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
    if not staff:
        raise HTTPException(status_code=403, detail="Не авторизован как сотрудник")

    # Find or create guest
    guest = None
    if data.guest_phone:
        guest = (await db.execute(select(Guest).where(Guest.phone == data.guest_phone, Guest.network_id == staff.network_id))).scalar_one_or_none()

    if not guest:
        guest = Guest(
            id=uuid.uuid4(),
            network_id=staff.network_id,
            name=data.guest_name or "Гость",
            phone=data.guest_phone,
        )
        db.add(guest)
        await db.flush()

    order_data = OrderCreate(
        venue_id=data.venue_id,
        items=[OrderItemCreate(menu_item_id=i.menu_item_id, quantity=i.quantity, comment=i.comment) for i in data.items],
        notes=data.notes,
        table_number=data.table_number,
        source="staff",
    )

    try:
        order = await create_order(order_data, guest, db, changed_by=staff.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "id": str(order.id),
        "table_number": order.table_number,
        "total_amount": float(order.total_amount),
        "status": order.status,
    }


# ── Staff active orders ──────────────────────────────────────────────────────

@router.get("/staff/orders/active")
async def staff_active_orders(
    telegram_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    staff = (await db.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
    if not staff:
        raise HTTPException(status_code=403, detail="Не авторизован как сотрудник")

    stmt = select(Order, Guest, Venue).join(Guest, Guest.id == Order.guest_id).join(Venue, Venue.id == Order.venue_id).where(
        Venue.network_id == staff.network_id,
        Order.status.in_(["new", "confirmed", "preparing", "ready"]),
    )
    if staff.venue_id:
        stmt = stmt.where(Order.venue_id == staff.venue_id)
    stmt = stmt.order_by(Order.created_at.desc()).limit(20)

    rows = (await db.execute(stmt)).all()
    return [
        {
            "id": str(o.id),
            "short_id": str(o.id)[:8].upper(),
            "table": o.table_number or "—",
            "status": o.status,
            "total": float(o.total_amount),
            "guest": g.name or g.phone or "Гость",
            "venue": v.name,
            "age_min": int((datetime.now(timezone.utc) - o.created_at.replace(tzinfo=timezone.utc)).total_seconds() / 60),
        }
        for o, g, v in rows
    ]


# ── Broadcasts ───────────────────────────────────────────────────────────────

@router.get("/broadcasts")
async def get_broadcasts(
    network_id: uuid.UUID,
    lang: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    result = await db.execute(
        select(Broadcast).where(Broadcast.network_id == network_id, Broadcast.sent_at == None)
    )
    broadcasts = result.scalars().all()

    now = datetime.now(timezone.utc)
    output = []
    for b in broadcasts:
        if b.lang_filter is not None and lang is not None and b.lang_filter != lang:
            continue
        b.sent_at = now
        b.sent_count += 1
        output.append({"id": str(b.id), "message": b.message, "lang_filter": b.lang_filter})

    if output:
        await db.commit()
    return output


@router.get("/guest-ids")
async def get_guest_telegram_ids(network_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[int]:
    result = await db.execute(
        select(Guest.telegram_id).where(Guest.network_id == network_id, Guest.telegram_id != None)
    )
    return [row[0] for row in result.all()]


# ── Reviews ──────────────────────────────────────────────────────────────────

class ReviewCreate(BaseModel):
    order_id: uuid.UUID
    guest_telegram_id: int
    overall_rating: int
    comment: str | None = None


@router.post("/review")
async def submit_review(data: ReviewCreate, db: AsyncSession = Depends(get_db)):
    guest = (await db.execute(select(Guest).where(Guest.telegram_id == data.guest_telegram_id))).scalar_one_or_none()
    if not guest:
        raise HTTPException(status_code=404, detail="Гость не найден")

    order = (await db.execute(
        select(Order).where(Order.id == data.order_id, Order.guest_id == guest.id)
    )).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    venue = (await db.execute(select(Venue).where(Venue.id == order.venue_id))).scalar_one_or_none()

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
