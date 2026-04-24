import os
from datetime import date
from typing import Optional

import pandas as pd
from sqlalchemy import create_engine, text

_QUERY = """
    SELECT
        customer_id,
        plan,
        mrr::float8   AS mrr,
        start_date,
        end_date,
        status
    FROM subscriptions
    ORDER BY customer_id, start_date
"""


def get_connection_string() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise ValueError("DATABASE_URL environment variable is not set")
    return url


def fetch_subscriptions(
    conn_str: str,
    as_of: Optional[date] = None,
) -> pd.DataFrame:
    """
    Query subscriptions and return a DataFrame with the exact contract expected
    by engine/calculator.py:
        customer_id  object
        plan         object
        mrr          float64
        start_date   datetime64[ns]
        end_date     datetime64[ns]  (NULL in DB → NaT)
        status       object
    The as_of argument is accepted for future use but not applied as a DB
    filter — the calculator needs all rows to compute period windows correctly.
    """
    engine = create_engine(conn_str, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text(_QUERY), conn)
    finally:
        engine.dispose()

    df["start_date"] = pd.to_datetime(df["start_date"])
    df["end_date"] = pd.to_datetime(df["end_date"], errors="coerce")
    df["mrr"] = df["mrr"].astype("float64")
    return df
