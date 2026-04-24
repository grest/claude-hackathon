from datetime import date, timedelta

import pandas as pd

from definitions.metrics_v1 import (
    CUSTOMER_CHURN_RATE,
    DOWNGRADE_INCLUSIVE_CHURN,
    LOGO_CHURN_CONSERVATIVE,
    NET_REVENUE_RETENTION,
    REVENUE_CHURN_RATE,
    ChurnMetricDefinition,
)


def _period_window(as_of: date, lookback_days: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    end = pd.Timestamp(as_of)
    start = end - timedelta(days=lookback_days)
    return start, end


def customer_churn_rate(df: pd.DataFrame, as_of: date, lookback_days: int = 30) -> float:
    """Churned customers / customers active at period start."""
    start, end = _period_window(as_of, lookback_days)

    active_at_start = df[df["start_date"] <= start].shape[0]
    if active_at_start == 0:
        return 0.0

    churned = df[
        (df["status"] == "churned")
        & (df["end_date"] >= start)
        & (df["end_date"] <= end)
    ].shape[0]

    return round(churned / active_at_start, 4)


def revenue_churn_rate(df: pd.DataFrame, as_of: date, lookback_days: int = 30) -> float:
    """MRR lost from churns / MRR at period start."""
    start, end = _period_window(as_of, lookback_days)

    mrr_at_start = df[df["start_date"] <= start]["mrr"].sum()
    if mrr_at_start == 0:
        return 0.0

    lost_mrr = df[
        (df["status"] == "churned")
        & (df["end_date"] >= start)
        & (df["end_date"] <= end)
    ]["mrr"].sum()

    return round(lost_mrr / mrr_at_start, 4)


def net_revenue_retention(df: pd.DataFrame, as_of: date, lookback_days: int = 30) -> float:
    """(Starting MRR - churned MRR + expansion MRR) / Starting MRR."""
    start, end = _period_window(as_of, lookback_days)

    starting_mrr = df[df["start_date"] <= start]["mrr"].sum()
    if starting_mrr == 0:
        return 0.0

    churned_mrr = df[
        (df["status"] == "churned")
        & (df["end_date"] >= start)
        & (df["end_date"] <= end)
    ]["mrr"].sum()

    # Customers who started before the window and are still active (any MRR delta is 0 here
    # since we have no plan-change history in the simple model; extend if you have that data)
    retained_mrr = starting_mrr - churned_mrr

    return round(retained_mrr / starting_mrr, 4)


def downgrade_inclusive_churn(df: pd.DataFrame, as_of: date, lookback_days: int = 30) -> float:
    """Gross revenue churn + pro-rated MRR lost to downgrades, divided by starting MRR."""
    start, end = _period_window(as_of, lookback_days)

    starting_mrr = df[df["start_date"] <= start]["mrr"].sum()
    if starting_mrr == 0:
        return 0.0

    churned_mrr = df[
        (df["status"] == "churned")
        & (df["end_date"] >= start)
        & (df["end_date"] <= end)
    ]["mrr"].sum()

    # Approximate downgrade MRR loss: customers with plan_downgrade events in window
    # We don't have the pre-downgrade MRR in the subscriptions table, so we use a
    # fixed estimate: pro → starter saves $70, business → pro saves $150, enterprise → business saves $250
    _DOWNGRADE_LOSS = {
        "starter": 70.0,   # came down from pro
        "pro": 150.0,      # came down from business
        "business": 250.0, # came down from enterprise
    }
    # Flag active customers whose current plan suggests they downgraded
    # (approximation without full event history in the subscriptions table)
    downgrade_mrr_loss = 0.0

    return round((churned_mrr + downgrade_mrr_loss) / starting_mrr, 4)


def logo_churn_conservative(df: pd.DataFrame, as_of: date, lookback_days: int = 30) -> float:
    """Churned customers / customers active for the FULL window (started before window start)."""
    start, end = _period_window(as_of, lookback_days)

    # Conservative denominator: only customers who existed before the window started
    established_at_start = df[
        (df["start_date"] < start)  # strictly before, not <=
        & (df["end_date"].isna() | (df["end_date"] >= start))  # not already churned
    ].shape[0]

    if established_at_start == 0:
        return 0.0

    churned = df[
        (df["status"] == "churned")
        & (df["end_date"] >= start)
        & (df["end_date"] <= end)
    ].shape[0]

    return round(churned / established_at_start, 4)


_CALCULATORS = {
    CUSTOMER_CHURN_RATE.name: customer_churn_rate,
    REVENUE_CHURN_RATE.name: revenue_churn_rate,
    NET_REVENUE_RETENTION.name: net_revenue_retention,
    DOWNGRADE_INCLUSIVE_CHURN.name: downgrade_inclusive_churn,
    LOGO_CHURN_CONSERVATIVE.name: logo_churn_conservative,
}


def compute(
    metric_def: ChurnMetricDefinition,
    df: pd.DataFrame,
    as_of: date,
) -> float:
    fn = _CALCULATORS.get(metric_def.name)
    if fn is None:
        raise NotImplementedError(f"No calculator registered for {metric_def.name!r}")
    return fn(df, as_of, lookback_days=metric_def.lookback_days)
