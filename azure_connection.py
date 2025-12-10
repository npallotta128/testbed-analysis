import os
import time
import pandas as pd
import pyodbc
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError

try:
    from azure.identity import DefaultAzureCredential
except Exception:
    DefaultAzureCredential = None
# Prefer centralized helper
try:
    from azure_db import get_engine, list_odbc_drivers
except Exception:
    get_engine = None
    list_odbc_drivers = None


def print_available_drivers():
    drivers = pyodbc.drivers()
    print("Available ODBC drivers:", drivers)


def build_connection_url():
    driver = os.environ.get("AZURE_ODBC_DRIVER", "ODBC Driver 18 for SQL Server")
    auth = os.environ.get("AZURE_SQL_AUTH", "ActiveDirectoryInteractive")
    server = os.environ.get("AZURE_SQL_SERVER", "lmnp2024.database.windows.net")
    database = os.environ.get("AZURE_SQL_DATABASE", "MarketData")

    return URL.create(
        "mssql+pyodbc",
        host=server,
        database=database,
        query={
            "driver": driver,
            "authentication": auth,
            # recommended flags for Driver 18
            "Encrypt": "yes",
            "TrustServerCertificate": "no",
        },
    )


def test_connection(engine):
    max_retries = 5
    for attempt in range(max_retries):
        try:
            with engine.connect() as conn:
                conn.exec_driver_sql("SELECT 1")
            print("✓ Connected to Azure SQL successfully")
            return True
        except OperationalError as e:
            if attempt < max_retries - 1:
                print(
                    f"Connection failed (attempt {attempt + 1}/{max_retries}): {e}\nRetrying in 5 seconds..."
                )
                time.sleep(5)
            else:
                print("Failed to connect to the database after multiple attempts.")
                raise


def fetch_market_values(engine, top_n=None):
    query = """
    SELECT CAST(Date AS DATE) AS Date, Symbol, Closing, Volume
    FROM MarketValues
    ORDER BY Date DESC
    """
    if top_n:
        query = f"SELECT TOP {int(top_n)} CAST(Date AS DATE) AS Date, Symbol, Closing, Volume FROM MarketValues ORDER BY Date DESC"
    with engine.connect() as conn:
        df = pd.read_sql_query(query, conn)
    return df


def get_access_token():
    if DefaultAzureCredential is None:
        return None
    # Scope for Azure SQL
    scope = "https://database.windows.net/.default"
    cred = DefaultAzureCredential()
    token = cred.get_token(scope)
    return token.token


def main():
    # Prefer the centralized engine helper if available
    if list_odbc_drivers:
        print("Available ODBC drivers:", list_odbc_drivers())
    else:
        print_available_drivers()

    if get_engine is None:
        # Fallback to local behavior if helper not importable
        url = build_connection_url()
        # Try token-based auth first to avoid interactive timeouts
        access_token = get_access_token()
        connect_args = {}
        if access_token:
            # Token needs to be bytes per ODBC spec
            token_bytes = bytes(access_token, "utf-8")
            # attrs_before 1256 is SQL_COPT_SS_ACCESS_TOKEN for MSDN drivers
            connect_args = {"attrs_before": {1256: token_bytes}}

        engine = create_engine(url, connect_args=connect_args)
    else:
        engine = get_engine(prefer_token=True)

    test_connection(engine)

    # Try small fetch to validate
    df = fetch_market_values(engine, top_n=1000)
    print(f"Fetched {len(df)} rows from MarketValues")
    # Save a local snapshot for downstream analysis
    df.to_csv("data_from_azure_snapshot.csv", index=False)
    print("✓ Saved data_from_azure_snapshot.csv")


if __name__ == "__main__":
    main()

