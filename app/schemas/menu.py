from pydantic import BaseModel, Field
from decimal import Decimal
import uuid


class MenuItemCreate(BaseModel):
    name: str
    description: str | None = None
    price: Decimal = Field(..., gt=0)
    category: str | None = None
    is_available: bool = True
    image_url: str | None = None


class MenuItemUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    price: Decimal | None = Field(None, gt=0)
    category: str | None = None
    is_available: bool | None = None
    image_url: str | None = None


class MenuItemOut(BaseModel):
    id: uuid.UUID
    venue_id: uuid.UUID
    name: str
    description: str | None
    price: Decimal
    category: str | None
    is_available: bool
    image_url: str | None

    model_config = {"from_attributes": True}
