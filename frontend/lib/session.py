"""Login state of this browser tab, kept in st.session_state.

The token is also kept in an HttpOnly cookie (lib/login_cookie.py), so a
refresh or a new tab can log in again without the password.
"""

import json
from typing import NoReturn, TypedDict
from urllib.parse import urlencode

import streamlit as st

from lib.config import BACKEND_WS_URL
from lib.login_cookie import issue_ticket
from lib.ws_listener import MetricsListener

EXPIRED_MESSAGE = "登入已過期或帳號已停用，請重新登入"


class Me(TypedDict):
    """The /users/me result."""

    id: str
    username: str
    email: str
    role: str
    is_active: bool
    created_at: str


def logged_in() -> bool:
    return "token" in st.session_state


def token() -> str | None:
    return st.session_state.get("token")


def user() -> Me:
    return st.session_state["user"]


def is_role(*roles: str) -> bool:
    return logged_in() and user()["role"] in roles


def redirect(url: str) -> NoReturn:
    """Send the browser to `url` (a full page load) and stop this run."""
    st.html(
        f"<script>window.location.replace({json.dumps(url)})</script>",
        unsafe_allow_javascript=True,
    )
    st.stop()


def login(access_token: str) -> NoReturn:
    """Save the token in the cookie; the reloaded app logs in from it."""
    query = urlencode({"ticket": issue_ticket(access_token)})
    redirect(f"/session/start?{query}")


def needs_cookie_check() -> bool:
    """True once per new session: try to log in again from the cookie."""
    if logged_in() or "session_cookie_checked" in st.session_state:
        return False
    st.session_state.session_cookie_checked = True
    return True


def start(access_token: str, me: Me) -> None:
    st.session_state.token = access_token
    st.session_state.user = me
    st.session_state.listener = MetricsListener(BACKEND_WS_URL, access_token)


def listener() -> MetricsListener:
    """The live metrics listener; restarted if it stopped while idle."""
    current = st.session_state.listener
    if current.stopped and not current.auth_failed:
        current = MetricsListener(BACKEND_WS_URL, st.session_state.token)
        st.session_state.listener = current
    return current


def end(expired: bool = False) -> None:
    """Log out: stop the live data and forget the token.

    The cookie is deleted by /session/end. Callers rerun the app, and the
    next run sends the browser there (see leave_if_ended). Going through a
    rerun also works when the login ends inside a fragment.
    """
    current = st.session_state.get("listener")
    if current is not None:
        current.close()
    st.session_state.clear()
    # The login page shows EXPIRED_MESSAGE for ?expired=1
    st.session_state.leave_to = (
        "/session/end?expired=1" if expired else "/session/end"
    )


def leave_if_ended() -> None:
    """Finish an end(): delete the cookie by going to /session/end."""
    if target := st.session_state.pop("leave_to", None):
        redirect(target)
