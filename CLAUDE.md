# SaaS Churn Metric Engine

A versioned metric calculation engine for SaaS churn analytics, exposed via FastAPI.

## Project layout

```
.
├── data/               # Raw CSV inputs (subscriptions, events)
├── definitions/        # Versioned metric definitions (immutable once published)
│   ├── metrics_v1.py   # All v1 metric definitions as frozen dataclasses
│   └── registry.py     # Central (name, version) → definition lookup
├── engine/             # Calculation logic + HTTP API
│   ├── loader.py       # CSV → DataFrame helpers
│   ├── calculator.py   # Pure functions: one function per metric
│   └── api.py          # FastAPI app (GET /metrics, GET /metrics/{name})
├── tests/              # pytest suite
│   ├── test_calculator.py
│   ├── test_registry.py
│   └── test_api.py
├── requirements.txt
└── CLAUDE.md
```

## Running the API

```bash
pip install -r requirements.txt
uvicorn engine.api:app --reload
```

Interactive docs at http://127.0.0.1:8000/docs

## Running tests

```bash
pytest tests/ -v
```

## Key design decisions

**Metric versioning** — each version lives in its own module (`definitions/metrics_v1.py`).
Never edit a published version; add a `metrics_v2.py` and register it in `registry.py`.
The API exposes a `?version=` query param so callers can pin to a specific definition.

**Pure calculator functions** — `engine/calculator.py` contains one plain Python function
per metric. They take a DataFrame and a date, return a float. No side effects, easy to test.

**CSV as the data boundary** — `engine/loader.py` converts CSVs to typed DataFrames.
Swap this for a DB query or parquet read without touching anything else.

## Adding a new metric

1. Add a `ChurnMetricDefinition` constant in `definitions/metrics_v1.py` (or a new version file).
2. Register it in `ALL_METRICS` at the bottom of that file.
3. Add the calculator function in `engine/calculator.py` and register it in `_CALCULATORS`.
4. Add tests in `tests/test_calculator.py`.

## Metric definitions

| Metric | Description |
|---|---|
| `customer_churn_rate` | Churned customers ÷ customers active at period start |
| `revenue_churn_rate` | Lost MRR ÷ MRR at period start |
| `net_revenue_retention` | (Starting MRR − churned MRR) ÷ Starting MRR |

All metrics default to a 30-day lookback window and accept `?as_of=YYYY-MM-DD`.
