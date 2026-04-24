from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd


def load_subscriptions(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["start_date", "end_date"])
    df["end_date"] = pd.to_datetime(df["end_date"], errors="coerce")
    return df


def load_subscriptions_from_db(
    db_path: str,
    as_of: Optional[date] = None,
) -> pd.DataFrame:
    from engine.db import fetch_subscriptions  # deferred import keeps sqlite3 optional
    return fetch_subscriptions(db_path, as_of=as_of)


def load_events(path: str | Path) -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=["event_date"])
