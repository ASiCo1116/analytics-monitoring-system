"""Time conversion between the API (UTC, "Z") and APP_TIMEZONE."""

from datetime import date, datetime, time, timedelta

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


def local_end_param(day: date | None) -> str | None:
    """The end of a date range picked on screen, for a query parameter.

    The day is inclusive on screen; the API end is exclusive, so this is
    the next local midnight.
    """
    return local_param(day + timedelta(days=1)) if day else None
