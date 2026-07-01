from app.templates_env import templates
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.venue import Venue
from app.routers.deps import get_current_user_dep, get_accessible_venue_ids
from app.schemas.order import OrderCreate, OrderOut
from app.services.order_service import create_order, get_or_create_walkin_guest

router = APIRouter(tags=["pos"])
logger = logging.getLogger(__name__)


@router.get("/pos", response_class=HTMLResponse)
async def pos_page(
    request: Request,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
    accessible_ids = await get_accessible_venue_ids(current_user, db)
    venues = (await db.execute(
        select(Venue).where(Venue.id.in_(accessible_ids), Venue.is_active == True).order_by(Venue.name)
    )).scalars().all()
    return templates.TemplateResponse("pos.html", {
        "request": request,
        "user": current_user,
        "venues": venues,
    })


@router.post("/api/pos/order", response_model=OrderOut)
async def place_pos_order(
    data: OrderCreate,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    accessible_ids = await get_accessible_venue_ids(current_user, db)
    if data.venue_id not in accessible_ids:
        raise HTTPException(status_code=403, detail="Нет доступа к этому заведению")
    try:
        guest = await get_or_create_walkin_guest(current_user.network_id, db)
        data.source = "pos"
        order = await create_order(data, guest, db, changed_by=current_user.email)
        return order
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("POS order error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка создания заказа")
