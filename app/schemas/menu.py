from pydantic import BaseModel, Field
from decimal import Decimal
import uuid


class MenuItemCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    price: Decimal = Field(..., gt=0)
    category: str | None = Field(None, max_length=100)  # DB column is String(100)
    is_available: bool = True
    image_url: str | None = None
    color: str | None = Field(None, max_length=7)


class MenuItemUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    price: Decimal | None = Field(None, gt=0)
    category: str | None = Field(None, max_length=100)
    is_available: bool | None = None
    image_url: str | None = None
    color: str | None = Field(None, max_length=7)


class CategoryRename(BaseModel):
    old: str = Field(..., min_length=1, max_length=100)
    next: str | None = Field(None, min_length=1, max_length=100)


class ModifierOptionOut(BaseModel):
    id: uuid.UUID
    name: str
    price_delta: Decimal

    model_config = {"from_attributes": True}


class ModifierGroupOut(BaseModel):
    id: uuid.UUID
    name: str
    required: bool
    multi: bool
    options: list[ModifierOptionOut] = []

    model_config = {"from_attributes": True}


class ModifierOptionIn(BaseModel):
    name: str
    price_delta: Decimal = 0


class ModifierGroupIn(BaseModel):
    name: str
    required: bool = False
    multi: bool = False
    options: list[ModifierOptionIn] = Field(..., min_length=1)


class MenuItemOut(BaseModel):
    id: uuid.UUID
    venue_id: uuid.UUID
    name: str
    description: str | None
    price: Decimal
    category: str | None
    is_available: bool
    image_url: str | None
    color: str | None = None
    modifier_groups: list[ModifierGroupOut] = []

    model_config = {"from_attributes": True}


class RecipeLineIn(BaseModel):
    ingredient_id: uuid.UUID
    quantity: Decimal = Field(..., gt=0)


class RecipeLineOut(BaseModel):
    ingredient_id: uuid.UUID
    ingredient_name: str
    unit: str
    quantity: Decimal
