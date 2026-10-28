"""Small UI pieces shared by several pages."""

import math
from collections.abc import Callable, Iterable
from typing import Any, NoReturn

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

ALL_LABEL = "全部"


def current_page(key: str) -> int:
    """The page number kept under `key` in session_state (from 1)."""
    return st.session_state.get(key, 1)


def reset_page(key: str) -> None:
    st.session_state[key] = 1


def _go_to_page(key: str, page: int) -> None:
    st.session_state[key] = page


def pager(key: str, total: int, page_size: int) -> None:
    """Previous/next buttons and a "page x of y" caption.

    Fetch the list with api.get_page, which keeps the page number valid.

    The buttons use callbacks, which run before the next script run, so a
    click fetches the new page once instead of the old page and then the
    new one.
    """
    page = current_page(key)
    pages = max(1, math.ceil(total / page_size))
    prev_col, info_col, next_col = st.columns([1, 3, 1])
    prev_col.button(
        "上一頁",
        disabled=page <= 1,
        key=f"{key}_prev",
        width="stretch",
        on_click=_go_to_page,
        args=(key, page - 1),
    )
    info_col.caption(f"共 {total} 筆，第 {page} / {pages} 頁")
    next_col.button(
        "下一頁",
        disabled=page >= pages,
        key=f"{key}_next",
        width="stretch",
        on_click=_go_to_page,
        args=(key, page + 1),
    )


def select_or_all(
    label: str,
    options: Iterable[Any],
    *,
    key: str,
    format_func: Callable[[Any], str] = str,
    container: DeltaGenerator | None = None,
) -> Any | None:
    """A selectbox whose first option, "全部", means no filter (None)."""
    return (container or st).selectbox(
        label,
        [None, *options],
        format_func=lambda v: ALL_LABEL if v is None else format_func(v),
        key=key,
    )


def flash(page: str, message: str) -> NoReturn:
    """Rerun and show `message` once at the top of `page` (see show_flash)."""
    st.session_state[f"{page}_flash"] = message
    st.rerun()


def show_flash(page: str) -> None:
    if message := st.session_state.pop(f"{page}_flash", None):
        st.success(message)
