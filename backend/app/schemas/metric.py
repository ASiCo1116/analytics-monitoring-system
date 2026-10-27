from pydantic import BaseModel, ConfigDict

from app.models import MetricName
from app.schemas.common import LocalDatetime, PageParams, UtcDatetime


class MetricSample(BaseModel):
    """One generated metric value, as pushed over the WebSocket."""

    model_config = ConfigDict(from_attributes=True)

    server: str
    metric: MetricName
    value: float
    unit: str
    threshold: float
    is_anomaly: bool
    recorded_at: UtcDatetime


class MetricRead(MetricSample):
    """A metric stored in the database."""

    id: int


class MetricListParams(PageParams):
    """Query parameters of GET /metrics."""

    server: str | None = None
    metric: MetricName | None = None
    # recorded_at range: start inclusive, end exclusive
    start: LocalDatetime | None = None
    end: LocalDatetime | None = None
    anomaly_only: bool = False
