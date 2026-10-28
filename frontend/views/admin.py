from datetime import timedelta

import streamlit as st

from lib import api
from lib.fmt import local_param, to_local
from lib.widgets import current_page, pager, reset_page

ROLES = ["admin", "user", "viewer"]
LEVELS = ["INFO", "WARNING", "ERROR"]
ACTIONS = [
    "login_success",
    "login_failed",
    "register",
    "record_create",
    "record_update",
    "record_delete",
    "record_import",
    "role_change",
    "user_status_change",
    "server_error",
    "metric_flush_failed",
]
METRICS = {"cpu": "CPU", "memory": "記憶體", "temperature": "溫度"}
FLUSH_REASONS = {
    "interval": "定期",
    "size": "條件（筆數）",
    "shutdown": "關閉時",
}
PAGE_SIZE = 50

st.title("系統管理")
if flash := st.session_state.pop("admin_flash", None):
    st.success(flash)

users_response = api.get("/admin/users", page_size=100)
if not users_response.ok:
    st.error(api.error_text(users_response))
    st.stop()
users = users_response.json()["items"]

users_tab, logs_tab, db_tab, history_tab = st.tabs(
    ["使用者管理", "系統日誌", "資料庫狀態", "即時資料歷史"]
)


def pending_changes(
    before: list[dict], after: list[dict]
) -> list[tuple[dict, dict]]:
    """(row, {field: new value}) for every row edited in the table."""
    result = []
    for old, new in zip(before, after, strict=True):
        change = {}
        if new["角色"] != old["角色"]:
            change["role"] = new["角色"]
        if new["啟用"] != old["啟用"]:
            change["is_active"] = new["啟用"]
        if change:
            result.append((old, change))
    return result


with users_tab:
    st.caption(
        "修改角色或啟用狀態後按「儲存變更」。不能修改自己的角色或停用自己。"
    )
    rows = [
        {
            "id": u["id"],
            "帳號": u["username"],
            "Email": u["email"],
            "角色": u["role"],
            "啟用": u["is_active"],
            "建立時間": to_local(u["created_at"]),
        }
        for u in users
    ]
    edited = st.data_editor(
        rows,
        key="users_editor",
        hide_index=True,
        column_order=["帳號", "Email", "角色", "啟用", "建立時間"],
        disabled=["帳號", "Email", "建立時間"],
        column_config={
            "角色": st.column_config.SelectboxColumn(
                options=ROLES, required=True
            ),
            "啟用": st.column_config.CheckboxColumn(),
            "建立時間": st.column_config.DatetimeColumn(
                format="YYYY-MM-DD HH:mm"
            ),
        },
    )
    if st.button("儲存變更", type="primary", key="save_users"):
        changes = pending_changes(rows, edited)
        if not changes:
            st.info("沒有任何變更")
        failed = []
        for row, change in changes:
            response = api.request(
                "PATCH", f"/admin/users/{row['id']}", json=change
            )
            if not response.ok:
                failed.append(f"{row['帳號']}：{api.error_text(response)}")
        if changes and not failed:
            st.session_state.admin_flash = f"已更新 {len(changes)} 位使用者"
            # Start the table again from the saved data
            del st.session_state["users_editor"]
            st.rerun()
        for message in failed:
            st.error(message)

with logs_tab:
    user_ids = {u["username"]: u["id"] for u in users}
    with st.form("log_filters"):
        c1, c2, c3, c4, c5 = st.columns(5)
        level = c1.selectbox("等級", ["全部", *LEVELS])
        action = c2.selectbox("事件", ["全部", *ACTIONS])
        username = c3.selectbox("使用者", ["全部", *user_ids])
        log_start = c4.date_input("開始日期", value=None, key="log_start")
        log_end = c5.date_input("結束日期（含）", value=None, key="log_end")
        if st.form_submit_button("查詢"):
            reset_page("logs_page")
    logs = api.get(
        "/admin/logs",
        page=current_page("logs_page"),
        page_size=PAGE_SIZE,
        level=None if level == "全部" else level,
        action=None if action == "全部" else action,
        user_id=user_ids.get(username),
        start=local_param(log_start),
        end=local_param(log_end + timedelta(days=1)) if log_end else None,
    )
    if logs.ok:
        body = logs.json()
        st.dataframe(
            [
                {
                    "時間": to_local(log["created_at"]),
                    "等級": log["level"],
                    "事件": log["action"],
                    "訊息": log["message"],
                    "使用者": log["username"] or "",
                    "IP": log["ip_address"] or "",
                }
                for log in body["items"]
            ],
            hide_index=True,
            column_config={
                "時間": st.column_config.DatetimeColumn(
                    format="YYYY-MM-DD HH:mm:ss"
                )
            },
        )
        pager("logs_page", body["total"], PAGE_SIZE)
    else:
        st.error(api.error_text(logs))

with db_tab:
    st.button("重新整理", key="refresh_db_status", icon=":material/refresh:")
    status = api.get("/admin/db-status")
    if not status.ok:
        st.error(api.error_text(status))
    else:
        s = status.json()
        c1, c2 = st.columns(2)
        c1.metric(
            "資料庫連線", "正常" if s["connected"] else "異常", border=True
        )
        c2.metric("回應時間", f"{s['response_ms']:.2f} ms", border=True)

        st.markdown("**連線池**")
        pool = s["pool"]
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("大小", pool["size"])
        p2.metric("使用中", pool["checked_out"])
        p3.metric("閒置", pool["idle"])
        p4.metric("溢出", pool["overflow"])

        st.markdown("**各資料表筆數**")
        for column, (table, count) in zip(
            st.columns(len(s["tables"])), s["tables"].items(), strict=True
        ):
            column.metric(table, f"{count:,}")

        st.markdown("**即時資料批次寫入**")
        buffer = s["buffer"]
        b1, b2, b3, b4 = st.columns(4)
        b1.metric("暫存區筆數", buffer["pending"])
        if buffer["last_flush_at"]:
            b2.metric(
                "上次寫入時間",
                to_local(buffer["last_flush_at"]).strftime("%H:%M:%S"),
            )
            b3.metric("上次寫入筆數", buffer["last_flush_count"])
            b4.metric(
                "觸發原因",
                FLUSH_REASONS.get(
                    buffer["last_flush_reason"], buffer["last_flush_reason"]
                ),
            )
        else:
            b2.metric("上次寫入時間", "尚未寫入")

with history_tab:
    with st.form("history_filters"):
        c1, c2, c3, c4, c5 = st.columns(5)
        server = c1.text_input("伺服器", placeholder="例如 server-2")
        metric = c2.selectbox(
            "指標", ["全部", *METRICS], format_func=lambda m: METRICS.get(m, m)
        )
        h_start = c3.date_input("開始日期", value=None, key="history_start")
        h_end = c4.date_input("結束日期（含）", value=None, key="history_end")
        anomaly_only = c5.checkbox("只看異常")
        if st.form_submit_button("查詢"):
            reset_page("history_page")
    history = api.get(
        "/metrics",
        page=current_page("history_page"),
        page_size=PAGE_SIZE,
        server=server.strip() or None,
        metric=None if metric == "全部" else metric,
        start=local_param(h_start),
        end=local_param(h_end + timedelta(days=1)) if h_end else None,
        anomaly_only=str(anomaly_only).lower(),
    )
    if history.ok:
        body = history.json()
        st.dataframe(
            [
                {
                    "時間": to_local(m["recorded_at"]),
                    "伺服器": m["server"],
                    "指標": METRICS[m["metric"]],
                    "數值": f"{m['value']:g} {m['unit']}",
                    "閾值": m["threshold"],
                    "異常": "⚠️" if m["is_anomaly"] else "",
                }
                for m in body["items"]
            ],
            hide_index=True,
            column_config={
                "時間": st.column_config.DatetimeColumn(
                    format="YYYY-MM-DD HH:mm:ss"
                )
            },
        )
        pager("history_page", body["total"], PAGE_SIZE)
    else:
        st.error(api.error_text(history))
