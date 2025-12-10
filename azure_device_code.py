"""Obtain an Azure AD access token via MSAL device-code flow and connect to Azure SQL.

Set these environment variables before running:
- `AZURE_CLIENT_ID` (required) - the application (client) id of a public client app
- `AZURE_TENANT_ID` (required) - your tenant id
- `AZURE_ODBC_DRIVER` (optional) - e.g. "ODBC Driver 18 for SQL Server"

This script prints a device-code message you can open in a browser on another
device to authenticate. After you complete the device code flow it will create
an engine using the obtained access token and run a small validation query.

Note: you still need the ODBC driver installed on this host (msodbcsql18).
"""
import os
import sys

try:
    import msal
except Exception:
    print("msal is required. Install with: pip install msal")
    raise

from azure_db import build_connection_url, create_engine_with_token
import pyodbc
import struct


def main():
    client_id = os.environ.get("AZURE_CLIENT_ID")
    tenant_id = os.environ.get("AZURE_TENANT_ID")
    if not client_id or not tenant_id:
        print("Please set AZURE_CLIENT_ID and AZURE_TENANT_ID in the environment.")
        sys.exit(1)

    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = msal.PublicClientApplication(client_id, authority=authority)
    flow = app.initiate_device_flow(scopes=["https://database.windows.net/.default"])
    if "message" not in flow:
        print("Failed to start device flow; response:", flow)
        sys.exit(1)

    print(flow["message"])  # instructs user to open URL and enter code
    print("Waiting for you to complete authentication in the browser...")
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        print("Failed to obtain token:", result)
        sys.exit(1)

    token = result["access_token"]
    print("Acquired access token; creating engine...")

    url = build_connection_url(auth=None)

    # First try using SQLAlchemy engine (original approach)
    try:
        engine = create_engine_with_token(url, token)
        with engine.connect() as conn:
            row = conn.exec_driver_sql("SELECT TOP 1 GETDATE()").fetchone()
            print("Server time:", row[0])
        print("Connection successful using token via SQLAlchemy engine.")
        return
    except Exception as e:
        print("Engine-based connection failed:", e)

    # Fallback: try direct pyodbc connection with attrs_before. This avoids
    # SQLAlchemy inferring extra connection options that can conflict with
    # Access Token usage.
    print("Trying direct pyodbc.connect() with access token (fallback)...")
    driver = os.environ.get("AZURE_ODBC_DRIVER", "ODBC Driver 18 for SQL Server")
    server = os.environ.get("AZURE_SQL_SERVER", "lmnp2024.database.windows.net")
    database = os.environ.get("AZURE_SQL_DATABASE", "MarketData")
    conn_str = (
        f"Driver={{{driver}}};"
        f"Server=tcp:{server},1433;"
        f"Database={database};"
        f"Encrypt=yes;TrustServerCertificate=no;"
    )

    # Try a couple of encodings/formats for the token expected by the driver
    attempts = []
    token_utf8 = token.encode("utf-8")
    attempts.append(token_utf8)
    # Some drivers/OS require UTF-16-LE encoding
    attempts.append(token.encode("utf-16-le"))
    # Some examples suggest prefixing with 4-byte length
    attempts.append(struct.pack("<I", len(token_utf8)) + token_utf8)
    attempts.append(struct.pack("<I", len(attempts[1])) + attempts[1])

    last_exc = None
    for tb in attempts:
        try:
            attrs = {1256: tb}
            cn = pyodbc.connect(conn_str, attrs_before=attrs)
            with cn:
                cur = cn.cursor()
                cur.execute("SELECT TOP 1 GETDATE()")
                row = cur.fetchone()
                print("Server time (pyodbc):", row[0])
            print("Connection successful using direct pyodbc with access token.")
            return
        except Exception as ex:
            last_exc = ex
            print("pyodbc attempt failed with token format, trying next...", ex)

    print("All pyodbc attempts failed. Last error:", last_exc)


if __name__ == "__main__":
    main()
