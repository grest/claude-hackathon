from datetime import date

import pandas as pd
import pytest

from engine.calculator import customer_churn_rate, net_revenue_retention, revenue_churn_rate


def _make_df(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["start_date"] = pd.to_datetime(df["start_date"])
    df["end_date"] = pd.to_datetime(df["end_date"])
    return df


@pytest.fixture()
def simple_df():
    return _make_df([
        {"customer_id": "A", "mrr": 100, "status": "active",  "start_date": "2024-01-01", "end_date": pd.NaT},
        {"customer_id": "B", "mrr": 200, "status": "churned", "start_date": "2024-01-01", "end_date": "2024-01-20"},
        {"customer_id": "C", "mrr": 300, "status": "active",  "start_date": "2024-01-01", "end_date": pd.NaT},
    ])


def test_customer_churn_rate_basic(simple_df):
    # as_of=2024-02-01, lookback=30 → window 2024-01-02 to 2024-02-01
    # Active at start (start_date <= 2024-01-02): A, B, C → 3
    # Churned in window: B (end_date 2024-01-20) → 1
    rate = customer_churn_rate(simple_df, date(2024, 2, 1), lookback_days=30)
    assert rate == round(1 / 3, 4)


def test_customer_churn_rate_no_churn(simple_df):
    rate = customer_churn_rate(simple_df, date(2024, 1, 5), lookback_days=3)
    assert rate == 0.0


def test_revenue_churn_rate_basic(simple_df):
    rate = revenue_churn_rate(simple_df, date(2024, 2, 1), lookback_days=30)
    total_mrr = 100 + 200 + 300  # 600
    lost_mrr = 200
    assert rate == round(lost_mrr / total_mrr, 4)


def test_net_revenue_retention_basic(simple_df):
    nrr = net_revenue_retention(simple_df, date(2024, 2, 1), lookback_days=30)
    starting = 600
    churned = 200
    assert nrr == round((starting - churned) / starting, 4)


def test_no_active_customers_at_start():
    df = _make_df([
        {"customer_id": "X", "mrr": 50, "status": "active", "start_date": "2024-06-01", "end_date": pd.NaT},
    ])
    rate = customer_churn_rate(df, date(2024, 1, 1), lookback_days=30)
    assert rate == 0.0
