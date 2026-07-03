"""Public read-only API v1, authenticated by X-API-Key. For integrations:
delivery aggregators, BI tools, custom dashboards. Keys are managed by the
owner in Settings → API; only the sha256 hash is stored server-side."""
import hashlib
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.api_key import ApiKey
from app.models.menu import MenuItem, ModifierGroup
from app.models.order import Order
from app.models.venue import Venue

router = APIRouter(prefix="/api/v1", tags=["public-api"])
logger = logging.getLogger(__name__)


async def get_network_from_api_key(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> uuid.UUID:
    key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()
    key = (await db.execute(
        select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.active == True)  # noqa: E712
    )).scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    key.last_used_at = datetime.now(timezone.utc)
    await db.commit()
    return key.network_id


@router.get("/venues")
async def api_venues(
    network_id: uuid.UUID = Depends(get_network_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    venues = (await db.execute(
        select(Venue).where(Venue.network_id == network_id).order_by(Venue.name)
    )).scalars().all()
    return {"venues": [
        {"id": str(v.id), "name": v.name, "address": v.address, "is_active": v.is_active}
        for v in venues
    ]}


@router.get("/menu")
async def api_menu(
    venue_id: uuid.UUID = Query(...),
    network_id: uuid.UUID = Depends(get_network_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    venue = (await db.execute(
        select(Venue).where(Venue.id == venue_id, Venue.network_id == network_id)
    )).scalar_one_or_none()
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    items = (await db.execute(
        select(MenuItem)
        .options(selectinload(MenuItem.modifier_groups).selectinload(ModifierGroup.options))
        .where(MenuItem.venue_id == venue_id)
        .order_by(MenuItem.category, MenuItem.name)
    )).scalars().all()
    return {"items": [
        {
            "id": str(i.id), "name": i.name, "description": i.description,
            "price": float(i.price), "category": i.category, "is_available": i.is_available,
            "modifier_groups": [
                {
                    "id": str(g.id), "name": g.name, "required": g.required, "multi": g.multi,
                    "options": [
                        {"id": str(o.id), "name": o.name, "price_delta": float(o.price_delta)}
                        for o in g.options
                    ],
                }
                for g in i.modifier_groups
            ],
        }
        for i in items
    ]}


@router.get("/orders")
async def api_orders(
    venue_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, le=200),
    network_id: uuid.UUID = Depends(get_network_from_api_key),
    db: AsyncSession = Depends(get_db),
):
    venue_ids = [row[0] for row in (await db.execute(
        select(Venue.id).where(Venue.network_id == network_id)
    )).all()]
    filter_ids = [venue_id] if venue_id and venue_id in venue_ids else venue_ids
    stmt = (
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.venue_id.in_(filter_ids))
        .order_by(Order.created_at.desc())
        .limit(limit)
    )
    if status:
        stmt = stmt.where(Order.status == status)
    orders = (await db.execute(stmt)).scalars().all()
    return {"orders": [
        {
            "id": str(o.id), "venue_id": str(o.venue_id), "status": o.status,
            "payment_status": o.payment_status, "payment_method": o.payment_method,
            "total_amount": float(o.total_amount),
            "table_number": o.table_number, "source": o.source,
            "created_at": o.created_at.isoformat(),
            "paid_at": o.paid_at.isoformat() if o.paid_at else None,
            "items": [
                {"name": i.name, "quantity": i.quantity, "price": float(i.price), "modifiers": i.modifiers}
                for i in o.items
            ],
        }
        for o in orders
    ]}
