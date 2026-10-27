from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas.record import RecordCreate, RecordListParams, RecordUpdate


def valid(**overrides) -> dict:
    return {"title": "Sales", "value": 12.5, "category": "sales"} | overrides


@pytest.mark.parametrize("title", ["", "   "])
def test_blank_title_is_rejected(title):
    with pytest.raises(ValidationError):
        RecordCreate(**valid(title=title))


def test_title_is_trimmed():
    assert RecordCreate(**valid(title="  Sales  ")).title == "Sales"


@pytest.mark.parametrize("value", ["abc", "nan", float("inf")])
def test_invalid_value_is_rejected(value):
    with pytest.raises(ValidationError):
        RecordCreate(**valid(value=value))


def test_time_without_zone_means_app_timezone():
    # Default APP_TIMEZONE is Asia/Taipei (UTC+8)
    record = RecordCreate(**valid(recorded_at="2026-10-01T08:00:00"))

    assert record.recorded_at == datetime(2026, 10, 1, 0, 0)


def test_time_with_zone_is_converted_to_utc():
    record = RecordCreate(**valid(recorded_at="2026-10-01T08:00:00+00:00"))

    assert record.recorded_at == datetime(2026, 10, 1, 8, 0)


def test_update_cannot_null_required_field():
    with pytest.raises(ValidationError):
        RecordUpdate(title=None)

    # description may be cleared
    assert RecordUpdate(description=None).model_fields_set == {"description"}


@pytest.mark.parametrize("sort", ["value", "-recorded_at", "category"])
def test_allowed_sort_fields(sort):
    assert RecordListParams(sort=sort).sort == sort


@pytest.mark.parametrize("sort", ["password", "-owner_id", "value;drop"])
def test_disallowed_sort_field_is_rejected(sort):
    with pytest.raises(ValidationError):
        RecordListParams(sort=sort)


def test_page_size_limit():
    with pytest.raises(ValidationError):
        RecordListParams(page_size=101)
