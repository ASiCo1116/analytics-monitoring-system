"""WebSocket /ws/metrics: the live metric stream."""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from sqlalchemy.exc import OperationalError

from app.core.errors import DATABASE_UNAVAILABLE, INVALID_CREDENTIALS
from app.db.session import SessionLocal
from app.deps import user_for_token
from app.models import User
from app.realtime.manager import manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["realtime"])


async def _authenticate(token: str | None) -> User | None:
    """The active user the token belongs to, or None."""
    if not token:
        return None
    # A short session of its own: a dependency session would hold a pooled
    # connection for as long as the WebSocket stays open
    async with SessionLocal() as db:
        user = await user_for_token(db, token)
    return user if user is not None and user.is_active else None


@router.websocket("/ws/metrics")
async def metrics_stream(
    websocket: WebSocket, token: str | None = None
) -> None:
    """Push every generated metric batch, once a second.

    Browsers cannot set headers on a WebSocket, so the JWT comes as the
    `token` query parameter. Any role may connect.
    """
    # Accept first, then check the token. Closing before accept() makes the
    # server refuse the handshake with HTTP 403, and the client would never
    # see the 1008 code it uses to log the user out.
    await websocket.accept()
    try:
        user = await _authenticate(token)
    except OperationalError:
        # Not the client's fault: 1011 lets it reconnect later
        await websocket.close(
            code=status.WS_1011_INTERNAL_ERROR, reason=DATABASE_UNAVAILABLE
        )
        return
    if user is None:
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason=INVALID_CREDENTIALS,
        )
        return

    manager.connect(websocket)
    logger.info("WebSocket opened by %s (%d open)", user.username, len(manager))
    try:
        # Clients only listen; reading is how a disconnect is noticed
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)
        logger.info(
            "WebSocket closed by %s (%d open)", user.username, len(manager)
        )
