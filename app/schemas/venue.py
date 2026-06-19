from pydantic import BaseModel
import uuid
from datetime import datetime


class VenueCreate(BaseModel):
    name: str
    address: str | None = None
    telegram_bot_token: str | None = None


class VenueUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    telegram_bot_token: str | None = None
    is_active: bool | None = None


class VenueOut(BaseModel):
    id: uuid.UUID
    network_id: uuid.UUID
    name: str
    address: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
