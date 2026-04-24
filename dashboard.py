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

# ── repo-root resolution (works regardless of cwd) ──────────────────────────
REPO_ROOT = Path(__file__).parent
sys.path.insert(0, str(REPO_ROOT))

from definitions.registry import get_definition, list_metrics
from engine.calculator import compute

# ── page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SaaS Churn Dashboard",
    page_icon=":bar_chart:",
    layout="wide",
)

# ── sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Settings")
    as_of: date = st.date_input(
        "As-of date",
        value=date.today(),
        max_value=date.today(),
    )
    db_path_str = st.text_input(
        "SQLite DB path",
        value=str(REPO_ROOT / "data" / "churn_engine.db"),
    )
    db_path = Path(db_path_str)

# ── DB existence check ────────────────────────────────────────────────────────
if not db_path.exists():
    st.warning(f"Database not found: `{db_path}`")
    if st.button("Generate DB"):
        with st.spinner("Building synthetic dataset…"):
            from db.init_db import build_db
            build_db(db_path)
        st.success("Database generated successfully.")
        st.rerun()
    st.stop()


# ── data loaders ─────────────────────────────────────────────────────────────
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


# ── load data ─────────────────────────────────────────────────────────────────
df = load_subscriptions_cached(str(db_path))
events_df = load_events_cached(str(db_path))

as_of_ts = pd.Timestamp(as_of)
lookback_days = 30
period_start = as_of_ts - timedelta(days=lookback_days)

# ── page header ───────────────────────────────────────────────────────────────
st.title("SaaS Churn Dashboard")
st.caption(f"As of **{as_of}** | 30-day lookback window | DB: `{db_path.name}`")

# ── KPI row ───────────────────────────────────────────────────────────────────
active_customers = int(df[df["status"] == "active"].shape[0])
churned_in_window = int(
    df[
        (df["status"] == "churned")
        & (df["end_date"] >= period_start)
        & (df["end_date"] <= as_of_ts)
    ].shape[0]
)
mrr_at_start = float(df[df["start_date"] <= period_start]["mrr"].sum())
active_at_start = int(df[df["start_date"] <= period_start].shape[0])
churn_rate_pct = (
    round(churned_in_window / active_at_start * 100, 2) if active_at_start else 0.0
)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Active Customers", f"{active_customers:,}")
col2.metric("Churned (in window)", f"{churned_in_window:,}")
col3.metric("MRR at Period Start", f"${mrr_at_start:,.0f}")
col4.metric("Customer Churn Rate", f"{churn_rate_pct:.2f}%")

st.divider()

# ── computed metrics ──────────────────────────────────────────────────────────
st.subheader("Metric Values")

metric_defs = list_metrics(version="v1")
mcols = st.columns(len(metric_defs))

for col, defn in zip(mcols, metric_defs):
    value = compute(defn, df, as_of)
    col.metric(
        label=defn.name.replace("_", " ").title(),
        value=f"{value * 100:.2f}%",
        help=defn.description,
    )

st.divider()

# ── plan breakdown ────────────────────────────────────────────────────────────
st.subheader("Plan Breakdown")

active_df = df[df["status"] == "active"].copy()
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
        plan_agg,
        x="plan",
        y="active_count",
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
        plan_agg,
        x="plan",
        y="total_mrr",
        title="Total MRR by Plan",
        labels={"plan": "Plan", "total_mrr": "MRR ($)"},
        color="plan",
        color_discrete_sequence=px.colors.qualitative.Pastel,
        text_auto=".2s",
    )
    fig_mrr.update_layout(showlegend=False, height=350)
    st.plotly_chart(fig_mrr, use_container_width=True)

st.divider()

# ── churn over time (last 12 months) ─────────────────────────────────────────
st.subheader("Monthly Churn Rate (last 12 months)")

ccr_def = get_definition("customer_churn_rate", "v1")
monthly_points: list[dict] = []

for offset in range(11, -1, -1):
    year = as_of.year
    month = as_of.month - offset
    while month <= 0:
        month += 12
        year -= 1
    # last day of that month
    next_m_first = date(year + (1 if month == 12 else 0), (month % 12) + 1, 1)
    last_day = next_m_first - timedelta(days=1)
    point = min(last_day, as_of)
    rate = compute(ccr_def, df, point)
    monthly_points.append({"month": point.strftime("%Y-%m"), "churn_rate": round(rate * 100, 2)})

churn_ts = pd.DataFrame(monthly_points)

fig_line = px.line(
    churn_ts,
    x="month",
    y="churn_rate",
    title="Monthly Customer Churn Rate (%)",
    labels={"month": "Month", "churn_rate": "Churn Rate (%)"},
    markers=True,
)
fig_line.update_layout(height=380)
st.plotly_chart(fig_line, use_container_width=True)

st.divider()

# ── recent events ──────────────────────────────────────────────────────────────
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
