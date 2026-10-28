import pytest

from app.models import Role


@pytest.mark.parametrize(
    "path", ["/api/v1/records", "/api/v1/metrics", "/api/v1/admin/logs"]
)
async def test_start_after_end_is_rejected(client, auth_headers, path):
    # Every time-filtered endpoint rejects an inverted range the same way
    # (the analytics endpoints are covered in test_analytics)
    response = await client.get(
        path,
        params={"start": "2026-10-02T00:00:00", "end": "2026-10-01T00:00:00"},
        headers=auth_headers[Role.admin],
    )

    assert response.status_code == 422
