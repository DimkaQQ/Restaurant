from pydantic import BaseModel
from datetime import datetime
import uuid


class GuestOut(BaseModel):
    id: uuid.UUID
    network_id: uuid.UUID
    telegram_id: int | None
    name: str | None
    phone: str | None
    total_points: int
    total_visits: int
    language: str = 'ru'
    preferred_venue_id: uuid.UUID | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class GuestCreate(BaseModel):
    network_id: uuid.UUID
    telegram_id: int | None = None
    name: str | None = None
    phone: str | None = None
    language: str = 'ru'
    preferred_venue_id: uuid.UUID | None = None
