# SaaS Churn Metric Engine

A versioned metric calculation engine for SaaS churn analytics, exposed via FastAPI with a Streamlit dashboard.

## Project layout

```
.
├── data/                        # SQLite DB + CSV fallback files
│   ├── churn_engine.db          # Generated SQLite DB (auto-created on first run)
│   ├── sample_subscriptions.csv # 50-row CSV fallback (starter/pro/business/enterprise)
│   └── sample_events.csv        # 45-row events fallback
├── db/
│   └── init_db.py               # Synthetic data generator → builds churn_engine.db
├── definitions/                 # Versioned metric definitions (immutable once published)
│   ├── metrics_v1.py            # All v1 metric definitions as frozen dataclasses
│   └── registry.py              # Central (name, version) → definition lookup
├── engine/                      # Calculation logic + HTTP API
│   ├── db.py                    # fetch_subscriptions() — SQLite query
│   ├── loader.py                # load_subscriptions() (CSV) + load_subscriptions_from_db() (SQLite)
│   ├── calculator.py            # Pure functions: one function per metric
│   └── api.py                   # FastAPI app
├── dashboard.py                 # Streamlit dashboard
├── tests/
│   ├── test_calculator.py       # Unit tests — in-memory DataFrames, no I/O
│   ├── test_registry.py         # Unit tests — metric definition lookup
│   ├── test_api.py              # API tests — CSV fallback (DATABASE_PATH cleared per test)
│   └── test_db.py               # Integration tests — builds a fresh synthetic DB in tmp dir
├── requirements.txt
└── CLAUDE.md
```

## Data source: SQLite vs CSV fallback

The API checks the `DATABASE_PATH` environment variable at request time:
- **Set** → queries SQLite via `engine/db.py`; response includes `"source": "db"`
- **Unset** → reads the CSV at `csv_path` query param (defaults to `data/sample_subscriptions.csv`); response includes `"source": "csv"`

On first startup the API auto-generates `data/churn_engine.db` if it does not exist.

## Quickstart

```bash
pip install -r requirements.txt

# API (auto-generates the SQLite DB on first request)
uvicorn engine.api:app --reload
# Interactive docs → http://127.0.0.1:8000/docs

# Dashboard
streamlit run dashboard.py
```

## Running without the auto-generated DB (CSV fallback)

```bash
uvicorn engine.api:app --reload
# DATABASE_PATH unset → uses data/sample_subscriptions.csv
```

## Generating / regenerating the database

```bash
python db/init_db.py
# Optional flags:
#   --output data/churn_engine.db   (default)
#   --seed 42                        (default; change for different data)
```

Generates **1 000 synthetic customers** spanning **2022-01-01 – 2024-12-31**:
- Plans: `starter` ($29), `pro` ($99), `business` ($249), `enterprise` ($499)
- ~30 % churn rate with realistic `cancel_requested` events
- ~15 % of active customers have a `plan_upgrade` or `plan_downgrade` event
- ~5 % of active customers have a `payment_failed` event

## Running tests

```bash
# All tests — no external services required
pytest tests/ -v
```

`tests/test_db.py` builds a fresh synthetic DB in a temp directory via the `db_path` fixture — no real DB needed.

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness check |
| GET | `/metrics` | List all metric definitions (`?version=v1`) |
| GET | `/metrics/summary` | All v1 metrics in one call (`?as_of=YYYY-MM-DD`) |
| GET | `/metrics/{name}` | Single metric (`?as_of=YYYY-MM-DD&version=v1`) |

Response shape for metric results:
```json
{"metric": "customer_churn_rate", "version": "v1", "as_of": "2024-12-31",
 "value": 0.0312, "description": "...", "source": "db"}
```

## Streamlit dashboard

```bash
streamlit run dashboard.py
```

Sidebar controls:
- **SQLite DB path** — path to `churn_engine.db`
- **Lookback** — `7 days` / `30 days` / `90 days` / `Custom` (date range picker)
- **End date** — defaults to the latest date in the dataset

Dashboard sections:
1. KPI row — Active Customers, Churned (in window), MRR at Period Start, Customer Churn Rate %
2. Metric Values — Customer Churn Rate, Revenue Churn Rate, Net Revenue Retention
3. Plan Breakdown — Active customers and MRR by plan (bar charts)
4. Monthly Churn Rate — line chart over the 12 months ending at the selected end date
5. Recent Events — last 20 rows from the `events` table

If `churn_engine.db` is missing, the dashboard shows a **Generate DB** button that calls `db/init_db.py` directly.

## Key design decisions

**Metric versioning** — each version lives in its own module (`definitions/metrics_v1.py`).
Never edit a published version; add a `metrics_v2.py` and register it in `registry.py`.
The API exposes a `?version=` query param so callers can pin to a specific definition.

**Pure calculator functions** — `engine/calculator.py` contains one plain Python function
per metric. Signature: `fn(df, as_of, lookback_days) -> float`. No side effects, easy to test.
All three functions accept a `lookback_days` override so the dashboard can apply any window.

**DataFrame contract** — both data paths produce the same schema:
`customer_id` (object), `plan` (object), `mrr` (float64), `start_date` (datetime64[ns]),
`end_date` (datetime64[ns], NaT for active customers), `status` (object).
`NULL` in SQLite maps to `NaT` via `pd.to_datetime(..., errors="coerce")`.

**No DB filter on `as_of`** — all rows are fetched; date-window filtering happens inside
the calculator functions, exactly as with the CSV path.

## Adding a new metric

1. Add a `ChurnMetricDefinition` constant in `definitions/metrics_v1.py` (or a new version file).
2. Register it in `ALL_METRICS` at the bottom of that file.
3. Add the calculator function in `engine/calculator.py` and register it in `_CALCULATORS`.
4. Add tests in `tests/test_calculator.py`.

## Metric definitions

| Metric | Description |
|--------|-------------|
| `customer_churn_rate` | Churned customers ÷ customers active at period start |
| `revenue_churn_rate` | Lost MRR ÷ MRR at period start |
| `net_revenue_retention` | (Starting MRR − churned MRR) ÷ Starting MRR |

All metrics default to a 30-day lookback window. Pass `?as_of=YYYY-MM-DD` to anchor the window end date. The synthetic dataset ends 2024-12-31 — use that date (or earlier) to see non-zero churn values.
