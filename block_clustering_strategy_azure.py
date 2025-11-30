import numpy as np
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.stats import zscore
from collections import Counter, defaultdict
import pandas as pd
import time
import pickle
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing as mp
from sqlalchemy import create_engine, URL
from sqlalchemy.exc import OperationalError
from azure.identity import DefaultAzureCredential

# Configuration
CACHE_DIR = 'cache'
USE_CACHE = True
NUM_PROCESSES = min(6, mp.cpu_count())
BLOCK_SIZE = 125  # First 125 timepoints per block
DISTANCE_THRESHOLD = 50
NUM_BLOCKS = 10  # This will give us 1250 timepoints total (125 * 10)

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

def create_cache_dir():
    """Create cache directory if it doesn't exist"""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)

def get_cache_filename(prefix, block_id):
    """Generate cache filename for block-based processing"""
    return os.path.join(CACHE_DIR, f"{prefix}_block_{block_id}_azure.pkl")

def save_to_cache(data, filename):
    """Save data to cache"""
    if USE_CACHE:
        with open(filename, 'wb') as f:
            pickle.dump(data, f)

def load_from_cache(filename):
    """Load data from cache"""
    if USE_CACHE and os.path.exists(filename):
        with open(filename, 'rb') as f:
            return pickle.load(f)
    return None

def load_and_prepare_data_from_azure(engine, start_idx, block_size):
    """Load and prepare data from Azure database for a specific block of timepoints"""
    print(f"Loading data from Azure for timepoints {start_idx} to {start_idx + block_size - 1}...")
    
    # Query to get data with row numbers for pagination
    query = f"""
    WITH OrderedData AS (
        SELECT 
            Date, 
            Symbol, 
            Closing, 
            Volume,
            ROW_NUMBER() OVER (PARTITION BY Symbol ORDER BY Date) as RowNum
        FROM MarketValues
    )
    SELECT Date, Symbol, Closing, Volume
    FROM OrderedData
    WHERE RowNum BETWEEN {start_idx + 1} AND {start_idx + block_size}
    ORDER BY Date, Symbol
    """
    
    # Load data from SQL query
    with engine.connect() as conn:
        data = pd.read_sql_query(query, conn)
    
    if len(data) == 0:
        raise ValueError(f"No data retrieved for timepoints {start_idx} to {start_idx + block_size - 1}")
    
    # Pivot to get closing prices with Date as index and Symbol as columns
    closing_table = data.pivot_table(
        index='Date', 
        columns='Symbol', 
        values='Closing', 
        aggfunc='first'
    )
    
    # Extract securities (symbols) and timepoints
    securities = closing_table.columns.to_numpy()
    timepoints = closing_table.index.to_numpy()
    
    # Handle missing values
    closing_table = closing_table.fillna(method='ffill').fillna(method='bfill').fillna(0)
    
    # Convert to numpy array (securities x timepoints)
    price_matrix = closing_table.T.to_numpy()
    
    print(f"Data loaded - Securities: {len(securities)}, Timepoints: {len(timepoints)}")
    
    return price_matrix, securities, timepoints

def perform_zscore_normalization(price_matrix, securities):
    """Perform z-score normalization on the price matrix"""
    print("Performing z-score normalization...")
    
    # Calculate z-scores for each security across timepoints
    normalized_matrix = np.zeros_like(price_matrix, dtype=float)
    
    for i, security in enumerate(securities):
        security_prices = price_matrix[i, :]
        
        # Remove zeros for calculation (if any)
        non_zero_prices = security_prices[security_prices > 0]
        
        if len(non_zero_prices) > 1:
            # Calculate z-scores
            mean_price = np.mean(non_zero_prices)
            std_price = np.std(non_zero_prices)
            
            if std_price > 0:
                normalized_matrix[i, :] = (security_prices - mean_price) / std_price
            else:
                normalized_matrix[i, :] = 0
        else:
            normalized_matrix[i, :] = 0
    
    # Remove securities with all zeros or infinite values
    finite_mask = np.all(np.isfinite(normalized_matrix), axis=1)
    clean_matrix = normalized_matrix[finite_mask]
    clean_securities = securities[finite_mask]
    
    print(f"Normalization complete - Clean securities: {len(clean_securities)}")
    
    return clean_matrix, clean_securities

def perform_hierarchical_clustering(normalized_matrix, securities, distance_threshold=50):
    """Perform hierarchical clustering on normalized price data"""
    print(f"Performing hierarchical clustering with distance threshold {distance_threshold}...")
    
    # Perform hierarchical clustering with Ward linkage
    linkage_matrix = linkage(normalized_matrix, method='ward')
    
    # Get cluster labels
    cluster_labels = fcluster(linkage_matrix, distance_threshold, criterion='distance') - 1
    
    # Create cluster mapping
    cluster_dict = defaultdict(list)
    for security_idx, cluster_id in enumerate(cluster_labels):
        cluster_dict[cluster_id].append(securities[security_idx])
    
    # Convert to regular dict and filter small clusters
    clusters = {}
    for cluster_id, security_list in cluster_dict.items():
        if len(security_list) >= 5:  # Minimum cluster size
            clusters[cluster_id] = security_list
    
    print(f"Clustering complete - Found {len(clusters)} clusters with ≥5 securities")
    
    # Print cluster summary
    for cluster_id, securities_in_cluster in clusters.items():
        print(f"  Cluster {cluster_id}: {len(securities_in_cluster)} securities")
    
    return clusters, cluster_labels

def process_single_block_azure(args):
    """Process a single block of timepoints from Azure"""
    block_id, start_timepoint, engine = args
    
    cache_file = get_cache_filename("block_clusters", block_id)
    
    # Try to load from cache
    cached_result = load_from_cache(cache_file)
    if cached_result is not None:
        print(f"Loaded block {block_id} results from cache")
        return cached_result
    
    try:
        print(f"\n{'='*60}")
        print(f"PROCESSING BLOCK {block_id}")
        print(f"Timepoints: {start_timepoint} to {start_timepoint + BLOCK_SIZE - 1}")
        print(f"{'='*60}")
        
        # Step 1: Load and prepare data from Azure
        price_matrix, securities, timepoints = load_and_prepare_data_from_azure(
            engine, start_timepoint, BLOCK_SIZE
        )
        
        # Step 2: Perform z-score normalization
        normalized_matrix, clean_securities = perform_zscore_normalization(
            price_matrix, securities
        )
        
        # Step 3: Perform hierarchical clustering
        clusters, cluster_labels = perform_hierarchical_clustering(
            normalized_matrix, clean_securities, DISTANCE_THRESHOLD
        )
        
        # Prepare result
        result = {
            'block_id': block_id,
            'start_timepoint': start_timepoint,
            'end_timepoint': start_timepoint + BLOCK_SIZE - 1,
            'num_securities': len(clean_securities),
            'num_clusters': len(clusters),
            'clusters': clusters,
            'cluster_labels': cluster_labels,
            'securities': clean_securities,
            'timepoints': timepoints
        }
        
        # Save to cache
        save_to_cache(result, cache_file)
        
        print(f"Block {block_id} completed successfully")
        return result
        
    except Exception as e:
        print(f"Error processing block {block_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

def main_azure():
    """Main function for Azure-based block clustering"""
    
    create_cache_dir()
    
    print(f"{'='*80}")
    print("AZURE BLOCK-BASED CLUSTERING STRATEGY")
    print(f"{'='*80}")
    print(f"Block size: {BLOCK_SIZE} timepoints")
    print(f"Number of blocks: {NUM_BLOCKS}")
    print(f"Total timepoints: {NUM_BLOCKS * BLOCK_SIZE}")
    print(f"Distance threshold: {DISTANCE_THRESHOLD}")
    print(f"Cache enabled: {USE_CACHE}")
    
    # Connect to Azure database
    engine = connect_to_azure_database()
    
    start_time = time.time()
    start_timepoint = 0
    
    # Process blocks sequentially (since they all need the same engine)
    all_results = []
    
    for block_id in range(NUM_BLOCKS):
        block_start = start_timepoint + (block_id * BLOCK_SIZE)
        args = (block_id, block_start, engine)
        
        result = process_single_block_azure(args)
        if result is not None:
            all_results.append(result)
        
        elapsed = time.time() - start_time
        print(f"Completed block {block_id} - Total time: {elapsed:.2f}s")
    
    # Sort results by block_id
    all_results.sort(key=lambda x: x['block_id'] if x else float('inf'))
    
    # Save results summary
    print("\nSaving results...")
    block_summary = []
    for result in all_results:
        if result is None:
            continue
            
        block_summary.append({
            'Block_ID': result['block_id'],
            'Start_Timepoint': result['start_timepoint'],
            'End_Timepoint': result['end_timepoint'],
            'Num_Securities': result['num_securities'],
            'Num_Clusters': result['num_clusters'],
            'Avg_Cluster_Size': np.mean([len(securities) for securities in result['clusters'].values()]) if result['clusters'] else 0
        })
    
    block_df = pd.DataFrame(block_summary)
    block_df.to_csv('azure_block_clustering_summary.csv', index=False)
    print(f"Block summary saved to: azure_block_clustering_summary.csv")
    
    # Final summary
    end_time = time.time()
    total_duration = end_time - start_time
    
    print(f"\n{'='*80}")
    print("AZURE BLOCK-BASED CLUSTERING COMPLETE!")
    print(f"{'='*80}")
    print(f"Total execution time: {total_duration:.2f} seconds")
    print(f"Blocks processed: {len(all_results)}")
    print(f"Average time per block: {total_duration/len(all_results):.2f} seconds")
    
    return all_results, engine

if __name__ == "__main__":
    all_results, engine = main_azure()
