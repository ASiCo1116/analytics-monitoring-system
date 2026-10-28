"""Plotly figures for the dashboard.

Plotly rather than st.line_chart: the live chart needs red anomaly points
and a threshold line.
"""

import plotly.graph_objects as go

from lib.fmt import to_local

ALERT = "#d62728"
# Series colours; red is kept for anomalies only
PALETTE = ["#1f77b4", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf", "#8c564b"]
HEIGHT = 340
# Opacity of the min-max band behind the trend line
BAND_OPACITY = 0.15


def _rgba(color: str, alpha: float) -> str:
    """ "#1f77b4" with an opacity, as Plotly's "rgba(...)"."""
    red, green, blue = (int(color[i : i + 2], 16) for i in (1, 3, 5))
    return f"rgba({red}, {green}, {blue}, {alpha})"


def _layout(fig: go.Figure, y_title: str = "") -> go.Figure:
    fig.update_layout(
        height=HEIGHT,
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
        legend={"orientation": "h", "y": 1.12},
        yaxis_title=y_title,
        # Keep zoom and legend clicks across the 1-second redraws
        uirevision="keep",
    )
    return fig


def _threshold_line(fig: go.Figure, threshold: float) -> None:
    fig.add_hline(
        y=threshold,
        line_dash="dash",
        line_color=ALERT,
        annotation_text=f"閾值 {threshold:g}",
        annotation_position="top left",
    )


def live_line(
    history: list[dict], metric: str, threshold: float, unit: str
) -> go.Figure:
    """Recent history of one metric: a line per server, red anomalies."""
    series: dict[str, list[dict]] = {}
    for message in history:
        for item in message["data"]:
            if item["metric"] == metric:
                series.setdefault(item["server"], []).append(item)
    fig = go.Figure()
    for index, (server, items) in enumerate(sorted(series.items())):
        color = PALETTE[index % len(PALETTE)]
        fig.add_scatter(
            x=[to_local(i["recorded_at"]) for i in items],
            y=[i["value"] for i in items],
            mode="lines+markers",
            name=server,
            line={"color": color},
            marker={
                "color": [ALERT if i["is_anomaly"] else color for i in items],
                "size": [10 if i["is_anomaly"] else 4 for i in items],
            },
        )
    _threshold_line(fig, threshold)
    return _layout(fig, unit)


def live_bar(latest: list[dict], threshold: float, unit: str) -> go.Figure:
    """Current value per server; bars above the threshold are red."""
    fig = go.Figure(
        go.Bar(
            x=[i["server"] for i in latest],
            y=[i["value"] for i in latest],
            marker_color=[
                ALERT if i["is_anomaly"] else PALETTE[0] for i in latest
            ],
            text=[f"{i['value']:g}" for i in latest],
            textposition="outside",
        )
    )
    _threshold_line(fig, threshold)
    return _layout(fig, unit)


def group_bar(groups: list[dict], value_key: str, y_title: str) -> go.Figure:
    """One bar per category or server."""
    fig = go.Figure(
        go.Bar(
            x=[g["group"] for g in groups],
            y=[g[value_key] for g in groups],
            marker_color=PALETTE[0],
        )
    )
    return _layout(fig, y_title)


def trend_line(points: list[dict], y_title: str) -> go.Figure:
    """Average per interval, with the min-max range shaded."""
    times = [to_local(p["bucket"]) for p in points]
    fig = go.Figure()
    fig.add_scatter(
        x=times,
        y=[p["max"] for p in points],
        mode="lines",
        line={"width": 0},
        showlegend=False,
        hoverinfo="skip",
    )
    fig.add_scatter(
        x=times,
        y=[p["min"] for p in points],
        mode="lines",
        line={"width": 0},
        fill="tonexty",
        fillcolor=_rgba(PALETTE[0], BAND_OPACITY),
        name="最小–最大",
    )
    fig.add_scatter(
        x=times,
        y=[p["avg"] for p in points],
        mode="lines+markers",
        name="平均",
        line={"color": PALETTE[0]},
    )
    return _layout(fig, y_title)
