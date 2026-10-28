from datetime import timedelta

import streamlit as st

from lib import api, charts
from lib.fmt import local_param

SOURCES = {"records": "資料記錄", "metrics": "即時監控資料"}
METRICS = {"cpu": "CPU", "memory": "記憶體", "temperature": "溫度"}
UNITS = {"cpu": "%", "memory": "%", "temperature": "°C"}
INTERVALS = {"minute": "每分鐘", "hour": "每小時", "day": "每天"}
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

st.title("資料分析")

source = st.segmented_control(
    "資料來源",
    list(SOURCES),
    format_func=SOURCES.get,
    default="records",
    required=True,
    key="analytics_source",
)

c1, c2, c3, c4 = st.columns(4)
start_day = c1.date_input("開始日期", value=None, key="analytics_start")
end_day = c2.date_input("結束日期（含）", value=None, key="analytics_end")
params = {
    "source": source,
    "start": local_param(start_day),
    # The end date is inclusive on screen; the API end is exclusive
    "end": local_param(end_day + timedelta(days=1)) if end_day else None,
}
if source == "records":
    categories = api.get("/records/categories")
    category = c3.selectbox(
        "分類",
        ["全部", *(categories.json() if categories.ok else [])],
        key="analytics_category",
    )
    params["category"] = None if category == "全部" else category
    unit = ""
else:
    metric = c3.selectbox(
        "指標", list(METRICS), format_func=METRICS.get, key="analytics_metric"
    )
    params["metric"] = metric
    unit = UNITS[metric]
    # Server names come from the data itself
    all_groups = api.get("/analytics/groups", **params)
    servers = [g["group"] for g in all_groups.json()] if all_groups.ok else []
    server = c4.selectbox("伺服器", ["全部", *servers], key="analytics_server")
    params["server"] = None if server == "全部" else server
    if start_day is None:
        st.caption("未指定開始日期時，即時監控資料只統計最近 24 小時。")

summary = api.get("/analytics/summary", **params)
if not summary.ok:
    st.error(api.error_text(summary))
    st.stop()
stats = summary.json()


def show(value: float | None) -> str:
    return "—" if value is None else f"{value:,.2f}".rstrip("0").rstrip(".")


cards = st.columns(5)
cards[0].metric("筆數", f"{stats['count']:,}", border=True)
for card, (key, label) in zip(
    cards[1:],
    [("sum", "總計"), ("avg", "平均"), ("max", "最大值"), ("min", "最小值")],
    strict=True,
):
    card.metric(label, show(stats[key]), border=True)

if stats["count"] == 0:
    st.info("沒有符合條件的資料。")
    st.stop()

left, right = st.columns(2)
with left:
    group_label = "分類" if source == "records" else "伺服器"
    st.markdown(f"**依{group_label}的平均值**")
    response = api.get("/analytics/groups", **params)
    if not response.ok:
        st.error(api.error_text(response))
    else:
        groups = response.json()
        st.plotly_chart(
            charts.group_bar(groups, "avg", unit), key="groups_chart"
        )
        st.dataframe(
            [
                {
                    group_label: g["group"],
                    "筆數": g["count"],
                    "總計": g["sum"],
                    "平均": g["avg"],
                    "最大值": g["max"],
                    "最小值": g["min"],
                }
                for g in groups
            ],
            hide_index=True,
        )
with right:
    interval = st.segmented_control(
        "趨勢粒度",
        list(INTERVALS),
        format_func=INTERVALS.get,
        default="hour",
        required=True,
        key="analytics_interval",
    )
    response = api.get("/analytics/trend", interval=interval, **params)
    if not response.ok:
        st.error(api.error_text(response))
    else:
        st.plotly_chart(
            charts.trend_line(response.json(), unit), key="trend_chart"
        )

# ---------- Excel ----------
st.divider()
# The prepared file belongs to these exact filters
export_key = repr(sorted(params.items()))
prepared = st.session_state.get("analytics_export")
if st.button("準備 Excel 檔", icon=":material/table_view:"):
    response = api.get("/analytics/export", **params)
    if response.ok:
        disposition = response.headers.get("content-disposition", "")
        filename = disposition.split('filename="')[-1].rstrip('"')
        prepared = st.session_state.analytics_export = {
            "key": export_key,
            "name": filename,
            "data": response.content,
        }
    else:
        st.error(api.error_text(response))
if prepared and prepared["key"] == export_key:
    st.download_button(
        f"下載 {prepared['name']}",
        prepared["data"],
        file_name=prepared["name"],
        mime=XLSX,
        type="primary",
        icon=":material/download:",
    )
    st.caption(
        "工作表：摘要、分組聚合、趨勢（依小時）、明細（最多最新 10,000 筆）"
    )
