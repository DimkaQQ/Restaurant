from pydantic import BaseModel, EmailStr
import uuid


class NetworkCreate(BaseModel):
    name: str
    slug: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    network_id: uuid.UUID

    model_config = {"from_attributes": True}
