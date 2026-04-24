import sqlite3
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

REPO_ROOT = Path(__file__).parent.parent
DEFAULT_DB = REPO_ROOT / "data" / "churn_engine.db"

_SUBSCRIPTIONS_QUERY = """
    SELECT customer_id, plan, mrr, start_date, end_date, status
    FROM subscriptions
"""


def fetch_subscriptions(db_path: str, as_of: Optional[date] = None) -> pd.DataFrame:
    """
    Query the SQLite DB and return a DataFrame matching the calculator contract:
        customer_id  object
        plan         object
        mrr          float64
        start_date   datetime64[ns]
        end_date     datetime64[ns]  (NULL in DB → NaT)
        status       object

    as_of is accepted for API compatibility but not applied as a DB filter —
    the calculator needs all rows to compute period windows correctly.
    """
    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql_query(_SUBSCRIPTIONS_QUERY, conn)
    finally:
        conn.close()

    df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce")
    df["end_date"]   = pd.to_datetime(df["end_date"],   errors="coerce")
    df["mrr"]        = df["mrr"].astype("float64")
    for col in ("customer_id", "plan", "status"):
        df[col] = df[col].astype(object)
    return df
