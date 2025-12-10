"""Azure Pipeline Runner

Purpose:
  Connect to Azure SQL (MarketData DB), fetch market values, persist to local
  `data.csv`, then run a minimal validation of the dropout optimization
  protocol on this freshly pulled dataset.

Environment Assumptions:
  - Interactive AAD auth OR service principal env vars supported by
    `DefaultAzureCredential`.
  - Table: MarketValues(Date, Symbol, Closing, Volume)
  - Optional future table: MarketCaps(Date, Symbol, MarketCap) (not yet present)

Config via environment variables:
  PROTOCOL_LIMIT: int (row fetch limit, default None => full table; start with a
                    cap like 250000 for fast validation)
  PROTOCOL_BLOCK_SIZE: default 200
  PROTOCOL_NUM_BLOCKS: default 8
  PROTOCOL_DISTANCE: default 40
  PROTOCOL_QUALITY_METRIC: default 'avg_return'

Outputs:
  - data.csv (full or sampled dataset) used by optimizer
  - Console summary of parameter test results
  - dropout_optimization_results_extended.csv if full optimization invoked

Usage:
  python azure_run_protocol.py  # runs minimal single configuration validation
  FULL_OPT=1 python azure_run_protocol.py  # runs broader optimization grid

Notes:
  Market cap weighting will be inactive until `market_caps.csv` is added.
"""

import os
import time
import subprocess
import pandas as pd
from sqlalchemy import create_engine, URL
from sqlalchemy.exc import OperationalError
from azure.identity import DefaultAzureCredential, DeviceCodeCredential, InteractiveBrowserCredential, AzureCliCredential
try:
    import pyodbc  # noqa
    _PYODBC_AVAILABLE = True
except ImportError:
    _PYODBC_AVAILABLE = False

from optimize_dropout_strategy_safe import optimize_dropout_detection, test_dropout_parameters, load_market_caps

def detect_odbc_driver():
    """Return (ok, message). Checks presence of unixODBC and MS SQL driver.
    This does not guarantee connectivity but surfaces common missing pieces.
    """
    if not _PYODBC_AVAILABLE:
        return False, "Python module pyodbc not installed. Install via pip first."
    # Try to list available drivers through pyodbc (this validates unixODBC is functional)
    try:
        drivers = [d for d in pyodbc.drivers()]
        has_unixodbc = True  # If pyodbc.drivers() works, unixODBC is functional
    except Exception as e:
        drivers = []
        has_unixodbc = False
        return False, f"pyodbc.drivers() failed: {e}. unixODBC may not be properly installed."
    
    has_ms_driver = any('ODBC Driver 17 for SQL Server' in d or 'ODBC Driver 18 for SQL Server' in d for d in drivers)
    if has_ms_driver:
        return True, f"Detected unixODBC and MS drivers: {drivers}"
    
    return False, f"Missing Microsoft ODBC Driver 17/18 for SQL Server. Drivers found: {drivers}"

def connect_engine():
    print("Connecting to Azure SQL (MarketData)...")
    ok, msg = detect_odbc_driver()
    if not ok:
        print("ODBC driver check failed:")
        print("  " + msg)
        print("Installation guidance (Ubuntu/Debian):\n  sudo apt-get update && sudo apt-get install -y unixodbc unixodbc-dev msodbcsql17 mssql-tools")
        print("Skipping connection attempt.")
        return None
    
    # Detect which driver is available (prefer 18, fallback to 17)
    drivers = pyodbc.drivers()
    driver = None
    if 'ODBC Driver 18 for SQL Server' in drivers:
        driver = 'ODBC Driver 18 for SQL Server'
    elif 'ODBC Driver 17 for SQL Server' in drivers:
        driver = 'ODBC Driver 17 for SQL Server'
    
    print("\n" + "="*80)
    print("AZURE CLI AUTHENTICATION")
    print("="*80)
    print("Using Azure CLI credentials (from 'az login')")
    print("="*80 + "\n")
    
    # Use Azure CLI credential - works with personal accounts after 'az login'
    try:
        credential = AzureCliCredential()
        print("Obtaining access token...")
        token = credential.get_token("https://database.windows.net/.default")
        print("\nAuthentication successful!\n")
    except Exception as e:
        print(f"Azure CLI authentication failed: {e}")
        print("Please run 'az login' first and try again.")
        return None
    
    # Build connection string with access token
    connection_string = (
        f"DRIVER={{{driver}}};"
        f"SERVER=lmnp2024.database.windows.net;"
        f"DATABASE=MarketData;"
        f"Encrypt=yes;"
        f"TrustServerCertificate=no;"
        f"Connection Timeout=30;"
    )
    
    retries = 3
    for attempt in range(1, retries+1):
        try:
            conn = pyodbc.connect(
                connection_string,
                attrs_before={
                    1256: token.token.encode('utf-16-le')  # SQL_COPT_SS_ACCESS_TOKEN
                }
            )
            print("Azure SQL connection established.")
            
            # Create SQLAlchemy engine
            from sqlalchemy import create_engine
            from sqlalchemy.pool import StaticPool
            
            def creator():
                # Get a fresh token for each connection
                fresh_token = credential.get_token("https://database.windows.net/.default")
                return pyodbc.connect(
                    connection_string,
                    attrs_before={1256: fresh_token.token.encode('utf-16-le')}
                )
            
            engine = create_engine("mssql+pyodbc://", creator=creator, poolclass=StaticPool)
            return engine
        except Exception as e:
            if attempt == retries:
                print(f"Failed to connect after {retries} attempts.")
                print(f"Last error: {e}")
                return None
            print(f"Attempt {attempt} failed: {e}. Retrying in 5s...")
            time.sleep(5)

def fetch_market_values(engine, limit=None):
    if limit:
        print(f"Fetching TOP {limit} rows from MarketValues...")
        query = f"""
        SELECT TOP {limit} Date, Symbol, Closing, Volume
        FROM MarketValues
        ORDER BY Date, Symbol
        """
    else:
        print("Fetching ALL rows from MarketValues (may be large)...")
        query = """
        SELECT Date, Symbol, Closing, Volume
        FROM MarketValues
        ORDER BY Date, Symbol
        """
    start = time.time()
    with engine.connect() as conn:
        df = pd.read_sql_query(query, conn)
    print(f"Fetched {len(df)} records in {time.time()-start:.1f}s")
    print(f"Date range: {df['Date'].min()} → {df['Date'].max()}; Symbols: {df['Symbol'].nunique()}")
    return df

def persist_dataset(df, path='data.csv'):
    print(f"Writing dataset to {path}...")
    df.to_csv(path, index=False)
    print("Write complete.")

def run_minimal_protocol(data_file,
                         block_size=200,
                         num_blocks=8,
                         distance_threshold=40,
                         quality_metric='avg_return'):
    print("\nRunning minimal dropout protocol validation...")
    result, loss_df, acq_df = test_dropout_parameters(
        data_file,
        block_size=block_size,
        num_blocks=num_blocks,
        distance_threshold=distance_threshold,
        quality_metric=quality_metric,
        quality_threshold_percentile=80,  # Using previously selected percentile
        market_caps_df=load_market_caps()  # Will be None until file present
    )
    if result:
        print("\nValidation Summary:")
        for k, v in result.items():
            if isinstance(v, (int, float)):
                print(f"  {k}: {v}")
            else:
                print(f"  {k}: {v}")
        print(f"\nDropout events: {len(loss_df)}; Acquisition events: {len(acq_df)}")
        print("Sample dropout returns (first 10):", loss_df['Future_Return'].head(10).to_list())
    else:
        print("No results produced; check data integrity or parameters.")

def maybe_full_optimization(data_file):
    print("\nExecuting broader optimization sweep (reduced set) ...")
    summary = optimize_dropout_detection(
        data_file,
        block_sizes=[150, 175, 200],
        num_blocks_list=[8],  # Keep small for initial Azure validation
        distance_thresholds=[30, 35, 40],
        quality_metrics=['avg_return', 'median_return'],
        quality_threshold_percentiles=[70, 75, 80],
        forward_window=500
    )
    print("\nTop configs by Dropout_Avg_Return:")
    print(summary.nlargest(5, 'Dropout_Avg_Return')[['Block_Size','Distance_Threshold','Quality_Metric','Quality_Threshold_Percentile','Dropout_Avg_Return']])

def main():
    limit_env = os.getenv('PROTOCOL_LIMIT')
    limit = int(limit_env) if limit_env else None
    block_size = int(os.getenv('PROTOCOL_BLOCK_SIZE', 200))
    num_blocks = int(os.getenv('PROTOCOL_NUM_BLOCKS', 8))
    distance = int(os.getenv('PROTOCOL_DISTANCE', 40))
    quality_metric = os.getenv('PROTOCOL_QUALITY_METRIC', 'avg_return')
    full_opt = os.getenv('FULL_OPT') == '1'

def fetch_market_values_chunked(engine, chunk_size=250000, max_rows=None, output_path='data.csv'):
    """Stream MarketValues rows in chunks to CSV to reduce memory usage.
    Uses OFFSET/FETCH for pagination. Requires modern SQL Server.
    If max_rows provided, stops after reaching that count.
    """
    print(f"Chunked fetch: chunk_size={chunk_size} max_rows={max_rows or 'ALL'}")
    total_written = 0
    offset = 0
    mode = 'w'
    header = True
    start = time.time()
    with engine.connect() as conn:
        while True:
            remaining_limit_clause = f"FETCH NEXT {chunk_size} ROWS ONLY"
            query = f"""
            SELECT Date, Symbol, Closing, Volume
            FROM MarketValues
            ORDER BY Date, Symbol
            OFFSET {offset} ROWS {remaining_limit_clause}
            """
            chunk = pd.read_sql_query(query, conn)
            if chunk.empty:
                break
            chunk.to_csv(output_path, mode=mode, header=header, index=False)
            mode = 'a'; header = False
            written = len(chunk)
            total_written += written
            offset += written
            print(f"  Wrote {written} rows (total {total_written})")
            if max_rows and total_written >= max_rows:
                print("Reached max_rows limit; stopping chunked fetch.")
                break
            if written < chunk_size:
                # Last partial chunk
                break
    print(f"Chunked fetch complete: {total_written} rows in {time.time()-start:.1f}s → {output_path}")
    return total_written
    engine = connect_engine()
    df = fetch_market_values(engine, limit=limit)
    persist_dataset(df, 'data.csv')

    run_minimal_protocol('data.csv', block_size, num_blocks, distance, quality_metric)

    if full_opt:
        maybe_full_optimization('data.csv')

    print("\nAzure protocol run complete.")

if __name__ == '__main__':
    main()
