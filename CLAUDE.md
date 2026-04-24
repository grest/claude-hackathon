# SaaS Churn Metric Engine

A versioned metric calculation engine for SaaS churn analytics, exposed via FastAPI.

## Project layout

```
.
├── data/                   # Raw CSV inputs (subscriptions, events) — also used as fallback
├── db/                     # PostgreSQL schema, seed data, and Alembic migrations
│   ├── schema.sql          # DDL for subscriptions + events tables
│   ├── seed.sql            # 8 subscription rows + 6 event rows (mirrors data/ CSVs)
│   └── migrations/         # Alembic migration history
│       ├── alembic.ini
│       ├── env.py
│       └── versions/001_initial_schema.py
├── definitions/            # Versioned metric definitions (immutable once published)
│   ├── metrics_v1.py       # All v1 metric definitions as frozen dataclasses
│   └── registry.py         # Central (name, version) → definition lookup
├── engine/                 # Calculation logic + HTTP API
│   ├── db.py               # fetch_subscriptions() — SQLAlchemy 2.0 Core query
│   ├── loader.py           # load_subscriptions() (CSV) + load_subscriptions_from_db() (PG)
│   ├── calculator.py       # Pure functions: one function per metric
│   └── api.py              # FastAPI app (GET /metrics, GET /metrics/{name})
├── tests/
│   ├── test_calculator.py  # Unit tests — in-memory DataFrames, no I/O
│   ├── test_registry.py    # Unit tests — metric definition lookup
│   ├── test_api.py         # API tests — CSV fallback (DATABASE_URL cleared per test)
│   └── test_db.py          # Integration tests — skipped unless DATABASE_URL is set
├── docker-compose.yml      # Postgres 16-alpine with auto schema+seed
├── requirements.txt
└── CLAUDE.md
```

## Data source: Postgres vs CSV fallback

The API checks the `DATABASE_URL` environment variable at request time:
- **Set** → queries Postgres via `engine/db.py`; response includes `"source": "db"`
- **Unset** → reads the CSV at `csv_path` query param (defaults to `data/sample_subscriptions.csv`); response includes `"source": "csv"`

This means unit tests and local dev without Docker work out of the box.

## Running with Postgres (recommended)

```bash
# Start Postgres (schema + seed applied automatically on first run)
docker compose up -d

# Install dependencies
pip install -r requirements.txt

# Start the API
export DATABASE_URL=postgresql+psycopg2://churn:churn_secret@localhost:5432/churn_engine
uvicorn engine.api:app --reload
```

Interactive docs at http://127.0.0.1:8000/docs

## Running without Postgres (CSV fallback)

```bash
pip install -r requirements.txt
uvicorn engine.api:app --reload
# No DATABASE_URL → uses data/sample_subscriptions.csv
```

## Running tests

```bash
# Fast path — no DB required
pytest tests/test_calculator.py tests/test_registry.py tests/test_api.py -v

# Full suite including DB integration tests
docker compose up -d
export DATABASE_URL=postgresql+psycopg2://churn:churn_secret@localhost:5432/churn_engine
pytest tests/ -v
```

`tests/test_db.py` is skipped automatically when `DATABASE_URL` is absent.

## Alembic migrations

```bash
# Apply all migrations to a fresh DB
export DATABASE_URL=postgresql+psycopg2://churn:churn_secret@localhost:5432/churn_engine
alembic -c db/migrations/alembic.ini upgrade head
```

## Key design decisions

**Metric versioning** — each version lives in its own module (`definitions/metrics_v1.py`).
Never edit a published version; add a `metrics_v2.py` and register it in `registry.py`.
The API exposes a `?version=` query param so callers can pin to a specific definition.

**Pure calculator functions** — `engine/calculator.py` contains one plain Python function
per metric. They take a DataFrame and a date, return a float. No side effects, easy to test.

**DataFrame contract** — both data paths produce the same DataFrame schema:
`customer_id` (object), `plan` (object), `mrr` (float64), `start_date` (datetime64[ns]),
`end_date` (datetime64[ns], NaT for active customers), `status` (object).
`NULL` in Postgres maps to `NaT` via `pd.to_datetime(..., errors="coerce")`.

**No DB filter on `as_of`** — all rows are fetched; date-window filtering happens inside
the calculator functions, exactly as with the CSV path.

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
