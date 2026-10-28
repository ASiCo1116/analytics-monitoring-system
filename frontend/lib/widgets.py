"""Small UI pieces shared by several pages."""

import math

import streamlit as st


def current_page(key: str) -> int:
    """The page number kept under `key` in session_state (from 1)."""
    return st.session_state.get(key, 1)


def reset_page(key: str) -> None:
    st.session_state[key] = 1


def pager(key: str, total: int, page_size: int) -> None:
    """Previous/next buttons and a "page x of y" caption."""
    page = current_page(key)
    pages = max(1, math.ceil(total / page_size))
    if page > pages:
        # The data shrank under us (e.g. the last page was deleted): go to
        # the new last page instead of showing an empty "3 / 2"
        st.session_state[key] = pages
        st.rerun()
    prev_col, info_col, next_col = st.columns([1, 3, 1])
    if prev_col.button(
        "上一頁", disabled=page <= 1, key=f"{key}_prev", width="stretch"
    ):
        st.session_state[key] = page - 1
        st.rerun()
    info_col.caption(f"共 {total} 筆，第 {page} / {pages} 頁")
    if next_col.button(
        "下一頁", disabled=page >= pages, key=f"{key}_next", width="stretch"
    ):
        st.session_state[key] = page + 1
        st.rerun()
