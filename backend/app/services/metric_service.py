"""Queries over the stored realtime metrics."""

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Metric
from app.schemas.metric import MetricListParams


def _filtered(query: Select, params: MetricListParams) -> Select:
    if params.server is not None:
        query = query.where(Metric.server == params.server)
    if params.metric is not None:
        query = query.where(Metric.metric == params.metric)
    if params.start is not None:
        query = query.where(Metric.recorded_at >= params.start)
    if params.end is not None:
        query = query.where(Metric.recorded_at < params.end)
    if params.anomaly_only:
        query = query.where(Metric.is_anomaly.is_(True))
    return query


async def list_metrics(
    db: AsyncSession, params: MetricListParams
) -> tuple[list[Metric], int]:
    total = await db.scalar(
        _filtered(select(func.count()).select_from(Metric), params)
    )
    query = (
        _filtered(select(Metric), params)
        # Newest first; id breaks ties within the same second
        .order_by(Metric.recorded_at.desc(), Metric.id.desc())
        .offset((params.page - 1) * params.page_size)
        .limit(params.page_size)
    )
    metrics = (await db.scalars(query)).all()
    return list(metrics), total
