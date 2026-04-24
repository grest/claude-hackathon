"""
SaaS Churn & Earnings Dashboard — v1.0 engine
Run: streamlit run saas_churn/dashboard.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import date

from saas_churn.engine import calculate_period_churn, classify_event
from saas_churn.data import MONTHS

st.set_page_config(page_title="SaaS Churn Dashboard", layout="wide")
st.title("SaaS Churn & Earnings Dashboard")
st.caption("Engine v1.0 — metric definition 2026-04-24")

# ---------------------------------------------------------------------------
# Compute monthly summaries
# ---------------------------------------------------------------------------

records = []
for m in MONTHS:
    summary = calculate_period_churn(
        events=m.events,
        period_start=m.period_start,
        period_end=m.period_end,
        period_start_mrr=m.period_start_mrr,
        period_start_account_count=m.period_start_account_count,
    )
    end_mrr = m.period_start_mrr - summary.total_mrr_lost + m.new_mrr
    records.append({
        "Month":              m.period_start.strftime("%b %Y"),
        "Start MRR":          m.period_start_mrr,
        "New MRR":            m.new_mrr,
        "MRR Lost":           summary.total_mrr_lost,
        "End MRR":            end_mrr,
        "Revenue Churn %":    summary.revenue_churn_rate,
        "Account Churn %":    summary.account_churn_rate,
        "Accounts Lost":      summary.total_accounts_lost,
        "Late Flags":         summary.late_notification_flags,
    })

df = pd.DataFrame(records)

# ---------------------------------------------------------------------------
# KPI cards — latest month
# ---------------------------------------------------------------------------

latest = df.iloc[-1]
prev   = df.iloc[-2]

col1, col2, col3, col4 = st.columns(4)

def delta_color(val, inverted=False):
    if inverted:
        return "normal" if val <= 0 else "inverse"
    return "normal" if val >= 0 else "inverse"

col1.metric(
    "Current MRR",
    f"${latest['End MRR']:,.0f}",
    f"${latest['End MRR'] - prev['End MRR']:+,.0f} vs prior month",
)
col2.metric(
    "Revenue Churn Rate",
    f"{latest['Revenue Churn %']:.2f}%",
    f"{latest['Revenue Churn %'] - prev['Revenue Churn %']:+.2f}pp vs prior month",
    delta_color="inverse",
)
col3.metric(
    "MRR Lost (churn)",
    f"${latest['MRR Lost']:,.0f}",
    f"${latest['MRR Lost'] - prev['MRR Lost']:+,.0f} vs prior month",
    delta_color="inverse",
)
col4.metric(
    "New MRR",
    f"${latest['New MRR']:,.0f}",
    f"${latest['New MRR'] - prev['New MRR']:+,.0f} vs prior month",
)

st.divider()

# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

left, right = st.columns(2)

# MRR waterfall — latest month
with left:
    st.subheader(f"MRR Waterfall — {latest['Month']}")
    waterfall = go.Figure(go.Waterfall(
        orientation="v",
        measure=["absolute", "relative", "relative", "total"],
        x=["Start MRR", "New MRR", "Churn Loss", "End MRR"],
        y=[latest["Start MRR"], latest["New MRR"], -latest["MRR Lost"], 0],
        connector={"line": {"color": "rgb(63,63,63)"}},
        increasing={"marker": {"color": "#2ecc71"}},
        decreasing={"marker": {"color": "#e74c3c"}},
        totals={"marker": {"color": "#3498db"}},
    ))
    waterfall.update_layout(
        showlegend=False, height=350,
        margin=dict(l=20, r=20, t=20, b=20),
        yaxis_tickprefix="$", yaxis_tickformat=",.0f",
    )
    st.plotly_chart(waterfall, use_container_width=True)

# Revenue churn rate trend
with right:
    st.subheader("Revenue Churn Rate — 6-Month Trend")
    fig_churn = go.Figure()
    fig_churn.add_trace(go.Scatter(
        x=df["Month"], y=df["Revenue Churn %"],
        mode="lines+markers", name="Revenue Churn %",
        line=dict(color="#e74c3c", width=2),
        marker=dict(size=7),
    ))
    fig_churn.update_layout(
        height=350, showlegend=False,
        margin=dict(l=20, r=20, t=20, b=20),
        yaxis_ticksuffix="%",
        yaxis=dict(rangemode="tozero"),
    )
    st.plotly_chart(fig_churn, use_container_width=True)

# MRR over time — stacked area
st.subheader("MRR Over Time")
fig_mrr = go.Figure()
fig_mrr.add_trace(go.Bar(
    x=df["Month"], y=df["MRR Lost"],
    name="MRR Lost", marker_color="#e74c3c", opacity=0.8,
))
fig_mrr.add_trace(go.Bar(
    x=df["Month"], y=df["New MRR"],
    name="New MRR", marker_color="#2ecc71", opacity=0.8,
))
fig_mrr.add_trace(go.Scatter(
    x=df["Month"], y=df["End MRR"],
    name="End MRR", mode="lines+markers",
    line=dict(color="#3498db", width=3),
    marker=dict(size=8), yaxis="y",
))
fig_mrr.update_layout(
    barmode="group", height=380,
    margin=dict(l=20, r=20, t=20, b=20),
    yaxis_tickprefix="$", yaxis_tickformat=",.0f",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)
st.plotly_chart(fig_mrr, use_container_width=True)

# ---------------------------------------------------------------------------
# Event-level detail — latest month
# ---------------------------------------------------------------------------

st.subheader(f"Account Events — {latest['Month']}")

latest_month = MONTHS[-1]
event_rows = []
for e in latest_month.events:
    result = classify_event(e)
    event_rows.append({
        "Account":        e.account_id.replace("_", " ").title(),
        "Event":          e.event_type.value.replace("_", " ").title(),
        "Old MRR":        f"${e.old_mrr:,.0f}",
        "New MRR":        f"${e.new_mrr:,.0f}",
        "MRR Lost":       f"${result.mrr_lost:,.0f}" if result.is_churn else "—",
        "Counted":        "Yes" if result.is_churn else "No",
        "Exclusion":      result.exclusion_reason or "—",
        "Late Flag":      "Yes" if result.late_notification_flag else "No",
    })

event_df = pd.DataFrame(event_rows)

def highlight_churn(row):
    if row["Counted"] == "Yes":
        return ["background-color: #fdecea"] * len(row)
    if row["Exclusion"] != "—":
        return ["background-color: #eaf4fb"] * len(row)
    return [""] * len(row)

st.dataframe(
    event_df.style.apply(highlight_churn, axis=1),
    use_container_width=True, hide_index=True,
)

# ---------------------------------------------------------------------------
# Monthly summary table
# ---------------------------------------------------------------------------

st.subheader("Monthly Summary")
display_df = df.copy()
display_df["Start MRR"]       = display_df["Start MRR"].map("${:,.0f}".format)
display_df["New MRR"]         = display_df["New MRR"].map("${:,.0f}".format)
display_df["MRR Lost"]        = display_df["MRR Lost"].map("${:,.0f}".format)
display_df["End MRR"]         = display_df["End MRR"].map("${:,.0f}".format)
display_df["Revenue Churn %"] = display_df["Revenue Churn %"].map("{:.2f}%".format)
display_df["Account Churn %"] = display_df["Account Churn %"].map("{:.2f}%".format)

st.dataframe(display_df, use_container_width=True, hide_index=True)
