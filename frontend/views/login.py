import streamlit as st

from lib import api, session

st.title("Analytics Monitoring System")

if notice := st.session_state.pop("notice", None):
    st.warning(notice)

login_tab, register_tab = st.tabs(["登入", "註冊"])

with login_tab, st.form("login"):
    username = st.text_input("帳號")
    password = st.text_input("密碼", type="password")
    if st.form_submit_button("登入", type="primary"):
        response = api.login(username, password)
        if response.status_code == 200:
            access_token = response.json()["access_token"]
            me = api.me(access_token)
            if me.status_code == 200:
                session.start(access_token, me.json())
                st.rerun()
            st.error(api.error_text(me))
        elif response.status_code == 401:
            st.error("帳號或密碼錯誤")
        elif response.status_code == 403:
            st.error("帳號已停用，請聯絡管理員")
        else:
            st.error(api.error_text(response))

with register_tab, st.form("register", clear_on_submit=False):
    st.caption("新帳號的角色為 User。")
    new_username = st.text_input("帳號", help="3–50 個英文字母、數字或底線")
    email = st.text_input("Email")
    new_password = st.text_input("密碼", type="password", help="至少 8 個字元")
    confirm = st.text_input("確認密碼", type="password")
    if st.form_submit_button("註冊"):
        if new_password != confirm:
            st.error("兩次輸入的密碼不一致")
        else:
            response = api.register(new_username, email, new_password)
            if response.status_code == 201:
                st.success("註冊成功，請切換到「登入」分頁登入。")
            elif response.status_code == 409:
                st.error("帳號或 Email 已被使用")
            else:
                st.error(api.error_text(response))
