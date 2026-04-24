"""
Build data/adventureworks.db from the AdventureWorks CSV files.

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
DEFAULT_OUTPUT  = REPO_ROOT / "data" / "adventureworks.db"

# ── Table registry ────────────────────────────────────────────────────────────
# Each entry: sqlite_table_name -> (csv_filename, delimiter, [columns])
#   delimiter "tab"  = FIELDTERMINATOR '\t', ROWTERMINATOR '\n'
#   delimiter "plus" = FIELDTERMINATOR '+|', ROWTERMINATOR '&|\n'  (XML columns)
#   columns = ordered list matching CSV column positions (no header row in files)

TAB = "tab"
PLUS = "plus"

TABLES: dict[str, tuple[str, str, list[str]]] = {
    "sales_customer": ("Customer.csv", TAB, [
        "CustomerID", "PersonID", "StoreID", "TerritoryID",
        "AccountNumber", "rowguid", "ModifiedDate",
    ]),
    "sales_salesorderheader": ("SalesOrderHeader.csv", TAB, [
        "SalesOrderID", "RevisionNumber", "OrderDate", "DueDate", "ShipDate",
        "Status", "OnlineOrderFlag", "SalesOrderNumber", "PurchaseOrderNumber",
        "AccountNumber", "CustomerID", "SalesPersonID", "TerritoryID",
        "BillToAddressID", "ShipToAddressID", "ShipMethodID", "CreditCardID",
        "CreditCardApprovalCode", "CurrencyRateID", "SubTotal", "TaxAmt",
        "Freight", "TotalDue", "Comment", "rowguid", "ModifiedDate",
    ]),
    "sales_salesorderdetail": ("SalesOrderDetail.csv", TAB, [
        "SalesOrderID", "SalesOrderDetailID", "CarrierTrackingNumber", "OrderQty",
        "ProductID", "SpecialOfferID", "UnitPrice", "UnitPriceDiscount",
        "LineTotal", "rowguid", "ModifiedDate",
    ]),
    "sales_salesterritory": ("SalesTerritory.csv", TAB, [
        "TerritoryID", "Name", "CountryRegionCode", "TerritoryGroup",
        "SalesYTD", "SalesLastYear", "CostYTD", "CostLastYear", "rowguid", "ModifiedDate",
    ]),
    "sales_salesperson": ("SalesPerson.csv", TAB, [
        "BusinessEntityID", "TerritoryID", "SalesQuota", "Bonus", "CommissionPct",
        "SalesYTD", "SalesLastYear", "rowguid", "ModifiedDate",
    ]),
    "sales_salesterritoryhistory": ("SalesTerritoryHistory.csv", TAB, [
        "BusinessEntityID", "TerritoryID", "StartDate", "EndDate", "rowguid", "ModifiedDate",
    ]),
    "sales_salesorderheadersalesreason": ("SalesOrderHeaderSalesReason.csv", TAB, [
        "SalesOrderID", "SalesReasonID", "ModifiedDate",
    ]),
    "sales_salesreason": ("SalesReason.csv", TAB, [
        "SalesReasonID", "Name", "ReasonType", "ModifiedDate",
    ]),
    "sales_specialoffer": ("SpecialOffer.csv", TAB, [
        "SpecialOfferID", "Description", "DiscountPct", "Type", "Category",
        "StartDate", "EndDate", "MinQty", "MaxQty", "rowguid", "ModifiedDate",
    ]),
    "sales_specialofferproduct": ("SpecialOfferProduct.csv", TAB, [
        "SpecialOfferID", "ProductID", "rowguid", "ModifiedDate",
    ]),
    "production_product": ("Product.csv", TAB, [
        "ProductID", "Name", "ProductNumber", "MakeFlag", "FinishedGoodsFlag",
        "Color", "SafetyStockLevel", "ReorderPoint", "StandardCost", "ListPrice",
        "Size", "SizeUnitMeasureCode", "WeightUnitMeasureCode", "Weight",
        "DaysToManufacture", "ProductLine", "Class", "Style", "ProductSubcategoryID",
        "ProductModelID", "SellStartDate", "SellEndDate", "DiscontinuedDate",
        "rowguid", "ModifiedDate",
    ]),
    "production_productcategory": ("ProductCategory.csv", TAB, [
        "ProductCategoryID", "Name", "rowguid", "ModifiedDate",
    ]),
    "production_productsubcategory": ("ProductSubcategory.csv", TAB, [
        "ProductSubcategoryID", "ProductCategoryID", "Name", "rowguid", "ModifiedDate",
    ]),
    "person_address": ("Address.csv", TAB, [
        "AddressID", "AddressLine1", "AddressLine2", "City", "StateProvinceID",
        "PostalCode", "SpatialLocation", "rowguid", "ModifiedDate",
    ]),
    "person_stateprovince": ("StateProvince.csv", TAB, [
        "StateProvinceID", "StateProvinceCode", "CountryRegionCode",
        "IsOnlyStateProvinceFlag", "Name", "TerritoryID", "rowguid", "ModifiedDate",
    ]),
    # +| delimited (XML columns prevent tab use)
    "person_person": ("Person.csv", PLUS, [
        "BusinessEntityID", "PersonType", "NameStyle", "Title", "FirstName",
        "MiddleName", "LastName", "Suffix", "EmailPromotion",
        "AdditionalContactInfo", "Demographics", "rowguid", "ModifiedDate",
    ]),
    "sales_store": ("Store.csv", PLUS, [
        "BusinessEntityID", "Name", "SalesPersonID", "Demographics", "rowguid", "ModifiedDate",
    ]),
}

# Indexes to create after all tables are loaded
INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_soh_customer    ON sales_salesorderheader(CustomerID)",
    "CREATE INDEX IF NOT EXISTS ix_soh_territory   ON sales_salesorderheader(TerritoryID)",
    "CREATE INDEX IF NOT EXISTS ix_sod_order       ON sales_salesorderdetail(SalesOrderID)",
    "CREATE INDEX IF NOT EXISTS ix_sod_product     ON sales_salesorderdetail(ProductID)",
    "CREATE INDEX IF NOT EXISTS ix_cust_store      ON sales_customer(StoreID)",
    "CREATE INDEX IF NOT EXISTS ix_cust_territory  ON sales_customer(TerritoryID)",
    "CREATE INDEX IF NOT EXISTS ix_product_subcat  ON production_product(ProductSubcategoryID)",
    "CREATE INDEX IF NOT EXISTS ix_subcat_cat      ON production_productsubcategory(ProductCategoryID)",
    "CREATE INDEX IF NOT EXISTS ix_sth_person      ON sales_salesterritoryhistory(BusinessEntityID)",
    "CREATE INDEX IF NOT EXISTS ix_store_sp        ON sales_store(SalesPersonID)",
]


def _load_tab(path: Path, columns: list[str]) -> pd.DataFrame:
    return pd.read_csv(
        path,
        sep="\t",
        header=None,
        names=columns,
        dtype=str,
        na_values=[""],
        keep_default_na=True,
        encoding="utf-8-sig",
        on_bad_lines="skip",
    )


def _load_plus(path: Path, columns: list[str]) -> pd.DataFrame:
    """Parse files with FIELDTERMINATOR='+|' and ROWTERMINATOR='&|\\n'.

    Used for tables with XML columns (Person, Store) where tab appears inside values.
    """
    raw = path.read_bytes().decode("utf-8-sig")
    rows = []
    for line in raw.split("&|\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split("+|")
        if len(parts) == len(columns):
            rows.append(dict(zip(columns, parts)))
        elif len(parts) > len(columns):
            # Extra fields (e.g. trailing delimiter) — truncate
            rows.append(dict(zip(columns, parts[: len(columns)])))
    df = pd.DataFrame(rows, columns=columns)
    # Replace empty strings with NaN to match tab-loader behaviour
    return df.replace("", pd.NA)


def build_db(csv_dir: Path, output: Path) -> None:
    print(f"CSV source : {csv_dir}")
    print(f"Output DB  : {output}")

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    conn = sqlite3.connect(output)

    for table_name, (csv_file, delim, columns) in TABLES.items():
        csv_path = csv_dir / csv_file
        if not csv_path.exists():
            print(f"  SKIP {csv_file} (not found)")
            continue

        print(f"Loading {csv_file} -> {table_name} ...", end=" ", flush=True)
        df = _load_tab(csv_path, columns) if delim == TAB else _load_plus(csv_path, columns)
        df.to_sql(table_name, conn, if_exists="replace", index=False)
        print(f"{len(df):,} rows")

    cur = conn.cursor()
    for idx_sql in INDEXES:
        cur.execute(idx_sql)

    conn.commit()
    conn.close()
    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv-dir", default=str(DEFAULT_CSV_DIR))
    parser.add_argument("--output",  default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    build_db(Path(args.csv_dir), Path(args.output))
