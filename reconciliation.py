"""
Waypoint 6 — Churn Reconciliation
Shows why Dev (4.2%), Priya (3.1%), and Tom (6.8%) got different answers
from the same underlying data, and what v1.0 produces.
"""

from dataclasses import dataclass
from datetime import date
from typing import List
from saas_churn.engine import (
    ChurnEvent, EventType, ContractType,
    classify_event, calculate_period_churn,
)

PERIOD_START = date(2026, 3, 1)
PERIOD_END   = date(2026, 3, 31)

# ---------------------------------------------------------------------------
# Synthetic dataset — March 2026
# Designed to reproduce: Dev 4.2% | Priya 3.1% | Tom 6.8% | v1.0 4.2%
# ---------------------------------------------------------------------------
#
# Paying accounts at period start : 100   ($100,000 MRR)
# Trial accounts (in Tom's system): 3     ($0 MRR — not yet converted)
# Priya's base                    : 97    (excludes accounts added mid-month)
#
# Events:
#   Acme Corp      — full cancellation          $1,000 MRR
#   TechStart Inc  — full cancellation          $800   MRR
#   MegaCorp       — permanent downgrade        $3,000 → $1,500 (delta $1,500)
#   FinCo          — paused                     $900   MRR
#   Trial A/B/C    — trial expiry               $0     (never converted)

PAYING_ACCOUNT_COUNT   = 100
PERIOD_START_MRR       = 100_000.0
PRIYA_ACCOUNT_BASE     = 97      # excludes 3 accounts added mid-month
TOM_ACCOUNT_BASE       = 103     # includes 3 trial accounts


EVENTS: List[ChurnEvent] = [
    ChurnEvent(
        account_id="acme_corp",
        event_type=EventType.CANCELLATION,
        notification_date=date(2026, 3, 1),
        contract_end_date=date(2026, 3, 31),
        old_mrr=1_000.0, new_mrr=0.0,
        is_permanent=True,
        contract_type=ContractType.ANNUAL,
    ),
    ChurnEvent(
        account_id="techstart_inc",
        event_type=EventType.CANCELLATION,
        notification_date=date(2026, 3, 10),
        contract_end_date=date(2026, 3, 31),
        old_mrr=800.0, new_mrr=0.0,
        is_permanent=True,
        contract_type=ContractType.ANNUAL,
    ),
    ChurnEvent(
        account_id="megacorp",
        event_type=EventType.DOWNGRADE,
        notification_date=date(2026, 3, 5),
        contract_end_date=date(2026, 3, 31),
        old_mrr=3_000.0, new_mrr=1_500.0,
        is_permanent=True,
        contract_type=ContractType.ANNUAL,
    ),
    ChurnEvent(
        account_id="finco",
        event_type=EventType.PAUSE,
        notification_date=date(2026, 3, 20),
        contract_end_date=date(2026, 3, 31),
        old_mrr=900.0, new_mrr=0.0,
        is_permanent=True,
        contract_type=ContractType.ANNUAL,
    ),
    ChurnEvent(
        account_id="trial_a",
        event_type=EventType.TRIAL_EXPIRY,
        notification_date=date(2026, 3, 15),
        contract_end_date=date(2026, 3, 15),
        old_mrr=0.0, new_mrr=0.0,
        is_permanent=True,
        is_trial=True,
        contract_type=ContractType.MONTHLY,
    ),
    ChurnEvent(
        account_id="trial_b",
        event_type=EventType.TRIAL_EXPIRY,
        notification_date=date(2026, 3, 22),
        contract_end_date=date(2026, 3, 22),
        old_mrr=0.0, new_mrr=0.0,
        is_permanent=True,
        is_trial=True,
        contract_type=ContractType.MONTHLY,
    ),
    ChurnEvent(
        account_id="trial_c",
        event_type=EventType.TRIAL_EXPIRY,
        notification_date=date(2026, 3, 28),
        contract_end_date=date(2026, 3, 28),
        old_mrr=0.0, new_mrr=0.0,
        is_permanent=True,
        is_trial=True,
        contract_type=ContractType.MONTHLY,
    ),
]


# ---------------------------------------------------------------------------
# Legacy methodology functions (one per stakeholder, as they actually ran)
# ---------------------------------------------------------------------------

def dev_revenue_churn(events: List[ChurnEvent]) -> float:
    """
    Dev (Finance): MRR lost / period-start MRR.
    Counts cancellations + permanent downgrades + pauses.
    Excludes trials (they were never in his MRR base).
    Does NOT exclude temporary discounts — he never saw any this period.
    """
    mrr_lost = sum(
        e.old_mrr - e.new_mrr
        for e in events
        if not e.is_trial
        and e.event_type in (EventType.CANCELLATION, EventType.DOWNGRADE, EventType.PAUSE)
        and e.is_permanent
    )
    return round(mrr_lost / PERIOD_START_MRR * 100, 2)


def priya_account_churn(events: List[ChurnEvent]) -> float:
    """
    Priya (Customer Success): accounts fully lost / Priya's account base.
    Counts only cancellations + pauses — NOT downgrades (account retained).
    Uses a smaller base (97) excluding accounts added mid-month.
    Excludes trials.
    """
    accounts_lost = sum(
        1 for e in events
        if not e.is_trial
        and e.event_type in (EventType.CANCELLATION, EventType.PAUSE)
    )
    return round(accounts_lost / PRIYA_ACCOUNT_BASE * 100, 2)


def tom_account_churn(events: List[ChurnEvent]) -> float:
    """
    Tom (Data Engineering): all account exits / Tom's total base.
    Includes trials (they exist in his subscriptions table).
    Counts cancellations + pauses + downgrades + trial expiries as 'exits'.
    Base includes trial accounts (103 total).
    """
    exits = sum(
        1 for e in events
        if e.event_type in (
            EventType.CANCELLATION, EventType.PAUSE,
            EventType.DOWNGRADE, EventType.TRIAL_EXPIRY,
        )
    )
    return round(exits / TOM_ACCOUNT_BASE * 100, 2)


# ---------------------------------------------------------------------------
# Reconciliation report
# ---------------------------------------------------------------------------

@dataclass
class EventRow:
    account: str
    event: str
    mrr_impact: str
    dev: str
    priya: str
    tom: str
    v1_0: str
    note: str


def build_reconciliation_table() -> List[EventRow]:
    return [
        EventRow("Acme Corp",     "Cancellation",           "$1,000",  "✓ Rev", "✓ Acct", "✓ Acct", "✓ Rev",  ""),
        EventRow("TechStart Inc", "Cancellation",           "$800",    "✓ Rev", "✓ Acct", "✓ Acct", "✓ Rev",  ""),
        EventRow("MegaCorp",      "Permanent downgrade",    "$1,500",  "✓ Rev", "✗",      "✓ Acct", "✓ Rev",  "Priya: account retained"),
        EventRow("FinCo",         "Pause",                  "$900",    "✓ Rev", "✓ Acct", "✓ Acct", "✓ Rev",  ""),
        EventRow("Trial A",       "Trial expiry",           "$0",      "✗",     "✗",      "✓ Acct", "✗",      "Tom: trial in subscriptions table"),
        EventRow("Trial B",       "Trial expiry",           "$0",      "✗",     "✗",      "✓ Acct", "✗",      "Tom: trial in subscriptions table"),
        EventRow("Trial C",       "Trial expiry",           "$0",      "✗",     "✗",      "✓ Acct", "✗",      "Tom: trial in subscriptions table"),
    ]


def print_report() -> None:
    dev   = dev_revenue_churn(EVENTS)
    priya = priya_account_churn(EVENTS)
    tom   = tom_account_churn(EVENTS)

    v1_summary = calculate_period_churn(
        events=EVENTS,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        period_start_mrr=PERIOD_START_MRR,
        period_start_account_count=PAYING_ACCOUNT_COUNT,
    )

    rows = build_reconciliation_table()

    print("=" * 80)
    print("SAAS CHURN RECONCILIATION — March 2026")
    print("=" * 80)

    print(f"\n{'ACCOUNT':<18} {'EVENT':<24} {'MRR LOST':>8}  {'Dev':>6}  {'Priya':>6}  {'Tom':>6}  {'v1.0':>6}  NOTE")
    print("-" * 95)
    for r in rows:
        print(f"{r.account:<18} {r.event:<24} {r.mrr_impact:>8}  {r.dev:>6}  {r.priya:>6}  {r.tom:>6}  {r.v1_0:>6}  {r.note}")

    print("\n" + "-" * 80)
    print(f"{'RESULT':18} {'':24} {'':>8}  {dev:>5}%  {priya:>5}%  {tom:>5}%  {v1_summary.revenue_churn_rate:>5}%")
    print(f"{'BASE':18} {'':24} {'':>8}  {'$100k MRR':>6}  {'97 acct':>6}  {'103 acct':>8}  {'$100k MRR':>9}")
    print("=" * 80)

    print("""
EXECUTIVE SUMMARY
─────────────────
Three teams measured churn in March 2026. Same company. Same month. Three answers.

  Dev   (Finance)       4.2%  Revenue churn — MRR lost from cancellations,
                               downgrades, and pauses against $100k MRR base.
                               Closest to business impact. Correct methodology.

  Priya (Customer Success) 3.1%  Account churn — counts only fully-lost accounts
                               (excludes MegaCorp downgrade, account retained).
                               Denominator is 97 mature accounts, not 100.
                               Understates revenue impact by ignoring downgrades.

  Tom   (Data Engineering) 6.8%  Account exits — counts everything that left the
                               subscriptions table, including 3 trial expirations
                               and MegaCorp's downgrade. Base inflated to 103
                               (trials included). Overstates churn by mixing
                               trials with paying customers.

  v1.0  (This engine)   4.2%  Revenue churn on paying accounts only.
                               Trials excluded. Downgrades counted as revenue
                               delta. Win-backs reversible. Multi-year contracts
                               booked at renewal date. Single auditable source.

Root causes of divergence
  1. METRIC TYPE     Dev tracks revenue; Priya and Tom track accounts.
  2. SCOPE           Tom includes trials; Dev and Priya exclude them.
  3. DOWNGRADE RULE  Dev and Tom count MegaCorp; Priya does not.
  4. DENOMINATOR     Priya uses 97 (mature accounts); Tom uses 103 (all).
""")


if __name__ == "__main__":
    print_report()
