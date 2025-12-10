
import numpy as np
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.stats import zscore
from collections import Counter
import pandas as pd
from sqlalchemy import create_engine
import pyodbc
from azure.identity import DefaultAzureCredential
from sqlalchemy.engine import URL

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
engine = create_engine(connection_string)

# Query the database for Date, Symbol, Closing, Volume
query = """
SELECT Date, Symbol, Closing, Volume
FROM MarketValues
"""

# Load data from SQL query
with engine.connect() as conn:
    data = pd.read_sql_query(query, conn)