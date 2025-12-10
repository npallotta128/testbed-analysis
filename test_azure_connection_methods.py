"""Test different Azure SQL authentication methods"""
import os
import sys
import pyodbc

# Set up ODBC environment
os.environ['LD_LIBRARY_PATH'] = f"{os.path.expanduser('~')}/.local/lib:{os.path.expanduser('~')}/.local/msodbcsql18/lib64"
os.environ['ODBCSYSINI'] = f"{os.path.expanduser('~')}/.local/etc"
os.environ['ODBCINI'] = f"{os.path.expanduser('~')}/.local/etc/odbc.ini"

server = "lmnp2024.database.windows.net"
database = "MarketData"
driver = "ODBC Driver 18 for SQL Server"

print("Testing Azure SQL Connection Methods")
print("=" * 80)

# Method 1: Try Azure CLI authentication (what c6cpy might use)
print("\n1. Testing Azure CLI Authentication...")
try:
    from azure.identity import AzureCliCredential
    credential = AzureCliCredential()
    token = credential.get_token("https://database.windows.net/.default")
    
    conn_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"Encrypt=yes;"
        f"TrustServerCertificate=no;"
    )
    
    conn = pyodbc.connect(
        conn_str,
        attrs_before={1256: token.token.encode('utf-16-le')}
    )
    print("✓ Azure CLI authentication WORKS!")
    print("  This means you're logged in via 'az login' command")
    conn.close()
    sys.exit(0)
except Exception as e:
    print(f"✗ Azure CLI auth failed: {e}")

# Method 2: Try DefaultAzureCredential (tries multiple methods)
print("\n2. Testing DefaultAzureCredential (tries multiple methods)...")
try:
    from azure.identity import DefaultAzureCredential
    credential = DefaultAzureCredential()
    token = credential.get_token("https://database.windows.net/.default")
    
    conn_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"Encrypt=yes;"
        f"TrustServerCertificate=no;"
    )
    
    conn = pyodbc.connect(
        conn_str,
        attrs_before={1256: token.token.encode('utf-16-le')}
    )
    print("✓ DefaultAzureCredential WORKS!")
    conn.close()
    sys.exit(0)
except Exception as e:
    print(f"✗ DefaultAzureCredential failed: {e}")

# Check if Azure CLI is installed and logged in
print("\n3. Checking Azure CLI status...")
import subprocess
try:
    result = subprocess.run(['az', 'account', 'show'], capture_output=True, text=True, timeout=5)
    if result.returncode == 0:
        print("✓ Azure CLI is installed and you're logged in!")
        print("  Account info:")
        import json
        account = json.loads(result.stdout)
        print(f"    User: {account.get('user', {}).get('name', 'unknown')}")
        print(f"    Subscription: {account.get('name', 'unknown')}")
    else:
        print("✗ Azure CLI not logged in. Run: az login")
except FileNotFoundError:
    print("✗ Azure CLI not installed")
except Exception as e:
    print(f"✗ Error checking Azure CLI: {e}")

print("\n" + "=" * 80)
print("RECOMMENDATION:")
print("If c6cpy works, it likely uses Azure CLI authentication.")
print("Try running: az login")
print("Then re-run this script to test.")
