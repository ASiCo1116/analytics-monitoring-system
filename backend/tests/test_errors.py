from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.main import app
from app.models import LogLevel, SystemLog

BOOM = "/_test/boom"
DB_DOWN = "/_test/db-down"


# Test-only routes that fail on purpose
async def boom():
    raise RuntimeError("secret internal detail")


async def db_down():
    raise OperationalError("SELECT 1", {}, ConnectionRefusedError())


app.add_api_route(BOOM, boom)
app.add_api_route(DB_DOWN, db_down)


async def test_unexpected_error_returns_plain_500(client, db, caplog):
    response = await client.get(BOOM)

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "secret internal detail" not in response.text
    # Full traceback in the application log
    assert "Traceback" in caplog.text
    assert "RuntimeError: secret internal detail" in caplog.text
    # Request log line is still written for the 500
    assert f"GET {BOOM} 500" in caplog.text
    # Audit event
    log = await db.scalar(
        select(SystemLog).where(SystemLog.action == "server_error")
    )
    assert log.level == LogLevel.ERROR
    assert BOOM in log.message


async def test_database_connection_error_returns_503(client):
    response = await client.get(DB_DOWN)

    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}
