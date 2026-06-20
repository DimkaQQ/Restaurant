from app.templates_env import templates
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


from app.database import get_db
from app.models.user import User
from app.models.venue import Venue
from app.routers.deps import get_current_user_dep
from app.services.auth_service import hash_password

router = APIRouter(prefix="/settings", tags=["settings"])
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
        if role not in ("owner", "manager", "cashier", "administrator"):
            raise HTTPException(status_code=400, detail="Некорректная роль")

        existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
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
