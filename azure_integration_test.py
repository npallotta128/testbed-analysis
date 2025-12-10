"""Guarded integration test for Azure SQL using real credentials.

This script will only run when `AZURE_RUN_INTEGRATION=1` is set in the
environment. It expects either:
- Service principal creds (set `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET`),
  or
- An environment where Managed Identity is available.

Running this script will attempt a live connection and fetch a small
snapshot from `MarketValues`. Do not check real credentials into the repo.
"""
import os
import sys

if os.environ.get("AZURE_RUN_INTEGRATION") != "1":
    print("Integration test skipped. Set AZURE_RUN_INTEGRATION=1 to run.")
    sys.exit(0)

from azure_db import get_engine


def main():
    engine = get_engine(prefer_token=True, verbose=True)
    import pandas as pd

    query = (
        "SELECT TOP 10 CAST(Date AS DATE) AS Date, Symbol, Closing, Volume "
        "FROM MarketValues ORDER BY Date DESC"
    )
    with engine.connect() as conn:
        df = pd.read_sql_query(query, conn)
    print(f"Fetched {len(df)} rows")


if __name__ == "__main__":
    main()
