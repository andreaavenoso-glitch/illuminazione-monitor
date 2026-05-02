from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


class UserCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str | None = None
    role: str = Field(default="viewer", pattern="^(admin|analyst|viewer)$")


class UserUpdateRequest(BaseModel):
    full_name: str | None = None
    role: str | None = Field(default=None, pattern="^(admin|analyst|viewer)$")
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    role: str
    full_name: str | None = None
    is_active: bool
    last_login_at: datetime | None = None
    created_at: datetime
