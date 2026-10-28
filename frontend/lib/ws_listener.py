"""Background WebSocket client for /ws/metrics.

Streamlit reruns the page script on every interaction, so the connection
lives in a daemon thread owned by an object kept in st.session_state. The
thread never touches st.session_state (Streamlit does not allow that from
other threads); it only appends to deques, which are thread-safe, and the
page reads them.
"""

import json
import threading
import time
from collections import deque

import websocket

RECONNECT_SECONDS = 3
HISTORY_SECONDS = 60
MAX_ALERTS = 20
# Close code the backend uses for a bad, expired or disabled login
POLICY_VIOLATION = 1008
# Stop when no page has used the data for this long, e.g. the browser tab
# was closed and the Streamlit session is gone
IDLE_SECONDS = 10 * 60


class MetricsListener:
    def __init__(self, ws_url: str, token: str) -> None:
        self.url = f"{ws_url}/ws/metrics?token={token}"
        # One message per second: {"type", "timestamp", "data": [...]}
        self.history: deque[dict] = deque(maxlen=HISTORY_SECONDS)
        # Anomalous samples, oldest first
        self.alerts: deque[dict] = deque(maxlen=MAX_ALERTS)
        self.connected = False
        # Set when the server rejected the token (close code 1008)
        self.auth_failed = False
        self._stop = threading.Event()
        self._app: websocket.WebSocketApp | None = None
        self._last_used = time.monotonic()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    @property
    def stopped(self) -> bool:
        return not self._thread.is_alive()

    def touch(self) -> None:
        """Called on every page run, so an open session is never idle."""
        self._last_used = time.monotonic()

    def close(self) -> None:
        self._stop.set()
        if self._app is not None:
            self._app.close()

    def _run(self) -> None:
        # Our own reconnect loop rather than run_forever(reconnect=...):
        # with built-in reconnects the library reconnects after a close
        # frame without reporting its code, so 1008 could not be detected
        while not self._stop.is_set():
            self._app = websocket.WebSocketApp(
                self.url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_close=self._on_close,
            )
            # Returns when the connection ends or cannot be opened
            self._app.run_forever(ping_interval=30, ping_timeout=10)
            self.connected = False
            if self.auth_failed:
                break
            if time.monotonic() - self._last_used > IDLE_SECONDS:
                break
            self._stop.wait(RECONNECT_SECONDS)

    def _on_open(self, app: websocket.WebSocketApp) -> None:
        # close() may have run while this connection was being created, in
        # which case it closed the previous app, not this one
        if self._stop.is_set():
            app.close()
            return
        self.connected = True

    def _on_message(self, app: websocket.WebSocketApp, raw: str) -> None:
        if time.monotonic() - self._last_used > IDLE_SECONDS:
            self.close()
            return
        message = json.loads(raw)
        if message.get("type") != "metrics":
            return
        self.history.append(message)
        self.alerts.extend(m for m in message["data"] if m["is_anomaly"])

    def _on_close(
        self, app: websocket.WebSocketApp, code: int | None, reason: str | None
    ) -> None:
        self.connected = False
        if code == POLICY_VIOLATION:
            self.auth_failed = True
