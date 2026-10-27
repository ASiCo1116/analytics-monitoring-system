from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models import LogLevel, Role, SystemLog
from app.services import audit_service


async def test_log_writes_one_row(db, users):
    admin = users[Role.admin]

    await audit_service.log(
        "role_change",
        "admin changed bob from user to viewer",
        level=LogLevel.INFO,
        user_id=admin.id,
        ip_address="10.0.0.1",
    )

    rows = (await db.scalars(select(SystemLog))).all()
    assert len(rows) == 1
    assert rows[0].action == "role_change"
    assert rows[0].user_id == admin.id
    assert rows[0].ip_address == "10.0.0.1"


async def test_long_message_is_truncated(db):
    await audit_service.log("server_error", "x" * 600)

    row = await db.scalar(select(SystemLog))
    assert len(row.message) == audit_service.MAX_MESSAGE_LENGTH


async def test_database_error_is_logged_not_raised(monkeypatch, caplog):
    # Nothing listens on port 1, so connecting fails
    broken = create_async_engine(
        "mysql+asyncmy://user:pass@127.0.0.1:1/none", poolclass=NullPool
    )
    monkeypatch.setattr(
        audit_service, "SessionLocal", async_sessionmaker(broken)
    )

    await audit_service.log("login_failed", "bad password for alice")

    assert "Could not write system log login_failed" in caplog.text
    # An unreachable database is expected: one line, no traceback
    [record] = caplog.records
    assert record.levelname == "ERROR"
    assert record.exc_info is None
