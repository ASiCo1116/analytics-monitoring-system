"""Time conversion between the API (UTC, "Z") and APP_TIMEZONE."""

from datetime import date, datetime, time

from lib.config import TZ


def to_local(value: str) -> datetime:
    """API timestamp ("...Z") as a naive local time for tables and charts."""
    parsed = datetime.fromisoformat(value)
    return parsed.astimezone(TZ).replace(tzinfo=None)


def local_param(day: date | None, at: time = time.min) -> str | None:
    """A local time for a query parameter.

    Sent without a zone: the backend reads it as APP_TIMEZONE.
    """
    if day is None:
        return None
    return datetime.combine(day, at).isoformat()
