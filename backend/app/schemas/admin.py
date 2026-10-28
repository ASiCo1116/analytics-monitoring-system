import uuid
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import LogLevel, Role
from app.realtime.buffer import FlushReason
from app.schemas.common import (
    PageParams,
    TimeRangeParams,
    UtcDatetime,
    reject_explicit_nulls,
)


class UserListParams(PageParams):
    """Query parameters of GET /admin/users."""

    role: Role | None = None
    is_active: bool | None = None
    q: str | None = Field(None, description="Keyword searched in the username")


class UserAdminUpdate(BaseModel):
    """Only the fields sent are changed."""

    role: Role | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def fields_not_null(self) -> Self:
        reject_explicit_nulls(self, "role", "is_active")
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
    size: int = Field(description="Configured pool size")
    checked_out: int = Field(description="Connections in use")
    idle: int = Field(description="Open connections waiting in the pool")
    overflow: int = Field(description="Extra connections beyond size")


class BufferStatus(BaseModel):
    pending: int = Field(description="Metrics waiting to be written")
    last_flush_at: UtcDatetime | None
    last_flush_count: int | None
    last_flush_reason: FlushReason | None


class DbStatus(BaseModel):
    connected: bool
    response_ms: float
    pool: PoolStatus
    tables: dict[str, int] = Field(description="Row count per table")
    buffer: BufferStatus
