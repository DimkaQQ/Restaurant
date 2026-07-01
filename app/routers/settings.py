from app.templates_env import templates
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


import os as _os

from app.database import get_db
from app.models.broadcast import Broadcast
from app.models.guest import Guest
from app.models.table import Table
from app.models.user import User
from app.models.venue import Venue
from app.routers.deps import get_current_user_dep
from app.services.auth_service import hash_password

_BOT_NAME = _os.getenv("BOT_NAME", "")

router = APIRouter(prefix="/settings", tags=["settings"])


logger = logging.getLogger(__name__)


class BroadcastCreate(BaseModel):
    message: str
    lang_filter: str | None = None



def _require_owner(current_user: User) -> None:
    if current_user.role != "owner":
        raise HTTPException(status_code=403, detail="Доступ запрещён: только для владельца")


@router.get("/users", response_class=HTMLResponse)
async def settings_users_page(
    request: Request,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        _require_owner(current_user)

        users = (await db.execute(
            select(User)
            .where(User.network_id == current_user.network_id)
            .options(selectinload(User.venue))
            .order_by(User.created_at)
        )).scalars().all()

        venues = (await db.execute(
            select(Venue)
            .where(Venue.network_id == current_user.network_id, Venue.is_active == True)
            .order_by(Venue.name)
        )).scalars().all()

        return templates.TemplateResponse("settings_users.html", {
            "request": request,
            "user": current_user,
            "users": users,
            "venues": venues,
            "bot_name": _BOT_NAME,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Settings users page error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка загрузки страницы пользователей")


@router.post("/users")
async def create_user(
    request: Request,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        _require_owner(current_user)

        body = await request.json()
        email = body.get("email", "").strip()
        password = body.get("password", "").strip()
        role = body.get("role", "manager")
        venue_id_str = body.get("venue_id") or None

        if not email or not password:
            raise HTTPException(status_code=400, detail="Email и пароль обязательны")
        if role not in ("manager", "cashier", "administrator"):
            raise HTTPException(status_code=400, detail="Некорректная роль")

        existing = (await db.execute(
            select(User).where(User.email == email, User.network_id == current_user.network_id)
        )).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail="Пользователь с таким email уже существует")

        venue_id = None
        if venue_id_str:
            try:
                venue_id = uuid.UUID(venue_id_str)
            except ValueError:
                raise HTTPException(status_code=400, detail="Некорректный venue_id")
            venue = (await db.execute(
                select(Venue).where(Venue.id == venue_id, Venue.network_id == current_user.network_id)
            )).scalar_one_or_none()
            if not venue:
                raise HTTPException(status_code=404, detail="Заведение не найдено")

        new_user = User(
            id=uuid.uuid4(),
            network_id=current_user.network_id,
            email=email,
            hashed_password=hash_password(password),
            role=role,
            venue_id=venue_id,
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        return {"id": str(new_user.id), "email": new_user.email, "role": new_user.role}
    except HTTPException:
        raise
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Пользователь с таким email уже существует")
    except Exception as e:
        logger.error("Create user error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка создания пользователя")


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        _require_owner(current_user)

        if user_id == current_user.id:
            raise HTTPException(status_code=400, detail="Нельзя удалить самого себя")

        target = (await db.execute(
            select(User).where(User.id == user_id, User.network_id == current_user.network_id)
        )).scalar_one_or_none()
        if not target:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        await db.delete(target)
        await db.commit()
        return {"message": "Удалено"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Delete user error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка удаления пользователя")


@router.get("/broadcasts", response_class=HTMLResponse)
async def broadcasts_page(
    request: Request,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(current_user)
    broadcasts = (await db.execute(
        select(Broadcast)
        .where(Broadcast.network_id == current_user.network_id)
        .order_by(Broadcast.created_at.desc())
    )).scalars().all()

    total_guests = (await db.execute(
        select(func.count(Guest.id)).where(Guest.network_id == current_user.network_id)
    )).scalar() or 0
    tg_guests = (await db.execute(
        select(func.count(Guest.id)).where(
            Guest.network_id == current_user.network_id,
            Guest.telegram_id != None,
        )
    )).scalar() or 0
    total_sent = sum(1 for b in broadcasts if b.sent_at)

    return templates.TemplateResponse("broadcasts.html", {
        "request": request,
        "user": current_user,
        "broadcasts": broadcasts,
        "total_guests": total_guests,
        "tg_guests": tg_guests,
        "total_sent": total_sent,
    })


@router.post("/api/broadcasts")
async def create_broadcast_api(
    data: BroadcastCreate,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(current_user)
    if not data.message.strip():
        raise HTTPException(status_code=400, detail="Сообщение не может быть пустым")
    bc = Broadcast(
        id=uuid.uuid4(),
        network_id=current_user.network_id,
        message=data.message.strip(),
        lang_filter=data.lang_filter,
    )
    db.add(bc)
    await db.commit()
    return {"id": str(bc.id)}


@router.delete("/api/broadcasts/{bc_id}")
async def delete_broadcast_api(
    bc_id: uuid.UUID,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(current_user)
    bc = (await db.execute(
        select(Broadcast).where(Broadcast.id == bc_id, Broadcast.network_id == current_user.network_id)
    )).scalar_one_or_none()
    if not bc:
        raise HTTPException(status_code=404, detail="Не найдено")
    await db.delete(bc)
    await db.commit()
    return {"ok": True}


class VenueSettingsPatch(BaseModel):
    gis_url: str | None = None
    manager_telegram_id: int | None = None


@router.get("/venues", response_class=HTMLResponse)
async def settings_venues_page(
    request: Request,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(current_user)
    venues = (await db.execute(
        select(Venue)
        .where(Venue.network_id == current_user.network_id)
        .order_by(Venue.name)
    )).scalars().all()
    return templates.TemplateResponse("settings_venues.html", {
        "request": request,
        "user": current_user,
        "venues": venues,
    })


@router.patch("/api/venues/{venue_id}")
async def update_venue_settings(
    venue_id: uuid.UUID,
    data: VenueSettingsPatch,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(current_user)
    venue = (await db.execute(
        select(Venue).where(Venue.id == venue_id, Venue.network_id == current_user.network_id)
    )).scalar_one_or_none()
    if not venue:
        raise HTTPException(status_code=404, detail="Заведение не найдено")
    if 'gis_url' in data.model_fields_set:
        venue.gis_url = data.gis_url.strip() if data.gis_url else None
    if 'manager_telegram_id' in data.model_fields_set:
        venue.manager_telegram_id = data.manager_telegram_id  # None clears the field
    await db.commit()
    return {"ok": True, "id": str(venue.id)}


class TableCreate(BaseModel):
    venue_id: uuid.UUID
    label: str
    seats: int = 4


class TableStatusUpdate(BaseModel):
    status: str


@router.get("/tables", response_class=HTMLResponse)
async def settings_tables_page(
    request: Request,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(current_user)
    venues = (await db.execute(
        select(Venue).where(Venue.network_id == current_user.network_id, Venue.is_active == True).order_by(Venue.name)
    )).scalars().all()
    tables = (await db.execute(
        select(Table).join(Venue).where(Venue.network_id == current_user.network_id).order_by(Table.label)
    )).scalars().all()
    tables_by_venue: dict[uuid.UUID, list[Table]] = {}
    for t in tables:
        tables_by_venue.setdefault(t.venue_id, []).append(t)
    return templates.TemplateResponse("settings_tables.html", {
        "request": request,
        "user": current_user,
        "venues": venues,
        "tables_by_venue": tables_by_venue,
    })


@router.post("/api/tables")
async def create_table(
    data: TableCreate,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(current_user)
    venue = (await db.execute(
        select(Venue).where(Venue.id == data.venue_id, Venue.network_id == current_user.network_id)
    )).scalar_one_or_none()
    if not venue:
        raise HTTPException(status_code=404, detail="Заведение не найдено")
    if not data.label.strip():
        raise HTTPException(status_code=400, detail="Название стола обязательно")

    table = Table(id=uuid.uuid4(), venue_id=data.venue_id, label=data.label.strip(), seats=max(1, data.seats))
    db.add(table)
    await db.commit()
    return {"id": str(table.id), "label": table.label, "seats": table.seats, "status": table.status}


@router.patch("/api/tables/{table_id}")
async def update_table_status(
    table_id: uuid.UUID,
    data: TableStatusUpdate,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(current_user)
    if data.status not in ("free", "occupied", "reserved"):
        raise HTTPException(status_code=400, detail="Неверный статус")
    table = (await db.execute(
        select(Table).join(Venue).where(Table.id == table_id, Venue.network_id == current_user.network_id)
    )).scalar_one_or_none()
    if not table:
        raise HTTPException(status_code=404, detail="Стол не найден")
    table.status = data.status
    await db.commit()
    return {"ok": True, "status": table.status}


@router.delete("/api/tables/{table_id}")
async def delete_table(
    table_id: uuid.UUID,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(current_user)
    table = (await db.execute(
        select(Table).join(Venue).where(Table.id == table_id, Venue.network_id == current_user.network_id)
    )).scalar_one_or_none()
    if not table:
        raise HTTPException(status_code=404, detail="Стол не найден")
    await db.delete(table)
    await db.commit()
    return {"message": "Удалено"}


import secrets as _secrets


@router.post("/api/me/bot-token")
async def generate_bot_link_token(
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Generate a one-time token to link staff Telegram account via bot deeplink."""
    token = _secrets.token_urlsafe(32)
    current_user.bot_link_token = token
    await db.commit()
    return {"token": token}


@router.delete("/api/me/bot-token")
async def unlink_telegram(
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Unlink Telegram from staff account."""
    current_user.telegram_id = None
    current_user.bot_link_token = None
    await db.commit()
    return {"ok": True}
