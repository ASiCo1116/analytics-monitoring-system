"""Open WebSocket connections and the broadcast to all of them."""

import asyncio
import logging
from contextlib import suppress

from fastapi import WebSocket, status

logger = logging.getLogger(__name__)

# A client that cannot take a message within this time is dropped, so a
# stalled connection never delays the others
SEND_TIMEOUT_SECONDS = 2


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        # Running close tasks, kept so they are not garbage-collected
        self._closing: set[asyncio.Task] = set()

    def __len__(self) -> int:
        return len(self._connections)

    def connect(self, websocket: WebSocket) -> None:
        """Register an accepted and authenticated connection."""
        self._connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)

    async def broadcast(self, message: dict) -> None:
        """Send to every client at once; failing clients are removed."""
        # Copy: connections may be added or removed while sending
        connections = list(self._connections)
        results = await asyncio.gather(
            *(
                asyncio.wait_for(ws.send_json(message), SEND_TIMEOUT_SECONDS)
                for ws in connections
            ),
            return_exceptions=True,
        )
        for websocket, result in zip(connections, results, strict=True):
            if isinstance(result, Exception):
                logger.info("Dropping WebSocket client: %r", result)
                self.disconnect(websocket)
                # Also close it: a client that only stalled would otherwise
                # stay connected but never get data again. In the
                # background, so a hanging close cannot delay this tick.
                task = asyncio.create_task(_close_quietly(websocket))
                self._closing.add(task)
                task.add_done_callback(self._closing.discard)


async def _close_quietly(websocket: WebSocket) -> None:
    """Best effort close with 1013, so the client reconnects."""
    with suppress(Exception):
        await asyncio.wait_for(
            websocket.close(code=status.WS_1013_TRY_AGAIN_LATER),
            SEND_TIMEOUT_SECONDS,
        )


manager = ConnectionManager()
