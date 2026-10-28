"""Settings from environment variables (set by Compose or the pixi task)."""

import os
from zoneinfo import ZoneInfo

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
BACKEND_WS_URL = os.environ.get("BACKEND_WS_URL", "ws://localhost:8000")
API_URL = f"{BACKEND_URL}/api/v1"
APP_TIMEZONE = os.environ.get("APP_TIMEZONE", "Asia/Taipei")
TZ = ZoneInfo(APP_TIMEZONE)
