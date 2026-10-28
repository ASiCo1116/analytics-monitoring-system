import uuid
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from app.schemas.common import LocalDatetime, PageParams, UtcDatetime

# Leading/trailing spaces are removed first, so "   " counts as empty
Title = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
Category = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
]
Description = Annotated[str, StringConstraints(max_length=1000)]
# NaN / infinity cannot be stored in a MariaDB DOUBLE
Value = Annotated[float, Field(allow_inf_nan=False)]

SORT_FIELDS = ("recorded_at", "value", "title", "category", "created_at")
# Optional "-" prefix for descending order, e.g. "-recorded_at"
SORT_PATTERN = rf"^-?({'|'.join(SORT_FIELDS)})$"


class RecordCreate(BaseModel):
    """Also used to validate every row of an imported file."""

    title: Title
    value: Value
    category: Category
    # Optional: the current time is used when missing
    recorded_at: LocalDatetime | None = None
    description: Description | None = None


class RecordUpdate(BaseModel):
    """Partial update: only the fields sent are changed."""

    title: Title | None = None
    value: Value | None = None
    category: Category | None = None
    recorded_at: LocalDatetime | None = None
    description: Description | None = None

    @model_validator(mode="after")
    def required_fields_not_null(self) -> Self:
        # description may be cleared with null; the other columns are NOT NULL
        for name in ("title", "value", "category", "recorded_at"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class RecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    value: float
    category: str
    description: str | None
    recorded_at: UtcDatetime
    owner_id: uuid.UUID
    owner_username: str
    created_at: UtcDatetime
    updated_at: UtcDatetime


class RecordListParams(PageParams):
    """Query parameters of GET /records."""

    category: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    # recorded_at range: start inclusive, end exclusive
    start: LocalDatetime | None = None
    end: LocalDatetime | None = None
    # Keyword searched in the title
    q: str | None = None
    sort: str = Field("-recorded_at", pattern=SORT_PATTERN)


class ImportResult(BaseModel):
    imported: int
