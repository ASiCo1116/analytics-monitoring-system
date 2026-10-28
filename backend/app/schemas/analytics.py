from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Self

from pydantic import AfterValidator, BaseModel, Field, model_validator

from app.db.base import utc_now
from app.models import MetricName
from app.schemas.common import TimeRangeParams, UtcDatetime

# Without a start time, metrics are limited to the last 24 hours: about
# 780,000 rows are generated per day
METRICS_DEFAULT_WINDOW = timedelta(hours=24)


class Source(StrEnum):
    records = "records"
    metrics = "metrics"


class Interval(StrEnum):
    minute = "minute"
    hour = "hour"
    day = "day"


class AnalyticsParams(TimeRangeParams):
    """Filters shared by every analytics endpoint.

    start/end filter recorded_at.
    """

    source: Source
    category: str | None = Field(None, description="source=records only")
    metric: MetricName | None = Field(
        None, description="Required for source=metrics"
    )
    server: str | None = Field(None, description="source=metrics only")

    @model_validator(mode="after")
    def check_filters(self) -> Self:
        # Different metrics have different units, so they are never mixed
        if self.source == Source.metrics and self.metric is None:
            raise ValueError("metric is required when source is metrics")
        return self

    def time_range(self) -> tuple[datetime | None, datetime | None]:
        """(start, end) to query, with the metrics default applied."""
        start = self.start
        if self.source == Source.metrics and start is None:
            start = (self.end or utc_now()) - METRICS_DEFAULT_WINDOW
        return start, self.end


class TrendParams(AnalyticsParams):
    interval: Interval = Interval.hour


# SUM and AVG over DOUBLE values carry floating point noise
# (400301.00000000023); 4 decimals keep every meaningful digit
Rounded = Annotated[float, AfterValidator(lambda value: round(value, 4))]


class Stats(BaseModel):
    """Aggregates over the filtered values; null when there is no data."""

    count: int
    sum: Rounded | None
    avg: Rounded | None
    max: float | None
    min: float | None


class GroupStats(Stats):
    group: str = Field(
        description="Category for records, server for metrics"
    )


class TrendPoint(BaseModel):
    bucket: UtcDatetime = Field(
        description="Start of the interval; intervals follow APP_TIMEZONE"
    )
    count: int
    avg: Rounded
    max: float
    min: float
