from datetime import UTC, datetime
from typing import Annotated, Self
from zoneinfo import ZoneInfo

from pydantic import (
    AfterValidator,
    BaseModel,
    Field,
    PlainSerializer,
    model_validator,
)

from app.core.config import settings


def _to_utc_string(value: datetime) -> str:
    # The database stores naive UTC; mark it as UTC before serializing
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


# Output type for every datetime in a response: ISO 8601 ending in "Z".
# Pydantic would otherwise serialize a naive datetime without any time zone.
UtcDatetime = Annotated[
    datetime,
    PlainSerializer(_to_utc_string, return_type=str, when_used="json"),
]


def _to_naive_utc(value: datetime) -> datetime:
    # People write local times (CSV files, the frontend), so a time without
    # a zone means APP_TIMEZONE
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo(settings.app_timezone))
    return value.astimezone(UTC).replace(tzinfo=None)


# Input type for every datetime in a request: converted to naive UTC, the
# form stored in the database.
LocalDatetime = Annotated[datetime, AfterValidator(_to_naive_utc)]


class Page[T](BaseModel):
    """Paginated list response."""

    items: list[T]
    total: int
    page: int
    page_size: int


class TimeRangeParams(BaseModel):
    """Time filter shared by the list and analytics endpoints.

    `start` is inclusive, `end` exclusive; each model says which column.
    """

    start: LocalDatetime | None = None
    end: LocalDatetime | None = None

    @model_validator(mode="after")
    def check_range(self) -> Self:
        if self.start and self.end and self.start > self.end:
            raise ValueError("start must not be later than end")
        return self


class PageParams(BaseModel):
    """Pagination query parameters shared by every list endpoint."""

    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
