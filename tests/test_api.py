from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engine.api import app

DATA_CSV = str(Path(__file__).parent.parent / "data" / "sample_subscriptions.csv")

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_database_url(monkeypatch):
    """Guarantee DATABASE_URL is absent so all tests use the CSV fallback."""
    monkeypatch.delenv("DATABASE_URL", raising=False)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_list_metrics():
    r = client.get("/metrics")
    assert r.status_code == 200
    names = {m["name"] for m in r.json()}
    assert "customer_churn_rate" in names


def test_calculate_customer_churn_rate():
    r = client.get(
        "/metrics/customer_churn_rate",
        params={"as_of": "2024-05-01", "csv_path": DATA_CSV},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["metric"] == "customer_churn_rate"
    assert 0.0 <= body["value"] <= 1.0


def test_unknown_metric_returns_404():
    r = client.get("/metrics/totally_fake_metric")
    assert r.status_code == 404


def test_missing_csv_returns_422():
    r = client.get(
        "/metrics/customer_churn_rate",
        params={"csv_path": "/nonexistent/path.csv"},
    )
    assert r.status_code == 422
