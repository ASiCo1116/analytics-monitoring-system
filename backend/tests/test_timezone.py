from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.timezone import to_naive_local, to_naive_utc

# Default APP_TIMEZONE is Asia/Taipei (UTC+8, no daylight saving time)
STORED = datetime(2026, 10, 1, 0, 30)
LOCAL = datetime(2026, 10, 1, 8, 30)


def test_naive_time_means_app_timezone():
    assert to_naive_utc(LOCAL) == STORED


def test_aware_time_keeps_its_own_zone():
    utc_minus_5 = timezone(timedelta(hours=-5))

    assert to_naive_utc(datetime(2026, 9, 30, 19, 30, tzinfo=utc_minus_5)) == (
        STORED
    )
    assert to_naive_utc(STORED.replace(tzinfo=UTC)) == STORED


def test_stored_time_to_local_round_trip():
    assert to_naive_local(STORED) == LOCAL
    assert to_naive_utc(to_naive_local(STORED)) == STORED


@pytest.mark.parametrize("name", ["Asia/Taipe", "", "not a zone"])
def test_unknown_app_timezone_fails_at_startup(name):
    with pytest.raises(ValidationError, match="unknown time zone"):
        Settings(app_timezone=name)
