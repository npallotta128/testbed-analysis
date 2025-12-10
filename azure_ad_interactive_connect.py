"""
Azure SQL Connection using Active Directory Interactive

This script uses ODBC Driver 18 for SQL Server with
Authentication=ActiveDirectoryInteractive to prompt an interactive
Azure sign-in. On success, it fetches a small snapshot from MarketValues
and writes data to data_from_azure_snapshot.csv.

Configure via environment variables:
- AZURE_SQL_SERVER (default: lmnp2024.database.windows.net)
- AZURE_SQL_DATABASE (default: MarketData)
- AZURE_ODBC_DRIVER (default: ODBC Driver 18 for SQL Server)

Prereqs:
- msodbcsql18 installed and visible to pyodbc
- LD_LIBRARY_PATH, ODBCSYSINI, ODBCINI set appropriately
"""

import os
import sys
import time
import pyodbc
import pandas as pd

SERVER = os.environ.get("AZURE_SQL_SERVER", "lmnp2024.database.windows.net")
DATABASE = os.environ.get("AZURE_SQL_DATABASE", "MarketData")
DRIVER = os.environ.get("AZURE_ODBC_DRIVER", "ODBC Driver 18 for SQL Server")

# Build a DSN-less connection string for Active Directory Interactive
conn_str = (
    f"Driver={{{DRIVER}}};"
    f"Server=tcp:{SERVER},1433;"
    f"Database={DATABASE};"
    f"Authentication=ActiveDirectoryInteractive;"
    f"Encrypt=yes;TrustServerCertificate=no;"
    f"Connection Timeout=30;"
)

print("Using ODBC Driver:", DRIVER)
print("Connecting to:", f"{SERVER}/{DATABASE}")

# Retry logic for transient issues
max_retries = 3
for attempt in range(1, max_retries + 1):
    try:
        cn = pyodbc.connect(conn_str)
        print("✓ Connected via ActiveDirectoryInteractive")
        break
    except pyodbc.Error as e:
        if attempt < max_retries:
            print(f"Connection failed (attempt {attempt}/{max_retries}): {e}\nRetrying in 5 seconds...")
            time.sleep(5)
        else:
            print("Failed to connect after multiple attempts.")
            raise

# Simple validation query
with cn:
    cur = cn.cursor()
    cur.execute("SELECT TOP 1 GETDATE()")
    dt = cur.fetchone()[0]
    print("Server time:", dt)

# Fetch small snapshot
query = (
    "SELECT TOP 1000 CAST(Date AS DATE) AS Date, Symbol, Closing, Volume "
    "FROM MarketValues ORDER BY Date DESC"
)
print("Fetching snapshot from MarketValues...")
df = pd.read_sql(query, cn)
print(f"Fetched {len(df)} rows")

out = "data_from_azure_snapshot.csv"
df.to_csv(out, index=False)
print(f"✓ Saved {out}")
