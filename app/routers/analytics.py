import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.templating import Jinja2Templates

from app.database import get_db
from app.models.guest import Guest
from app.models.order import Order, OrderItem
from app.models.user import User
from app.models.venue import Venue
from app.routers.deps import get_current_user_dep

router = APIRouter(prefix="/analytics", tags=["analytics"])
logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def analytics_page(
    request: Request,
    venue_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        now = datetime.now(timezone.utc)
        thirty_days_ago = now - timedelta(days=30)

        all_venues = (await db.execute(
            select(Venue)
            .where(Venue.network_id == current_user.network_id, Venue.is_active == True)
            .order_by(Venue.name)
        )).scalars().all()

        # Determine which venue IDs to query
        if venue_id:
            venue_ids = [venue_id]
            selected_venue = next((v for v in all_venues if v.id == venue_id), None)
        else:
            venue_ids = [v.id for v in all_venues]
            selected_venue = None

        revenue_rows = (await db.execute(
            select(cast(Order.created_at, Date).label("day"), func.sum(Order.total_amount).label("revenue"))
            .where(
                Order.venue_id.in_(venue_ids),
                Order.status == "done",
                Order.created_at >= thirty_days_ago,
            )
            .group_by("day")
            .order_by("day")
        )).all()
        revenue_data = [{"day": str(r.day), "revenue": float(r.revenue)} for r in revenue_rows]

        top_items = (await db.execute(
            select(OrderItem.name, func.sum(OrderItem.quantity).label("total_qty"))
            .join(Order)
            .where(Order.venue_id.in_(venue_ids), Order.status == "done")
            .group_by(OrderItem.name)
            .order_by(func.sum(OrderItem.quantity).desc())
            .limit(10)
        )).all()
        top_items_data = [{"name": r.name, "qty": int(r.total_qty)} for r in top_items]

        loyal_guests = (await db.execute(
            select(Guest)
            .where(Guest.network_id == current_user.network_id)
            .order_by(Guest.total_visits.desc())
            .limit(10)
        )).scalars().all()

        venue_revenue = (await db.execute(
            select(Venue.name, func.sum(Order.total_amount).label("revenue"))
            .join(Order, Order.venue_id == Venue.id)
            .where(Order.venue_id.in_(venue_ids), Order.status == "done")
            .group_by(Venue.name)
            .order_by(func.sum(Order.total_amount).desc())
        )).all()
        venue_revenue_data = [{"name": r.name, "revenue": float(r.revenue)} for r in venue_revenue]

        # Summary stats for selected scope
        total_revenue = sum(r["revenue"] for r in venue_revenue_data)
        total_orders = (await db.execute(
            select(func.count(Order.id))
            .where(Order.venue_id.in_(venue_ids), Order.status == "done")
        )).scalar() or 0

        return templates.TemplateResponse("analytics.html", {
            "request": request,
            "user": current_user,
            "venues": all_venues,
            "selected_venue": selected_venue,
            "selected_venue_id": str(venue_id) if venue_id else "",
            "revenue_data": revenue_data,
            "top_items": top_items_data,
            "loyal_guests": loyal_guests,
            "venue_revenue": venue_revenue_data,
            "total_revenue": total_revenue,
            "total_orders": total_orders,
        })
    except Exception as e:
        logger.error("Analytics error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка аналитики")
