import uuid
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from app.models import LogLevel, Role
from app.realtime.buffer import FlushReason
from app.schemas.common import PageParams, TimeRangeParams, UtcDatetime


class UserListParams(PageParams):
    """Query parameters of GET /admin/users."""

    role: Role | None = None
    is_active: bool | None = None
    # Keyword searched in the username
    q: str | None = None


class UserAdminUpdate(BaseModel):
    """Only the fields sent are changed."""

    role: Role | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def fields_not_null(self) -> Self:
        for name in ("role", "is_active"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class LogListParams(PageParams, TimeRangeParams):
    """Query parameters of GET /admin/logs; start/end filter created_at."""

    level: LogLevel | None = None
    action: str | None = None
    user_id: uuid.UUID | None = None


class SystemLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    level: LogLevel
    action: str
    message: str
    user_id: uuid.UUID | None
    username: str | None
    ip_address: str | None
    created_at: UtcDatetime


class PoolStatus(BaseModel):
    size: int  # configured pool size
    checked_out: int  # in use
    idle: int  # open and waiting in the pool
    overflow: int  # extra connections beyond size


class BufferStatus(BaseModel):
    pending: int  # metrics waiting to be written
    last_flush_at: UtcDatetime | None
    last_flush_count: int | None
    last_flush_reason: FlushReason | None


class DbStatus(BaseModel):
    connected: bool
    response_ms: float
    pool: PoolStatus
    # Row count per table
    tables: dict[str, int]
    buffer: BufferStatus
