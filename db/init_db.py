"""
Generate a synthetic SaaS subscription dataset and populate data/churn_engine.db.

Usage:
    python db/init_db.py
    python db/init_db.py --output data/churn_engine.db --seed 42
"""
import argparse
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "data" / "churn_engine.db"

PLANS = [
    ("starter",     29.00),
    ("pro",         99.00),
    ("business",   249.00),
    ("enterprise", 499.00),
]

CHURN_REASONS = ["price", "competitor", "unused", "too_complex", "budget_cut", "switching_tools"]
UPGRADE_PATHS = [
    ("starter", "pro"),
    ("pro", "business"),
    ("business", "enterprise"),
    ("starter", "business"),
]
DOWNGRADE_PATHS = [
    ("enterprise", "business"),
    ("business", "pro"),
    ("pro", "starter"),
]

DATASET_START = date(2022, 1, 1)
DATASET_END   = date(2024, 12, 31)
NUM_CUSTOMERS = 1000


def _random_date(start: date, end: date, rng: random.Random) -> date:
    delta = (end - start).days
    return start + timedelta(days=rng.randint(0, delta))


def generate(seed: int = 42) -> tuple[list[dict], list[dict]]:
    rng = random.Random(seed)
    subscriptions: list[dict] = []
    events: list[dict] = []
    event_counter = 1

    for i in range(1, NUM_CUSTOMERS + 1):
        customer_id = f"C{i:04d}"
        plan_name, mrr = rng.choice(PLANS)
        start_date = _random_date(DATASET_START, date(2024, 6, 30), rng)

        if rng.random() < 0.30:  # ~30% churn rate
            max_end = min(start_date + timedelta(days=730), DATASET_END)
            earliest_end = start_date + timedelta(days=30)
            end_date = _random_date(
                earliest_end if earliest_end < max_end else max_end,
                max_end,
                rng,
            )
            status = "churned"

            # cancel_requested event a few days before end_date
            days_before = rng.randint(5, 20)
            event_date = end_date - timedelta(days=days_before)
            if event_date >= start_date:
                events.append({
                    "event_id":    f"E{event_counter:05d}",
                    "customer_id": customer_id,
                    "event_type":  "cancel_requested",
                    "event_date":  event_date.isoformat(),
                    "metadata":    f"reason={rng.choice(CHURN_REASONS)}",
                })
                event_counter += 1
        else:
            end_date = None
            status = "active"

            # ~15% of active customers have a plan change event
            if rng.random() < 0.15:
                paths = list(UPGRADE_PATHS + DOWNGRADE_PATHS)
                rng.shuffle(paths)
                for from_plan, to_plan in paths:
                    if from_plan == plan_name:
                        earliest_event = start_date + timedelta(days=30)
                        if earliest_event < DATASET_END:
                            event_date = _random_date(earliest_event, DATASET_END, rng)
                            is_upgrade = (from_plan, to_plan) in UPGRADE_PATHS
                            events.append({
                                "event_id":    f"E{event_counter:05d}",
                                "customer_id": customer_id,
                                "event_type":  "plan_upgrade" if is_upgrade else "plan_downgrade",
                                "event_date":  event_date.isoformat(),
                                "metadata":    f"from={from_plan}&to={to_plan}",
                            })
                            event_counter += 1
                        break

            # ~5% of active customers have a payment failure
            if rng.random() < 0.05:
                earliest_event = start_date + timedelta(days=14)
                if earliest_event < DATASET_END:
                    event_date = _random_date(earliest_event, DATASET_END, rng)
                    events.append({
                        "event_id":    f"E{event_counter:05d}",
                        "customer_id": customer_id,
                        "event_type":  "payment_failed",
                        "event_date":  event_date.isoformat(),
                        "metadata":    "attempt=1",
                    })
                    event_counter += 1

        subscriptions.append({
            "customer_id": customer_id,
            "plan":        plan_name,
            "mrr":         mrr,
            "start_date":  start_date.isoformat(),
            "end_date":    end_date.isoformat() if end_date else None,
            "status":      status,
        })

    return subscriptions, events


_DDL = """
CREATE TABLE subscriptions (
    id          INTEGER  PRIMARY KEY AUTOINCREMENT,
    customer_id TEXT     NOT NULL,
    plan        TEXT     NOT NULL,
    mrr         REAL     NOT NULL,
    start_date  TEXT     NOT NULL,
    end_date    TEXT     NULL,
    status      TEXT     NOT NULL CHECK(status IN ('active', 'churned')),
    created_at  TEXT     NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT     NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_sub_customer_id     ON subscriptions (customer_id);
CREATE INDEX idx_sub_status_end_date ON subscriptions (status, end_date);

CREATE TABLE events (
    id          INTEGER  PRIMARY KEY AUTOINCREMENT,
    event_id    TEXT     NOT NULL UNIQUE,
    customer_id TEXT     NOT NULL,
    event_type  TEXT     NOT NULL,
    event_date  TEXT     NOT NULL,
    metadata    TEXT     NULL,
    created_at  TEXT     NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_events_customer_id ON events (customer_id);
CREATE INDEX idx_events_event_date  ON events (event_date);
"""


def build_db(output: Path, seed: int = 42) -> None:
    print(f"Output DB  : {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    subscriptions, events = generate(seed)

    conn = sqlite3.connect(output)
    try:
        conn.executescript(_DDL)
        conn.executemany(
            "INSERT INTO subscriptions (customer_id, plan, mrr, start_date, end_date, status) "
            "VALUES (:customer_id, :plan, :mrr, :start_date, :end_date, :status)",
            subscriptions,
        )
        conn.executemany(
            "INSERT INTO events (event_id, customer_id, event_type, event_date, metadata) "
            "VALUES (:event_id, :customer_id, :event_type, :event_date, :metadata)",
            events,
        )
        conn.commit()
    finally:
        conn.close()

    print(f"Inserted {len(subscriptions)} subscriptions, {len(events)} events.")
    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--seed",   type=int, default=42)
    args = parser.parse_args()
    build_db(Path(args.output), args.seed)
