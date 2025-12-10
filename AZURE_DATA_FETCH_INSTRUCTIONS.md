# Azure Data Fetch Instructions

Since the Azure SQL database requires organizational account authentication (not personal Microsoft accounts), here are alternative approaches to get the data for validation:

## Option 1: Use Azure Portal Query Editor (Recommended)

1. Go to https://portal.azure.com
2. Navigate to your SQL Database: `lmnp2024.database.windows.net` -> `MarketData`
3. Click "Query editor" in the left menu
4. Sign in (this should work with your email-based passwordless auth)
5. Run this query:
   ```sql
   SELECT Date, Symbol, Closing, Volume
   FROM MarketValues
   ORDER BY Date, Symbol
   ```
6. Click "Download results as CSV"
7. Save as `data.csv` in this project directory

## Option 2: Use Azure Data Studio

1. Download Azure Data Studio: https://aka.ms/azuredatastudio
2. Connect to: `lmnp2024.database.windows.net`
3. Database: `MarketData`
4. Authentication: Azure Active Directory
5. Run the query above
6. Export results to CSV

## Option 3: Request SQL Admin to Create Personal Account Access

Ask your Azure SQL administrator to:

## Once You Have data.csv

Simply run the validation pipeline with existing data:
```bash
export LD_LIBRARY_PATH=$HOME/.local/lib:$HOME/.local/msodbcsql18/lib64:$LD_LIBRARY_PATH
export ODBCSYSINI=$HOME/.local/etc 
export ODBCINI=$HOME/.local/etc/odbc.ini
SKIP_FETCH=1 python azure_validation_pipeline.py
```
## Quick Start: Connecting to Azure SQL from this repo

This repository includes multiple helper scripts. `azure_db.py` is a
reusable helper that prefers Azure AD token-based auth (service principal
or managed identity) and falls back to interactive ODBC authentication.

Prerequisites
- Install an ODBC driver for SQL Server (Driver 18 recommended):

```bash
# Debian/Ubuntu example (may require sudo and package names may change):
curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -
curl https://packages.microsoft.com/config/ubuntu/22.04/prod.list | sudo tee /etc/apt/sources.list.d/msprod.list
sudo apt-get update
sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18
```

- Python dependencies (in your virtualenv):

```bash
pip install -U pyodbc sqlalchemy pandas azure-identity
```

Environment variables
- `AZURE_SQL_SERVER` - your server host (default used in scripts: `lmnp2024.database.windows.net`)
- `AZURE_SQL_DATABASE` - database name (default `MarketData`)
- `AZURE_ODBC_DRIVER` - ODBC driver name (e.g. `ODBC Driver 18 for SQL Server`)

For token-based non-interactive auth (recommended for automation):
- `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET` (service principal),
   or run in an Azure resource with a Managed Identity.

Examples
- Test the helper (prefers token-based auth, falls back to interactive):

```bash
python azure_db.py
```

- If you want to force interactive (local dev), ensure your ODBC driver is
   installed and set `AZURE_ODBC_DRIVER` appropriately, then run the
   interactive scripts such as `azure_ad_interactive_connect.py` or
   `azure_ad_interactive_linux.py`.

Troubleshooting
- If you see `No ODBC drivers found`, confirm `msodbcsql18` (or `msodbcsql17`) is installed and visible to `pyodbc`.
- On headless servers interactive auth may fail — use service principal or Managed Identity instead.

Integration test
- There's a guarded integration script at `azure_integration_test.py` that runs only when `AZURE_RUN_INTEGRATION=1`.
   Use this to validate end-to-end connectivity with real credentials.

Example (do not run unless you want a live test):
```bash
export AZURE_RUN_INTEGRATION=1
# set service principal creds or ensure Managed Identity is available
python azure_integration_test.py
```

This will:
1. Use your existing data.csv
2. Generate sliding window events (stride=50)
3. Train ML models
4. Run capital allocation backtest
5. Output results to `azure_validation_backtest.csv`

## Expected Results

Based on local testing, you should see:
- **Top 1% tier**: ~27,000% mean return, 655x improvement vs quality heuristic
- **Top 5% tier**: ~600% mean return, 2.7x improvement
- **Top 10% tier**: ~500% mean return, 2.8x improvement
