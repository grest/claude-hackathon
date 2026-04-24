from dataclasses import dataclass, field
from typing import Literal

MetricVersion = Literal["v1"]

CURRENT_VERSION: MetricVersion = "v1"


@dataclass(frozen=True)
class ChurnMetricDefinition:
    name: str
    version: MetricVersion
    description: str
    lookback_days: int
    # Fields required in the input DataFrame
    required_columns: list[str] = field(default_factory=list)


CUSTOMER_CHURN_RATE = ChurnMetricDefinition(
    name="customer_churn_rate",
    version="v1",
    description=(
        "Percentage of customers who cancelled during the period "
        "relative to customers active at period start."
    ),
    lookback_days=30,
    required_columns=["customer_id", "status", "start_date", "end_date"],
)

REVENUE_CHURN_RATE = ChurnMetricDefinition(
    name="revenue_churn_rate",
    version="v1",
    description=(
        "Percentage of MRR lost from cancellations during the period "
        "relative to MRR at period start."
    ),
    lookback_days=30,
    required_columns=["customer_id", "mrr", "status", "start_date", "end_date"],
)

NET_REVENUE_RETENTION = ChurnMetricDefinition(
    name="net_revenue_retention",
    version="v1",
    description=(
        "MRR retained plus expansion revenue, divided by starting MRR. "
        "Values above 100% indicate net growth."
    ),
    lookback_days=30,
    required_columns=["customer_id", "mrr", "status", "start_date", "end_date"],
)

ALL_METRICS: dict[str, ChurnMetricDefinition] = {
    m.name: m
    for m in [CUSTOMER_CHURN_RATE, REVENUE_CHURN_RATE, NET_REVENUE_RETENTION]
}
