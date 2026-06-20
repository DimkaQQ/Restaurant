import logging
import uuid
import shutil
import os

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.menu import MenuItem
from app.models.user import User
from app.models.venue import Venue
from app.routers.deps import get_current_user_dep
from app.schemas.menu import MenuItemCreate, MenuItemOut, MenuItemUpdate

UPLOAD_DIR = "app/static/uploads/menu"
os.makedirs(UPLOAD_DIR, exist_ok=True)

router = APIRouter(prefix="/api/menu", tags=["menu"])
logger = logging.getLogger(__name__)


async def _check_venue_owner(venue_id: uuid.UUID, user: User, db: AsyncSession) -> Venue:
    result = await db.execute(
        select(Venue).where(Venue.id == venue_id, Venue.network_id == user.network_id)
    )
    venue = result.scalar_one_or_none()
    if not venue:
        raise HTTPException(status_code=404, detail="Заведение не найдено")
    return venue


@router.get("/{venue_id}", response_model=list[MenuItemOut])
async def list_menu(
    venue_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await db.execute(select(MenuItem).where(MenuItem.venue_id == venue_id))
        return result.scalars().all()
    except Exception as e:
        logger.error("List menu error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка загрузки меню")


@router.post("/{venue_id}", response_model=MenuItemOut)
async def create_item(
    venue_id: uuid.UUID,
    data: MenuItemCreate,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        await _check_venue_owner(venue_id, current_user, db)
        item = MenuItem(id=uuid.uuid4(), venue_id=venue_id, **data.model_dump())
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Create menu item error: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{item_id}", response_model=MenuItemOut)
async def update_item(
    item_id: uuid.UUID,
    data: MenuItemUpdate,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await db.execute(select(MenuItem).where(MenuItem.id == item_id))
        item = result.scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=404, detail="Позиция не найдена")
        await _check_venue_owner(item.venue_id, current_user, db)
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(item, field, value)
        await db.commit()
        await db.refresh(item)
        return item
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Update menu item error: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{item_id}")
async def delete_item(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await db.execute(select(MenuItem).where(MenuItem.id == item_id))
        item = result.scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=404, detail="Позиция не найдена")
        await _check_venue_owner(item.venue_id, current_user, db)
        await db.delete(item)
        await db.commit()
        return {"message": "Удалено"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Delete menu item error: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{item_id}/photo", response_model=MenuItemOut)
async def upload_photo(
    item_id: uuid.UUID,
    photo: UploadFile = File(...),
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await db.execute(select(MenuItem).where(MenuItem.id == item_id))
        item = result.scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=404, detail="Позиция не найдена")
        await _check_venue_owner(item.venue_id, current_user, db)

        ext = photo.filename.rsplit(".", 1)[-1].lower() if "." in photo.filename else "jpg"
        if ext not in ("jpg", "jpeg", "png", "webp"):
            raise HTTPException(status_code=400, detail="Только jpg/png/webp")

        filename = f"{item_id}.{ext}"
        path = os.path.join(UPLOAD_DIR, filename)
        with open(path, "wb") as f:
            shutil.copyfileobj(photo.file, f)

        item.image_url = f"/static/uploads/menu/{filename}"
        await db.commit()
        await db.refresh(item)
        return item
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Upload photo error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка загрузки фото")
