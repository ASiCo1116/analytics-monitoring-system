import asyncio
import logging
import time

import pytest
from fastapi import WebSocketDisconnect

from app.core.logging import RedactTokens
from app.core.security import create_access_token
from app.models import Role
from app.realtime import manager as manager_module
from app.realtime.manager import ConnectionManager, manager

MESSAGE = {"type": "metrics", "timestamp": "2026-10-27T00:00:00Z", "data": []}


def token_of(headers: dict[str, str]) -> str:
    return headers["Authorization"].removeprefix("Bearer ")


def wait_for_connections(count: int) -> None:
    """The server registers a client only after checking its token."""
    deadline = time.monotonic() + 3
    while len(manager) != count:
        if time.monotonic() > deadline:
            raise AssertionError(f"expected {count} connections")
        time.sleep(0.01)


def close_code(sync_client, url: str) -> int:
    with (
        pytest.raises(WebSocketDisconnect) as exc_info,
        sync_client.websocket_connect(url) as websocket,
    ):
        websocket.receive_json()
    return exc_info.value.code


def test_invalid_token_is_closed_with_1008(sync_client):
    assert close_code(sync_client, "/ws/metrics?token=not-a-jwt") == 1008


def test_missing_token_is_closed_with_1008(sync_client):
    assert close_code(sync_client, "/ws/metrics") == 1008


@pytest.fixture
async def inactive_token(db, users) -> str:
    viewer = users[Role.viewer]
    viewer.is_active = False
    await db.commit()
    return create_access_token(viewer.id, viewer.role)


def test_inactive_user_is_closed_with_1008(sync_client, inactive_token):
    url = f"/ws/metrics?token={inactive_token}"
    assert close_code(sync_client, url) == 1008


def test_viewer_receives_broadcast(sync_client, auth_headers):
    token = token_of(auth_headers[Role.viewer])
    with sync_client.websocket_connect(f"/ws/metrics?token={token}") as ws:
        wait_for_connections(1)

        # Run the broadcast in the app's event loop
        sync_client.portal.call(manager.broadcast, MESSAGE)

        assert ws.receive_json() == MESSAGE
    wait_for_connections(0)


def test_other_clients_keep_receiving_after_one_leaves(
    sync_client, auth_headers
):
    url = f"/ws/metrics?token={token_of(auth_headers[Role.user])}"
    with sync_client.websocket_connect(url) as staying:
        with sync_client.websocket_connect(url):
            wait_for_connections(2)
        wait_for_connections(1)

        sync_client.portal.call(manager.broadcast, MESSAGE)

        assert staying.receive_json() == MESSAGE


class FakeSocket:
    def __init__(self, error: Exception | None = None, delay: float = 0):
        self.error = error
        self.delay = delay
        self.received = []
        self.close_code = None

    async def send_json(self, message):
        await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        self.received.append(message)

    async def close(self, code):
        self.close_code = code


async def test_broadcast_drops_failing_and_stalled_clients(monkeypatch):
    monkeypatch.setattr(manager_module, "SEND_TIMEOUT_SECONDS", 0.05)
    connections = ConnectionManager()
    healthy = FakeSocket()
    broken = FakeSocket(error=RuntimeError("connection reset"))
    stalled = FakeSocket(delay=1)
    for websocket in (healthy, broken, stalled):
        connections.connect(websocket)

    await connections.broadcast(MESSAGE)
    await connections.broadcast(MESSAGE)

    assert healthy.received == [MESSAGE, MESSAGE]
    assert len(connections) == 1
    # Dropped clients are closed so they reconnect; the healthy one is not
    await asyncio.sleep(0.1)
    assert broken.close_code == stalled.close_code == 1013
    assert healthy.close_code is None


def test_tokens_are_redacted_from_logs():
    record = logging.LogRecord(
        "uvicorn.error",
        logging.INFO,
        __file__,
        1,
        '%s - "WebSocket %s" [accepted]',
        ("127.0.0.1:5000", "/ws/metrics?token=eyJhbGci.abc.def&x=1"),
        None,
    )

    RedactTokens().filter(record)

    assert record.getMessage() == (
        '127.0.0.1:5000 - "WebSocket /ws/metrics?token=***&x=1" [accepted]'
    )
