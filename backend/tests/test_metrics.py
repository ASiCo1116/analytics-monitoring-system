from datetime import datetime, timedelta

import pytest

from app.models import Metric, MetricName, Role

METRICS = "/api/v1/metrics"
BASE_TIME = datetime(2026, 10, 1, 0, 0, 0)  # naive UTC, as stored


@pytest.fixture
async def stored_metrics(db) -> list[Metric]:
    """3 servers x 3 metrics x 4 seconds; server-2 cpu spikes at second 2."""
    metrics = []
    for second in range(4):
        for server in ("server-1", "server-2", "server-3"):
            for metric in MetricName:
                value = 50.0
                if server == "server-2" and metric == MetricName.cpu:
                    value = 95.0 if second == 2 else 60.0
                metrics.append(
                    Metric(
                        server=server,
                        metric=metric,
                        value=value,
                        threshold=90,
                        is_anomaly=value > 90,
                        recorded_at=BASE_TIME + timedelta(seconds=second),
                    )
                )
    db.add_all(metrics)
    await db.commit()
    return metrics


async def test_admin_lists_newest_first(client, auth_headers, stored_metrics):
    response = await client.get(
        METRICS, params={"page_size": 5}, headers=auth_headers[Role.admin]
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 36
    assert len(body["items"]) == 5
    times = [item["recorded_at"] for item in body["items"]]
    assert times == sorted(times, reverse=True)
    assert times[0] == "2026-10-01T00:00:03Z"
    assert body["items"][0]["unit"] in {"%", "°C"}


async def test_anomalies_of_one_server(client, auth_headers, stored_metrics):
    response = await client.get(
        METRICS,
        params={"server": "server-2", "anomaly_only": "true"},
        headers=auth_headers[Role.admin],
    )

    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["server"] == "server-2"
    assert items[0]["metric"] == "cpu"
    assert items[0]["value"] == 95.0
    assert items[0]["is_anomaly"] is True


async def test_metric_and_time_range(client, auth_headers, stored_metrics):
    # Local time (Asia/Taipei, UTC+8): start inclusive, end exclusive
    response = await client.get(
        METRICS,
        params={
            "metric": "temperature",
            "start": "2026-10-01T08:00:01",
            "end": "2026-10-01T08:00:03",
        },
        headers=auth_headers[Role.admin],
    )

    body = response.json()
    assert body["total"] == 6  # 3 servers x seconds 1 and 2
    assert {item["metric"] for item in body["items"]} == {"temperature"}
    assert {item["recorded_at"] for item in body["items"]} == {
        "2026-10-01T00:00:01Z",
        "2026-10-01T00:00:02Z",
    }


async def test_unknown_metric_is_rejected(client, auth_headers):
    response = await client.get(
        METRICS, params={"metric": "disk"}, headers=auth_headers[Role.admin]
    )

    assert response.status_code == 422


@pytest.mark.parametrize("role", [Role.user, Role.viewer])
async def test_only_admin(client, auth_headers, role):
    response = await client.get(METRICS, headers=auth_headers[role])

    assert response.status_code == 403


async def test_requires_login(client):
    response = await client.get(METRICS)

    assert response.status_code == 401
