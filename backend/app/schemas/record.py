import uuid
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.schemas.common import (
    LocalDatetime,
    PageParams,
    TimeRangeParams,
    UtcDatetime,
    reject_explicit_nulls,
)

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

# Same as the largest page, so one page of the table can be deleted at once
MAX_BATCH_DELETE = 100

SORT_FIELDS = ("recorded_at", "value", "title", "category", "created_at")
# Optional "-" prefix for descending order, e.g. "-recorded_at"
SORT_PATTERN = rf"^-?({'|'.join(SORT_FIELDS)})$"


class RecordCreate(BaseModel):
    """Also used to validate every row of an imported file."""

    title: Title
    value: Value
    category: Category
    recorded_at: LocalDatetime | None = Field(
        None, description="When the data happened; defaults to now"
    )
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
        reject_explicit_nulls(self, "title", "value", "category", "recorded_at")
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


class RecordListParams(PageParams, TimeRangeParams):
    """Query parameters of GET /records; start/end filter recorded_at."""

    category: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    q: str | None = Field(None, description="Keyword searched in the title")
    sort: str = Field("-recorded_at", pattern=SORT_PATTERN)


class ImportResult(BaseModel):
    imported: int


class RecordBatchDelete(BaseModel):
    """Body of POST /records/batch-delete."""

    ids: list[PositiveInt] = Field(min_length=1, max_length=MAX_BATCH_DELETE)

    @field_validator("ids")
    @classmethod
    def no_duplicates(cls, ids: list[int]) -> list[int]:
        if len(set(ids)) != len(ids):
            raise ValueError("ids must not repeat")
        return ids


class BatchDeleteResult(BaseModel):
    deleted: int
