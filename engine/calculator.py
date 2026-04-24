from datetime import date, timedelta

import pandas as pd

from definitions.metrics_v1 import (
    CUSTOMER_CHURN_RATE,
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


_CALCULATORS = {
    CUSTOMER_CHURN_RATE.name: customer_churn_rate,
    REVENUE_CHURN_RATE.name: revenue_churn_rate,
    NET_REVENUE_RETENTION.name: net_revenue_retention,
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
