import numpy as np
import pandas as pd
import time
from sqlalchemy import create_engine, URL
from sqlalchemy.exc import OperationalError
from azure.identity import DefaultAzureCredential

def connect_to_azure_database():
    """Establish connection to Azure SQL database using passwordless authentication"""
    print("Connecting to Azure database...")
    
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
            print("Successfully connected to Azure database")
            break
        except OperationalError as e:
            if attempt < max_retries - 1:
                print(f"Connection failed (attempt {attempt + 1}/{max_retries}), retrying in 5 seconds...")
                time.sleep(5)
            else:
                print("Failed to connect to the database after multiple attempts.")
                raise
    
    return engine

def fetch_market_data(engine, limit=None):
    """Fetch market data from Azure database"""
    print("Fetching market data from database...")
    
    # Query the database for Date, Symbol, Closing, Volume
    if limit:
        query = f"""
        SELECT TOP {limit} Date, Symbol, Closing, Volume
        FROM MarketValues
        ORDER BY Date, Symbol
        """
    else:
        query = """
        SELECT Date, Symbol, Closing, Volume
        FROM MarketValues
        ORDER BY Date, Symbol
        """
    
    # Load data from SQL query
    with engine.connect() as conn:
        data = pd.read_sql_query(query, conn)
    
    print(f"Fetched {len(data)} records")
    print(f"Date range: {data['Date'].min()} to {data['Date'].max()}")
    print(f"Unique symbols: {data['Symbol'].nunique()}")
    
    return data

def get_database_statistics(engine):
    """Get basic statistics about the database"""
    print("\n" + "="*60)
    print("DATABASE STATISTICS")
    print("="*60)
    
    queries = {
        'Total Records': "SELECT COUNT(*) as count FROM MarketValues",
        'Unique Symbols': "SELECT COUNT(DISTINCT Symbol) as count FROM MarketValues",
        'Date Range': "SELECT MIN(Date) as min_date, MAX(Date) as max_date FROM MarketValues",
        'Records per Symbol': """
            SELECT AVG(record_count) as avg_records
            FROM (
                SELECT Symbol, COUNT(*) as record_count
                FROM MarketValues
                GROUP BY Symbol
            ) as symbol_counts
        """
    }
    
    with engine.connect() as conn:
        for stat_name, query in queries.items():
            result = pd.read_sql_query(query, conn)
            print(f"\n{stat_name}:")
            print(result)

def analyze_market_data(data):
    """Perform basic analysis on market data"""
    print("\n" + "="*60)
    print("MARKET DATA ANALYSIS")
    print("="*60)
    
    # Create pivot table with Closing values
    closing_table = data.pivot_table(index='Date', columns='Symbol', values='Closing', aggfunc='first')
    
    print(f"\nClosing table shape: {closing_table.shape}")
    print(f"Number of dates: {len(closing_table)}")
    print(f"Number of symbols: {len(closing_table.columns)}")
    
    # Check for missing data
    missing_pct = (closing_table.isna().sum() / len(closing_table) * 100).describe()
    print(f"\nMissing data statistics (% missing per symbol):")
    print(missing_pct)
    
    # Calculate basic statistics
    print(f"\nPrice statistics:")
    print(closing_table.describe())
    
    # Volume analysis
    volume_table = data.pivot_table(index='Date', columns='Symbol', values='Volume', aggfunc='first')
    print(f"\nVolume statistics:")
    print(volume_table.describe())
    
    return closing_table, volume_table

def fetch_symbol_metadata(engine):
    """Fetch additional metadata about symbols if available"""
    print("\n" + "="*60)
    print("CHECKING FOR METADATA TABLES")
    print("="*60)
    
    # Check what tables are available
    tables_query = """
    SELECT TABLE_NAME 
    FROM INFORMATION_SCHEMA.TABLES 
    WHERE TABLE_TYPE = 'BASE TABLE'
    """
    
    with engine.connect() as conn:
        tables = pd.read_sql_query(tables_query, conn)
        print("\nAvailable tables:")
        print(tables)
        
        # If there are metadata tables, query them
        for table_name in tables['TABLE_NAME']:
            if table_name != 'MarketValues':
                print(f"\nSampling from {table_name}:")
                try:
                    sample_query = f"SELECT TOP 5 * FROM {table_name}"
                    sample = pd.read_sql_query(sample_query, conn)
                    print(sample)
                except Exception as e:
                    print(f"Could not query {table_name}: {e}")
    
    return tables

def main():
    """Main function to connect and analyze Azure database"""
    
    print("="*80)
    print("AZURE DATABASE ANALYSIS")
    print("="*80)
    
    # Connect to database
    engine = connect_to_azure_database()
    
    # Get database statistics
    get_database_statistics(engine)
    
    # Check for metadata tables
    tables = fetch_symbol_metadata(engine)
    
    # Fetch sample data (first 10000 records for quick analysis)
    print("\n" + "="*60)
    print("FETCHING SAMPLE DATA")
    print("="*60)
    sample_data = fetch_market_data(engine, limit=10000)
    
    # Analyze sample
    closing_table, volume_table = analyze_market_data(sample_data)
    
    # Save sample to CSV for inspection
    sample_data.to_csv('azure_sample_data.csv', index=False)
    print("\nSample data saved to: azure_sample_data.csv")
    
    print("\n" + "="*60)
    print("Would you like to:")
    print("1. Fetch all data and save to CSV")
    print("2. Run clustering analysis directly from database")
    print("3. Export specific date range or symbols")
    print("="*60)
    
    return engine, sample_data

if __name__ == "__main__":
    engine, sample_data = main()
