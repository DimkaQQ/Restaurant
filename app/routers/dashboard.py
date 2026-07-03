from app.templates_env import templates
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.guest import Guest
from app.models.menu import MenuItem
from app.models.order import Order, OrderItem
from app.models.table import Table
from app.models.user import User
from app.models.venue import Venue
from app.routers.deps import get_current_user_dep, get_current_user_optional, get_accessible_venue_ids
from app.services.order_service import update_order_status, pay_order, WALKIN_MARKER
from app.config import settings

router = APIRouter(tags=["dashboard"])
logger = logging.getLogger(__name__)



@router.get("/", response_class=HTMLResponse)
async def root(request: Request, current_user: User | None = Depends(get_current_user_optional)):
    if current_user:
        return RedirectResponse(url="/dashboard")
    from app.i18n import get_translator
    gettext_fn, locale = get_translator(request)
    response = templates.TemplateResponse("landing.html", {
        "request": request, "year": datetime.now(timezone.utc).year, "_": gettext_fn, "locale": locale,
        "public_url": settings.PUBLIC_URL,
    })
    if request.query_params.get("lang") in ("ru", "en"):
        response.set_cookie("lang", request.query_params["lang"], max_age=60 * 60 * 24 * 365)
    return response


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        today = datetime.now(timezone.utc).date()
        today_start = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)

        venue_ids = await get_accessible_venue_ids(current_user, db)
        venues_result = await db.execute(select(Venue).where(Venue.id.in_(venue_ids)))
        venues = venues_result.scalars().all()

        # Revenue = money actually received (payment_status), not orders served.
        total_rev = (await db.execute(
            select(func.sum(Order.total_amount))
            .where(Order.venue_id.in_(venue_ids), Order.payment_status == "paid")
        )).scalar() or 0

        today_rev = (await db.execute(
            select(func.sum(Order.total_amount))
            .where(Order.venue_id.in_(venue_ids), Order.payment_status == "paid", Order.paid_at >= today_start)
        )).scalar() or 0

        new_guests = (await db.execute(
            select(func.count(Guest.id))
            .where(
                Guest.network_id == current_user.network_id,
                Guest.phone != WALKIN_MARKER,
                Guest.created_at >= today_start,
            )
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

        # Order counts by status (active)
        status_counts_rows = (await db.execute(
            select(Order.status, func.count(Order.id))
            .where(Order.venue_id.in_(venue_ids), Order.status.in_(["new", "confirmed", "preparing", "ready"]))
            .group_by(Order.status)
        )).all()
        status_map = {r[0]: r[1] for r in status_counts_rows}

        # Done orders today
        done_today = (await db.execute(
            select(func.count(Order.id))
            .where(Order.venue_id.in_(venue_ids), Order.status == "done", Order.created_at >= today_start)
        )).scalar() or 0

        onboarding = None
        if current_user.role == "owner":
            menu_count = (await db.execute(
                select(func.count(MenuItem.id)).where(MenuItem.venue_id.in_(venue_ids))
            )).scalar() or 0
            table_count = (await db.execute(
                select(func.count(Table.id)).where(Table.venue_id.in_(venue_ids))
            )).scalar() or 0
            staff_count = (await db.execute(
                select(func.count(User.id)).where(User.network_id == current_user.network_id)
            )).scalar() or 0
            any_order = (await db.execute(
                select(func.count(Order.id)).where(Order.venue_id.in_(venue_ids)).limit(1)
            )).scalar() or 0

            steps = [
                {"done": len(venues) > 0, "key": "venue", "href": "/settings/venues"},
                {"done": menu_count > 0, "key": "menu", "href": "/menu"},
                {"done": table_count > 0, "key": "tables", "href": "/settings/tables"},
                {"done": staff_count > 1, "key": "staff", "href": "/settings/users"},
                {"done": any_order > 0, "key": "order", "href": "/pos"},
            ]
            done_count = sum(1 for s in steps if s["done"])
            if done_count < len(steps):
                onboarding = {"steps": steps, "done_count": done_count, "total": len(steps)}

        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "user": current_user,
            "venues": venues,
            "total_revenue": total_rev,
            "today_revenue": today_rev,
            "new_guests": new_guests,
            "orders_today": orders_today_count,
            "orders_status": {
                "new": status_map.get("new", 0),
                "confirmed": status_map.get("confirmed", 0),
                "preparing": status_map.get("preparing", 0),
                "ready": status_map.get("ready", 0),
                "done": done_today,
            },
            "active_orders": orders,
            "top_items": top_items_data,
            "onboarding": onboarding,
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
        accessible_ids = await get_accessible_venue_ids(current_user, db)
        filter_ids = [venue_id] if venue_id and venue_id in accessible_ids else accessible_ids
        from sqlalchemy import or_, and_
        stmt = (
            select(Order)
            .options(selectinload(Order.items), selectinload(Order.guest))
            .where(
                Order.venue_id.in_(filter_ids),
                or_(
                    Order.status.in_(["new", "confirmed", "preparing", "ready"]),
                    # served but not yet paid — keep on the board until money is collected
                    and_(Order.status == "done", Order.payment_status == "unpaid"),
                ),
            )
            .order_by(Order.created_at.desc())
            .limit(50)
        )
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
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            body = await request.json()
            new_status = body.get("status")
        else:
            form = await request.form()
            new_status = form.get("status")
        if not new_status:
            return HTMLResponse("<p class='error-state'>Статус обязателен</p>", status_code=400)
        venue_ids = await get_accessible_venue_ids(current_user, db)
        check = (await db.execute(
            select(Order).where(Order.id == order_id, Order.venue_id.in_(venue_ids))
        )).scalar_one_or_none()
        if not check:
            return HTMLResponse("<p class='error-state'>Заказ не найден</p>", status_code=404)
        if new_status == "cancelled":
            from app.services.audit import log_action
            log_action(db, current_user.network_id, current_user.email, "order_cancelled",
                       f"#{str(order_id)[:8].upper()} на {check.total_amount} ₸")
            await db.commit()
        order = await update_order_status(order_id, new_status, db, changed_by=current_user.email)

        # The card leaves the board only when nothing is left to do: cancelled,
        # or served AND paid. A served-but-unpaid order stays visible so the
        # waiter doesn't forget to collect payment.
        if order.status == "cancelled" or (order.status == "done" and order.payment_status == "paid"):
            return HTMLResponse("", headers={"HX-Reswap": "delete"})
        return templates.TemplateResponse("partials/orders_list.html", {
            "request": request,
            "orders": [order],
        })
    except ValueError as e:
        return HTMLResponse(f"<p class='error-state'>{e}</p>", status_code=400)
    except Exception as e:
        logger.error("Status change error: %s", e)
        return HTMLResponse("<p class='error-state'>Ошибка</p>", status_code=500)


@router.post("/api/orders/{order_id}/pay", response_class=HTMLResponse)
async def pay_order_html(
    order_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            body = await request.json()
            method = body.get("method")
        else:
            form = await request.form()
            method = form.get("method")
        if not method:
            return HTMLResponse("<p class='error-state'>Способ оплаты обязателен</p>", status_code=400)
        venue_ids = await get_accessible_venue_ids(current_user, db)
        check = (await db.execute(
            select(Order).where(Order.id == order_id, Order.venue_id.in_(venue_ids))
        )).scalar_one_or_none()
        if not check:
            return HTMLResponse("<p class='error-state'>Заказ не найден</p>", status_code=404)
        order = await pay_order(order_id, method, db, changed_by=current_user.email)

        if order.status == "done":
            return HTMLResponse("", headers={"HX-Reswap": "delete"})
        return templates.TemplateResponse("partials/orders_list.html", {
            "request": request,
            "orders": [order],
        })
    except ValueError as e:
        return HTMLResponse(f"<p class='error-state'>{e}</p>", status_code=400)
    except Exception as e:
        logger.error("Payment error: %s", e)
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
            .where(Guest.network_id == current_user.network_id, Guest.phone != WALKIN_MARKER)
            .order_by(Guest.total_visits.desc())
            .limit(100)
        )
        if search:
            from sqlalchemy import func as sqlfunc
            normalized = search.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
            db_normalized = sqlfunc.replace(sqlfunc.replace(sqlfunc.replace(sqlfunc.replace(Guest.phone, " ", ""), "-", ""), "(", ""), ")", "")
            stmt = stmt.where(
                Guest.name.ilike(f"%{search}%") |
                Guest.phone.ilike(f"%{search}%") |
                db_normalized.ilike(f"%{normalized}%")
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
        accessible_ids = await get_accessible_venue_ids(current_user, db)
        venues = (await db.execute(
            select(Venue).where(Venue.id.in_(accessible_ids))
        )).scalars().all()
        return templates.TemplateResponse("orders.html", {
            "request": request,
            "user": current_user,
            "venues": venues,
        })
    except Exception as e:
        logger.error("Orders page error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка загрузки страницы заказов")


@router.get("/orders/{order_id}/receipt", response_class=HTMLResponse)
async def order_receipt(
    order_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Print-friendly receipt / kitchen ticket — opened in a new tab and
    printed via the browser (works with any thermal printer set as the
    default system printer, no special driver integration needed)."""
    try:
        accessible_ids = await get_accessible_venue_ids(current_user, db)
        order = (await db.execute(
            select(Order)
            .options(selectinload(Order.items), selectinload(Order.guest), selectinload(Order.venue))
            .where(Order.id == order_id, Order.venue_id.in_(accessible_ids))
        )).scalar_one_or_none()
        if not order:
            raise HTTPException(status_code=404, detail="Заказ не найден")
        return templates.TemplateResponse("receipt.html", {
            "request": request,
            "order": order,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Receipt page error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка загрузки чека")


@router.get("/menu", response_class=HTMLResponse)
async def menu_page(
    request: Request,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        accessible_ids = await get_accessible_venue_ids(current_user, db)
        venues = (await db.execute(
            select(Venue).where(Venue.id.in_(accessible_ids))
        )).scalars().all()
        return templates.TemplateResponse("menu.html", {
            "request": request,
            "user": current_user,
            "venues": venues,
        })
    except Exception as e:
        logger.error("Menu page error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка загрузки меню")


@router.get("/kitchen", response_class=HTMLResponse)
async def kitchen_page(
    request: Request,
    venue_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        accessible_ids = await get_accessible_venue_ids(current_user, db)
        venues = (await db.execute(
            select(Venue)
            .where(Venue.id.in_(accessible_ids), Venue.is_active == True)
            .order_by(Venue.name)
        )).scalars().all()
        current_venue = next((v for v in venues if v.id == venue_id), None) if venue_id else None
        return templates.TemplateResponse("kitchen.html", {
            "request": request,
            "venues": venues,
            "current_venue": current_venue,
        })
    except Exception as e:
        logger.error("Kitchen page error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка кухонного экрана")


@router.get("/partials/kitchen", response_class=HTMLResponse)
async def kitchen_partial(
    request: Request,
    venue_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        accessible_ids = await get_accessible_venue_ids(current_user, db)
        filter_ids = [venue_id] if venue_id and venue_id in accessible_ids else accessible_ids
        stmt = (
            select(Order)
            .options(selectinload(Order.items), selectinload(Order.venue))
            .where(
                Order.venue_id.in_(filter_ids),
                Order.status.in_(["new", "confirmed", "preparing", "ready"]),
            )
            .order_by(Order.created_at.asc())
        )
        orders = (await db.execute(stmt)).scalars().all()
        return templates.TemplateResponse("partials/kitchen_board.html", {
            "request": request,
            "orders": orders,
            "venue_id": str(venue_id) if venue_id else None,
            "now": datetime.now(timezone.utc),
        })
    except Exception as e:
        logger.error("Kitchen partial error: %s", e)
        return HTMLResponse("<p class='kds-empty'>Ошибка загрузки</p>")


@router.get("/partials/kitchen/history", response_class=HTMLResponse)
async def kitchen_history(
    request: Request,
    venue_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        accessible_ids = await get_accessible_venue_ids(current_user, db)
        filter_ids = [venue_id] if venue_id and venue_id in accessible_ids else accessible_ids
        today_start = datetime.combine(
            datetime.now(timezone.utc).date(), datetime.min.time()
        ).replace(tzinfo=timezone.utc)
        orders = (await db.execute(
            select(Order)
            .options(selectinload(Order.items), selectinload(Order.venue))
            .where(
                Order.venue_id.in_(filter_ids),
                Order.status == "done",
                Order.updated_at >= today_start,
            )
            .order_by(Order.updated_at.desc())
            .limit(100)
        )).scalars().all()
        return templates.TemplateResponse("partials/kitchen_history.html", {
            "request": request,
            "orders": orders,
            "now": datetime.now(timezone.utc),
        })
    except Exception as e:
        logger.error("Kitchen history error: %s", e)
        return HTMLResponse("<p class='kds-empty'>Ошибка загрузки истории</p>")


@router.get("/guests", response_class=HTMLResponse)
async def guests_page(
    request: Request,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        guests = (await db.execute(
            select(Guest)
            .where(Guest.network_id == current_user.network_id, Guest.phone != WALKIN_MARKER)
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
