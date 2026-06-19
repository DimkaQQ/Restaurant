import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.guest import Guest
from app.models.menu import MenuItem
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
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        now = datetime.now(timezone.utc)
        thirty_days_ago = now - timedelta(days=30)

        revenue_rows = await db.execute(
            select(cast(Order.created_at, Date).label("day"), func.sum(Order.total_amount).label("revenue"))
            .join(Venue)
            .where(
                Venue.network_id == current_user.network_id,
                Order.status == "done",
                Order.created_at >= thirty_days_ago,
            )
            .group_by("day")
            .order_by("day")
        )
        revenue_data = [{"day": str(r.day), "revenue": float(r.revenue)} for r in revenue_rows]

        top_items = await db.execute(
            select(OrderItem.name, func.sum(OrderItem.quantity).label("total_qty"))
            .join(Order)
            .join(Venue)
            .where(Venue.network_id == current_user.network_id, Order.status == "done")
            .group_by(OrderItem.name)
            .order_by(func.sum(OrderItem.quantity).desc())
            .limit(10)
        )
        top_items_data = [{"name": r.name, "qty": int(r.total_qty)} for r in top_items]

        loyal_guests = await db.execute(
            select(Guest)
            .where(Guest.network_id == current_user.network_id)
            .order_by(Guest.total_visits.desc())
            .limit(10)
        )
        loyal_guests_data = loyal_guests.scalars().all()

        venue_revenue = await db.execute(
            select(Venue.name, func.sum(Order.total_amount).label("revenue"))
            .join(Order, Order.venue_id == Venue.id)
            .where(Venue.network_id == current_user.network_id, Order.status == "done")
            .group_by(Venue.name)
        )
        venue_revenue_data = [{"name": r.name, "revenue": float(r.revenue)} for r in venue_revenue]

        return templates.TemplateResponse("analytics.html", {
            "request": request,
            "user": current_user,
            "revenue_data": revenue_data,
            "top_items": top_items_data,
            "loyal_guests": loyal_guests_data,
            "venue_revenue": venue_revenue_data,
        })
    except Exception as e:
        logger.error("Analytics error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка аналитики")
