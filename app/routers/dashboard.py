import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.guest import Guest
from app.models.order import Order, OrderItem
from app.models.user import User
from app.models.venue import Venue
from app.routers.deps import get_current_user_dep, get_current_user_optional
from app.services.order_service import update_order_status

router = APIRouter(tags=["dashboard"])
logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def root(request: Request, current_user: User | None = Depends(get_current_user_optional)):
    if current_user:
        return RedirectResponse(url="/dashboard")
    return RedirectResponse(url="/auth/login")


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        today = datetime.now(timezone.utc).date()
        today_start = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)

        venues_result = await db.execute(
            select(Venue).where(Venue.network_id == current_user.network_id, Venue.is_active == True)
        )
        venues = venues_result.scalars().all()
        venue_ids = [v.id for v in venues]

        total_rev = (await db.execute(
            select(func.sum(Order.total_amount))
            .where(Order.venue_id.in_(venue_ids), Order.status == "done")
        )).scalar() or 0

        today_rev = (await db.execute(
            select(func.sum(Order.total_amount))
            .where(Order.venue_id.in_(venue_ids), Order.status == "done", Order.created_at >= today_start)
        )).scalar() or 0

        new_guests = (await db.execute(
            select(func.count(Guest.id))
            .where(Guest.network_id == current_user.network_id, Guest.created_at >= today_start)
        )).scalar() or 0

        orders = (await db.execute(
            select(Order)
            .options(selectinload(Order.items), selectinload(Order.guest))
            .where(Order.venue_id.in_(venue_ids), Order.status.in_(["new", "confirmed", "preparing", "ready"]))
            .order_by(Order.created_at.desc())
            .limit(20)
        )).scalars().all()

        top_items_rows = (await db.execute(
            select(OrderItem.name, func.sum(OrderItem.quantity).label("qty"))
            .join(Order)
            .where(Order.venue_id.in_(venue_ids), Order.created_at >= today_start)
            .group_by(OrderItem.name)
            .order_by(func.sum(OrderItem.quantity).desc())
            .limit(5)
        )).all()
        top_items_data = [{"name": r.name, "qty": int(r.qty)} for r in top_items_rows]

        orders_today_count = (await db.execute(
            select(func.count(Order.id))
            .where(Order.venue_id.in_(venue_ids), Order.created_at >= today_start)
        )).scalar() or 0

        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "user": current_user,
            "venues": venues,
            "total_revenue": total_rev,
            "today_revenue": today_rev,
            "new_guests": new_guests,
            "orders_today": orders_today_count,
            "active_orders": orders,
            "top_items": top_items_data,
        })
    except Exception as e:
        logger.error("Dashboard error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка загрузки дашборда")


@router.get("/partials/orders", response_class=HTMLResponse)
async def orders_partial(
    request: Request,
    venue_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        stmt = (
            select(Order)
            .options(selectinload(Order.items), selectinload(Order.guest))
            .join(Venue)
            .where(
                Venue.network_id == current_user.network_id,
                Order.status.in_(["new", "confirmed", "preparing", "ready"]),
            )
            .order_by(Order.created_at.desc())
            .limit(50)
        )
        if venue_id:
            stmt = stmt.where(Order.venue_id == venue_id)
        orders = (await db.execute(stmt)).scalars().all()

        return templates.TemplateResponse("partials/orders_list.html", {
            "request": request,
            "orders": orders,
        })
    except Exception as e:
        logger.error("Orders partial error: %s", e)
        return HTMLResponse("<p class='empty-state'>Ошибка загрузки</p>")


@router.patch("/api/orders/{order_id}/status", response_class=HTMLResponse)
async def change_status_html(
    order_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        body = await request.json()
        new_status = body.get("status")
        order = await update_order_status(order_id, new_status, db)

        return templates.TemplateResponse("partials/orders_list.html", {
            "request": request,
            "orders": [order],
        })
    except ValueError as e:
        return HTMLResponse(f"<p class='error-state'>{e}</p>", status_code=400)
    except Exception as e:
        logger.error("Status change error: %s", e)
        return HTMLResponse("<p class='error-state'>Ошибка</p>", status_code=500)


@router.get("/partials/guests", response_class=HTMLResponse)
async def guests_partial(
    request: Request,
    search: str | None = Query(None),
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        stmt = (
            select(Guest)
            .where(Guest.network_id == current_user.network_id)
            .order_by(Guest.total_visits.desc())
            .limit(100)
        )
        if search:
            stmt = stmt.where(
                Guest.name.ilike(f"%{search}%") | Guest.phone.ilike(f"%{search}%")
            )
        guests = (await db.execute(stmt)).scalars().all()
        return templates.TemplateResponse("partials/guests_rows.html", {
            "request": request,
            "guests": guests,
        })
    except Exception as e:
        logger.error("Guests partial error: %s", e)
        return HTMLResponse("<tr><td colspan='5' class='empty-state'>Ошибка</td></tr>")


@router.get("/orders", response_class=HTMLResponse)
async def orders_page(
    request: Request,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        venues = (await db.execute(
            select(Venue).where(Venue.network_id == current_user.network_id)
        )).scalars().all()
        return templates.TemplateResponse("orders.html", {
            "request": request,
            "user": current_user,
            "venues": venues,
        })
    except Exception as e:
        logger.error("Orders page error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка загрузки страницы заказов")


@router.get("/menu", response_class=HTMLResponse)
async def menu_page(
    request: Request,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        venues = (await db.execute(
            select(Venue).where(Venue.network_id == current_user.network_id)
        )).scalars().all()
        return templates.TemplateResponse("menu.html", {
            "request": request,
            "user": current_user,
            "venues": venues,
        })
    except Exception as e:
        logger.error("Menu page error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка загрузки меню")


@router.get("/guests", response_class=HTMLResponse)
async def guests_page(
    request: Request,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        guests = (await db.execute(
            select(Guest)
            .where(Guest.network_id == current_user.network_id)
            .order_by(Guest.total_visits.desc())
            .limit(100)
        )).scalars().all()
        return templates.TemplateResponse("guests.html", {
            "request": request,
            "user": current_user,
            "guests": guests,
        })
    except Exception as e:
        logger.error("Guests page error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка загрузки гостей")
