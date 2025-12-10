"""
Azure SQL Connection (Linux) using Active Directory Interactive + ODBC Driver 17

This script prompts Azure AD interactive sign-in via ODBC Driver 17 and
fetches a small snapshot from MarketValues.

Env vars (optional):
- AZURE_SQL_SERVER (default: lmnp2024.database.windows.net)
- AZURE_SQL_DATABASE (default: MarketData)
- AZURE_ODBC_DRIVER (default: ODBC Driver 17 for SQL Server)

Prereqs (Linux):
- msodbcsql17 installed and visible to pyodbc
- LD_LIBRARY_PATH, ODBCSYSINI, ODBCINI configured if installed under $HOME/.local
"""

import os
import time
import pyodbc
import pandas as pd

SERVER = os.environ.get("AZURE_SQL_SERVER", "lmnp2024.database.windows.net")
DATABASE = os.environ.get("AZURE_SQL_DATABASE", "MarketData")
DRIVER = os.environ.get("AZURE_ODBC_DRIVER", "ODBC Driver 17 for SQL Server")

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

max_retries = 3
for attempt in range(1, max_retries + 1):
    try:
        cn = pyodbc.connect(conn_str)
        print("✓ Connected via ActiveDirectoryInteractive (Driver 17)")
        break
    except pyodbc.Error as e:
        if attempt < max_retries:
            print(f"Connection failed (attempt {attempt}/{max_retries}): {e}\nRetrying in 5 seconds...")
            time.sleep(5)
        else:
            print("Failed to connect after multiple attempts.")
            raise

with cn:
    cur = cn.cursor()
    cur.execute("SELECT TOP 1 GETDATE()")
    dt = cur.fetchone()[0]
    print("Server time:", dt)

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
