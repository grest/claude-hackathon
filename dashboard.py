"""
SaaS Churn Metric Dashboard
Run with:  streamlit run dashboard.py
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

REPO_ROOT = Path(__file__).parent
sys.path.insert(0, str(REPO_ROOT))

from definitions.registry import get_definition, list_metrics
from engine.calculator import (
    customer_churn_rate as _ccr,
    revenue_churn_rate as _rcr,
    net_revenue_retention as _nrr,
)

st.set_page_config(
    page_title="SaaS Churn Dashboard",
    page_icon=":bar_chart:",
    layout="wide",
)

# ── helpers ───────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def _max_dataset_date(db: str) -> date:
    """Return the latest date present in the dataset (end_date or start_date)."""
    try:
        conn = sqlite3.connect(db)
        row = conn.execute(
            "SELECT MAX(COALESCE(end_date, start_date)) FROM subscriptions"
        ).fetchone()
        conn.close()
        if row and row[0]:
            return date.fromisoformat(row[0])
    except Exception:
        pass
    return date(2024, 12, 31)


@st.cache_data(ttl=60)
def load_subscriptions_cached(db: str) -> pd.DataFrame:
    from engine.db import fetch_subscriptions
    return fetch_subscriptions(db)


@st.cache_data(ttl=60)
def load_events_cached(db: str) -> pd.DataFrame:
    conn = sqlite3.connect(db)
    try:
        df = pd.read_sql_query(
            "SELECT event_id, customer_id, event_type, event_date, metadata "
            "FROM events ORDER BY event_date DESC",
            conn,
        )
    finally:
        conn.close()
    df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce")
    return df


# ── sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Settings")

    db_path_str = st.text_input(
        "SQLite DB path",
        value=str(REPO_ROOT / "data" / "churn_engine.db"),
    )
    db_path = Path(db_path_str)

    st.subheader("Time Period")

    _max_date = _max_dataset_date(str(db_path)) if db_path.exists() else date(2024, 12, 31)

    period_choice = st.radio(
        "Lookback",
        ["7 days", "30 days", "90 days", "Custom"],
        index=1,
        horizontal=True,
    )

    end_date: date = st.date_input(
        "End date",
        value=_max_date,
        max_value=date.today(),
    )

    if period_choice == "Custom":
        start_date: date = st.date_input(
            "Start date",
            value=end_date - timedelta(days=30),
            max_value=end_date - timedelta(days=1),
        )
        lookback_days = max((end_date - start_date).days, 1)
    else:
        lookback_days = {"7 days": 7, "30 days": 30, "90 days": 90}[period_choice]
        start_date = end_date - timedelta(days=lookback_days)

# ── DB existence check ────────────────────────────────────────────────────────
if not db_path.exists():
    st.warning(f"Database not found: `{db_path}`")
    if st.button("Generate DB"):
        with st.spinner("Building synthetic dataset…"):
            from db.init_db import build_db
            build_db(db_path)
        st.success("Database generated.")
        st.rerun()
    st.stop()

# ── load data ─────────────────────────────────────────────────────────────────
df = load_subscriptions_cached(str(db_path))
events_df = load_events_cached(str(db_path))

as_of_ts     = pd.Timestamp(end_date)
period_start = pd.Timestamp(start_date)

# ── page header ───────────────────────────────────────────────────────────────
st.title("SaaS Churn Dashboard")
st.caption(
    f"**{start_date}** → **{end_date}** ({lookback_days}-day window) | DB: `{db_path.name}`"
)

# ── KPI row ───────────────────────────────────────────────────────────────────
active_at_start = int(df[df["start_date"] <= period_start].shape[0])
active_now = int(
    df[
        (df["start_date"] <= as_of_ts)
        & (df["end_date"].isna() | (df["end_date"] > as_of_ts))
    ].shape[0]
)
churned_in_window = int(
    df[
        (df["status"] == "churned")
        & (df["end_date"] >= period_start)
        & (df["end_date"] <= as_of_ts)
    ].shape[0]
)
mrr_at_start = float(df[df["start_date"] <= period_start]["mrr"].sum())
churn_rate_pct = (
    round(churned_in_window / active_at_start * 100, 2) if active_at_start else 0.0
)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Active Customers", f"{active_now:,}")
col2.metric("Churned (in window)", f"{churned_in_window:,}")
col3.metric("MRR at Period Start", f"${mrr_at_start:,.0f}")
col4.metric("Customer Churn Rate", f"{churn_rate_pct:.2f}%")

st.divider()

# ── computed metrics ──────────────────────────────────────────────────────────
st.subheader("Metric Values")

_calc_map = {
    "customer_churn_rate":   _ccr,
    "revenue_churn_rate":    _rcr,
    "net_revenue_retention": _nrr,
}

metric_defs = list_metrics(version="v1")
mcols = st.columns(len(metric_defs))

for col, defn in zip(mcols, metric_defs):
    fn = _calc_map[defn.name]
    value = fn(df, end_date, lookback_days=lookback_days)
    col.metric(
        label=defn.name.replace("_", " ").title(),
        value=f"{value * 100:.2f}%",
        help=defn.description,
    )

st.divider()

# ── plan breakdown ────────────────────────────────────────────────────────────
st.subheader("Plan Breakdown")

active_df = df[
    (df["start_date"] <= as_of_ts)
    & (df["end_date"].isna() | (df["end_date"] > as_of_ts))
].copy()
plan_order = ["starter", "pro", "business", "enterprise"]

plan_agg = (
    active_df.groupby("plan", observed=True)
    .agg(active_count=("customer_id", "count"), total_mrr=("mrr", "sum"))
    .reindex(plan_order)
    .reset_index()
)

pb_col1, pb_col2 = st.columns(2)

with pb_col1:
    fig_count = px.bar(
        plan_agg, x="plan", y="active_count",
        title="Active Customers by Plan",
        labels={"plan": "Plan", "active_count": "Customers"},
        color="plan",
        color_discrete_sequence=px.colors.qualitative.Pastel,
        text_auto=True,
    )
    fig_count.update_layout(showlegend=False, height=350)
    st.plotly_chart(fig_count, use_container_width=True)

with pb_col2:
    fig_mrr = px.bar(
        plan_agg, x="plan", y="total_mrr",
        title="Total MRR by Plan (active)",
        labels={"plan": "Plan", "total_mrr": "MRR ($)"},
        color="plan",
        color_discrete_sequence=px.colors.qualitative.Pastel,
        text_auto=".2s",
    )
    fig_mrr.update_layout(showlegend=False, height=350)
    st.plotly_chart(fig_mrr, use_container_width=True)

st.divider()

# ── churn over time ───────────────────────────────────────────────────────────
st.subheader("Monthly Churn Rate (12 months ending at end date)")

monthly_points: list[dict] = []
for offset in range(11, -1, -1):
    y, m = end_date.year, end_date.month - offset
    while m <= 0:
        m += 12
        y -= 1
    next_first = date(y + (1 if m == 12 else 0), (m % 12) + 1, 1)
    last_day = min(next_first - timedelta(days=1), end_date)
    rate = _ccr(df, last_day, lookback_days=lookback_days)
    monthly_points.append({"month": last_day.strftime("%Y-%m"), "churn_rate": round(rate * 100, 2)})

churn_ts = pd.DataFrame(monthly_points)
fig_line = px.line(
    churn_ts, x="month", y="churn_rate",
    title="Monthly Customer Churn Rate (%)",
    labels={"month": "Month", "churn_rate": "Churn Rate (%)"},
    markers=True,
)
fig_line.update_layout(height=380)
st.plotly_chart(fig_line, use_container_width=True)

st.divider()

# ── recent events ─────────────────────────────────────────────────────────────
st.subheader("Recent Events (last 20)")

display_events = events_df.head(20).copy()
display_events["event_date"] = display_events["event_date"].dt.strftime("%Y-%m-%d")

st.dataframe(
    display_events[["event_id", "customer_id", "event_type", "event_date", "metadata"]],
    use_container_width=True,
    hide_index=True,
    column_config={
        "event_id":    st.column_config.TextColumn("Event ID"),
        "customer_id": st.column_config.TextColumn("Customer"),
        "event_type":  st.column_config.TextColumn("Type"),
        "event_date":  st.column_config.TextColumn("Date"),
        "metadata":    st.column_config.TextColumn("Metadata"),
    },
)
