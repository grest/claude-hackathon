"""
Synthetic 6-month SaaS dataset (Oct 2025 – Mar 2026).
Produces realistic MRR movements and churn events for the dashboard.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import List, Tuple
from saas_churn.engine import ChurnEvent, EventType, ContractType


@dataclass
class MonthlySnapshot:
    period_start: date
    period_end: date
    period_start_mrr: float
    period_start_account_count: int
    new_mrr: float          # expansion / new business
    events: List[ChurnEvent] = field(default_factory=list)


def last_day(year: int, month: int) -> date:
    import calendar
    return date(year, month, calendar.monthrange(year, month)[1])


MONTHS: List[MonthlySnapshot] = [
    # October 2025 — healthy growth, one small cancellation
    MonthlySnapshot(
        period_start=date(2025, 10, 1), period_end=last_day(2025, 10),
        period_start_mrr=82_000.0, period_start_account_count=84,
        new_mrr=6_500.0,
        events=[
            ChurnEvent("oct_cancel_1", EventType.CANCELLATION,
                       date(2025, 10, 8), last_day(2025, 10),
                       800.0, 0.0, True, ContractType.ANNUAL),
        ],
    ),
    # November 2025 — discount season, a pause, no big losses
    MonthlySnapshot(
        period_start=date(2025, 11, 1), period_end=last_day(2025, 11),
        period_start_mrr=87_700.0, period_start_account_count=88,
        new_mrr=4_200.0,
        events=[
            ChurnEvent("nov_pause_1", EventType.PAUSE,
                       date(2025, 11, 12), last_day(2025, 11),
                       600.0, 0.0, True, ContractType.ANNUAL),
            ChurnEvent("nov_discount_1", EventType.DISCOUNT,
                       date(2025, 11, 20), last_day(2025, 11),
                       1_200.0, 900.0, False, ContractType.ANNUAL),  # excluded
        ],
    ),
    # December 2025 — slow month, one mid-size cancellation
    MonthlySnapshot(
        period_start=date(2025, 12, 1), period_end=last_day(2025, 12),
        period_start_mrr=91_300.0, period_start_account_count=91,
        new_mrr=3_100.0,
        events=[
            ChurnEvent("dec_cancel_1", EventType.CANCELLATION,
                       date(2025, 12, 3), last_day(2025, 12),
                       2_100.0, 0.0, True, ContractType.ANNUAL),
            ChurnEvent("dec_trial_1", EventType.TRIAL_EXPIRY,
                       date(2025, 12, 15), date(2025, 12, 15),
                       0.0, 0.0, True, ContractType.MONTHLY, is_trial=True),
        ],
    ),
    # January 2026 — strong new year, downgrade on one account
    MonthlySnapshot(
        period_start=date(2026, 1, 1), period_end=last_day(2026, 1),
        period_start_mrr=92_300.0, period_start_account_count=92,
        new_mrr=9_800.0,
        events=[
            ChurnEvent("jan_downgrade_1", EventType.DOWNGRADE,
                       date(2026, 1, 14), last_day(2026, 1),
                       2_500.0, 1_200.0, True, ContractType.ANNUAL),
            ChurnEvent("jan_winback_1", EventType.CANCELLATION,
                       date(2026, 1, 20), last_day(2026, 1),
                       1_000.0, 0.0, True, ContractType.ANNUAL,
                       win_back_date=date(2026, 1, 25), churn_reversed=True),
        ],
    ),
    # February 2026 — churn spike, two cancellations
    MonthlySnapshot(
        period_start=date(2026, 2, 1), period_end=last_day(2026, 2),
        period_start_mrr=98_800.0, period_start_account_count=98,
        new_mrr=5_400.0,
        events=[
            ChurnEvent("feb_cancel_1", EventType.CANCELLATION,
                       date(2026, 2, 5), last_day(2026, 2),
                       3_200.0, 0.0, True, ContractType.ANNUAL),
            ChurnEvent("feb_cancel_2", EventType.CANCELLATION,
                       date(2026, 2, 18), last_day(2026, 2),
                       1_800.0, 0.0, True, ContractType.ANNUAL),
            ChurnEvent("feb_trial_1", EventType.TRIAL_EXPIRY,
                       date(2026, 2, 10), date(2026, 2, 10),
                       0.0, 0.0, True, ContractType.MONTHLY, is_trial=True),
        ],
    ),
    # March 2026 — the reconciliation month from waypoint 6
    MonthlySnapshot(
        period_start=date(2026, 3, 1), period_end=last_day(2026, 3),
        period_start_mrr=100_000.0, period_start_account_count=100,
        new_mrr=6_200.0,
        events=[
            ChurnEvent("acme_corp", EventType.CANCELLATION,
                       date(2026, 3, 1), last_day(2026, 3),
                       1_000.0, 0.0, True, ContractType.ANNUAL),
            ChurnEvent("techstart_inc", EventType.CANCELLATION,
                       date(2026, 3, 10), last_day(2026, 3),
                       800.0, 0.0, True, ContractType.ANNUAL),
            ChurnEvent("megacorp", EventType.DOWNGRADE,
                       date(2026, 3, 5), last_day(2026, 3),
                       3_000.0, 1_500.0, True, ContractType.ANNUAL),
            ChurnEvent("finco", EventType.PAUSE,
                       date(2026, 3, 20), last_day(2026, 3),
                       900.0, 0.0, True, ContractType.ANNUAL),
            ChurnEvent("trial_a", EventType.TRIAL_EXPIRY,
                       date(2026, 3, 15), date(2026, 3, 15),
                       0.0, 0.0, True, ContractType.MONTHLY, is_trial=True),
            ChurnEvent("trial_b", EventType.TRIAL_EXPIRY,
                       date(2026, 3, 22), date(2026, 3, 22),
                       0.0, 0.0, True, ContractType.MONTHLY, is_trial=True),
            ChurnEvent("trial_c", EventType.TRIAL_EXPIRY,
                       date(2026, 3, 28), date(2026, 3, 28),
                       0.0, 0.0, True, ContractType.MONTHLY, is_trial=True),
        ],
    ),
]
