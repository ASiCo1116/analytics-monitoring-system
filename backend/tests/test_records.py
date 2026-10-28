from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.db.base import utc_now
from app.models import Record, Role, SystemLog, User

RECORDS = "/api/v1/records"


@pytest.fixture
def add_records(db, users):
    """Insert records directly; returns a coroutine taking dict overrides."""

    async def add(*rows: dict, owner: Role = Role.user) -> list[Record]:
        records = [
            Record(
                title=row.get("title", f"Record {i}"),
                value=row.get("value", float(i)),
                category=row.get("category", "sales"),
                recorded_at=row.get(
                    "recorded_at", datetime(2026, 10, 1) + timedelta(hours=i)
                ),
                owner_id=users[owner].id,
            )
            for i, row in enumerate(rows)
        ]
        db.add_all(records)
        await db.commit()
        return records

    return add


# ---------- create ----------


async def test_create_record(client, db, users, auth_headers):
    before = utc_now()

    response = await client.post(
        RECORDS,
        json={"title": "Daily sales", "value": 12.5, "category": "sales"},
        headers=auth_headers[Role.user],
    )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Daily sales"
    assert body["owner_id"] == str(users[Role.user].id)
    assert body["owner_username"] == "user"
    recorded_at = datetime.fromisoformat(body["recorded_at"])
    assert recorded_at.replace(tzinfo=None) >= before.replace(microsecond=0)
    assert body["recorded_at"].endswith("Z")
    log = await db.scalar(
        select(SystemLog).where(SystemLog.action == "record_create")
    )
    assert log is not None


async def test_create_record_validation(client, auth_headers):
    blank_title = await client.post(
        RECORDS,
        json={"title": " ", "value": 1, "category": "sales"},
        headers=auth_headers[Role.user],
    )
    bad_value = await client.post(
        RECORDS,
        json={"title": "A", "value": "abc", "category": "sales"},
        headers=auth_headers[Role.user],
    )

    assert blank_title.status_code == 422
    assert blank_title.json()["detail"][0]["loc"][-1] == "title"
    assert bad_value.status_code == 422
    assert bad_value.json()["detail"][0]["loc"][-1] == "value"


async def test_viewer_cannot_create(client, auth_headers):
    response = await client.post(
        RECORDS,
        json={"title": "A", "value": 1, "category": "sales"},
        headers=auth_headers[Role.viewer],
    )

    assert response.status_code == 403


# ---------- list ----------


async def test_pagination(client, auth_headers, add_records):
    await add_records(*[{} for _ in range(45)])

    response = await client.get(
        RECORDS,
        params={"page": 3, "page_size": 20},
        headers=auth_headers[Role.viewer],
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 5
    assert body["total"] == 45
    assert body["page"] == 3
    assert body["page_size"] == 20
    assert body["items"][0]["owner_username"] == "user"


async def test_filter_and_sort(client, auth_headers, add_records):
    await add_records(
        {"category": "cpu", "value": 40},
        {"category": "cpu", "value": 50},
        {"category": "cpu", "value": 90},
        {"category": "memory", "value": 95},
    )

    response = await client.get(
        RECORDS,
        params={"category": "cpu", "min_value": 50, "sort": "-value"},
        headers=auth_headers[Role.viewer],
    )

    values = [item["value"] for item in response.json()["items"]]
    assert values == [90, 50]


async def test_filter_by_time_range_and_keyword(
    client, auth_headers, add_records
):
    await add_records(
        {"title": "Morning sales", "recorded_at": datetime(2026, 10, 1, 0)},
        {"title": "Evening sales", "recorded_at": datetime(2026, 10, 1, 12)},
        {"title": "Evening traffic", "recorded_at": datetime(2026, 10, 2, 0)},
    )

    response = await client.get(
        RECORDS,
        # Times with a zone; the end is exclusive
        params={
            "start": "2026-10-01T06:00:00Z",
            "end": "2026-10-02T00:00:00Z",
            "q": "sales",
        },
        headers=auth_headers[Role.viewer],
    )

    titles = [item["title"] for item in response.json()["items"]]
    assert titles == ["Evening sales"]


async def test_disallowed_sort_field(client, auth_headers):
    response = await client.get(
        RECORDS, params={"sort": "password"}, headers=auth_headers[Role.viewer]
    )

    assert response.status_code == 422


async def test_list_requires_login(client):
    response = await client.get(RECORDS)

    assert response.status_code == 401


# ---------- single record and categories ----------


async def test_get_record(client, auth_headers, add_records):
    (record,) = await add_records({"title": "One"})

    found = await client.get(
        f"{RECORDS}/{record.id}", headers=auth_headers[Role.viewer]
    )
    missing = await client.get(
        f"{RECORDS}/{record.id + 1000}", headers=auth_headers[Role.viewer]
    )

    assert found.status_code == 200
    assert found.json()["title"] == "One"
    assert missing.status_code == 404


async def test_categories_are_distinct_and_sorted(
    client, auth_headers, add_records
):
    await add_records(
        {"category": "traffic"},
        {"category": "sales"},
        {"category": "traffic"},
        {"category": "inventory"},
    )

    response = await client.get(
        f"{RECORDS}/categories", headers=auth_headers[Role.viewer]
    )

    assert response.json() == ["inventory", "sales", "traffic"]


# ---------- update and delete ----------


@pytest.fixture
async def other_user(db):
    """A second User-role account, to test editing someone else's record."""
    user = User(
        username="other",
        email="other@example.com",
        hashed_password=hash_password("Password123"),
        role=Role.user,
    )
    db.add(user)
    await db.commit()
    return user


async def test_owner_can_update(client, db, auth_headers, add_records):
    (record,) = await add_records({"value": 1})
    old_updated_at = record.updated_at

    response = await client.patch(
        f"{RECORDS}/{record.id}",
        json={"value": 42},
        headers=auth_headers[Role.user],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["value"] == 42
    assert body["title"] == record.title  # untouched fields stay
    assert datetime.fromisoformat(body["updated_at"]).replace(
        tzinfo=None
    ) >= old_updated_at.replace(microsecond=0)
    log = await db.scalar(
        select(SystemLog).where(SystemLog.action == "record_update")
    )
    assert "value" in log.message


async def test_other_user_cannot_update(
    client, db, auth_headers, add_records, other_user
):
    (record,) = await add_records({"value": 1})
    token = create_access_token(other_user.id, other_user.role)

    response = await client.patch(
        f"{RECORDS}/{record.id}",
        json={"value": 42},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    await db.refresh(record)
    assert record.value == 1


async def test_admin_can_update_any_record(client, auth_headers, add_records):
    (record,) = await add_records({"value": 1})

    response = await client.patch(
        f"{RECORDS}/{record.id}",
        json={"title": "Fixed by admin"},
        headers=auth_headers[Role.admin],
    )

    assert response.status_code == 200
    # The owner does not change
    assert response.json()["owner_username"] == "user"


async def test_update_cannot_change_owner_or_null_title(
    client, users, auth_headers, add_records
):
    (record,) = await add_records({})

    owner = await client.patch(
        f"{RECORDS}/{record.id}",
        json={"owner_id": str(users[Role.admin].id)},
        headers=auth_headers[Role.user],
    )
    null_title = await client.patch(
        f"{RECORDS}/{record.id}",
        json={"title": None},
        headers=auth_headers[Role.user],
    )

    assert owner.json()["owner_username"] == "user"
    assert null_title.status_code == 422


async def test_owner_can_delete(client, db, auth_headers, add_records):
    (record,) = await add_records({})

    deleted = await client.delete(
        f"{RECORDS}/{record.id}", headers=auth_headers[Role.user]
    )
    again = await client.get(
        f"{RECORDS}/{record.id}", headers=auth_headers[Role.user]
    )

    assert deleted.status_code == 204
    assert again.status_code == 404
    log = await db.scalar(
        select(SystemLog).where(SystemLog.action == "record_delete")
    )
    assert log is not None


async def test_viewer_cannot_delete(client, auth_headers, add_records):
    (record,) = await add_records({})

    response = await client.delete(
        f"{RECORDS}/{record.id}", headers=auth_headers[Role.viewer]
    )

    assert response.status_code == 403


async def test_update_missing_record(client, auth_headers):
    response = await client.patch(
        f"{RECORDS}/999999", json={"value": 1}, headers=auth_headers[Role.user]
    )

    assert response.status_code == 404
