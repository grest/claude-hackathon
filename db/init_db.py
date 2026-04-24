"""
Create (or recreate) data/adventureworks.db from the AdventureWorks CSV files.

Usage:
    python db/init_db.py
    python db/init_db.py --csv-dir data/AdventureWorks-oltp-install-script --output data/adventureworks.db
"""
import argparse
import sqlite3
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).parent.parent
DEFAULT_CSV_DIR = REPO_ROOT / "data" / "AdventureWorks-oltp-install-script"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "adventureworks.db"

# ── Column definitions ────────────────────────────────────────────────────────
# All files: tab-delimited, no header row, FIELDTERMINATOR='\t', ROWTERMINATOR='\n'
# Store.csv exception: FIELDTERMINATOR='+|', ROWTERMINATOR='&|\n'  (XML column)

CUSTOMER_COLS = ["CustomerID", "PersonID", "StoreID", "TerritoryID", "AccountNumber", "rowguid", "ModifiedDate"]
CUSTOMER_USE  = [0, 2, 3]           # CustomerID, StoreID, TerritoryID

SOH_COLS = [
    "SalesOrderID", "RevisionNumber", "OrderDate", "DueDate", "ShipDate",
    "Status", "OnlineOrderFlag", "SalesOrderNumber", "PurchaseOrderNumber",
    "AccountNumber", "CustomerID", "SalesPersonID", "TerritoryID",
    "BillToAddressID", "ShipToAddressID", "ShipMethodID", "CreditCardID",
    "CreditCardApprovalCode", "CurrencyRateID", "SubTotal", "TaxAmt",
    "Freight", "TotalDue", "Comment", "rowguid", "ModifiedDate",
]
SOH_USE = [0, 2, 10, 22]            # SalesOrderID, OrderDate, CustomerID, TotalDue

TERRITORY_COLS = ["TerritoryID", "Name", "CountryRegionCode", "TerritoryGroup",
                  "SalesYTD", "SalesLastYear", "CostYTD", "CostLastYear", "rowguid", "ModifiedDate"]
TERRITORY_USE  = [0, 1, 3]          # TerritoryID, Name, TerritoryGroup


def _load_tab(path: Path, all_cols: list[str], use_idx: list[int]) -> pd.DataFrame:
    names = [all_cols[i] for i in use_idx]
    return pd.read_csv(
        path,
        sep="\t",
        header=None,
        usecols=use_idx,
        names=names,
        dtype=str,
        na_values=[""],
        keep_default_na=True,
        encoding="utf-8-sig",
        on_bad_lines="skip",
    )


def _load_store(path: Path) -> pd.DataFrame:
    """Store.csv uses +| / &| delimiters because the XML Demographics column contains tabs."""
    rows = []
    raw = path.read_bytes().decode("utf-8-sig")
    for line in raw.split("&|\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split("+|")
        if len(parts) >= 2:
            rows.append({"StoreID": parts[0].strip(), "StoreName": parts[1].strip()})
    return pd.DataFrame(rows)


def build_db(csv_dir: Path, output: Path) -> None:
    print(f"CSV source : {csv_dir}")
    print(f"Output DB  : {output}")

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    conn = sqlite3.connect(output)
    cur = conn.cursor()

    # ── sales_customer ────────────────────────────────────────────────────────
    print("Loading Customer.csv …")
    customer = _load_tab(csv_dir / "Customer.csv", CUSTOMER_COLS, CUSTOMER_USE)
    customer["StoreID"] = pd.to_numeric(customer["StoreID"], errors="coerce")
    customer["TerritoryID"] = pd.to_numeric(customer["TerritoryID"], errors="coerce")
    customer = customer.dropna(subset=["StoreID"])     # keep only store customers
    customer["CustomerID"] = customer["CustomerID"].astype(int)
    customer["StoreID"] = customer["StoreID"].astype(int)
    customer["TerritoryID"] = customer["TerritoryID"].astype(int)
    customer.to_sql("sales_customer", conn, if_exists="replace", index=False)
    print(f"  {len(customer):,} store-customer rows")

    # ── sales_salesterritory ──────────────────────────────────────────────────
    print("Loading SalesTerritory.csv …")
    territory = _load_tab(csv_dir / "SalesTerritory.csv", TERRITORY_COLS, TERRITORY_USE)
    territory["TerritoryID"] = territory["TerritoryID"].astype(int)
    territory.to_sql("sales_salesterritory", conn, if_exists="replace", index=False)
    print(f"  {len(territory):,} territory rows")

    # ── sales_salesorderheader ────────────────────────────────────────────────
    print("Loading SalesOrderHeader.csv …")
    soh = _load_tab(csv_dir / "SalesOrderHeader.csv", SOH_COLS, SOH_USE)
    soh["SalesOrderID"] = soh["SalesOrderID"].astype(int)
    soh["CustomerID"] = soh["CustomerID"].astype(int)
    soh["TotalDue"] = pd.to_numeric(soh["TotalDue"], errors="coerce")
    # Normalise datetime string to ISO date (keep date part only)
    soh["OrderDate"] = pd.to_datetime(soh["OrderDate"], errors="coerce").dt.strftime("%Y-%m-%d")
    soh = soh.dropna(subset=["OrderDate", "TotalDue"])
    soh.to_sql("sales_salesorderheader", conn, if_exists="replace", index=False)
    print(f"  {len(soh):,} order rows")

    # ── indexes for the churn query ───────────────────────────────────────────
    cur.execute("CREATE INDEX IF NOT EXISTS ix_soh_customer ON sales_salesorderheader(CustomerID)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_cust_store   ON sales_customer(StoreID)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_cust_terr    ON sales_customer(TerritoryID)")

    conn.commit()
    conn.close()
    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv-dir", default=str(DEFAULT_CSV_DIR))
    parser.add_argument("--output",  default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    build_db(Path(args.csv_dir), Path(args.output))
