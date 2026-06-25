from app.templates_env import templates
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only


from app.database import get_db
from app.models.guest import Guest
from app.models.order import Order, OrderItem
from app.models.review import Review
from app.models.user import User
from app.models.venue import Venue
from app.routers.deps import get_current_user_dep, get_accessible_venue_ids

router = APIRouter(prefix="/analytics", tags=["analytics"])
logger = logging.getLogger(__name__)



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

        accessible_ids = await get_accessible_venue_ids(current_user, db)
        all_venues = (await db.execute(
            select(Venue)
            .where(Venue.id.in_(accessible_ids))
            .order_by(Venue.name)
        )).scalars().all()

        # Determine which venue IDs to query
        if venue_id and venue_id in accessible_ids:
            venue_ids = [venue_id]
            selected_venue = next((v for v in all_venues if v.id == venue_id), None)
        else:
            venue_ids = accessible_ids
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
        revenue_data = [{"day": str(r.day), "revenue": float(r.revenue or 0)} for r in revenue_rows]

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
            .join(Order, Order.guest_id == Guest.id)
            .where(Order.venue_id.in_(venue_ids))
            .group_by(Guest.id)
            .order_by(Guest.total_visits.desc())
            .limit(10)
            .options(load_only(Guest.id, Guest.name, Guest.phone, Guest.total_visits, Guest.total_points))
        )).scalars().all()

        venue_revenue = (await db.execute(
            select(Venue.name, func.sum(Order.total_amount).label("revenue"))
            .join(Order, Order.venue_id == Venue.id)
            .where(Order.venue_id.in_(venue_ids), Order.status == "done")
            .group_by(Venue.name)
            .order_by(func.sum(Order.total_amount).desc())
        )).all()
        venue_revenue_data = [{"name": r.name, "revenue": float(r.revenue or 0)} for r in venue_revenue]

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
            "selected_venue_id": str(venue_id) if (venue_id and venue_id in accessible_ids) else "",
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


@router.get("/nps", response_class=HTMLResponse)
async def nps_page(
    request: Request,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        now = datetime.now(timezone.utc)
        thirty_days_ago = now - timedelta(days=30)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        accessible_ids = await get_accessible_venue_ids(current_user, db)

        # All reviews for accessible venues
        all_reviews = (await db.execute(
            select(Review, Guest, Venue)
            .join(Venue, Venue.id == Review.venue_id)
            .outerjoin(Guest, Guest.id == Review.guest_id)
            .where(Venue.id.in_(accessible_ids))
            .order_by(Review.created_at.desc())
        )).all()

        total_reviews = len(all_reviews)
        month_reviews = [r for r, g, v in all_reviews if r.created_at >= month_start]
        total_month = len(month_reviews)

        # Overall NPS: promoters (4-5) - detractors (1-2) as percentage of total
        if total_reviews > 0:
            promoters = sum(1 for r, g, v in all_reviews if r.overall_rating >= 4)
            detractors = sum(1 for r, g, v in all_reviews if r.overall_rating <= 2)
            overall_nps = round((promoters - detractors) / total_reviews * 100)
        else:
            overall_nps = 0

        avg_rating = round(
            sum(r.overall_rating for r, g, v in all_reviews) / total_reviews, 1
        ) if total_reviews > 0 else 0

        # Per-venue stats
        venue_stats: dict[uuid.UUID, dict] = {}
        for review, guest, venue in all_reviews:
            vid = venue.id
            if vid not in venue_stats:
                venue_stats[vid] = {
                    "name": venue.name,
                    "ratings": [],
                    "promoters": 0,
                    "detractors": 0,
                    "count": 0,
                }
            venue_stats[vid]["ratings"].append(review.overall_rating)
            venue_stats[vid]["count"] += 1
            if review.overall_rating >= 4:
                venue_stats[vid]["promoters"] += 1
            elif review.overall_rating <= 2:
                venue_stats[vid]["detractors"] += 1

        venue_cards = []
        for vid, stats in venue_stats.items():
            count = stats["count"]
            avg = round(sum(stats["ratings"]) / count, 1) if count > 0 else 0
            nps = round((stats["promoters"] - stats["detractors"]) / count * 100) if count > 0 else 0
            nps_badge = "green" if nps >= 50 else ("yellow" if nps >= 0 else "red")
            venue_cards.append({
                "name": stats["name"],
                "avg_rating": avg,
                "count": count,
                "nps": nps,
                "nps_badge": nps_badge,
            })
        venue_cards.sort(key=lambda x: x["nps"], reverse=True)

        # Recent negative reviews (rating 1-3)
        negative_reviews = [
            {
                "date": r.created_at.strftime("%d.%m.%Y %H:%M"),
                "venue": v.name,
                "guest_name": g.name if g else "—",
                "rating": r.overall_rating,
                "comment": r.comment or "",
            }
            for r, g, v in all_reviews
            if r.overall_rating <= 3
        ][:20]

        # Trend: reviews per day for last 30 days
        trend_rows = (await db.execute(
            select(cast(Review.created_at, Date).label("day"), func.count(Review.id).label("cnt"))
            .join(Venue, Venue.id == Review.venue_id)
            .where(
                Venue.id.in_(accessible_ids),
                Review.created_at >= thirty_days_ago,
            )
            .group_by("day")
            .order_by("day")
        )).all()
        trend_data = [{"day": str(r.day), "cnt": r.cnt} for r in trend_rows]

        return templates.TemplateResponse("nps.html", {
            "request": request,
            "user": current_user,
            "overall_nps": overall_nps,
            "total_month": total_month,
            "avg_rating": avg_rating,
            "venue_cards": venue_cards,
            "negative_reviews": negative_reviews,
            "trend_data": trend_data,
        })
    except Exception as e:
        logger.error("NPS analytics error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка NPS аналитики")
