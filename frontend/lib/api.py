"""Calls to the backend REST API.

Every call carries the JWT. A 401, or a 403 for a disabled account, ends
the login: the session is cleared and the app goes back to the login page.
A plain 403 (not enough permissions) is left to the page to show.
"""

import math
import time
from typing import Any

import requests
import streamlit as st

from lib import session
from lib.config import API_URL
from lib.widgets import current_page

TIMEOUT_SECONDS = 15
# The backend uses this exact detail for disabled accounts
INACTIVE_USER = "Inactive user"
# The category list is reused this long within a session
CATEGORIES_TTL_SECONDS = 60
CATEGORIES_KEY = "api_categories"


def detail(response: requests.Response) -> Any:
    """The `detail` of an error response, or None."""
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
        response.status_code == 403 and detail(response) == INACTIVE_USER
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


def get_page(
    path: str, page_key: str, page_size: int, **params: Any
) -> requests.Response:
    """One page of a list endpoint; the page number is kept under page_key.

    When that page no longer exists (the data shrank, e.g. the last page
    was deleted), the new last page is fetched and remembered instead. Done
    here rather than by rerunning the page, which would drop a message
    shown in this run.
    """
    page = current_page(page_key)
    response = get(path, page=page, page_size=page_size, **params)
    if response.ok:
        last = max(1, math.ceil(response.json()["total"] / page_size))
        if page > last:
            st.session_state[page_key] = last
            response = get(path, page=last, page_size=page_size, **params)
    return response


def categories() -> list[str]:
    """Distinct record categories, reused within the session for a minute.

    Records pages call forget_categories() after changing records, so the
    person who made a change sees it right away.
    """
    cached = st.session_state.get(CATEGORIES_KEY)
    if cached and time.monotonic() - cached[0] < CATEGORIES_TTL_SECONDS:
        return cached[1]
    response = get("/records/categories")
    if not response.ok:
        # Not cached: the filter works without categories until next time
        return []
    st.session_state[CATEGORIES_KEY] = (time.monotonic(), response.json())
    return response.json()


def forget_categories() -> None:
    st.session_state.pop(CATEGORIES_KEY, None)


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
    body = detail(response)
    if isinstance(body, dict) and "ids" in body:
        # Batch delete names the records it refused: {message, ids}
        reason = {403: "權限不足", 404: "找不到記錄"}.get(
            response.status_code, body.get("message")
        )
        return f"{reason}：記錄 {', '.join(map(str, body['ids']))}"
    if response.status_code == 403:
        return "權限不足，無法執行此操作。"
    if isinstance(body, str):
        return body
    if isinstance(body, list):
        # FastAPI validation errors: [{"loc": [...], "msg": ...}, ...]
        return "；".join(
            f"{'.'.join(str(p) for p in e.get('loc', [])[1:])} {e.get('msg')}"
            for e in body
        )
    return f"發生錯誤（HTTP {response.status_code}）"
