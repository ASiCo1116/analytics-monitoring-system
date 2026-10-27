"""Statistics over data records or stored metrics, computed in the database."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.config import settings
from app.models import Metric, Record
from app.schemas.analytics import (
    AnalyticsParams,
    GroupStats,
    Interval,
    Source,
    Stats,
    TrendPoint,
)

# MariaDB DATE_FORMAT patterns giving the start of each interval
BUCKET_FORMATS = {
    Interval.minute: "%Y-%m-%d %H:%i:00",
    Interval.hour: "%Y-%m-%d %H:00:00",
    Interval.day: "%Y-%m-%d 00:00:00",
}
# The same text, parsed back in Python
BUCKET_PARSE_FORMAT = "%Y-%m-%d %H:%M:%S"


def columns(
    params: AnalyticsParams,
) -> tuple[InstrumentedAttribute, InstrumentedAttribute, InstrumentedAttribute]:
    """(value, recorded_at, group) columns of the chosen source."""
    if params.source == Source.records:
        return Record.value, Record.recorded_at, Record.category
    return Metric.value, Metric.recorded_at, Metric.server


def conditions(params: AnalyticsParams) -> list[ColumnElement[bool]]:
    _, recorded_at, _ = columns(params)
    start, end = params.time_range()
    result = []
    if start is not None:
        result.append(recorded_at >= start)
    if end is not None:
        result.append(recorded_at < end)
    if params.source == Source.records:
        if params.category is not None:
            result.append(Record.category == params.category)
    else:
        result.append(Metric.metric == params.metric)
        if params.server is not None:
            result.append(Metric.server == params.server)
    return result


def _aggregates(value: InstrumentedAttribute) -> list:
    return [
        func.count(value).label("count"),
        func.sum(value).label("sum"),
        func.avg(value).label("avg"),
        func.max(value).label("max"),
        func.min(value).label("min"),
    ]


async def summary(db: AsyncSession, params: AnalyticsParams) -> Stats:
    value, _, _ = columns(params)
    query = select(*_aggregates(value)).where(*conditions(params))
    row = (await db.execute(query)).one()
    return Stats.model_validate(row._asdict())


async def groups(db: AsyncSession, params: AnalyticsParams) -> list[GroupStats]:
    """Records by category, metrics by server, sorted by group name."""
    value, _, group = columns(params)
    query = (
        select(group.label("group"), *_aggregates(value))
        .where(*conditions(params))
        .group_by(group)
        .order_by(group)
    )
    rows = (await db.execute(query)).all()
    return [GroupStats.model_validate(row._asdict()) for row in rows]


def _utc_offset() -> str:
    """Current offset of APP_TIMEZONE as "+08:00".

    A fixed offset, because the MariaDB image has no time zone name tables
    (so CONVERT_TZ cannot take "Asia/Taipei"). Zones with daylight saving
    time are off by an hour around the switch.
    """
    offset = datetime.now(ZoneInfo(settings.app_timezone)).utcoffset()
    minutes = int(offset.total_seconds() // 60)
    sign = "-" if minutes < 0 else "+"
    return f"{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"


def _bucket_to_utc(text: str) -> datetime:
    local = datetime.strptime(text, BUCKET_PARSE_FORMAT).replace(
        tzinfo=ZoneInfo(settings.app_timezone)
    )
    return local.astimezone(UTC).replace(tzinfo=None)


async def trend(
    db: AsyncSession, params: AnalyticsParams, interval: Interval
) -> list[TrendPoint]:
    """One point per interval that has data, oldest first.

    Intervals are cut in APP_TIMEZONE (a day is local midnight to
    midnight): the UTC times are converted before formatting.
    """
    value, recorded_at, _ = columns(params)
    local_time = func.convert_tz(recorded_at, "+00:00", _utc_offset())
    bucket = func.date_format(local_time, BUCKET_FORMATS[interval])
    query = (
        select(
            bucket.label("bucket"),
            func.count(value).label("count"),
            func.avg(value).label("avg"),
            func.max(value).label("max"),
            func.min(value).label("min"),
        )
        .where(*conditions(params))
        .group_by(bucket)
        .order_by(bucket)
    )
    rows = (await db.execute(query)).all()
    return [
        TrendPoint(
            bucket=_bucket_to_utc(row.bucket),
            count=row.count,
            avg=row.avg,
            max=row.max,
            min=row.min,
        )
        for row in rows
    ]
