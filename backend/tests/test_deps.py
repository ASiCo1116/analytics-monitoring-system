import uuid
from datetime import timedelta

import pytest
from fastapi import Depends

from app.core.security import create_access_token
from app.deps import require_roles
from app.models import Role
from tests.helpers import bearer, temporary_route

ME = "/api/v1/users/me"
ADMIN_ONLY = "/_test/admin-only"


# Test-only route: checks require_roles on its own, apart from any real
# endpoint's other logic
async def admin_only() -> dict[str, bool]:
    return {"ok": True}


@pytest.fixture(autouse=True, scope="module")
def admin_only_route():
    with temporary_route(
        ADMIN_ONLY,
        admin_only,
        dependencies=[Depends(require_roles(Role.admin))],
    ):
        yield


async def test_missing_token(client):
    response = await client.get(ME)

    assert response.status_code == 401


async def test_invalid_token(client):
    response = await client.get(ME, headers=bearer("not-a-jwt"))

    assert response.status_code == 401


async def test_expired_token(client, users):
    user = users[Role.user]
    token = create_access_token(
        user.id, user.role, expires_delta=timedelta(seconds=-1)
    )

    response = await client.get(ME, headers=bearer(token))

    assert response.status_code == 401


async def test_token_of_unknown_user(client):
    token = create_access_token(uuid.uuid7(), Role.admin)

    response = await client.get(ME, headers=bearer(token))

    assert response.status_code == 401


async def test_old_token_rejected_after_user_disabled(
    client, db, users, auth_headers
):
    users[Role.user].is_active = False
    await db.commit()

    response = await client.get(ME, headers=auth_headers[Role.user])

    assert response.status_code == 403
    assert response.json() == {"detail": "Inactive user"}


async def test_require_roles(client, auth_headers):
    allowed = await client.get(ADMIN_ONLY, headers=auth_headers[Role.admin])
    denied = await client.get(ADMIN_ONLY, headers=auth_headers[Role.viewer])

    assert allowed.status_code == 200
    assert denied.status_code == 403
    assert denied.json() == {"detail": "Not enough permissions"}


async def test_role_change_applies_to_existing_token(
    client, db, users, auth_headers
):
    # The role inside the token is ignored; the database role decides
    users[Role.admin].role = Role.viewer
    await db.commit()

    response = await client.get(ADMIN_ONLY, headers=auth_headers[Role.admin])

    assert response.status_code == 403
