import logging
import os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from definitions.registry import get_definition, list_metrics
from engine.calculator import compute
from engine.loader import load_subscriptions, load_subscriptions_from_db

log = logging.getLogger(__name__)

REPO_ROOT   = Path(__file__).parent.parent
DATA_DIR    = REPO_ROOT / "data"
DEFAULT_CSV = DATA_DIR / "sample_subscriptions.csv"
DEFAULT_DB  = DATA_DIR / "churn_engine.db"


def _ensure_db() -> None:
    """Build churn_engine.db from synthetic data if it doesn't exist yet."""
    db_path = Path(os.environ.get("DATABASE_PATH", "").strip() or DEFAULT_DB)

    if not db_path.exists():
        log.info("Generating synthetic SaaS dataset at %s …", db_path)
        from db.init_db import build_db
        build_db(db_path)
        log.info("Database ready at %s", db_path)
    else:
        log.info("Database already exists at %s — skipping init.", db_path)

    os.environ["DATABASE_PATH"] = str(db_path)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
    _ensure_db()
    yield


app = FastAPI(
    title="SaaS Churn Metric Engine",
    description="Versioned metric definitions + on-demand churn calculations.",
    version="1.0.0",
    lifespan=lifespan,
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


@app.get("/metrics/summary", response_model=list[MetricResult])
def metrics_summary(
    as_of: date = Query(default_factory=date.today),
    version: str = Query(default="v1"),
    csv_path: str = Query(default=str(DEFAULT_CSV)),
):
    """Return all v1 metrics in a single call."""
    from definitions.registry import list_metrics as _list_metrics

    definitions = _list_metrics(version=version)

    database_path = os.environ.get("DATABASE_PATH", "").strip()

    if database_path:
        try:
            df = load_subscriptions_from_db(database_path)
            source: Literal["db", "csv"] = "db"
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"DB load failed: {exc}") from exc
    else:
        try:
            df = load_subscriptions(csv_path)
            source = "csv"
        except FileNotFoundError as exc:
            raise HTTPException(status_code=422, detail=f"CSV not found: {csv_path}") from exc

    results = []
    for definition in definitions:
        missing = [c for c in definition.required_columns if c not in df.columns]
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"Data source missing required columns for {definition.name}: {missing}",
            )
        value = compute(definition, df, as_of)
        results.append(
            MetricResult(
                metric=definition.name,
                version=definition.version,
                as_of=as_of,
                value=value,
                description=definition.description,
                source=source,
            )
        )

    return results


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

    database_path = os.environ.get("DATABASE_PATH", "").strip()

    if database_path:
        try:
            df = load_subscriptions_from_db(database_path)
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
