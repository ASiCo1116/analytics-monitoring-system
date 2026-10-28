from datetime import datetime, timedelta

import pytest

from app.core.timezone import to_naive_utc
from app.db.base import utc_now
from app.models import Metric, MetricName, Record, Role

SUMMARY = "/api/v1/analytics/summary"
GROUPS = "/api/v1/analytics/groups"
TREND = "/api/v1/analytics/trend"


def local(text: str) -> datetime:
    """A local (APP_TIMEZONE) time as the naive UTC value stored."""
    return to_naive_utc(datetime.fromisoformat(text))


@pytest.fixture
def add_category_values(db, users):
    async def _add(*rows: tuple[str, float, datetime]) -> None:
        db.add_all(
            Record(
                title=f"{category} {value}",
                value=value,
                category=category,
                recorded_at=recorded_at,
                owner_id=users[Role.user].id,
            )
            for category, value, recorded_at in rows
        )
        await db.commit()

    return _add


@pytest.fixture
def add_metrics(db):
    async def _add(*rows: tuple[str, MetricName, float, datetime]) -> None:
        db.add_all(
            Metric(
                server=server,
                metric=metric,
                value=value,
                threshold=90,
                is_anomaly=value > 90,
                recorded_at=recorded_at,
            )
            for server, metric, value, recorded_at in rows
        )
        await db.commit()

    return _add


@pytest.mark.parametrize("url", [SUMMARY, GROUPS, TREND])
async def test_metrics_need_a_metric(client, auth_headers, url):
    response = await client.get(
        url, params={"source": "metrics"}, headers=auth_headers[Role.viewer]
    )

    assert response.status_code == 422
    assert "metric is required" in response.text


@pytest.mark.parametrize("url", [SUMMARY, GROUPS, TREND])
async def test_start_after_end(client, auth_headers, url):
    response = await client.get(
        url,
        params={
            "source": "records",
            "start": "2026-10-02T00:00:00",
            "end": "2026-10-01T00:00:00",
        },
        headers=auth_headers[Role.viewer],
    )

    assert response.status_code == 422
    assert "start must not be later than end" in response.text


async def test_requires_login(client):
    response = await client.get(SUMMARY, params={"source": "records"})

    assert response.status_code == 401


async def test_records_summary(client, auth_headers, add_category_values):
    now = utc_now()
    await add_category_values(
        ("sales", 10, now), ("sales", 20, now), ("traffic", 30, now)
    )

    response = await client.get(
        SUMMARY, params={"source": "records"}, headers=auth_headers[Role.viewer]
    )

    assert response.status_code == 200
    assert response.json() == {
        "count": 3,
        "sum": 60,
        "avg": 20,
        "max": 30,
        "min": 10,
    }


async def test_summary_filters(client, auth_headers, add_category_values):
    await add_category_values(
        ("sales", 10, local("2026-10-01T09:00")),
        ("sales", 20, local("2026-10-02T09:00")),
        ("traffic", 30, local("2026-10-01T09:00")),
    )

    response = await client.get(
        SUMMARY,
        params={
            "source": "records",
            "category": "sales",
            "start": "2026-10-01T00:00:00",
            "end": "2026-10-02T00:00:00",
        },
        headers=auth_headers[Role.viewer],
    )

    assert response.json()["count"] == 1
    assert response.json()["sum"] == 10


async def test_summary_without_data(client, auth_headers):
    response = await client.get(
        SUMMARY, params={"source": "records"}, headers=auth_headers[Role.viewer]
    )

    assert response.json() == {
        "count": 0,
        "sum": None,
        "avg": None,
        "max": None,
        "min": None,
    }


async def test_records_grouped_by_category(
    client, auth_headers, add_category_values
):
    now = utc_now()
    await add_category_values(
        ("memory", 30, now),
        ("cpu", 10, now),
        ("memory", 50, now),
        ("cpu", 20, now),
        ("memory", 40, now),
    )

    response = await client.get(
        GROUPS, params={"source": "records"}, headers=auth_headers[Role.viewer]
    )

    assert response.json() == [
        {
            "group": "cpu",
            "count": 2,
            "sum": 30,
            "avg": 15,
            "max": 20,
            "min": 10,
        },
        {
            "group": "memory",
            "count": 3,
            "sum": 120,
            "avg": 40,
            "max": 50,
            "min": 30,
        },
    ]


async def test_metrics_grouped_by_server(client, auth_headers, add_metrics):
    now = utc_now()
    await add_metrics(
        ("server-2", MetricName.cpu, 40, now),
        ("server-1", MetricName.cpu, 20, now),
        ("server-1", MetricName.cpu, 30, now),
        ("server-1", MetricName.memory, 99, now),  # another metric
    )

    response = await client.get(
        GROUPS,
        params={"source": "metrics", "metric": "cpu"},
        headers=auth_headers[Role.viewer],
    )

    groups = response.json()
    assert [(g["group"], g["count"], g["avg"]) for g in groups] == [
        ("server-1", 2, 25),
        ("server-2", 1, 40),
    ]


async def test_metrics_default_to_last_24_hours(
    client, auth_headers, add_metrics
):
    now = utc_now()
    await add_metrics(
        ("server-1", MetricName.cpu, 50, now - timedelta(hours=1)),
        ("server-1", MetricName.cpu, 70, now - timedelta(hours=25)),
    )

    response = await client.get(
        SUMMARY,
        params={"source": "metrics", "metric": "cpu", "server": "server-1"},
        headers=auth_headers[Role.viewer],
    )

    assert response.json()["count"] == 1
    assert response.json()["max"] == 50


async def test_hourly_trend(client, auth_headers, add_category_values):
    await add_category_values(
        ("sales", 30, local("2026-10-01T11:05")),
        ("sales", 10, local("2026-10-01T09:10")),
        ("sales", 20, local("2026-10-01T09:40")),
    )

    response = await client.get(
        TREND,
        params={
            "source": "records",
            "interval": "hour",
            "start": "2026-10-01T00:00:00",
            "end": "2026-10-02T00:00:00",
        },
        headers=auth_headers[Role.viewer],
    )

    # Only the hours with data, oldest first; 09:00 Taipei is 01:00 UTC
    assert response.json() == [
        {
            "bucket": "2026-10-01T01:00:00Z",
            "count": 2,
            "avg": 15,
            "max": 20,
            "min": 10,
        },
        {
            "bucket": "2026-10-01T03:00:00Z",
            "count": 1,
            "avg": 30,
            "max": 30,
            "min": 30,
        },
    ]


async def test_days_follow_local_midnight(
    client, auth_headers, add_category_values
):
    # Both on 2026-10-01 in UTC, but on two different days in Taipei
    await add_category_values(
        ("sales", 1, local("2026-10-01T23:30")),
        ("sales", 2, local("2026-10-02T00:30")),
    )

    response = await client.get(
        TREND,
        params={"source": "records", "interval": "day"},
        headers=auth_headers[Role.viewer],
    )

    assert [(p["bucket"], p["count"]) for p in response.json()] == [
        ("2026-09-30T16:00:00Z", 1),
        ("2026-10-01T16:00:00Z", 1),
    ]


async def test_minute_trend(client, auth_headers, add_metrics):
    now = utc_now().replace(second=0, microsecond=0) - timedelta(minutes=5)
    await add_metrics(
        ("server-1", MetricName.memory, 10, now + timedelta(seconds=1)),
        ("server-1", MetricName.memory, 20, now + timedelta(seconds=59)),
        ("server-1", MetricName.memory, 30, now + timedelta(seconds=60)),
    )

    response = await client.get(
        TREND,
        params={"source": "metrics", "metric": "memory", "interval": "minute"},
        headers=auth_headers[Role.viewer],
    )

    assert [p["count"] for p in response.json()] == [2, 1]
