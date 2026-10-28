"""Entry point: picks the pages for the current login and role."""

import streamlit as st

from lib import api, session
from lib.login_cookie import COOKIE_NAME

st.set_page_config(page_title="Analytics Monitoring System", layout="wide")

if session.logged_in():
    live = session.listener()
    live.touch()
    # The WebSocket was refused (1008): the login is no longer valid
    if live.auth_failed:
        session.end(expired=True)

# A logout or an expired login: delete the cookie
session.leave_if_ended()

# A refresh or a new tab is a new session: log in again from the cookie,
# checked once per session
saved_token = st.context.cookies.get(COOKIE_NAME)
if (
    saved_token
    and not session.logged_in()
    and "cookie_checked" not in st.session_state
):
    st.session_state.cookie_checked = True
    me = api.me(saved_token)
    if me.status_code == 200:
        session.start(saved_token, me.json())
    elif api.ends_login(me):
        session.end(expired=True)
        session.leave_if_ended()
    else:
        # Backend trouble: keep the cookie, a later refresh can retry
        st.error(api.error_text(me))

if not session.logged_in():
    page = st.navigation(
        [st.Page("views/login.py", title="登入", icon=":material/login:")]
    )
else:
    pages = [
        st.Page(
            "views/monitor.py", title="即時監控", icon=":material/monitoring:"
        ),
        st.Page("views/records.py", title="資料記錄", icon=":material/table:"),
        st.Page(
            "views/analytics.py", title="資料分析", icon=":material/analytics:"
        ),
    ]
    if session.is_role("admin"):
        pages.append(
            st.Page(
                "views/admin.py",
                title="系統管理",
                icon=":material/admin_panel_settings:",
            )
        )
    page = st.navigation(pages)

    me = session.user()
    with st.sidebar:
        st.markdown(f"**{me['username']}**")
        st.caption(f"角色：{session.ROLE_LABELS[me['role']]}")
        if st.button("登出", icon=":material/logout:"):
            session.end()
            st.rerun()

page.run()
