from datetime import datetime

import streamlit as st

from lib import api, session
from lib.config import APP_TIMEZONE, TZ
from lib.fmt import local_end_param, local_param, to_local
from lib.widgets import (
    flash,
    pager,
    reset_page,
    select_or_all,
    show_flash,
)

SORTS = {
    "記錄時間（新到舊）": "-recorded_at",
    "記錄時間（舊到新）": "recorded_at",
    "數值（大到小）": "-value",
    "數值（小到大）": "value",
    "標題": "title",
    "分類": "category",
}
PAGE_SIZES = [10, 20, 50, 100]
DEFAULT_PAGE_SIZE = 20


def can_modify(record: dict) -> bool:
    """Only the creator or an Admin may change or delete a record."""
    return (
        session.is_role("admin") or record["owner_id"] == session.user()["id"]
    )


def changed(message: str) -> None:
    """After any change to the records: refresh the categories, rerun."""
    api.forget_categories()
    flash("records", message)


def render_filters() -> tuple[dict, int]:
    """The filter form; returns the /records filters and the page size."""
    with st.form("records_filters"):
        c1, c2, c3, c4 = st.columns(4)
        category = select_or_all(
            "分類", api.categories(), key="records_category", container=c1
        )
        start = c2.date_input("開始日期", value=None, key="records_start")
        end = c3.date_input("結束日期（含）", value=None, key="records_end")
        keyword = c4.text_input("標題關鍵字", key="records_keyword")
        c5, c6, c7, c8 = st.columns(4)
        min_value = c5.number_input(
            "最小值", value=None, format="%g", key="records_min"
        )
        max_value = c6.number_input(
            "最大值", value=None, format="%g", key="records_max"
        )
        sort = c7.selectbox("排序", list(SORTS), key="records_sort")
        page_size = c8.selectbox(
            "每頁筆數",
            PAGE_SIZES,
            index=PAGE_SIZES.index(DEFAULT_PAGE_SIZE),
            key="records_page_size",
        )
        if st.form_submit_button("查詢", type="primary"):
            reset_page("records_page")
    query = {
        "category": category,
        "start": local_param(start),
        "end": local_end_param(end),
        "min_value": min_value,
        "max_value": max_value,
        "q": keyword,
        "sort": SORTS[sort],
    }
    return query, page_size


def render_table(records: list[dict], selectable: bool) -> list[dict]:
    """The records of this page; returns the rows ticked for deleting."""
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
    if not selectable:
        st.dataframe(rows, hide_index=True, column_config=column_config)
        return []
    # The key follows the rows shown, so another page, filter or a delete
    # clears the selection instead of pointing old row numbers at new
    # records
    table = st.dataframe(
        rows,
        hide_index=True,
        column_config=column_config,
        on_select="rerun",
        selection_mode="multi-row",
        key=f"records_table_{hash(tuple(r['id'] for r in records))}",
    )
    return [records[i] for i in table.selection.rows]


def render_batch_delete(selected: list[dict]) -> None:
    deletable = [r for r in selected if can_modify(r)]
    if skipped := len(selected) - len(deletable):
        st.warning(f"選取的記錄中有 {skipped} 筆不是你建立的，刪除時會略過。")
    if not deletable:
        return
    count = len(deletable)
    ids = [r["id"] for r in deletable]
    # Keyed by the exact rows: ticking it for one selection must not carry
    # over to another selection of the same size
    confirm = st.checkbox(
        f"確認刪除選取的 {count} 筆記錄",
        key=f"records_batch_confirm_{hash(tuple(ids))}",
    )
    if st.button(
        f"刪除選取的 {count} 筆",
        disabled=not confirm,
        icon=":material/delete:",
        key="records_batch_delete",
    ):
        response = api.request(
            "POST", "/records/batch-delete", json={"ids": ids}
        )
        if response.ok:
            changed(f"已刪除 {response.json()['deleted']} 筆記錄")
        st.error(api.error_text(response))


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


def render_create() -> None:
    # Bumped after each successful create: new widget keys give an empty
    # form, while after an error the same keys keep what the user typed
    form_round = st.session_state.get("records_create_round", 0)
    with st.form(f"records_create_{form_round}"):
        data = record_fields(f"records_create_{form_round}")
        if st.form_submit_button("新增", type="primary"):
            response = api.request("POST", "/records", json=data)
            if response.ok:
                st.session_state.records_create_round = form_round + 1
                changed(f"已新增記錄 {response.json()['id']}")
            st.error(api.error_text(response))


def render_edit(records: list[dict]) -> None:
    editable = [r for r in records if can_modify(r)]
    if not editable:
        st.caption("這一頁沒有可編輯的記錄（只能編輯自己建立的記錄）。")
        return
    by_id = {r["id"]: r for r in editable}
    # Options are ids and the widget is keyed, so the choice survives a
    # title edit (the shown label changes, the id does not)
    chosen = by_id[
        st.selectbox(
            "選擇記錄",
            list(by_id),
            format_func=lambda i: f"{i} – {by_id[i]['title']}",
            key="records_edit_choice",
        )
    ]
    with st.form(f"records_edit_{chosen['id']}"):
        data = record_fields(f"records_edit_{chosen['id']}", chosen)
        if st.form_submit_button("儲存變更", type="primary"):
            # Send only what changed, so the audit log names the fields that
            # were really edited
            original = {
                "title": chosen["title"],
                "value": chosen["value"],
                "category": chosen["category"],
                # The time input keeps minutes only; compare at that
                # precision so an untouched time is not a change
                "recorded_at": to_local(chosen["recorded_at"])
                .replace(second=0, microsecond=0)
                .isoformat(),
                "description": chosen["description"],
            }
            changes = {k: v for k, v in data.items() if v != original[k]}
            if not changes:
                st.info("沒有任何變更")
            else:
                response = api.request(
                    "PATCH", f"/records/{chosen['id']}", json=changes
                )
                if response.ok:
                    changed(f"已更新記錄 {chosen['id']}")
                st.error(api.error_text(response))
    confirm = st.checkbox(
        f"確認刪除記錄 {chosen['id']}",
        key=f"records_delete_confirm_{chosen['id']}",
    )
    if st.button(
        "刪除",
        disabled=not confirm,
        icon=":material/delete:",
        key="records_delete",
    ):
        response = api.request("DELETE", f"/records/{chosen['id']}")
        if response.ok:
            changed(f"已刪除記錄 {chosen['id']}")
        st.error(api.error_text(response))


def show_import_errors(errors: list[dict]) -> None:
    st.error(f"共 {len(errors)} 個錯誤，沒有匯入任何資料。")
    st.dataframe(
        [
            {
                # One text column: row numbers and the whole-file case
                # (row 0) mixed
                "列": str(e["row"]) if e["row"] else "整個檔案",
                "欄位": e["field"] or "",
                "原因": e["message"],
            }
            for e in errors
        ],
        hide_index=True,
    )


def render_import() -> None:
    st.caption(
        "CSV 標頭：title,value,category,recorded_at,description"
        "（recorded_at 與 description 可留空）；JSON 為相同欄位的物件陣列。"
        f"時間未帶時區時視為 {APP_TIMEZONE} 時間。"
        "任一列有錯就不會匯入任何資料。"
    )
    upload = st.file_uploader(
        "選擇 CSV 或 JSON 檔", type=["csv", "json"], key="records_upload"
    )
    if not st.button(
        "匯入", type="primary", disabled=upload is None, key="records_import"
    ):
        return
    response = api.request(
        "POST",
        "/records/import",
        files={"file": (upload.name, upload.getvalue(), upload.type)},
    )
    if response.ok:
        changed(f"已匯入 {response.json()['imported']} 筆記錄")
    detail = api.detail(response)
    if response.status_code == 422 and isinstance(detail, dict):
        show_import_errors(detail["errors"])
    else:
        st.error(api.error_text(response))


st.title("資料記錄")
show_flash("records")

query, page_size = render_filters()
response = api.get_page("/records", "records_page", page_size, **query)
if not response.ok:
    st.error(api.error_text(response))
    st.stop()
result = response.json()
records = result["items"]

can_write = session.is_role("admin", "user")
selected = render_table(records, selectable=can_write)
pager("records_page", result["total"], page_size)

if not can_write:
    # Viewers only browse; the backend refuses writes anyway
    st.stop()

if selected:
    render_batch_delete(selected)

# Not lazy like the admin tabs: these make no API calls, and rendering all
# of them keeps unsaved input when switching tabs
create_tab, edit_tab, import_tab = st.tabs(["新增", "編輯／刪除", "匯入"])
with create_tab:
    render_create()
with edit_tab:
    render_edit(records)
with import_tab:
    render_import()
