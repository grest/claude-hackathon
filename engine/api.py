import os
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from definitions.registry import get_definition, list_metrics
from engine.calculator import compute
from engine.loader import load_subscriptions, load_subscriptions_from_db

DATA_DIR = Path(__file__).parent.parent / "data"
DEFAULT_CSV = DATA_DIR / "sample_subscriptions.csv"

app = FastAPI(
    title="SaaS Churn Metric Engine",
    description="Versioned metric definitions + on-demand churn calculations.",
    version="1.0.0",
)


class MetricResult(BaseModel):
    metric: str
    version: str
    as_of: date
    value: float
    description: str
    source: Literal["db", "csv"]


class MetricSummary(BaseModel):
    name: str
    version: str
    description: str
    lookback_days: int


@app.get("/metrics", response_model=list[MetricSummary])
def list_available_metrics(version: str = Query(default="v1")):
    return [
        MetricSummary(
            name=m.name,
            version=m.version,
            description=m.description,
            lookback_days=m.lookback_days,
        )
        for m in list_metrics(version=version)
    ]


@app.get("/metrics/{metric_name}", response_model=MetricResult)
def calculate_metric(
    metric_name: str,
    as_of: date = Query(default_factory=date.today),
    version: str = Query(default="v1"),
    csv_path: str = Query(default=str(DEFAULT_CSV)),
):
    try:
        definition = get_definition(metric_name, version)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    database_url = os.environ.get("DATABASE_URL", "").strip()

    if database_url:
        try:
            df = load_subscriptions_from_db(database_url)
            source: Literal["db", "csv"] = "db"
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"DB load failed: {exc}") from exc
    else:
        try:
            df = load_subscriptions(csv_path)
            source = "csv"
        except FileNotFoundError as exc:
            raise HTTPException(status_code=422, detail=f"CSV not found: {csv_path}") from exc

    missing = [c for c in definition.required_columns if c not in df.columns]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Data source missing required columns: {missing}",
        )

    value = compute(definition, df, as_of)

    return MetricResult(
        metric=definition.name,
        version=definition.version,
        as_of=as_of,
        value=value,
        description=definition.description,
        source=source,
    )


@app.get("/health")
def health():
    return {"status": "ok"}
