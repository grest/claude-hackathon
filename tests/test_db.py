"""
Integration tests for engine/db.py.
Requires a live Postgres connection. The entire module is skipped automatically
when DATABASE_URL is not set — run `docker compose up -d` then set the env var.
"""
import os
from datetime import date

import pandas as pd
import pytest

DATABASE_URL = os.environ.get("DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping DB integration tests",
)


@pytest.fixture(scope="module")
def conn_str():
    return DATABASE_URL


def test_fetch_returns_dataframe(conn_str):
    from engine.db import fetch_subscriptions
    df = fetch_subscriptions(conn_str)
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 0


def test_dtype_contract(conn_str):
    from engine.db import fetch_subscriptions
    df = fetch_subscriptions(conn_str)
    assert df["customer_id"].dtype == object
    assert df["plan"].dtype == object
    assert df["mrr"].dtype == "float64"
    assert pd.api.types.is_datetime64_any_dtype(df["start_date"])
    assert pd.api.types.is_datetime64_any_dtype(df["end_date"])
    assert df["status"].dtype == object


def test_active_rows_have_nat_end_date(conn_str):
    from engine.db import fetch_subscriptions
    df = fetch_subscriptions(conn_str)
    active = df[df["status"] == "active"]
    assert active["end_date"].isna().all()


def test_churned_rows_have_end_date(conn_str):
    from engine.db import fetch_subscriptions
    df = fetch_subscriptions(conn_str)
    churned = df[df["status"] == "churned"]
    assert churned["end_date"].notna().all()


def test_seed_row_count(conn_str):
    from engine.db import fetch_subscriptions
    df = fetch_subscriptions(conn_str)
    assert len(df) == 8


def test_api_endpoint_returns_db_source(conn_str):
    import pytest
    from fastapi.testclient import TestClient
    from engine.api import app

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("DATABASE_URL", conn_str)
        client = TestClient(app)
        r = client.get("/metrics/customer_churn_rate", params={"as_of": "2024-05-01"})

    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "db"
    assert 0.0 <= body["value"] <= 1.0
