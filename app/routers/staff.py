import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from fastapi.templating import Jinja2Templates

from app.database import get_db
from app.models.staff import Staff
from app.models.review import Review
from app.models.venue import Venue
from app.models.user import User
from app.routers.deps import get_current_user_dep

router = APIRouter(prefix="/staff", tags=["staff"])
logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def staff_page(
    request: Request,
    venue_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        all_venues = (await db.execute(
            select(Venue)
            .where(Venue.network_id == current_user.network_id, Venue.is_active == True)
            .order_by(Venue.name)
        )).scalars().all()

        if venue_id:
            venue_ids = [venue_id]
            selected_venue = next((v for v in all_venues if v.id == venue_id), None)
        else:
            venue_ids = [v.id for v in all_venues]
            selected_venue = None

        staff_list = (await db.execute(
            select(Staff)
            .where(
                Staff.network_id == current_user.network_id,
                Staff.venue_id.in_(venue_ids),
                Staff.is_active == True,
            )
            .options(selectinload(Staff.venue))
            .order_by(Staff.avg_rating.desc().nulls_last(), Staff.name)
        )).scalars().all()

        return templates.TemplateResponse("staff.html", {
            "request": request,
            "user": current_user,
            "venues": all_venues,
            "selected_venue": selected_venue,
            "selected_venue_id": str(venue_id) if venue_id else "",
            "staff": staff_list,
        })
    except Exception as e:
        logger.error("Staff page error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка загрузки персонала")


@router.get("/{staff_id}/reviews", response_class=HTMLResponse)
async def staff_reviews(
    request: Request,
    staff_id: uuid.UUID,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        staff = (await db.execute(
            select(Staff)
            .where(Staff.id == staff_id, Staff.network_id == current_user.network_id)
            .options(selectinload(Staff.venue))
        )).scalar_one_or_none()

        if not staff:
            raise HTTPException(status_code=404, detail="Сотрудник не найден")

        reviews = (await db.execute(
            select(Review)
            .where(Review.staff_id == staff_id)
            .options(selectinload(Review.guest))
            .order_by(Review.created_at.desc())
            .limit(50)
        )).scalars().all()

        return templates.TemplateResponse("partials/staff_reviews.html", {
            "request": request,
            "staff": staff,
            "reviews": reviews,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Staff reviews error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка загрузки отзывов")
