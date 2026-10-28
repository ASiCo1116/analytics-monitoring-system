"""Login state of this browser tab, kept in st.session_state."""

import streamlit as st

from lib.config import BACKEND_WS_URL
from lib.ws_listener import MetricsListener

EXPIRED_MESSAGE = "登入已過期或帳號已停用，請重新登入"
ROLE_LABELS = {"admin": "Admin", "user": "User", "viewer": "Viewer"}


def logged_in() -> bool:
    return "token" in st.session_state


def token() -> str | None:
    return st.session_state.get("token")


def user() -> dict:
    """The /users/me result: id, username, email, role, is_active, ..."""
    return st.session_state["user"]


def is_role(*roles: str) -> bool:
    return logged_in() and user()["role"] in roles


def start(access_token: str, me: dict) -> None:
    st.session_state.token = access_token
    st.session_state.user = me
    st.session_state.listener = MetricsListener(BACKEND_WS_URL, access_token)


def listener() -> MetricsListener:
    """The live metrics listener; restarted if it stopped while idle."""
    current = st.session_state.listener
    if current.stopped and not current.auth_failed:
        current = MetricsListener(BACKEND_WS_URL, token())
        st.session_state.listener = current
    return current


def end(expired: bool = False) -> None:
    """Log out: stop the live data and forget the token."""
    current = st.session_state.get("listener")
    if current is not None:
        current.close()
    st.session_state.clear()
    if expired:
        # Shown once by the login page
        st.session_state.notice = EXPIRED_MESSAGE
