
# Create a connection to the Azure database using passwordless sign-in
credential = DefaultAzureCredential()
connection_string = URL.create(
    "mssql+pyodbc",
    username="",
    password="",
    host="lmnp2024.database.windows.net",
    database="MarketData",
    query={
        "driver": "ODBC Driver 17 for SQL Server",
        "authentication": "ActiveDirectoryInteractive"
    }
)

max_retries = 5
for attempt in range(max_retries):
    try:
        engine = create_engine(connection_string)
        # Test connection
        with engine.connect() as conn:
            pass
        break
    except OperationalError as e:
        if attempt < max_retries - 1:
            print(f"Connection failed (attempt {attempt + 1}/{max_retries}), retrying in 5 seconds...")
            time.sleep(5)
        else:
            print("Failed to connect to the database after multiple attempts.")
            raise

# Query the database for Date, Symbol, Closing, Volume
query = """
SELECT Date, Symbol, Closing, Volume
FROM MarketValues
"""

# Load data from SQL query
with engine.connect() as conn:
    data = pd.read_sql_query(query, conn)

# Pivot the data to create the first table with Closing values
closing_table = data.pivot_table(index='Date', columns='Symbol', values='Closing', aggfunc='first')# Azure Connection Configuration

