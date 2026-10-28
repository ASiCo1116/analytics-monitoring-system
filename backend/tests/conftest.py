"""Shared test fixtures.

Tests run against a dedicated MariaDB (the db-test service). Tables are
created once per run and emptied after every test.
"""

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.db import session as db_session
from app.db.base import Base
from app.main import app
from app.models import Role, User
from app.realtime.buffer import metric_buffer

TEST_PASSWORD = "Password123"

# Safety net: these fixtures drop every table, so never run against a
# non-test database
database_url = make_url(settings.database_url)
if not database_url.database.endswith("_test"):
    shown = database_url.render_as_string(hide_password=True)
    pytest.exit(
        f"Refusing to run tests: database name must end with '_test' ({shown})"
    )
if settings.simulator_enabled:
    pytest.exit("Refusing to run tests: set SIMULATOR_ENABLED=false")

# NullPool opens a fresh connection for every checkout, so no asyncmy
# connection is shared between event loops (TestClient runs the app in its
# own thread and loop).
test_engine = create_async_engine(settings.database_url, poolclass=NullPool)
# configure() changes the existing sessionmaker in place, so all code using
# SessionLocal follows
db_session.SessionLocal.configure(bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
async def database():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest.fixture(autouse=True)
def fresh_metric_buffer(monkeypatch):
    """Start every test with an empty app-wide buffer.

    It is a module-level object, so a test that fills or flushes it (e.g.
    the lifespan test) would otherwise leak into later tests.
    """
    monkeypatch.setattr(metric_buffer, "_items", [])
    monkeypatch.setattr(metric_buffer, "last_flush", None)


@pytest.fixture(autouse=True)
async def clean_tables():
    """Empty every table after each test.

    Children go before parents because of the foreign keys.
    """
    yield
    async with db_session.SessionLocal() as session:
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(delete(table))
        await session.commit()


@pytest.fixture
async def db():
    async with db_session.SessionLocal() as session:
        yield session


@pytest.fixture
async def client():
    """Async HTTP client calling the app in-process (no server, no lifespan)."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture
def sync_client():
    """Starlette TestClient, needed for WebSocket tests.

    httpx AsyncClient has no WebSocket support.
    """
    with TestClient(app) as tc:
        yield tc


@pytest.fixture
async def users(db) -> dict[Role, User]:
    """One active user per role; every password is TEST_PASSWORD."""
    hashed = hash_password(TEST_PASSWORD)
    created = {
        role: User(
            username=role.value,
            email=f"{role.value}@example.com",
            hashed_password=hashed,
            role=role,
        )
        for role in Role
    }
    db.add_all(created.values())
    await db.commit()
    return created


@pytest.fixture
def auth_headers(users) -> dict[Role, dict[str, str]]:
    """Authorization headers per role, e.g. headers=auth_headers[Role.admin]."""
    return {
        role: {"Authorization": f"Bearer {create_access_token(u.id, u.role)}"}
        for role, u in users.items()
    }
