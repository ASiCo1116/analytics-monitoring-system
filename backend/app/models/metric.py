from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Double, Enum, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MetricName(StrEnum):
    cpu = "cpu"
    memory = "memory"
    temperature = "temperature"


# Units are known by the code and not stored
METRIC_UNITS = {
    MetricName.cpu: "%",
    MetricName.memory: "%",
    MetricName.temperature: "°C",
}


class Metric(Base):
    """A simulated server metric sample, persisted in batches."""

    __tablename__ = "metrics"
    __table_args__ = (
        # Analytics queries
        Index("ix_metrics_metric_recorded_at", "metric", "recorded_at"),
        # History queries
        Index(
            "ix_metrics_server_metric_recorded_at",
            "server",
            "metric",
            "recorded_at",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    server: Mapped[str] = mapped_column(String(50))
    metric: Mapped[MetricName] = mapped_column(
        Enum(MetricName, name="metric_name")
    )
    value: Mapped[float] = mapped_column(Double)
    # Threshold at generation time, so changing it later does not rewrite
    # history
    threshold: Mapped[float] = mapped_column(Double)
    is_anomaly: Mapped[bool]
    recorded_at: Mapped[datetime] = mapped_column(index=True)

    @property
    def unit(self) -> str:
        return METRIC_UNITS[self.metric]
