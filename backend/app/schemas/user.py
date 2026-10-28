import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.security import MAX_PASSWORD_BYTES
from app.models import Role
from app.schemas.common import UtcDatetime


class UserCreate(BaseModel):
    """Registration input. Unknown fields such as `role` are ignored."""

    username: str = Field(pattern=r"^[A-Za-z0-9_]{3,50}$")
    email: EmailStr
    password: str = Field(min_length=8)

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, value: str) -> str:
        if len(value.encode()) > MAX_PASSWORD_BYTES:
            raise ValueError(
                f"Password must be at most {MAX_PASSWORD_BYTES} bytes in UTF-8"
            )
        return value


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: str
    role: Role
    is_active: bool
    created_at: UtcDatetime
