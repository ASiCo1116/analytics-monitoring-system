import streamlit as st

from lib import charts, session
from lib.fmt import to_local
from lib.labels import METRICS, metric_label
from lib.ws_listener import HISTORY_SECONDS, MAX_ALERTS

st.title("即時監控")
metric = st.segmented_control(
    "指標",
    list(METRICS),
    format_func=METRICS.get,
    default="cpu",
    required=True,
    key="monitor_metric",
)


@st.fragment(run_every=1)
def live_panel(metric: str) -> None:
    """Redrawn every second; only this part of the page reruns."""
    listener = session.listener()
    listener.touch()
    if listener.auth_failed:
        session.end(expired=True)
        st.rerun(scope="app")

    if listener.connected:
        st.caption(":green[●] 已連線，每秒更新")
    else:
        st.caption(":red[●] 已斷線，正在重新連線…")

    # Snapshot: the listener thread keeps appending meanwhile
    history = list(listener.history)
    if not history:
        st.info("等待即時資料…")
        return
    latest = [i for i in history[-1]["data"] if i["metric"] == metric]
    if not latest:
        # The backend sends an empty batch when no servers are configured
        st.info("目前沒有任何伺服器的資料。")
        return
    threshold = latest[0]["threshold"]
    unit = latest[0]["unit"]

    for column, item in zip(st.columns(len(latest)), latest, strict=True):
        with column.container(border=True):
            st.caption(item["server"])
            value = f"{item['value']:g} {unit}"
            if item["is_anomaly"]:
                st.markdown(f"### :red[{value}] ⚠️")
                st.caption(f":red[超過閾值 {threshold:g}]")
            else:
                st.markdown(f"### {value}")
                st.caption(f"閾值 {threshold:g}")

    line, bar = st.columns([2, 1])
    with line:
        st.markdown(f"**最近 {HISTORY_SECONDS} 秒的{metric_label(metric)}**")
        st.plotly_chart(
            charts.live_line(history, metric, threshold, unit),
            key="monitor_line",
        )
    with bar:
        st.markdown("**目前數值**")
        st.plotly_chart(
            charts.live_bar(latest, threshold, unit), key="monitor_bar"
        )

    st.markdown(f"**最近 {MAX_ALERTS} 筆告警**（所有指標）")
    alerts = list(listener.alerts)
    if alerts:
        st.dataframe(
            [
                {
                    "時間": to_local(a["recorded_at"]),
                    "伺服器": a["server"],
                    "指標": metric_label(a["metric"]),
                    "數值": f"{a['value']:g} {a['unit']}",
                    "閾值": a["threshold"],
                }
                for a in reversed(alerts)
            ],
            hide_index=True,
        )
    else:
        st.caption("目前沒有告警")


live_panel(metric)
