"""Calls to the backend REST API.

Every call carries the JWT. A 401, or a 403 for a disabled account, ends
the login: the session is cleared and the app goes back to the login page.
A plain 403 (not enough permissions) is left to the page to show.
"""

from typing import Any

import requests
import streamlit as st

from lib import session
from lib.config import API_URL

TIMEOUT_SECONDS = 15
# The backend uses this exact detail for disabled accounts
INACTIVE_USER = "Inactive user"


def _detail(response: requests.Response) -> Any:
    try:
        return response.json().get("detail")
    except ValueError, AttributeError:
        return None


def _send(method: str, path: str, **kwargs: Any) -> requests.Response:
    try:
        return requests.request(
            method, f"{API_URL}{path}", timeout=TIMEOUT_SECONDS, **kwargs
        )
    except requests.RequestException:
        st.error("無法連線到後端服務，請稍後再試。")
        st.stop()


def ends_login(response: requests.Response) -> bool:
    """A 401, or a 403 for a disabled account: the login is over."""
    return response.status_code == 401 or (
        response.status_code == 403 and _detail(response) == INACTIVE_USER
    )


def request(method: str, path: str, **kwargs: Any) -> requests.Response:
    headers = {"Authorization": f"Bearer {session.token()}"}
    response = _send(method, path, headers=headers, **kwargs)
    if ends_login(response):
        session.end(expired=True)
        st.rerun()
    return response


def get(path: str, **params: Any) -> requests.Response:
    # Leave out empty filters instead of sending "None"
    params = {k: v for k, v in params.items() if v is not None and v != ""}
    return request("GET", path, params=params)


def login(username: str, password: str) -> requests.Response:
    return _send(
        "POST",
        "/auth/login",
        data={"username": username, "password": password},
    )


def me(access_token: str) -> requests.Response:
    return _send(
        "GET",
        "/users/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )


def register(username: str, email: str, password: str) -> requests.Response:
    return _send(
        "POST",
        "/auth/register",
        json={"username": username, "email": email, "password": password},
    )


def error_text(response: requests.Response) -> str:
    """A readable message for a failed call."""
    if response.status_code == 503:
        return "資料庫無法連線，請稍後再試。"
    if response.status_code == 403:
        return "權限不足，無法執行此操作。"
    detail = _detail(response)
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):
        # FastAPI validation errors: [{"loc": [...], "msg": ...}, ...]
        return "；".join(
            f"{'.'.join(str(p) for p in e.get('loc', [])[1:])} {e.get('msg')}"
            for e in detail
        )
    return f"發生錯誤（HTTP {response.status_code}）"
