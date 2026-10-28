from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Annotated, Any, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    Field,
    PlainSerializer,
    model_validator,
)

from app.core.timezone import to_naive_utc


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


# Input type for every datetime in a request: converted to naive UTC, the
# form stored in the database. A time without a zone means APP_TIMEZONE.
LocalDatetime = Annotated[datetime, AfterValidator(to_naive_utc)]


class Page[T](BaseModel):
    """Paginated list response."""

    items: list[T]
    total: int
    page: int
    page_size: int

    @classmethod
    def of(cls, items: Sequence[Any], total: int, params: PageParams) -> Self:
        """Build from ORM objects, e.g. Page[UserRead].of(users, n, params)."""
        return cls.model_validate(
            {
                "items": items,
                "total": total,
                "page": params.page,
                "page_size": params.page_size,
            },
            from_attributes=True,
        )


def reject_explicit_nulls(model: BaseModel, *names: str) -> None:
    """For partial updates: these fields may be left out, but not sent as
    null (their columns are NOT NULL)."""
    for name in names:
        if name in model.model_fields_set and getattr(model, name) is None:
            raise ValueError(f"{name} cannot be null")


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

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size
