from pathlib import Path

import pandas as pd


def load_subscriptions(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["start_date", "end_date"])
    df["end_date"] = pd.to_datetime(df["end_date"], errors="coerce")
    return df


def load_events(path: str | Path) -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=["event_date"])
