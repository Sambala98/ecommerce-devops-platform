from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole


class UserCreate(BaseModel):
    email: EmailStr
    name: str
    password: str = Field(
        min_length=8,
        max_length=128,
    )
    model_config = ConfigDict(
        extra="forbid",
    )


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    name: str
    role: UserRole
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )