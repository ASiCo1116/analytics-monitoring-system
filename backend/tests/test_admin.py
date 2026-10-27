import uuid

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import LogLevel, Role, SystemLog, User
from app.services import audit_service
from tests.conftest import TEST_PASSWORD

USERS = "/api/v1/admin/users"
LOGS = "/api/v1/admin/logs"
DB_STATUS = "/api/v1/admin/db-status"


async def logs_with_action(action: str) -> list[SystemLog]:
    # A new session sees rows committed by the request
    async with SessionLocal() as session:
        return list(
            await session.scalars(
                select(SystemLog).where(SystemLog.action == action)
            )
        )


async def current_state(user: User) -> tuple[Role, bool]:
    async with SessionLocal() as session:
        fresh = await session.get(User, user.id)
        return fresh.role, fresh.is_active


@pytest.mark.parametrize("role", [Role.user, Role.viewer])
@pytest.mark.parametrize("url", [USERS, LOGS, DB_STATUS])
async def test_admin_only(client, auth_headers, role, url):
    response = await client.get(url, headers=auth_headers[role])

    assert response.status_code == 403


async def test_list_users(client, auth_headers):
    response = await client.get(USERS, headers=auth_headers[Role.admin])

    body = response.json()
    assert body["total"] == 3
    assert [u["username"] for u in body["items"]] == ["admin", "user", "viewer"]
    assert set(body["items"][0]) == {
        "id",
        "username",
        "email",
        "role",
        "is_active",
        "created_at",
    }


async def test_list_users_filters(client, auth_headers):
    response = await client.get(
        USERS,
        params={"role": "viewer", "is_active": "true", "q": "view"},
        headers=auth_headers[Role.admin],
    )

    assert [u["username"] for u in response.json()["items"]] == ["viewer"]


async def test_role_change_applies_immediately(client, users, auth_headers):
    target = users[Role.user]
    record = {"title": "A", "value": 1, "category": "sales"}
    before = await client.post(
        "/api/v1/records", json=record, headers=auth_headers[Role.user]
    )
    assert before.status_code == 201

    response = await client.patch(
        f"{USERS}/{target.id}",
        json={"role": "viewer"},
        headers=auth_headers[Role.admin],
    )

    assert response.status_code == 200
    assert response.json()["role"] == "viewer"
    # Same token as before: the role is read from the database
    after = await client.post(
        "/api/v1/records", json=record, headers=auth_headers[Role.user]
    )
    assert after.status_code == 403
    [log] = await logs_with_action("role_change")
    assert log.message == "admin changed the role of user from user to viewer"
    assert log.user_id == users[Role.admin].id


async def test_deactivate_user(client, users, auth_headers):
    target = users[Role.viewer]

    response = await client.patch(
        f"{USERS}/{target.id}",
        json={"is_active": False},
        headers=auth_headers[Role.admin],
    )

    assert response.status_code == 200
    me = await client.get("/api/v1/users/me", headers=auth_headers[Role.viewer])
    assert me.status_code == 403
    assert me.json() == {"detail": "Inactive user"}
    [log] = await logs_with_action("user_status_change")
    assert log.message == "admin deactivated viewer"
    assert await logs_with_action("role_change") == []


@pytest.mark.parametrize(
    "change", [{"is_active": False}, {"role": "user"}, {"role": "viewer"}]
)
async def test_admin_cannot_change_themselves(
    client, users, auth_headers, change
):
    admin = users[Role.admin]

    response = await client.patch(
        f"{USERS}/{admin.id}", json=change, headers=auth_headers[Role.admin]
    )

    assert response.status_code == 400
    assert await current_state(admin) == (Role.admin, True)


async def test_unchanged_values_are_allowed_for_yourself(
    client, users, auth_headers
):
    admin = users[Role.admin]

    response = await client.patch(
        f"{USERS}/{admin.id}",
        json={"role": "admin", "is_active": True},
        headers=auth_headers[Role.admin],
    )

    assert response.status_code == 200
    assert await logs_with_action("role_change") == []


async def test_unknown_user(client, auth_headers):
    response = await client.patch(
        f"{USERS}/{uuid.uuid7()}",
        json={"role": "viewer"},
        headers=auth_headers[Role.admin],
    )

    assert response.status_code == 404


async def test_user_id_must_be_a_uuid(client, auth_headers):
    response = await client.patch(
        f"{USERS}/42", json={"role": "viewer"}, headers=auth_headers[Role.admin]
    )

    assert response.status_code == 422


async def test_role_cannot_be_null(client, users, auth_headers):
    response = await client.patch(
        f"{USERS}/{users[Role.user].id}",
        json={"role": None},
        headers=auth_headers[Role.admin],
    )

    assert response.status_code == 422


async def test_failed_login_shows_up_in_logs(client, users, auth_headers):
    await client.post(
        "/api/v1/auth/login",
        data={"username": "user", "password": "wrong-password"},
    )
    await client.post(
        "/api/v1/auth/login",
        data={"username": "user", "password": TEST_PASSWORD},
    )

    response = await client.get(
        LOGS,
        params={"action": "login_failed"},
        headers=auth_headers[Role.admin],
    )

    body = response.json()
    assert body["total"] == 1
    log = body["items"][0]
    assert log["level"] == "WARNING"
    assert "user" in log["message"]
    assert log["username"] == "user"
    assert log["created_at"].endswith("Z")


async def test_logs_by_level_newest_first(client, users, auth_headers):
    await audit_service.log("server_error", "first", level=LogLevel.ERROR)
    await audit_service.log("register", "not an error")
    await audit_service.log("server_error", "second", level=LogLevel.ERROR)

    response = await client.get(
        LOGS, params={"level": "ERROR"}, headers=auth_headers[Role.admin]
    )

    items = response.json()["items"]
    assert [log["message"] for log in items] == ["second", "first"]
    assert items[0]["username"] is None


async def test_logs_by_user(client, users, auth_headers):
    admin = users[Role.admin]
    await audit_service.log("register", "by admin", user_id=admin.id)
    await audit_service.log("register", "by nobody")

    response = await client.get(
        LOGS,
        params={"user_id": str(admin.id)},
        headers=auth_headers[Role.admin],
    )

    assert [log["message"] for log in response.json()["items"]] == ["by admin"]


async def test_db_status(client, auth_headers):
    response = await client.get(DB_STATUS, headers=auth_headers[Role.admin])

    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is True
    assert body["response_ms"] >= 0
    assert set(body["pool"]) == {"size", "checked_out", "idle", "overflow"}
    assert body["tables"] == {
        "users": 3,
        "records": 0,
        "metrics": 0,
        "system_logs": 0,
    }
    assert body["buffer"] == {
        "pending": 0,
        "last_flush_at": None,
        "last_flush_count": None,
        "last_flush_reason": None,
    }
