from pydantic import BaseModel, EmailStr, Field
import uuid


class NetworkCreate(BaseModel):
    name: str
    slug: str
    email: EmailStr
    password: str = Field(..., min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    totp_code: str | None = None  # required when the account has 2FA enabled


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    password: str = Field(..., min_length=8)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    network_id: uuid.UUID

    model_config = {"from_attributes": True}
