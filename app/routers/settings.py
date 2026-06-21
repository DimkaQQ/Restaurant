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


from app.database import get_db
from app.models.broadcast import Broadcast
from app.models.guest import Guest
from app.models.user import User
from app.models.venue import Venue
from app.routers.deps import get_current_user_dep
from app.services.auth_service import hash_password

router = APIRouter(prefix="/settings", tags=["settings"])


class BroadcastCreate(BaseModel):
    message: str
    lang_filter: str | None = None
logger = logging.getLogger(__name__)



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
        select(func.count()).where(Guest.network_id == current_user.network_id)
    )).scalar() or 0
    tg_guests = (await db.execute(
        select(func.count()).where(
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
