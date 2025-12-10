"""Reusable Azure SQL (MSSQL) connection helper

Provides a `get_engine()` helper that prefers Azure AD token-based auth
via `DefaultAzureCredential`, and falls back to ODBC interactive auth when
necessary. Also includes diagnostic helpers and a small CLI demo for testing.

Usage examples:
  - Token-based (service principal / managed identity): set
      `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET` (or run
      where Managed Identity is available). Then run this script to test.
  - Interactive: ensure an ODBC driver is installed and `AZURE_ODBC_DRIVER`
    points to it (e.g. `ODBC Driver 18 for SQL Server`). The script will
    fall back to interactive login if token auth fails.

This file intentionally keeps external dependencies minimal and mirrors the
approach used elsewhere in the repo.
"""
import os
import time
from typing import Optional

import pyodbc
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError

try:
    from azure.identity import DefaultAzureCredential
except Exception:
    DefaultAzureCredential = None


ODBC_TOKEN_ATTR = 1256  # SQL_COPT_SS_ACCESS_TOKEN


def list_odbc_drivers():
    """Return a list of available ODBC drivers visible to pyodbc."""
    return pyodbc.drivers()


def build_connection_url(auth: Optional[str] = None) -> URL:
    """Build a SQLAlchemy URL for Azure SQL.

    If `auth` is provided it will be set as the `authentication` query
    parameter (e.g. `ActiveDirectoryInteractive`). For token-based auth,
    pass `auth=None`.
    """
    driver = os.environ.get("AZURE_ODBC_DRIVER", "ODBC Driver 18 for SQL Server")
    server = os.environ.get("AZURE_SQL_SERVER", "lmnp2024.database.windows.net")
    database = os.environ.get("AZURE_SQL_DATABASE", "MarketData")

    query = {
        "driver": driver,
        "Encrypt": "yes",
        "TrustServerCertificate": "no",
    }
    if auth:
        query["authentication"] = auth

    return URL.create(
        "mssql+pyodbc",
        host=server,
        database=database,
        query=query,
    )


def get_access_token(scope: str = "https://database.windows.net/.default") -> Optional[str]:
    """Try to obtain an Azure AD access token using DefaultAzureCredential.

    Returns the token string on success or `None` on failure or if
    `azure.identity` is not available.
    """
    if DefaultAzureCredential is None:
        return None
    try:
        cred = DefaultAzureCredential()
        token = cred.get_token(scope)
        return token.token
    except Exception:
        return None


def create_engine_with_token(url: URL, access_token: str):
    """Create a SQLAlchemy engine that uses an access token for auth.

    The access token must be passed to pyodbc via `attrs_before` using the
    driver-specific attribute `SQL_COPT_SS_ACCESS_TOKEN` (1256).
    """
    token_bytes = access_token.encode("utf-8")
    connect_args = {"attrs_before": {ODBC_TOKEN_ATTR: token_bytes}}
    return create_engine(url, connect_args=connect_args)


def create_engine_interactive(url: URL):
    """Create an engine that uses ODBC interactive authentication.

    This expects `authentication=ActiveDirectoryInteractive` to exist in the
    URL's query parameters.
    """
    return create_engine(url)


def test_connection(engine, max_retries: int = 3):
    for attempt in range(1, max_retries + 1):
        try:
            with engine.connect() as conn:
                conn.exec_driver_sql("SELECT 1")
            return True
        except OperationalError as e:
            if attempt < max_retries:
                delay = 2 * attempt
                print(f"Connection attempt {attempt} failed: {e}; retrying in {delay}s...")
                time.sleep(delay)
            else:
                print("Connection failed after retries.")
                raise


def get_engine(prefer_token: bool = True, max_retries: int = 3, backoff_factor: float = 2.0, verbose: bool = True):
    """Return a SQLAlchemy engine ready to use.

    Flow:
      1. If `prefer_token` is True, attempt to obtain an Azure AD access token
         via `DefaultAzureCredential` and use token-based auth.
      2. If token fetch fails, fall back to ODBC interactive auth.

    Use environment variables to override server, database, driver.
    """
    # Build token-less URL first (token auth doesn't require `authentication`)
    url_no_auth = build_connection_url(auth=None)

    # Try token-based authentication first
    if prefer_token:
        token = get_access_token()
        if token:
            if verbose:
                print("Attempting Azure AD token-based authentication...")
            try:
                engine = create_engine_with_token(url_no_auth, token)
                test_connection(engine, max_retries=max_retries)
                if verbose:
                    print("✓ Token-based auth succeeded")
                return engine
            except Exception as e:
                if verbose:
                    print(f"Token-based auth failed: {e}")
                # Fall through to interactive

    # Fallback to interactive ODBC auth
    if verbose:
        print("Falling back to ODBC interactive authentication...")
    url_interactive = build_connection_url(auth="ActiveDirectoryInteractive")
    drivers = list_odbc_drivers()
    if not drivers:
        raise RuntimeError(
            "No ODBC drivers found. Install msodbcsql and set AZURE_ODBC_DRIVER."
        )

    # Create engine and attempt connection with retries/backoff
    engine = create_engine_interactive(url_interactive)
    try:
        test_connection(engine, max_retries=max_retries)
    except Exception as e:
        raise RuntimeError(
            "Interactive ODBC authentication failed. Check driver installation, environment variables, and whether interactive login is possible on this host."
        ) from e
    return engine


if __name__ == "__main__":
    # Simple CLI demo: list drivers, create engine, fetch a small snapshot
    print("ODBC drivers visible:", list_odbc_drivers())
    try:
        eng = get_engine(prefer_token=True)
        print("✓ Obtained engine; fetching snapshot...")
        import pandas as pd

        query = (
            "SELECT TOP 1000 CAST(Date AS DATE) AS Date, Symbol, Closing, Volume "
            "FROM MarketValues ORDER BY Date DESC"
        )
        with eng.connect() as conn:
            df = pd.read_sql_query(query, conn)
        out = "data_from_azure_snapshot.csv"
        df.to_csv(out, index=False)
        print(f"✓ Fetched {len(df)} rows and saved to {out}")
    except Exception as e:
        print("Connection or query failed:", e)
