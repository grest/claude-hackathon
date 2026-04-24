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
    logo_churn_conservative as _logo_cons,
    downgrade_inclusive_churn as _di_churn,
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

    if st.button("📊 Jump to reconciliation window", use_container_width=True):
        st.session_state["_end_date"] = date(2024, 11, 30)
        st.session_state["_period"] = "30 days"
        st.rerun()

    _PERIOD_OPTIONS = ["7 days", "30 days", "90 days", "Custom"]
    period_choice = st.radio(
        "Lookback",
        _PERIOD_OPTIONS,
        index=_PERIOD_OPTIONS.index(st.session_state.get("_period", "30 days")),
        horizontal=True,
    )
    st.session_state["_period"] = period_choice

    end_date: date = st.date_input(
        "End date",
        value=st.session_state.get("_end_date", _max_date),
        max_value=date.today(),
    )
    st.session_state["_end_date"] = end_date

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
    "customer_churn_rate":       _ccr,
    "revenue_churn_rate":        _rcr,
    "net_revenue_retention":     _nrr,
    "downgrade_inclusive_churn": _di_churn,
    "logo_churn_conservative":   _logo_cons,
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

# EC customers active at as_of — mark their plan bars
_ec_active_by_plan = (
    df[
        df["customer_id"].str.startswith("EC")
        & (df["start_date"] <= as_of_ts)
        & (df["end_date"].isna() | (df["end_date"] > as_of_ts))
        & df["plan"].isin(plan_order)
    ]
    .groupby("plan")["customer_id"].nunique()
    .to_dict()
)
# EC churns inside the Nov-2024 reconciliation window — show impact per plan
_ec_nov_churns_by_plan = (
    df[
        df["customer_id"].str.startswith("EC")
        & (df["status"] == "churned")
        & (df["end_date"] >= pd.Timestamp("2024-11-01"))
        & (df["end_date"] <= pd.Timestamp("2024-11-30"))
        & df["plan"].isin(plan_order)
    ]
    .groupby("plan")["customer_id"].count()
    .to_dict()
)

def _add_ec_bar_annotations(fig, plan_agg_df: pd.DataFrame, y_col: str) -> None:
    """Add red edge-case markers above bars that contain EC customers."""
    for _, row in plan_agg_df.iterrows():
        plan = row["plan"]
        n_active = _ec_active_by_plan.get(plan, 0)
        n_churns = _ec_nov_churns_by_plan.get(plan, 0)
        if n_active == 0 and n_churns == 0:
            continue
        parts = []
        if n_active:
            parts.append(f"★ incl. {n_active} EC")
        if n_churns:
            parts.append(f"⚠ {n_churns} EC churned (Nov)")
        y_val = row[y_col] if pd.notna(row[y_col]) else 0
        fig.add_annotation(
            x=plan, y=y_val,
            text="<br>".join(parts),
            showarrow=True,
            arrowhead=2,
            arrowcolor="#d62728",
            arrowwidth=1,
            ax=0, ay=-36,
            font=dict(color="#d62728", size=9),
            bgcolor="rgba(255,235,235,0.9)",
            bordercolor="#d62728",
            borderwidth=1,
            align="center",
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
    _add_ec_bar_annotations(fig_count, plan_agg, "active_count")
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
    _add_ec_bar_annotations(fig_mrr, plan_agg, "total_mrr")
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

# Mark the edge-case reconciliation window if it falls inside the chart range
_ec_month = "2024-11"
if _ec_month in churn_ts["month"].values:
    _ec_rate = churn_ts.loc[churn_ts["month"] == _ec_month, "churn_rate"].iloc[0]
    _n_ec = len(
        df[
            df["customer_id"].str.startswith("EC")
            & (df["status"] == "churned")
            & (df["end_date"] >= pd.Timestamp("2024-11-01"))
            & (df["end_date"] <= pd.Timestamp("2024-11-30"))
        ]
    )
    fig_line.add_vline(
        x=_ec_month, line_dash="dot", line_color="#d62728", line_width=1.5, opacity=0.6,
    )
    fig_line.add_annotation(
        x=_ec_month, y=_ec_rate,
        text=f"⚠ edge case window<br>{_n_ec} EC churns injected",
        showarrow=True,
        arrowhead=2,
        arrowcolor="#d62728",
        arrowwidth=1.5,
        ax=90, ay=-45,
        font=dict(color="#d62728", size=10),
        bgcolor="rgba(255,235,235,0.9)",
        bordercolor="#d62728",
        borderwidth=1,
        align="left",
    )

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

st.divider()
st.subheader("Reconciliation Table — Edge Cases × Definitions")
st.info(
    "This table is **always pinned to 2024-11-01 → 2024-11-30** regardless of the sidebar "
    "selection — the 15 edge cases (EC001–EC015) were designed for this window. "
    "Use **📊 Jump to reconciliation window** in the sidebar to align the KPIs above with this view."
)

RECON_AS_OF = date(2024, 11, 30)
RECON_LOOKBACK = 30
EDGE_CASE_IDS = [f"EC{str(i).zfill(3)}" for i in range(1, 16)]

# All 5 calculator functions
CALC_FNS = {
    "customer_churn_rate":       _ccr,
    "revenue_churn_rate":        _rcr,
    "net_revenue_retention":     _nrr,
    "logo_churn_conservative":   _logo_cons,
    "downgrade_inclusive_churn": _di_churn,
}

recon_rows = []
for ec_id in EDGE_CASE_IDS:
    ec_df = df[df["customer_id"] == ec_id]
    if ec_df.empty:
        continue
    row = {"Customer": ec_id}
    for metric_name, fn in CALC_FNS.items():
        val = fn(ec_df, RECON_AS_OF, lookback_days=RECON_LOOKBACK)
        row[metric_name] = f"{val*100:.1f}%"
    recon_rows.append(row)

if recon_rows:
    recon_df = pd.DataFrame(recon_rows).set_index("Customer")
    st.dataframe(recon_df, use_container_width=True)
else:
    st.info(
        "No edge-case customers (EC001–EC015) found in the current dataset. "
        "Load a dataset that includes these IDs to see the reconciliation table."
    )

with st.expander("What each row demonstrates (window: 2024-11-01 → 2024-11-30)"):
    st.markdown("""
| Customer | Scenario | Expected values | What it shows |
|----------|----------|-----------------|---------------|
| EC001 | Started exactly on period boundary (Oct 31) | ccr=**100%** · logo_cons=**0%** | `customer_churn_rate` uses `≤ period_start`; `logo_churn_conservative` uses `< period_start` — one character difference, different answer |
| EC002 | Unknown plan, MRR=$149, churned Nov 15 | ccr=rcr=100% · nrr=0% | All definitions include unknown-plan revenue equally; the business question is whether to exclude it before calculating |
| EC003 | Churned exactly on Oct 31 (= period start) | All churn=**100%** · nrr=0% | Confirms the window start boundary is inclusive in every definition |
| EC004 | Long-tenure enterprise ($499) churned Nov 20 | All churn=**100%** · nrr=0% | All definitions agree — the disagreement shows up in the dollar *amount*, not the rate |
| EC005 | Active customer, plan downgrade event in window | All churn=**0%** · nrr=**100%** | NRR sees full retention (active = no lost MRR); downgrade MRR loss not modeled in current engine |
| EC006 | Active customer, plan upgrade event in window | All churn=**0%** · nrr=**100%** | NRR would show >100% in a full model (expansion MRR); current engine caps at 100% |
| EC007 | 7-day tenure (Oct 25→Nov 1) — trial-like | All churn=**100%** · nrr=0% | All 5 definitions count this as 100% churn; none has a minimum-tenure exclusion |
| EC008 | Churned Nov 30 (UTC) = Dec 1 Europe/Berlin | All churn=**100%** · nrr=0% | Our system counts it (UTC date = Nov 30 is in-window); a timezone-aware system would move it to Dec 1 and produce 0% |
| EC009 | Duplicate cancel events (retry storm) | All churn=**100%** · nrr=0% | Subscription-level metrics are unaffected; an event-count-based definition would double-count the cancellation |
| EC010 | Reactivated: churned Jun 2023, rejoined Jul 2023 | All churn=**0%** · nrr=**100%** | No churn in Nov 2024 window; the prior churn (Jun 2023) is outside — definitions that use ever-churned status would disagree |
| EC011 | Free-tier ($0 MRR) churned Nov 5 | ccr=logo_cons=**100%** · rcr=nrr=di=**0%** | **Logo churn ≠ revenue churn** — a customer left (logo says 100%) but no revenue was lost (revenue says 0%) |
| EC012 | Started Oct 16, churned Nov 30 | All churn=**100%** · nrr=0% | All definitions agree; some BI tools would pro-rate the $249 MRR for the 15-day pre-window tenure |
| EC013 | Churned Oct 30 — 1 day before window | All churn=**0%** · nrr=**100%** | Confirms window boundary is exclusive on the far side; NRR shows full retention (starting MRR preserved) |
| EC014 | Paused account treated as churned Nov 25 | All churn=**100%** · nrr=0% | All definitions agree; a real system with a `paused` status would exclude this from churn |
| EC015 | Unknown plan, $0 MRR, churned Nov 18 | ccr=logo_cons=**100%** · rcr=nrr=di=**0%** | Same logo vs. revenue split as EC011; worst case for revenue definitions (no MRR basis at all) |
""")
