from pydantic import BaseModel, Field
from decimal import Decimal
from datetime import datetime
import uuid


class OrderItemCreate(BaseModel):
    menu_item_id: uuid.UUID
    quantity: int = Field(..., ge=1)
    comment: str | None = None


class OrderCreate(BaseModel):
    venue_id: uuid.UUID
    items: list[OrderItemCreate] = Field(..., min_length=1)
    notes: str | None = None
    table_number: str | None = None
    table_id: uuid.UUID | None = None
    source: str | None = None
    # Counter-service flow: take payment at order time (cash/card/mobile).
    # None = pay later (table service) — payment recorded separately.
    payment_method: str | None = None
    # Idempotency key for offline-queued orders (client-generated UUID).
    client_order_id: str | None = Field(None, max_length=64)


class OrderItemOut(BaseModel):
    id: uuid.UUID
    menu_item_id: uuid.UUID | None
    quantity: int
    price: Decimal
    name: str
    comment: str | None = None

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
    table_number: str | None = None
    table_id: uuid.UUID | None = None
    source: str | None = None
    created_at: datetime
    updated_at: datetime
    payment_status: str = "unpaid"
    paid_at: datetime | None = None
    payment_method: str | None = None
    fiscal_status: str | None = None
    fiscal_check_number: str | None = None
    fiscal_ticket_url: str | None = None
    fiscal_error: str | None = None
    items: list[OrderItemOut] = []
    guest: GuestShort | None = None

    model_config = {"from_attributes": True}


class OrderStatusUpdate(BaseModel):
    status: str
    payment_method: str | None = None
