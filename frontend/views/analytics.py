import streamlit as st

from lib import api, charts
from lib.fmt import local_end_param, local_param
from lib.labels import METRIC_UNITS, METRICS, metric_label
from lib.widgets import select_or_all

SOURCES = {"records": "資料記錄", "metrics": "即時監控資料"}
INTERVALS = {"minute": "每分鐘", "hour": "每小時", "day": "每天"}
XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


def format_stat(value: float | None) -> str:
    """A statistic for a card: thousands separators, no trailing zeros."""
    return "—" if value is None else f"{value:,.2f}".rstrip("0").rstrip(".")


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
    "end": local_end_param(end_day),
}
# The per-group statistics, when they are already known from building the
# server list (metrics with no server chosen)
groups_response = None
if source == "records":
    params["category"] = select_or_all(
        "分類", api.categories(), key="analytics_category", container=c3
    )
    unit = ""
else:
    metric = c3.selectbox(
        "指標", list(METRICS), format_func=metric_label, key="analytics_metric"
    )
    params["metric"] = metric
    unit = METRIC_UNITS[metric]
    # Server names come from the data itself
    all_groups = api.get("/analytics/groups", **params)
    servers = [g["group"] for g in all_groups.json()] if all_groups.ok else []
    params["server"] = select_or_all(
        "伺服器", servers, key="analytics_server", container=c4
    )
    if params["server"] is None:
        groups_response = all_groups
    if start_day is None:
        st.caption("未指定開始日期時，即時監控資料只統計最近 24 小時。")

summary = api.get("/analytics/summary", **params)
if not summary.ok:
    st.error(api.error_text(summary))
    st.stop()
stats = summary.json()

cards = st.columns(5)
cards[0].metric("筆數", f"{stats['count']:,}", border=True)
for card, (key, label) in zip(
    cards[1:],
    [("sum", "總計"), ("avg", "平均"), ("max", "最大值"), ("min", "最小值")],
    strict=True,
):
    card.metric(label, format_stat(stats[key]), border=True)

if stats["count"] == 0:
    st.info("沒有符合條件的資料。")
    st.stop()

left, right = st.columns(2)
with left:
    group_label = "分類" if source == "records" else "伺服器"
    st.markdown(f"**依{group_label}的平均值**")
    response = (
        groups_response
        if groups_response is not None
        else api.get("/analytics/groups", **params)
    )
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
        mime=XLSX_MEDIA_TYPE,
        type="primary",
        icon=":material/download:",
    )
    st.caption(
        "工作表：摘要、分組聚合、趨勢（依小時）、明細（最多最新 10,000 筆）"
    )
