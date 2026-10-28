"""Conversions between stored naive UTC and APP_TIMEZONE local time.

The database stores naive UTC. People read and write local time: forms,
CSV files and Excel sheets carry no zone, so a time without one means
APP_TIMEZONE.
"""

from datetime import UTC, datetime

from app.core.config import settings


def to_naive_utc(value: datetime) -> datetime:
    """An aware time, or a naive one in APP_TIMEZONE, as naive UTC."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=settings.tz)
    return value.astimezone(UTC).replace(tzinfo=None)


def to_naive_local(value: datetime) -> datetime:
    """A stored naive UTC time as naive APP_TIMEZONE time."""
    local = value.replace(tzinfo=UTC).astimezone(settings.tz)
    return local.replace(tzinfo=None)
