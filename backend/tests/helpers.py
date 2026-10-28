"""Helpers shared by the test modules."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import select

from app.db.session import SessionLocal
from app.main import app
from app.models import SystemLog

TEST_PASSWORD = "Password123"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def audit_logs(action: str) -> list[SystemLog]:
    """Audit events with this action, oldest first.

    Reads in a session of its own, which sees every row a request committed.
    """
    async with SessionLocal() as session:
        return list(
            await session.scalars(
                select(SystemLog)
                .where(SystemLog.action == action)
                .order_by(SystemLog.id)
            )
        )


@contextmanager
def temporary_route(
    path: str, endpoint: Callable[..., Any], **kwargs: Any
) -> Iterator[None]:
    """A test-only route on the real app, removed again afterwards."""
    app.add_api_route(path, endpoint, include_in_schema=False, **kwargs)
    route = app.router.routes[-1]
    try:
        yield
    finally:
        app.router.routes.remove(route)
