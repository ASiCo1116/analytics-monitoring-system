import streamlit as st

from lib import api
from lib.fmt import local_end_param, local_param, to_local
from lib.labels import METRICS, ROLES, metric_label, role_label
from lib.widgets import (
    flash,
    pager,
    reset_page,
    select_or_all,
    show_flash,
)

LEVELS = ["INFO", "WARNING", "ERROR"]
ACTIONS = [
    "login_success",
    "login_failed",
    "register",
    "record_create",
    "record_update",
    "record_delete",
    "record_batch_delete",
    "record_import",
    "role_change",
    "user_status_change",
    "server_error",
    "metric_flush_failed",
]
FLUSH_REASONS = {
    "interval": "定期",
    "size": "條件（筆數）",
    "shutdown": "關閉時",
}
PAGE_SIZE = 50
# The largest page the API returns; the user table shows one page
USER_LIST_LIMIT = 100
TIME_FORMAT = "YYYY-MM-DD HH:mm:ss"


def load_users() -> list[dict] | None:
    """Up to USER_LIST_LIMIT users, or None after showing the error."""
    response = api.get("/admin/users", page_size=USER_LIST_LIMIT)
    if not response.ok:
        st.error(api.error_text(response))
        return None
    body = response.json()
    if body["total"] > len(body["items"]):
        st.caption(
            f"共 {body['total']} 位使用者，只列出前 {USER_LIST_LIMIT} 位。"
        )
    return body["items"]


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


def render_users() -> None:
    st.caption(
        "修改角色或啟用狀態後按「儲存變更」。不能修改自己的角色或停用自己。"
    )
    users = load_users()
    if users is None:
        return
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
        key="admin_users_editor",
        hide_index=True,
        column_order=["帳號", "Email", "角色", "啟用", "建立時間"],
        disabled=["帳號", "Email", "建立時間"],
        column_config={
            "角色": st.column_config.SelectboxColumn(
                options=list(ROLES), format_func=role_label, required=True
            ),
            "啟用": st.column_config.CheckboxColumn(),
            "建立時間": st.column_config.DatetimeColumn(
                format="YYYY-MM-DD HH:mm"
            ),
        },
    )
    if not st.button("儲存變更", type="primary", key="admin_save_users"):
        return
    changes = pending_changes(rows, edited)
    if not changes:
        st.info("沒有任何變更")
        return
    failed = []
    for row, change in changes:
        response = api.request(
            "PATCH", f"/admin/users/{row['id']}", json=change
        )
        if not response.ok:
            failed.append(f"{row['帳號']}：{api.error_text(response)}")
    saved = len(changes) - len(failed)
    if not failed:
        # Start the table again from the saved data
        del st.session_state["admin_users_editor"]
        flash("admin", f"已更新 {saved} 位使用者")
    if saved:
        st.warning(f"已更新 {saved} 位使用者，{len(failed)} 位未更新：")
    for message in failed:
        st.error(message)


def render_logs() -> None:
    users = load_users()
    user_ids = {u["username"]: u["id"] for u in users or []}
    with st.form("admin_log_filters"):
        c1, c2, c3, c4, c5 = st.columns(5)
        level = select_or_all(
            "等級", LEVELS, key="admin_log_level", container=c1
        )
        action = select_or_all(
            "事件", ACTIONS, key="admin_log_action", container=c2
        )
        username = select_or_all(
            "使用者", user_ids, key="admin_log_user", container=c3
        )
        start = c4.date_input("開始日期", value=None, key="admin_log_start")
        end = c5.date_input("結束日期（含）", value=None, key="admin_log_end")
        if st.form_submit_button("查詢"):
            reset_page("admin_logs_page")
    response = api.get_page(
        "/admin/logs",
        "admin_logs_page",
        PAGE_SIZE,
        level=level,
        action=action,
        user_id=user_ids.get(username),
        start=local_param(start),
        end=local_end_param(end),
    )
    if not response.ok:
        st.error(api.error_text(response))
        return
    body = response.json()
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
            "時間": st.column_config.DatetimeColumn(format=TIME_FORMAT)
        },
    )
    pager("admin_logs_page", body["total"], PAGE_SIZE)


def render_db_status() -> None:
    st.button("重新整理", key="admin_refresh_db", icon=":material/refresh:")
    response = api.get("/admin/db-status")
    if not response.ok:
        st.error(api.error_text(response))
        return
    status = response.json()
    c1, c2 = st.columns(2)
    c1.metric(
        "資料庫連線", "正常" if status["connected"] else "異常", border=True
    )
    c2.metric("回應時間", f"{status['response_ms']:.2f} ms", border=True)

    st.markdown("**連線池**")
    pool = status["pool"]
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("大小", pool["size"])
    p2.metric("使用中", pool["checked_out"])
    p3.metric("閒置", pool["idle"])
    p4.metric("溢出", pool["overflow"])

    st.markdown("**各資料表筆數**")
    tables = status["tables"]
    for column, (table, count) in zip(
        st.columns(len(tables)), tables.items(), strict=True
    ):
        column.metric(table, f"{count:,}")

    st.markdown("**即時資料批次寫入**")
    buffer = status["buffer"]
    b1, b2, b3, b4 = st.columns(4)
    b1.metric("暫存區筆數", buffer["pending"])
    if not buffer["last_flush_at"]:
        b2.metric("上次寫入時間", "尚未寫入")
        return
    b2.metric(
        "上次寫入時間",
        to_local(buffer["last_flush_at"]).strftime("%H:%M:%S"),
    )
    b3.metric("上次寫入筆數", buffer["last_flush_count"])
    reason = buffer["last_flush_reason"]
    b4.metric("觸發原因", FLUSH_REASONS.get(reason, reason))


def render_history() -> None:
    with st.form("admin_history_filters"):
        c1, c2, c3, c4, c5 = st.columns(5)
        server = c1.text_input(
            "伺服器", placeholder="例如 server-2", key="admin_history_server"
        )
        metric = select_or_all(
            "指標",
            METRICS,
            key="admin_history_metric",
            format_func=metric_label,
            container=c2,
        )
        start = c3.date_input("開始日期", value=None, key="admin_history_start")
        end = c4.date_input(
            "結束日期（含）", value=None, key="admin_history_end"
        )
        anomaly_only = c5.checkbox("只看異常", key="admin_history_anomaly")
        if st.form_submit_button("查詢"):
            reset_page("admin_history_page")
    response = api.get_page(
        "/metrics",
        "admin_history_page",
        PAGE_SIZE,
        server=server.strip() or None,
        metric=metric,
        start=local_param(start),
        end=local_end_param(end),
        anomaly_only=str(anomaly_only).lower(),
    )
    if not response.ok:
        st.error(api.error_text(response))
        return
    body = response.json()
    st.dataframe(
        [
            {
                "時間": to_local(m["recorded_at"]),
                "伺服器": m["server"],
                "指標": metric_label(m["metric"]),
                "數值": f"{m['value']:g} {m['unit']}",
                "閾值": m["threshold"],
                "異常": "⚠️" if m["is_anomaly"] else "",
            }
            for m in body["items"]
        ],
        hide_index=True,
        column_config={
            "時間": st.column_config.DatetimeColumn(format=TIME_FORMAT)
        },
    )
    pager("admin_history_page", body["total"], PAGE_SIZE)


st.title("系統管理")
show_flash("admin")

# on_change="rerun" runs only the open tab, so editing the user table does
# not also query the logs, the database status and the metric history
tabs = st.tabs(
    ["使用者管理", "系統日誌", "資料庫狀態", "即時資料歷史"],
    key="admin_tab",
    on_change="rerun",
)
sections = [render_users, render_logs, render_db_status, render_history]
for tab, render in zip(tabs, sections, strict=True):
    if tab.open:
        with tab:
            render()
