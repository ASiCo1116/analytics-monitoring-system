"""Keep the login in an HttpOnly cookie, so a page refresh stays logged in.

Streamlit code cannot set cookies, so two routes on the Streamlit server
(mounted by server.py) do it. After a login the script stores the token
under a one-time ticket and sends the browser to /session/start?ticket=...;
the route swaps the ticket for the cookie. The token itself never appears
in a URL. /session/end deletes the cookie (logout, expiry).
"""

import base64
import binascii
import json
import secrets
import threading
import time

from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.routing import Route

COOKIE_NAME = "ams_session"
TICKET_SECONDS = 30

# ticket -> (token, expiry as time.monotonic()). The routes and the
# Streamlit scripts run in the same process, so a dict is enough.
_tickets: dict[str, tuple[str, float]] = {}
_lock = threading.Lock()


def _drop_expired(now: float) -> None:
    for ticket in [t for t, (_, exp) in _tickets.items() if exp <= now]:
        del _tickets[ticket]


def issue_ticket(token: str) -> str:
    """A ticket the browser can exchange once, within 30 seconds."""
    ticket = secrets.token_urlsafe(32)
    now = time.monotonic()
    with _lock:
        _drop_expired(now)
        _tickets[ticket] = (token, now + TICKET_SECONDS)
    return ticket


def claim_ticket(ticket: str) -> str | None:
    """The token of a valid ticket; the ticket cannot be used again."""
    now = time.monotonic()
    with _lock:
        _drop_expired(now)
        entry = _tickets.pop(ticket, None)
    return entry[0] if entry else None


def seconds_left(token: str) -> int:
    """Seconds until the JWT's `exp`, read without checking the signature.

    Only sets the cookie lifetime; the backend verifies the token on every
    call. 0 when the token cannot be read.
    """
    try:
        payload = token.split(".")[1]
        # base64url without padding
        claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
        return max(int(claims["exp"] - time.time()), 0)
    except IndexError, ValueError, KeyError, TypeError, binascii.Error:
        return 0


async def start(request: Request) -> RedirectResponse:
    """GET /session/start?ticket=...: set the cookie, back to the app."""
    response = RedirectResponse("/", status_code=303)
    token = claim_ticket(request.query_params.get("ticket", ""))
    max_age = seconds_left(token) if token else 0
    if token and max_age > 0:
        response.set_cookie(
            COOKIE_NAME,
            token,
            max_age=max_age,
            path="/",
            httponly=True,
            samesite="lax",
            secure=request.url.scheme == "https",
        )
    return response


async def end(request: Request) -> RedirectResponse:
    """GET /session/end[?expired=1]: delete the cookie, back to login."""
    target = "/?expired=1" if request.query_params.get("expired") else "/"
    response = RedirectResponse(target, status_code=303)
    response.delete_cookie(
        COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
    return response


routes = [
    Route("/session/start", start, methods=["GET"]),
    Route("/session/end", end, methods=["GET"]),
]
