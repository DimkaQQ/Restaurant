from pydantic import BaseModel, Field
from decimal import Decimal
from datetime import datetime
import uuid


class OrderItemCreate(BaseModel):
    # None = free-form line ("Прочее" on the POS): staff types a name and a
    # price for something not in the menu. Only staff endpoints allow it.
    menu_item_id: uuid.UUID | None = None
    quantity: int = Field(..., ge=1, le=999)  # fat-finger/DoS guard
    comment: str | None = Field(None, max_length=500)
    # Free-form line fields (used only when menu_item_id is None)
    name: str | None = Field(None, max_length=100)
    price: Decimal | None = Field(None, ge=0, le=10_000_000)
    # Chosen modifier option ids — validated server-side against the item's
    # groups; their price deltas are added to the line price.
    modifier_option_ids: list[uuid.UUID] = []


class OrderCreate(BaseModel):
    venue_id: uuid.UUID
    items: list[OrderItemCreate] = Field(..., min_length=1)
    notes: str | None = Field(None, max_length=1000)
    table_number: str | None = Field(None, max_length=20)  # matches the DB column
    table_id: uuid.UUID | None = None
    source: str | None = None
    # Counter-service flow: take payment at order time (cash/card/mobile).
    # None = pay later (table service) — payment recorded separately.
    payment_method: str | None = None
    # Idempotency key for offline-queued orders (client-generated UUID).
    client_order_id: str | None = Field(None, max_length=64)
    # Staff-applied discount (POS only — the online endpoint never passes these).
    discount_type: str | None = None   # percent | amount
    discount_value: Decimal | None = Field(None, gt=0)
    # Guest promo code (validated server-side against the network's codes).
    promo_code: str | None = Field(None, max_length=50)


class OrderItemOut(BaseModel):
    id: uuid.UUID
    menu_item_id: uuid.UUID | None
    quantity: int
    price: Decimal
    name: str
    comment: str | None = None
    modifiers: str | None = None

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
    subtotal_amount: Decimal | None = None
    discount_type: str | None = None
    discount_value: Decimal | None = None
    promo_code: str | None = None
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
    waiter_user_id: uuid.UUID | None = None
    waiter_name: str | None = None
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
