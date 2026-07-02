from pydantic import BaseModel
import uuid
from datetime import datetime


class VenueCreate(BaseModel):
    name: str
    address: str | None = None
    telegram_bot_token: str | None = None
    city: str | None = None
    gis_url: str | None = None
    manager_telegram_id: int | None = None


class VenueUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    telegram_bot_token: str | None = None
    is_active: bool | None = None
    city: str | None = None
    gis_url: str | None = None
    manager_telegram_id: int | None = None
    fiscal_provider: str | None = None
    fiscal_api_key: str | None = None
    fiscal_login: str | None = None
    fiscal_password: str | None = None
    fiscal_cashbox_number: str | None = None


class VenueOut(BaseModel):
    id: uuid.UUID
    network_id: uuid.UUID
    name: str
    address: str | None
    city: str | None = None
    gis_url: str | None = None
    manager_telegram_id: int | None = None
    is_active: bool
    created_at: datetime
    fiscal_provider: str | None = None
    fiscal_cashbox_number: str | None = None

    model_config = {"from_attributes": True}
