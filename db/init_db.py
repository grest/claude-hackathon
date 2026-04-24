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

        # ~4% unknown plan tiers: unlabeled/migrated accounts that break revenue-churn
        # calculations differently depending on the definition used.
        if rng.random() < 0.04:
            plan_name = "unknown"
            mrr = 0.0
        else:
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

            # EU timezone-shifted customers (i=1..80): if they churn on Jan 1 of any
            # year, shift end_date back by 1 day (to Dec 31) to simulate UTC vs.
            # local-time boundary disagreements.
            if i <= 80 and end_date.month == 1 and end_date.day == 1:
                end_date = end_date - timedelta(days=1)

            # cancel_requested event a few days before end_date
            days_before = rng.randint(5, 20)
            event_date = end_date - timedelta(days=days_before)
            if event_date >= start_date:
                reason = rng.choice(CHURN_REASONS)
                # EU timezone note for first 80 customers
                metadata = f"reason={reason}"
                if i <= 80 and end_date.month == 12 and end_date.day == 31:
                    metadata += "&tz=Europe/Berlin"
                events.append({
                    "event_id":    f"E{event_counter:05d}",
                    "customer_id": customer_id,
                    "event_type":  "cancel_requested",
                    "event_date":  event_date.isoformat(),
                    "metadata":    metadata,
                })
                event_counter += 1

                # Retry-storm: ~5% of cancel_requested events get a duplicate row
                # with event_id suffixed _r1, same date, simulating billing-system
                # retries that cause naive event-count definitions to double-count.
                if rng.random() < 0.05:
                    events.append({
                        "event_id":    f"E{event_counter - 1:05d}_r1",
                        "customer_id": customer_id,
                        "event_type":  "cancel_requested",
                        "event_date":  event_date.isoformat(),
                        "metadata":    metadata + "&retry=1",
                    })
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

    # --- Fifteen hard-coded edge-case rows ---
    # These are referenced by the dashboard reconciliation table by customer_id.
    EDGE_CASES = [
        # EC001: started AND churned within the same 30-day window → denominator disagreement
        {"customer_id": "EC001", "plan": "pro",        "mrr": 99.00,  "start_date": "2024-11-05", "end_date": "2024-11-28", "status": "churned"},
        # EC002: unknown plan tier with non-zero MRR → data quality / revenue calc disagreement
        {"customer_id": "EC002", "plan": "unknown",    "mrr": 149.00, "start_date": "2023-03-01", "end_date": "2024-01-15", "status": "churned"},
        # EC003: churned on exact period boundary (end_date == period_start)
        {"customer_id": "EC003", "plan": "starter",    "mrr": 29.00,  "start_date": "2023-10-01", "end_date": "2024-10-31", "status": "churned"},
        # EC004: long-lived enterprise account churned in window → high MRR impact
        {"customer_id": "EC004", "plan": "enterprise", "mrr": 499.00, "start_date": "2022-01-15", "end_date": "2024-11-20", "status": "churned"},
        # EC005: active customer with a plan_downgrade event in the window
        {"customer_id": "EC005", "plan": "pro",        "mrr": 99.00,  "start_date": "2022-06-01", "end_date": None,         "status": "active"},
        # EC006: active customer with plan_upgrade event → offsets net revenue churn
        {"customer_id": "EC006", "plan": "enterprise", "mrr": 499.00, "start_date": "2023-01-01", "end_date": None,         "status": "active"},
        # EC007: very short tenure (7 days) churn → trial-like behaviour
        {"customer_id": "EC007", "plan": "starter",    "mrr": 29.00,  "start_date": "2024-11-15", "end_date": "2024-11-22", "status": "churned"},
        # EC008: EU timezone boundary case (churned Dec 31 after timezone shift)
        {"customer_id": "EC008", "plan": "business",   "mrr": 249.00, "start_date": "2023-08-01", "end_date": "2023-12-31", "status": "churned"},
        # EC009: retry-storm customer (will have duplicate cancel event)
        {"customer_id": "EC009", "plan": "pro",        "mrr": 99.00,  "start_date": "2024-09-01", "end_date": "2024-11-10", "status": "churned"},
        # EC010: reactivated — churned then started a new subscription (two rows same customer)
        {"customer_id": "EC010", "plan": "starter",    "mrr": 29.00,  "start_date": "2023-01-01", "end_date": "2023-06-30", "status": "churned"},
        {"customer_id": "EC010", "plan": "pro",        "mrr": 99.00,  "start_date": "2023-07-25", "end_date": None,         "status": "active"},
        # EC011: zero-MRR free-tier account that churned → logo churn yes, revenue churn no
        {"customer_id": "EC011", "plan": "starter",    "mrr": 0.00,   "start_date": "2024-08-01", "end_date": "2024-11-05", "status": "churned"},
        # EC012: mid-month start and churn — denominator depends on whether partial months count
        {"customer_id": "EC012", "plan": "business",   "mrr": 249.00, "start_date": "2024-11-16", "end_date": "2024-11-30", "status": "churned"},
        # EC013: churned 1 day outside the window (should NOT appear in 30-day window ending 2024-11-30)
        {"customer_id": "EC013", "plan": "pro",        "mrr": 99.00,  "start_date": "2023-05-01", "end_date": "2024-10-30", "status": "churned"},
        # EC014: paused account — status churned but will be re-examined by some definitions
        {"customer_id": "EC014", "plan": "business",   "mrr": 249.00, "start_date": "2022-11-01", "end_date": "2024-11-25", "status": "churned"},
        # EC015: plan unknown + churned → worst case for revenue definitions
        {"customer_id": "EC015", "plan": "unknown",    "mrr": 0.00,   "start_date": "2024-10-01", "end_date": "2024-11-18", "status": "churned"},
    ]

    EDGE_CASE_EVENTS = [
        {"event_id": "ECE001",    "customer_id": "EC001", "event_type": "cancel_requested", "event_date": "2024-11-25", "metadata": "reason=price"},
        {"event_id": "ECE001_r1", "customer_id": "EC001", "event_type": "cancel_requested", "event_date": "2024-11-25", "metadata": "reason=price&retry=1"},  # retry storm
        {"event_id": "ECE002",    "customer_id": "EC002", "event_type": "cancel_requested", "event_date": "2024-01-10", "metadata": "reason=competitor"},
        {"event_id": "ECE003",    "customer_id": "EC003", "event_type": "cancel_requested", "event_date": "2024-10-28", "metadata": "reason=budget_cut"},
        {"event_id": "ECE004",    "customer_id": "EC004", "event_type": "cancel_requested", "event_date": "2024-11-15", "metadata": "reason=switching_tools"},
        {"event_id": "ECE005",    "customer_id": "EC005", "event_type": "plan_downgrade",   "event_date": "2024-11-10", "metadata": "from=business&to=pro"},
        {"event_id": "ECE006",    "customer_id": "EC006", "event_type": "plan_upgrade",     "event_date": "2024-11-05", "metadata": "from=business&to=enterprise"},
        {"event_id": "ECE007",    "customer_id": "EC007", "event_type": "cancel_requested", "event_date": "2024-11-20", "metadata": "reason=price&note=trial_like"},
        {"event_id": "ECE008",    "customer_id": "EC008", "event_type": "cancel_requested", "event_date": "2023-12-31", "metadata": "reason=price&tz=Europe/Berlin"},
        {"event_id": "ECE009",    "customer_id": "EC009", "event_type": "cancel_requested", "event_date": "2024-11-08", "metadata": "reason=unused"},
        {"event_id": "ECE009_r1", "customer_id": "EC009", "event_type": "cancel_requested", "event_date": "2024-11-08", "metadata": "reason=unused&retry=1"},  # retry storm
        {"event_id": "ECE010a",   "customer_id": "EC010", "event_type": "cancel_requested", "event_date": "2023-06-25", "metadata": "reason=price"},
        {"event_id": "ECE010b",   "customer_id": "EC010", "event_type": "plan_upgrade",     "event_date": "2023-07-25", "metadata": "from=starter&to=pro&note=reactivation"},
        {"event_id": "ECE011",    "customer_id": "EC011", "event_type": "cancel_requested", "event_date": "2024-11-02", "metadata": "reason=unused&tier=free"},
        {"event_id": "ECE013",    "customer_id": "EC013", "event_type": "cancel_requested", "event_date": "2024-10-27", "metadata": "reason=competitor&note=outside_window"},
        {"event_id": "ECE014",    "customer_id": "EC014", "event_type": "cancel_requested", "event_date": "2024-11-20", "metadata": "reason=budget_cut&note=paused"},
        {"event_id": "ECE015",    "customer_id": "EC015", "event_type": "cancel_requested", "event_date": "2024-11-15", "metadata": "reason=price&tier=unknown"},
    ]

    subscriptions.extend(EDGE_CASES)
    events.extend(EDGE_CASE_EVENTS)

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
