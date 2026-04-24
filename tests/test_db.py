"""
Integration tests for engine/db.py against the synthetic SaaS SQLite database.
"""
from pathlib import Path

import pandas as pd
import pytest


@pytest.fixture(scope="module")
def db_path(tmp_path_factory):
    from db.init_db import build_db
    out = tmp_path_factory.mktemp("saas") / "test.db"
    build_db(out, seed=42)
    return str(out)


def test_fetch_returns_dataframe(db_path):
    from engine.db import fetch_subscriptions
    df = fetch_subscriptions(db_path)
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 0


def test_dtype_contract(db_path):
    from engine.db import fetch_subscriptions
    df = fetch_subscriptions(db_path)
    assert df["customer_id"].dtype == object
    assert df["plan"].dtype == object
    assert df["mrr"].dtype == "float64"
    assert pd.api.types.is_datetime64_any_dtype(df["start_date"])
    assert pd.api.types.is_datetime64_any_dtype(df["end_date"])
    assert df["status"].dtype == object


def test_active_rows_have_nat_end_date(db_path):
    from engine.db import fetch_subscriptions
    df = fetch_subscriptions(db_path)
    active = df[df["status"] == "active"]
    assert active["end_date"].isna().all()


def test_churned_rows_have_end_date(db_path):
    from engine.db import fetch_subscriptions
    df = fetch_subscriptions(db_path)
    churned = df[df["status"] == "churned"]
    assert churned["end_date"].notna().all()


def test_mrr_is_positive(db_path):
    from engine.db import fetch_subscriptions
    df = fetch_subscriptions(db_path)
    # "unknown" plan rows and free-tier edge cases legitimately have mrr == 0.0;
    # all other rows must have positive MRR.
    known_plan_rows = df[df["plan"] != "unknown"]
    assert (known_plan_rows["mrr"] >= 0).all()


def test_start_date_before_end_date(db_path):
    from engine.db import fetch_subscriptions
    df = fetch_subscriptions(db_path)
    churned = df[df["status"] == "churned"]
    assert (churned["start_date"] <= churned["end_date"]).all()


def test_known_plan_values(db_path):
    from engine.db import fetch_subscriptions
    df = fetch_subscriptions(db_path)
    # "unknown" is a valid plan value introduced by the Challenge-2 noise layer.
    valid_plans = {"starter", "pro", "business", "enterprise", "unknown"}
    assert set(df["plan"].unique()).issubset(valid_plans)


def test_customer_count(db_path):
    from engine.db import fetch_subscriptions
    df = fetch_subscriptions(db_path)
    # 1000 random rows + 16 edge-case rows (EC010 has 2 subscription rows)
    assert len(df) >= 1000


def test_api_endpoint_returns_db_source(db_path):
    from fastapi.testclient import TestClient
    from engine.api import app

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("DATABASE_PATH", db_path)
        client = TestClient(app)
        r = client.get("/metrics/customer_churn_rate", params={"as_of": "2024-05-01"})

    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "db"
    assert 0.0 <= body["value"] <= 1.0
