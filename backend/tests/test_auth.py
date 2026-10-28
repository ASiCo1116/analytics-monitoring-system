import uuid

from app.models import LogLevel, Role
from tests.helpers import TEST_PASSWORD, audit_logs, bearer

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"


def new_user(**overrides) -> dict:
    data = {
        "username": "alice",
        "email": "alice@example.com",
        "password": TEST_PASSWORD,
    }
    return data | overrides


async def login(client, username: str, password: str):
    return await client.post(
        LOGIN, data={"username": username, "password": password}
    )


# ---------- register ----------


async def test_register_returns_user_without_password(client, db):
    response = await client.post(REGISTER, json=new_user())

    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "alice"
    assert body["email"] == "alice@example.com"
    assert body["role"] == "user"
    assert body["is_active"] is True
    assert "password" not in body and "hashed_password" not in body
    assert uuid.UUID(body["id"]).version == 7
    assert body["created_at"].endswith("Z")
    [log] = await audit_logs("register")
    assert log is not None


async def test_register_duplicate_does_not_say_which_field(client):
    await client.post(REGISTER, json=new_user())

    same_name = await client.post(
        REGISTER, json=new_user(email="other@example.com")
    )
    same_email = await client.post(REGISTER, json=new_user(username="bob"))

    for response in (same_name, same_email):
        assert response.status_code == 409
        assert response.json() == {
            "detail": "Username or email already registered"
        }


async def test_register_rejects_invalid_input(client):
    short_password = await client.post(
        REGISTER, json=new_user(password="1234567")
    )
    bad_email = await client.post(REGISTER, json=new_user(email="not-email"))

    assert short_password.status_code == 422
    assert bad_email.status_code == 422


async def test_register_rejects_password_over_72_bytes(client):
    # 25 three-byte characters: 25 characters but 75 bytes
    response = await client.post(REGISTER, json=new_user(password="密" * 25))

    assert response.status_code == 422


async def test_register_ignores_role(client):
    response = await client.post(REGISTER, json=new_user(role="admin"))

    assert response.status_code == 201
    assert response.json()["role"] == "user"


async def test_later_user_gets_larger_id(client):
    first = await client.post(REGISTER, json=new_user())
    second = await client.post(
        REGISTER, json=new_user(username="bob", email="bob@example.com")
    )

    assert second.json()["id"] > first.json()["id"]


# ---------- login ----------


async def test_login_returns_bearer_token(client, users):
    response = await login(client, "user", TEST_PASSWORD)

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


async def test_login_wrong_password_or_unknown_user(client, db, users):
    unknown_user = await login(client, "alice_unknown", TEST_PASSWORD)
    wrong_password = await login(client, "user", "wrong-password")

    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json()
    [log] = [
        log
        for log in await audit_logs("login_failed")
        if "alice_unknown" in log.message
    ]
    assert log.level == LogLevel.WARNING


async def test_login_password_over_72_bytes(client, users):
    response = await login(client, "user", "a" * 73)

    assert response.status_code == 401


async def test_login_inactive_user(client, db, users):
    users[Role.user].is_active = False
    await db.commit()

    response = await login(client, "user", TEST_PASSWORD)

    assert response.status_code == 403
    assert response.json() == {"detail": "Inactive user"}


# ---------- current user ----------


async def test_me_returns_own_data(client, users):
    token = (await login(client, "viewer", TEST_PASSWORD)).json()

    response = await client.get(
        "/api/v1/users/me",
        headers=bearer(token["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "viewer"
    assert body["role"] == "viewer"
    assert body["created_at"].endswith("Z")
