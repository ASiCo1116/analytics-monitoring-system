from datetime import datetime, timedelta

import streamlit as st

from lib import api, session
from lib.config import TZ
from lib.fmt import local_param, to_local
from lib.widgets import current_page, pager, reset_page

SORTS = {
    "記錄時間（新到舊）": "-recorded_at",
    "記錄時間（舊到新）": "recorded_at",
    "數值（大到小）": "-value",
    "數值（小到大）": "value",
    "標題": "title",
    "分類": "category",
}
PAGE_SIZES = [10, 20, 50, 100]

can_write = session.is_role("admin", "user")
me = session.user()

st.title("資料記錄")
if flash := st.session_state.pop("records_flash", None):
    st.success(flash)

categories_response = api.get("/records/categories")
categories = categories_response.json() if categories_response.ok else []

# ---------- filters ----------
with st.form("record_filters"):
    c1, c2, c3, c4 = st.columns(4)
    category = c1.selectbox("分類", ["全部", *categories])
    start_day = c2.date_input("開始日期", value=None)
    end_day = c3.date_input("結束日期（含）", value=None)
    keyword = c4.text_input("標題關鍵字")
    c5, c6, c7, c8 = st.columns(4)
    min_value = c5.number_input("最小值", value=None, format="%g")
    max_value = c6.number_input("最大值", value=None, format="%g")
    sort_label = c7.selectbox("排序", list(SORTS))
    page_size = c8.selectbox("每頁筆數", PAGE_SIZES, index=1)
    if st.form_submit_button("查詢", type="primary"):
        reset_page("records_page")

page = current_page("records_page")
response = api.get(
    "/records",
    page=page,
    page_size=page_size,
    category=None if category == "全部" else category,
    start=local_param(start_day),
    # The end date is inclusive on screen; the API end is exclusive
    end=local_param(end_day + timedelta(days=1)) if end_day else None,
    min_value=min_value,
    max_value=max_value,
    q=keyword,
    sort=SORTS[sort_label],
)
if not response.ok:
    st.error(api.error_text(response))
    st.stop()
result = response.json()
records = result["items"]



def can_modify(record: dict) -> bool:
    """Only the creator or an Admin may change or delete a record."""
    return me["role"] == "admin" or record["owner_id"] == me["id"]


# ---------- table ----------
rows = [
    {
        "ID": r["id"],
        "標題": r["title"],
        "數值": r["value"],
        "分類": r["category"],
        "記錄時間": to_local(r["recorded_at"]),
        "建立者": r["owner_username"],
        "描述": r["description"],
    }
    for r in records
]
column_config = {
    "記錄時間": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm")
}
if can_write:
    # Rows can be ticked for batch delete. The key follows the rows shown,
    # so another page, filter or a delete clears the selection instead of
    # pointing old row numbers at new records.
    table = st.dataframe(
        rows,
        hide_index=True,
        column_config=column_config,
        on_select="rerun",
        selection_mode="multi-row",
        key=f"records_table_{hash(tuple(r['id'] for r in records))}",
    )
    selected = [records[i] for i in table.selection.rows]
else:
    st.dataframe(rows, hide_index=True, column_config=column_config)
pager("records_page", result["total"], page_size)

if not can_write:
    # Viewers only browse; the backend refuses writes anyway
    st.stop()

# ---------- batch delete ----------
if selected:
    deletable = [r for r in selected if can_modify(r)]
    if skipped := len(selected) - len(deletable):
        st.warning(f"選取的記錄中有 {skipped} 筆不是你建立的，刪除時會略過。")
    if deletable:
        count = len(deletable)
        confirm = st.checkbox(f"確認刪除選取的 {count} 筆記錄")
        if st.button(
            f"刪除選取的 {count} 筆",
            disabled=not confirm,
            icon=":material/delete:",
        ):
            deleted = api.request(
                "POST",
                "/records/batch-delete",
                json={"ids": [r["id"] for r in deletable]},
            )
            if deleted.ok:
                st.session_state.records_flash = (
                    f"已刪除 {deleted.json()['deleted']} 筆記錄"
                )
                st.rerun()
            st.error(api.error_text(deleted))


def record_fields(prefix: str, record: dict | None = None) -> dict:
    """Inputs shared by the create and edit forms."""
    record = record or {}
    title = st.text_input(
        "標題", value=record.get("title", ""), key=f"{prefix}_title"
    )
    c1, c2 = st.columns(2)
    value = c1.number_input(
        "數值",
        value=record.get("value", 0.0),
        format="%g",
        key=f"{prefix}_value",
    )
    category = c2.text_input(
        "分類", value=record.get("category", ""), key=f"{prefix}_category"
    )
    recorded_at = st.datetime_input(
        "記錄時間",
        value=(
            to_local(record["recorded_at"])
            if record
            else datetime.now(TZ).replace(tzinfo=None, microsecond=0)
        ),
        key=f"{prefix}_recorded_at",
    )
    description = st.text_area(
        "描述",
        value=record.get("description") or "",
        key=f"{prefix}_description",
    )
    return {
        "title": title,
        "value": value,
        "category": category,
        # No zone: the backend reads it as APP_TIMEZONE
        "recorded_at": recorded_at.isoformat(),
        "description": description or None,
    }


create_tab, edit_tab, import_tab = st.tabs(["新增", "編輯／刪除", "匯入"])

with create_tab, st.form("create_record", clear_on_submit=True):
    data = record_fields("create")
    if st.form_submit_button("新增", type="primary"):
        created = api.request("POST", "/records", json=data)
        if created.status_code == 201:
            st.session_state.records_flash = (
                f"已新增記錄 {created.json()['id']}"
            )
            st.rerun()
        st.error(api.error_text(created))

with edit_tab:
    editable = [r for r in records if can_modify(r)]
    if not editable:
        st.caption("這一頁沒有可編輯的記錄（只能編輯自己建立的記錄）。")
    else:
        chosen = st.selectbox(
            "選擇記錄",
            editable,
            format_func=lambda r: f"{r['id']} – {r['title']}",
        )
        with st.form(f"edit_record_{chosen['id']}"):
            data = record_fields(f"edit_{chosen['id']}", chosen)
            if st.form_submit_button("儲存變更", type="primary"):
                # Send only what changed, so the audit log names the
                # fields that were really edited
                original = {
                    "title": chosen["title"],
                    "value": chosen["value"],
                    "category": chosen["category"],
                    "recorded_at": to_local(chosen["recorded_at"]).isoformat(),
                    "description": chosen["description"],
                }
                changes = {k: v for k, v in data.items() if v != original[k]}
                if not changes:
                    st.info("沒有任何變更")
                else:
                    updated = api.request(
                        "PATCH", f"/records/{chosen['id']}", json=changes
                    )
                    if updated.ok:
                        st.session_state.records_flash = (
                            f"已更新記錄 {chosen['id']}"
                        )
                        st.rerun()
                    st.error(api.error_text(updated))
        confirm = st.checkbox(f"確認刪除記錄 {chosen['id']}")
        if st.button("刪除", disabled=not confirm, icon=":material/delete:"):
            deleted = api.request("DELETE", f"/records/{chosen['id']}")
            if deleted.status_code == 204:
                st.session_state.records_flash = f"已刪除記錄 {chosen['id']}"
                st.rerun()
            st.error(api.error_text(deleted))

with import_tab:
    st.caption(
        "CSV 標頭：title,value,category,recorded_at,description"
        "（recorded_at 與 description 可留空）；JSON 為相同欄位的物件陣列。"
        "時間未帶時區時視為台灣時間。任一列有錯就不會匯入任何資料。"
    )
    upload = st.file_uploader("選擇 CSV 或 JSON 檔", type=["csv", "json"])
    if st.button("匯入", type="primary", disabled=upload is None):
        imported = api.request(
            "POST",
            "/records/import",
            files={"file": (upload.name, upload.getvalue(), upload.type)},
        )
        if imported.status_code == 201:
            st.session_state.records_flash = (
                f"已匯入 {imported.json()['imported']} 筆記錄"
            )
            st.rerun()
        detail = imported.json().get("detail")
        if imported.status_code == 422 and isinstance(detail, dict):
            errors = detail["errors"]
            st.error(f"共 {len(errors)} 個錯誤，沒有匯入任何資料。")
            st.dataframe(
                [
                    {
                        # One text column: row numbers and the whole-file
                        # case (row 0) mixed
                        "列": str(e["row"]) if e["row"] else "整個檔案",
                        "欄位": e["field"] or "",
                        "原因": e["message"],
                    }
                    for e in errors
                ],
                hide_index=True,
            )
        else:
            st.error(api.error_text(imported))
