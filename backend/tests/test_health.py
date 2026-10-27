from sqlalchemy import select

from app.models import Role, User


async def test_health_checks_database(client):
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_users_fixture_creates_one_user_per_role(db, users):
    result = await db.scalars(select(User))
    stored = result.all()

    assert {user.role for user in stored} == set(Role)
    assert all(user.id.version == 7 for user in stored)


def test_health_through_sync_client(sync_client):
    # TestClient runs the app in another thread and event loop; NullPool keeps that safe
    response = sync_client.get("/health")

    assert response.status_code == 200
