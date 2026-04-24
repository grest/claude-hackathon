import os
import sqlite3
from pathlib import Path
from typing import Optional
from datetime import date

import pandas as pd

REPO_ROOT = Path(__file__).parent.parent
DEFAULT_DB = REPO_ROOT / "data" / "adventureworks.db"

# Treat stores as SaaS "customers":
#   plan       = territory name
#   mrr        = avg monthly spend (total revenue / months active)
#   start_date = first order date
#   end_date   = NULL if active; last_order_date if silent for > 365 days
#   status     = 'active' | 'churned'
# Reference date = MAX(OrderDate) in the dataset (deterministic regardless of run date).

_CHURN_QUERY = """
WITH store_orders AS (
    SELECT
        c.StoreID                             AS customer_id,
        t.Name                                AS plan,
        MIN(h.OrderDate)                      AS first_order_date,
        MAX(h.OrderDate)                      AS last_order_date,
        SUM(h.TotalDue)                       AS total_revenue
    FROM sales_customer c
    JOIN sales_salesorderheader h  ON c.CustomerID  = h.CustomerID
    JOIN sales_salesterritory   t  ON c.TerritoryID = t.TerritoryID
    GROUP BY c.StoreID, t.Name
),
ref AS (
    SELECT MAX(OrderDate) AS max_date FROM sales_salesorderheader
)
SELECT
    so.customer_id,
    so.plan,
    ROUND(
        so.total_revenue
        / MAX((JULIANDAY(so.last_order_date) - JULIANDAY(so.first_order_date) + 30) / 30.0, 1.0),
        2
    )                                                     AS mrr,
    so.first_order_date                                   AS start_date,
    CASE
        WHEN JULIANDAY(ref.max_date) - JULIANDAY(so.last_order_date) > 365
        THEN so.last_order_date
        ELSE NULL
    END                                                   AS end_date,
    CASE
        WHEN JULIANDAY(ref.max_date) - JULIANDAY(so.last_order_date) > 365
        THEN 'churned'
        ELSE 'active'
    END                                                   AS status
FROM store_orders so, ref
ORDER BY so.customer_id
"""


def get_db_path() -> str:
    path = os.environ.get("DATABASE_PATH", "").strip()
    if not path:
        raise ValueError("DATABASE_PATH environment variable is not set")
    return path


def fetch_subscriptions(db_path: str, as_of: Optional[date] = None) -> pd.DataFrame:
    """
    Query the AdventureWorks SQLite DB and return a DataFrame matching the
    calculator contract:
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
        df = pd.read_sql_query(_CHURN_QUERY, conn)
    finally:
        conn.close()

    df["start_date"]  = pd.to_datetime(df["start_date"], errors="coerce")
    df["end_date"]    = pd.to_datetime(df["end_date"],   errors="coerce")
    df["mrr"]         = df["mrr"].astype("float64")
    # Force legacy object dtype for string columns so the calculator's
    # equality comparisons (e.g. df["status"] == "churned") behave identically
    # regardless of which pandas StringDtype variant sqlite3 infers.
    for col in ("customer_id", "plan", "status"):
        df[col] = df[col].astype(object)
    return df
