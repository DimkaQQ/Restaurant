from app.templates_env import templates
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from decimal import Decimal
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.inventory import Ingredient, WriteOff
from app.models.venue import Venue
from app.models.user import User
from app.routers.deps import get_current_user_dep, get_accessible_venue_ids

router = APIRouter(tags=["inventory"])
logger = logging.getLogger(__name__)


class IngredientCreate(BaseModel):
    venue_id: uuid.UUID
    name: str
    unit: str = "кг"
    quantity: Decimal = Field(default=0, ge=0)
    min_quantity: Decimal = Field(default=0, ge=0)
    cost_per_unit: Decimal = Field(default=0, ge=0)
    category: str | None = None


class IngredientUpdate(BaseModel):
    name: str | None = None
    unit: str | None = None
    quantity: Decimal | None = Field(None, ge=0)
    min_quantity: Decimal | None = Field(None, ge=0)
    cost_per_unit: Decimal | None = Field(None, ge=0)
    category: str | None = None


class WriteOffCreate(BaseModel):
    quantity: Decimal = Field(..., gt=0)
    reason: str = "usage"
    note: str | None = None


@router.get("/api/inventory/list")
async def list_ingredients_json(
    venue_id: uuid.UUID = Query(...),
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    accessible_ids = await get_accessible_venue_ids(current_user, db)
    if venue_id not in accessible_ids:
        raise HTTPException(status_code=403, detail="Нет доступа к этому заведению")
    result = await db.execute(
        select(Ingredient).where(Ingredient.venue_id == venue_id).order_by(Ingredient.name)
    )
    return [
        {"id": str(i.id), "name": i.name, "unit": i.unit}
        for i in result.scalars().all()
    ]


@router.get("/inventory", response_class=HTMLResponse)
async def inventory_page(
    request: Request,
    venue_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        accessible_ids = await get_accessible_venue_ids(current_user, db)
        venues = (await db.execute(
            select(Venue).where(Venue.id.in_(accessible_ids), Venue.is_active == True).order_by(Venue.name)
        )).scalars().all()

        filter_ids = [venue_id] if venue_id and venue_id in accessible_ids else accessible_ids

        ingredients = (await db.execute(
            select(Ingredient)
            .where(Ingredient.venue_id.in_(filter_ids))
            .order_by(Ingredient.category, Ingredient.name)
        )).scalars().all()

        # Stats
        total_value = sum(float(i.total_value) for i in ingredients)
        low_stock = [i for i in ingredients if i.stock_status in ("low", "empty")]

        categories = sorted(set(i.category for i in ingredients if i.category))

        return templates.TemplateResponse("inventory.html", {
            "request": request,
            "user": current_user,
            "venues": venues,
            "selected_venue_id": str(venue_id) if venue_id and venue_id in accessible_ids else "",
            "ingredients": ingredients,
            "total_value": total_value,
            "low_stock_count": len(low_stock),
            "categories": categories,
        })
    except Exception as e:
        logger.error("Inventory page error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка загрузки склада")


@router.get("/inventory/tablet", response_class=HTMLResponse)
async def inventory_tablet(
    request: Request,
    venue_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        accessible_ids = await get_accessible_venue_ids(current_user, db)
        venues = (await db.execute(
            select(Venue).where(Venue.id.in_(accessible_ids), Venue.is_active == True).order_by(Venue.name)
        )).scalars().all()

        filter_ids = [venue_id] if venue_id and venue_id in accessible_ids else accessible_ids

        ingredients = (await db.execute(
            select(Ingredient)
            .where(Ingredient.venue_id.in_(filter_ids))
            .order_by(Ingredient.category, Ingredient.name)
        )).scalars().all()

        return templates.TemplateResponse("inventory_tablet.html", {
            "request": request,
            "venues": venues,
            "selected_venue_id": str(venue_id) if venue_id and venue_id in accessible_ids else "",
            "ingredients": ingredients,
        })
    except Exception as e:
        logger.error("Inventory tablet error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка загрузки склада")


@router.post("/api/inventory")
async def create_ingredient(
    data: IngredientCreate,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        accessible_ids = await get_accessible_venue_ids(current_user, db)
        if data.venue_id not in accessible_ids:
            raise HTTPException(status_code=403, detail="Нет доступа к заведению")

        item = Ingredient(
            id=uuid.uuid4(),
            network_id=current_user.network_id,
            **data.model_dump(),
        )
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return {"id": str(item.id), "name": item.name, "status": item.stock_status}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Create ingredient error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка создания позиции")


@router.patch("/api/inventory/{item_id}")
async def update_ingredient(
    item_id: uuid.UUID,
    data: IngredientUpdate,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        accessible_ids = await get_accessible_venue_ids(current_user, db)
        item = (await db.execute(
            select(Ingredient).where(Ingredient.id == item_id, Ingredient.venue_id.in_(accessible_ids))
        )).scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=404, detail="Позиция не найдена")

        for field, value in data.model_dump(exclude_none=True).items():
            setattr(item, field, value)
        await db.commit()
        await db.refresh(item)
        return {"id": str(item.id), "quantity": float(item.quantity), "status": item.stock_status}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Update ingredient error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка обновления")


@router.delete("/api/inventory/{item_id}")
async def delete_ingredient(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        accessible_ids = await get_accessible_venue_ids(current_user, db)
        item = (await db.execute(
            select(Ingredient).where(Ingredient.id == item_id, Ingredient.venue_id.in_(accessible_ids))
        )).scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=404, detail="Позиция не найдена")
        await db.delete(item)
        await db.commit()
        return {"message": "Удалено"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Delete ingredient error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка удаления")


@router.post("/api/inventory/{item_id}/writeoff")
async def write_off(
    item_id: uuid.UUID,
    data: WriteOffCreate,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        accessible_ids = await get_accessible_venue_ids(current_user, db)
        item = (await db.execute(
            select(Ingredient).where(Ingredient.id == item_id, Ingredient.venue_id.in_(accessible_ids))
        )).scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=404, detail="Позиция не найдена")
        if item.quantity < data.quantity:
            raise HTTPException(status_code=400, detail="Недостаточно на складе")

        item.quantity -= data.quantity
        writeoff = WriteOff(
            id=uuid.uuid4(),
            ingredient_id=item_id,
            quantity=data.quantity,
            reason=data.reason,
            note=data.note,
            created_by_id=current_user.id,
        )
        db.add(writeoff)
        await db.commit()
        await db.refresh(item)
        return {"quantity": float(item.quantity), "status": item.stock_status}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Write-off error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка списания")


@router.post("/api/inventory/{item_id}/restock")
async def restock(
    item_id: uuid.UUID,
    data: WriteOffCreate,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        accessible_ids = await get_accessible_venue_ids(current_user, db)
        item = (await db.execute(
            select(Ingredient).where(Ingredient.id == item_id, Ingredient.venue_id.in_(accessible_ids))
        )).scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=404, detail="Позиция не найдена")

        item.quantity += data.quantity
        await db.commit()
        await db.refresh(item)
        return {"quantity": float(item.quantity), "status": item.stock_status}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Restock error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка пополнения")
