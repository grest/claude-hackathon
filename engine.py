"""
SaaS Churn Calculation Engine
Version: 1.0
Owner: Revenue Operations
Boundary cases: see metric definition v1.0 (2026-04-24)
"""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import List, Optional

ENGINE_VERSION = "1.0"

DAYS_TO_CONTRACT_END_FLAG_THRESHOLD = 45


class EventType(Enum):
    CANCELLATION = "cancellation"
    DOWNGRADE = "downgrade"
    DISCOUNT = "discount"
    PAUSE = "pause"
    TRIAL_EXPIRY = "trial_expiry"
    WIN_BACK = "win_back"


class ContractType(Enum):
    MONTHLY = "monthly"
    ANNUAL = "annual"
    MULTI_YEAR = "multi_year"


@dataclass
class ChurnEvent:
    account_id: str
    event_type: EventType
    notification_date: date
    contract_end_date: date
    old_mrr: float
    new_mrr: float                      # 0.0 for full cancellation/pause
    is_permanent: bool                  # False for temporary discounts
    contract_type: ContractType = ContractType.ANNUAL
    is_trial: bool = False
    win_back_date: Optional[date] = None
    churn_reversed: bool = False


@dataclass
class ChurnResult:
    account_id: str
    is_churn: bool
    mrr_lost: float
    churn_date: date                    # notification_date or renewal_date for multi-year
    days_to_contract_end: int
    late_notification_flag: bool
    churn_reversed: bool
    engine_version: str = ENGINE_VERSION
    exclusion_reason: Optional[str] = None


@dataclass
class PeriodChurnSummary:
    period_start: date
    period_end: date
    period_start_mrr: float
    total_mrr_lost: float
    total_accounts_lost: int
    revenue_churn_rate: float
    account_churn_rate: float
    period_start_account_count: int
    late_notification_flags: int
    engine_version: str = ENGINE_VERSION


def _churn_date(event: ChurnEvent) -> date:
    """
    Multi-year contracts: churn date is renewal date (contract_end_date).
    All others: notification_date.
    """
    if event.contract_type == ContractType.MULTI_YEAR:
        return event.contract_end_date
    return event.notification_date


def _mrr_lost(event: ChurnEvent) -> float:
    return round(event.old_mrr - event.new_mrr, 2)


def classify_event(event: ChurnEvent) -> ChurnResult:
    """
    Classify a single subscription event against the v1.0 metric definition.
    Returns a ChurnResult with is_churn=False and an exclusion_reason for non-churn events.
    """
    days_to_end = (event.contract_end_date - event.notification_date).days
    late_flag = days_to_end > DAYS_TO_CONTRACT_END_FLAG_THRESHOLD

    base = dict(
        account_id=event.account_id,
        churn_date=_churn_date(event),
        days_to_contract_end=days_to_end,
        late_notification_flag=late_flag,
        churn_reversed=event.churn_reversed,
    )

    # --- Exclusions (order matters) ---

    if event.is_trial:
        return ChurnResult(**base, is_churn=False, mrr_lost=0.0,
                           exclusion_reason="trial_expiry")

    if event.event_type == EventType.TRIAL_EXPIRY:
        return ChurnResult(**base, is_churn=False, mrr_lost=0.0,
                           exclusion_reason="trial_expiry")

    if event.event_type == EventType.DISCOUNT or not event.is_permanent:
        return ChurnResult(**base, is_churn=False, mrr_lost=0.0,
                           exclusion_reason="temporary_discount")

    if event.churn_reversed:
        return ChurnResult(**base, is_churn=False, mrr_lost=0.0,
                           exclusion_reason="win_back")

    # --- Churn cases ---

    if event.event_type == EventType.CANCELLATION:
        return ChurnResult(**base, is_churn=True, mrr_lost=event.old_mrr)

    if event.event_type == EventType.PAUSE:
        return ChurnResult(**base, is_churn=True, mrr_lost=event.old_mrr)

    if event.event_type == EventType.DOWNGRADE:
        return ChurnResult(**base, is_churn=True, mrr_lost=_mrr_lost(event))

    return ChurnResult(**base, is_churn=False, mrr_lost=0.0,
                       exclusion_reason="unclassified")


def calculate_period_churn(
    events: List[ChurnEvent],
    period_start: date,
    period_end: date,
    period_start_mrr: float,
    period_start_account_count: int,
) -> PeriodChurnSummary:
    """
    Aggregate churn events within a calendar period into revenue and account churn rates.
    Only events whose churn_date falls within [period_start, period_end] are counted.
    """
    results = [classify_event(e) for e in events]

    in_period = [
        r for r in results
        if r.is_churn and period_start <= r.churn_date <= period_end
    ]

    total_mrr_lost = round(sum(r.mrr_lost for r in in_period), 2)
    total_accounts_lost = len(in_period)
    late_flags = sum(1 for r in results if r.late_notification_flag)

    revenue_churn_rate = (
        round(total_mrr_lost / period_start_mrr * 100, 4)
        if period_start_mrr > 0 else 0.0
    )
    account_churn_rate = (
        round(total_accounts_lost / period_start_account_count * 100, 4)
        if period_start_account_count > 0 else 0.0
    )

    return PeriodChurnSummary(
        period_start=period_start,
        period_end=period_end,
        period_start_mrr=period_start_mrr,
        total_mrr_lost=total_mrr_lost,
        total_accounts_lost=total_accounts_lost,
        revenue_churn_rate=revenue_churn_rate,
        account_churn_rate=account_churn_rate,
        period_start_account_count=period_start_account_count,
        late_notification_flags=late_flags,
    )
