from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.db.base import utc_now
from app.models import Record, Role, User
from tests.helpers import TEST_PASSWORD, audit_logs, bearer

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
    [log] = await audit_logs("record_create")
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
        hashed_password=hash_password(TEST_PASSWORD),
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
    [log] = await audit_logs("record_update")
    assert "value" in log.message



async def test_update_logs_only_changed_fields(
    client, db, auth_headers, add_records
):
    (record,) = await add_records({"value": 1, "title": "Same"})

    await client.patch(
        f"{RECORDS}/{record.id}",
        json={"value": 2, "title": "Same"},
        headers=auth_headers[Role.user],
    )

    [log] = await audit_logs("record_update")
    assert log.message == f"user updated record {record.id} (value)"

async def test_other_user_cannot_update(
    client, db, auth_headers, add_records, other_user
):
    (record,) = await add_records({"value": 1})
    token = create_access_token(other_user.id, other_user.role)

    response = await client.patch(
        f"{RECORDS}/{record.id}",
        json={"value": 42},
        headers=bearer(token),
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
    [log] = await audit_logs("record_delete")
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


# ---------- batch delete ----------


async def remaining_ids(db, records: list[Record]) -> set[int]:
    ids = [record.id for record in records]
    return set(await db.scalars(select(Record.id).where(Record.id.in_(ids))))


async def test_owner_can_batch_delete(client, db, auth_headers, add_records):
    records = await add_records({}, {}, {})

    response = await client.post(
        f"{RECORDS}/batch-delete",
        json={"ids": [r.id for r in records]},
        headers=auth_headers[Role.user],
    )

    assert response.status_code == 200
    assert response.json() == {"deleted": 3}
    assert await remaining_ids(db, records) == set()
    for record in records:
        again = await client.get(
            f"{RECORDS}/{record.id}", headers=auth_headers[Role.user]
        )
        assert again.status_code == 404


async def test_batch_delete_with_others_record_deletes_nothing(
    client, db, auth_headers, add_records
):
    own = await add_records({}, {})
    (others,) = await add_records({}, owner=Role.admin)

    response = await client.post(
        f"{RECORDS}/batch-delete",
        json={"ids": [own[0].id, others.id, own[1].id]},
        headers=auth_headers[Role.user],
    )

    assert response.status_code == 403
    assert response.json()["detail"]["ids"] == [others.id]
    assert await remaining_ids(db, [*own, others]) == {
        own[0].id,
        own[1].id,
        others.id,
    }


async def test_batch_delete_with_missing_id_deletes_nothing(
    client, db, auth_headers, add_records
):
    records = await add_records({}, {})

    response = await client.post(
        f"{RECORDS}/batch-delete",
        json={"ids": [records[0].id, 999999, records[1].id]},
        headers=auth_headers[Role.user],
    )

    assert response.status_code == 404
    assert response.json()["detail"]["ids"] == [999999]
    assert await remaining_ids(db, records) == {r.id for r in records}


async def test_admin_can_batch_delete_anyones_records(
    client, db, auth_headers, add_records, other_user
):
    users_record = await add_records({})
    (others_record,) = await add_records({})
    others_record.owner_id = other_user.id
    await db.commit()
    records = [*users_record, others_record]

    response = await client.post(
        f"{RECORDS}/batch-delete",
        json={"ids": [r.id for r in records]},
        headers=auth_headers[Role.admin],
    )

    assert response.status_code == 200
    assert response.json() == {"deleted": 2}
    assert await remaining_ids(db, records) == set()


async def test_viewer_cannot_batch_delete(
    client, db, auth_headers, add_records
):
    records = await add_records({})

    response = await client.post(
        f"{RECORDS}/batch-delete",
        json={"ids": [records[0].id]},
        headers=auth_headers[Role.viewer],
    )

    assert response.status_code == 403
    assert await remaining_ids(db, records) == {records[0].id}


@pytest.mark.parametrize("ids", [[], list(range(1, 102)), [1, 1]])
async def test_batch_delete_rejects_bad_id_lists(client, auth_headers, ids):
    response = await client.post(
        f"{RECORDS}/batch-delete",
        json={"ids": ids},
        headers=auth_headers[Role.admin],
    )

    assert response.status_code == 422


async def test_batch_delete_is_logged(client, db, auth_headers, add_records):
    records = await add_records({}, {}, {})
    ids = [r.id for r in records]

    await client.post(
        f"{RECORDS}/batch-delete",
        json={"ids": ids},
        headers=auth_headers[Role.admin],
    )

    [log] = await audit_logs("record_batch_delete")
    assert log.message == (
        f"admin deleted 3 records: {', '.join(map(str, ids))}"
    )
