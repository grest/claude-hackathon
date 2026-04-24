import pytest

from definitions.registry import get_definition, list_metrics


def test_get_known_metric():
    defn = get_definition("customer_churn_rate", "v1")
    assert defn.name == "customer_churn_rate"
    assert defn.version == "v1"


def test_get_unknown_metric_raises():
    with pytest.raises(KeyError):
        get_definition("nonexistent_metric", "v1")


def test_list_metrics_v1():
    metrics = list_metrics(version="v1")
    names = {m.name for m in metrics}
    assert {
        "customer_churn_rate",
        "revenue_churn_rate",
        "net_revenue_retention",
        "downgrade_inclusive_churn",
        "logo_churn_conservative",
    } == names


def test_list_all_metrics():
    assert len(list_metrics()) >= 3
