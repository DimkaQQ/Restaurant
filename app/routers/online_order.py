"""Public online ordering page — accessible via QR code at table."""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.guest import Guest
from app.models.menu import MenuItem
from app.models.venue import Venue
from app.schemas.order import OrderCreate, OrderItemCreate
from app.services.order_service import create_order
from app.templates_env import templates

router = APIRouter(tags=["online_order"])
logger = logging.getLogger(__name__)


@router.get("/order/{venue_id}", response_class=HTMLResponse)
async def online_menu_page(
    request: Request,
    venue_id: uuid.UUID,
    table: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    venue = (await db.execute(
        select(Venue).where(Venue.id == venue_id, Venue.is_active == True)
    )).scalar_one_or_none()
    if not venue:
        raise HTTPException(status_code=404, detail="Заведение не найдено")

    items_result = await db.execute(
        select(MenuItem)
        .where(MenuItem.venue_id == venue_id, MenuItem.is_available == True)
        .order_by(MenuItem.category, MenuItem.name)
    )
    menu_items = items_result.scalars().all()

    categories: dict[str, list] = {}
    for item in menu_items:
        cat = item.category or "Прочее"
        categories.setdefault(cat, []).append({
            "id": str(item.id),
            "name": item.name,
            "description": item.description or "",
            "price": float(item.price),
            "image_url": item.image_url or "",
        })

    return templates.TemplateResponse("online_order.html", {
        "request": request,
        "venue": venue,
        "categories": categories,
        "table": table or "",
    })


class OnlineOrderItem(BaseModel):
    menu_item_id: uuid.UUID
    quantity: int = Field(1, ge=1)
    comment: str | None = None


class OnlineOrderSubmit(BaseModel):
    items: list[OnlineOrderItem]
    guest_name: str | None = None
    guest_phone: str | None = None
    table_number: str | None = None
    notes: str | None = None


@router.post("/order/{venue_id}/submit")
async def submit_online_order(
    venue_id: uuid.UUID,
    data: OnlineOrderSubmit,
    db: AsyncSession = Depends(get_db),
):
    venue = (await db.execute(
        select(Venue).where(Venue.id == venue_id, Venue.is_active == True)
    )).scalar_one_or_none()
    if not venue:
        raise HTTPException(status_code=404, detail="Заведение не найдено")

    if not data.items:
        raise HTTPException(status_code=400, detail="Корзина пуста")

    # Find or create guest
    guest = None
    if data.guest_phone:
        phone_clean = data.guest_phone.strip()
        guest = (await db.execute(
            select(Guest).where(Guest.phone == phone_clean, Guest.network_id == venue.network_id)
        )).scalar_one_or_none()
        if not guest:
            guest = Guest(
                id=uuid.uuid4(),
                network_id=venue.network_id,
                name=data.guest_name or "Гость",
                phone=phone_clean,
            )
            db.add(guest)
            await db.flush()
    else:
        guest = Guest(
            id=uuid.uuid4(),
            network_id=venue.network_id,
            name=data.guest_name or "Онлайн-гость",
            phone=None,
        )
        db.add(guest)
        await db.flush()

    order_data = OrderCreate(
        venue_id=venue_id,
        items=[OrderItemCreate(menu_item_id=i.menu_item_id, quantity=i.quantity, comment=i.comment) for i in data.items],
        notes=data.notes,
        table_number=data.table_number,
        source="online",
    )

    try:
        order = await create_order(order_data, guest, db, changed_by="online")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "ok": True,
        "order_id": str(order.id),
        "short_id": str(order.id)[:8].upper(),
        "total": float(order.total_amount),
        "points_earned": order.points_earned,
    }
