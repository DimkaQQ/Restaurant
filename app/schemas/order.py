from pydantic import BaseModel
from decimal import Decimal
from datetime import datetime
import uuid


class OrderItemCreate(BaseModel):
    menu_item_id: uuid.UUID
    quantity: int


class OrderCreate(BaseModel):
    venue_id: uuid.UUID
    items: list[OrderItemCreate]
    notes: str | None = None


class OrderItemOut(BaseModel):
    id: uuid.UUID
    menu_item_id: uuid.UUID | None
    quantity: int
    price: Decimal
    name: str

    model_config = {"from_attributes": True}


class GuestShort(BaseModel):
    id: uuid.UUID
    name: str | None
    phone: str | None

    model_config = {"from_attributes": True}


class OrderOut(BaseModel):
    id: uuid.UUID
    venue_id: uuid.UUID
    guest_id: uuid.UUID
    status: str
    total_amount: Decimal
    points_earned: int
    notes: str | None
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemOut] = []
    guest: GuestShort | None = None

    model_config = {"from_attributes": True}


class OrderStatusUpdate(BaseModel):
    status: str
