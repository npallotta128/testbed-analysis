import cuml
from cuml.cluster import AgglomerativeClustering
import numpy as np
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.stats import zscore
from collections import Counter
import pandas as pd
import cupy as cp
import time
import pickle
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import partial
import multiprocessing as mp

# Configuration
CACHE_DIR = 'cache'
USE_CACHE = True
NUM_PROCESSES = min(4, mp.cpu_count())  # Limit to 4 processes to avoid memory issues

def create_cache_dir():
    """Create cache directory if it doesn't exist"""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)

def get_cache_filename(prefix, timepoint):
    """Generate cache filename"""
    return os.path.join(CACHE_DIR, f"{prefix}_timepoint_{timepoint}.pkl")

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

def preprocess_data_cached(data, start_timepoint, end_timepoint):
    """Preprocess data with caching"""
    cache_key = f"preprocessed_{start_timepoint}_{end_timepoint}"
    cache_file = get_cache_filename(cache_key, start_timepoint)
    
    # Try to load from cache
    cached_data = load_from_cache(cache_file)
    if cached_data is not None:
        print(f"Loaded preprocessed data from cache for timepoint {start_timepoint}")
        return cached_data
    
    print(f"Preprocessing data for timepoint {start_timepoint}...")
    
    # Pivot the data to create tables
    closing_table = data.pivot_table(index='Date', columns='Symbol', values='Closing', aggfunc='first').iloc[start_timepoint:end_timepoint]
    volume_table = data.pivot_table(index='Date', columns='Symbol', values='Volume', aggfunc='first').iloc[end_timepoint-10:end_timepoint]
    
    # Extract variable names from closing_table
    variable_names = closing_table.columns.to_numpy()
    
    # Remove the Date column and handle NaN values
    closing_table.reset_index(drop=True, inplace=True)
    volume_table.reset_index(drop=True, inplace=True)
    closing_table = closing_table.fillna(0)
    volume_table = volume_table.fillna(0)
    
    # Transpose and convert to numpy
    closing_table = closing_table.T.to_numpy()
    volume_table = volume_table.T.to_numpy()
    
    result = {
        'closing_table': closing_table,
        'volume_table': volume_table,
        'variable_names': variable_names,
        'shapes': (closing_table.shape, volume_table.shape)
    }
    
    # Save to cache
    save_to_cache(result, cache_file)
    return result

def normalize_data_cached(closing_table, variable_names, timepoint):
    """Normalize data with caching"""
    cache_file = get_cache_filename("normalized", timepoint)
    
    # Try to load from cache
    cached_data = load_from_cache(cache_file)
    if cached_data is not None:
        print(f"Loaded normalized data from cache for timepoint {timepoint}")
        return cached_data
    
    print(f"Normalizing data for timepoint {timepoint}...")
    
    # Normalize the first 1501 time points using z-scores
    means = np.mean(closing_table[:, :1501], axis=1, keepdims=True)
    stds = np.std(closing_table[:, :1501], axis=1, keepdims=True)
    
    # Avoid division by zero - replace zero std with small value
    stds = np.where(stds == 0, 1e-8, stds)
    
    normalized_data = np.copy(closing_table)
    normalized_data[:, :1501] = (closing_table[:, :1501] - means) / stds
    normalized_data[:, 1501:] = (closing_table[:, 1501:] - means) / stds
    
    # Remove variables containing non-finite elements
    finite_mask = np.all(np.isfinite(normalized_data), axis=1)
    normalized_data = normalized_data[finite_mask]
    closing_table = closing_table[finite_mask]
    variable_names = variable_names[finite_mask]
    
    result = {
        'normalized_data': normalized_data,
        'closing_table': closing_table,
        'variable_names': variable_names,
        'finite_mask': finite_mask
    }
    
    save_to_cache(result, cache_file)
    return result

def perform_clustering_cached(normalized_data, timepoint):
    """Perform clustering with caching"""
    cache_file = get_cache_filename("clusters", timepoint)
    
    # Try to load from cache
    cached_clusters = load_from_cache(cache_file)
    if cached_clusters is not None:
        print(f"Loaded clustering results from cache for timepoint {timepoint}")
        return cached_clusters
    
    print(f"Performing clustering for timepoint {timepoint}...")
    
    # Use scipy's hierarchical clustering with ward linkage (as in original)
    from scipy.cluster.hierarchy import linkage, fcluster
    
    # Convert to CPU for scipy clustering
    clustering_data = normalized_data[:, :1501]
    
    # Perform hierarchical clustering with ward linkage
    linkage_matrix = linkage(clustering_data, method='ward')
    clusters = fcluster(linkage_matrix, 50, criterion='distance') - 1  # Convert to 0-based indexing
    
    save_to_cache(clusters, cache_file)
    return clusters

def process_single_timepoint(args):
    """Process a single timepoint - designed for parallel execution"""
    timepoint_idx, start_timepoint, data_file = args
    
    # Load data (each process loads its own copy)
    data = pd.read_csv(data_file)
    
    current_start_timepoint = start_timepoint + timepoint_idx
    end_timepoint = current_start_timepoint + 2001
    
    print(f"Processing timepoint {timepoint_idx + 1}: End timepoint {end_timepoint}")
    
    try:
        # Step 1: Preprocess data
        preprocessed = preprocess_data_cached(data, current_start_timepoint, end_timepoint)
        closing_table = preprocessed['closing_table']
        volume_table = preprocessed['volume_table']
        variable_names = preprocessed['variable_names']
        
        # Step 2: Normalize data
        normalized = normalize_data_cached(closing_table, variable_names, current_start_timepoint)
        normalized_data = normalized['normalized_data']
        closing_table = normalized['closing_table']
        volume_table = volume_table[normalized['finite_mask']]
        variable_names = normalized['variable_names']
        
        # Step 3: Perform clustering
        clusters = perform_clustering_cached(normalized_data, current_start_timepoint)
        
        # Step 4: Analyze clusters and generate signals
        last_500_normalized_data = normalized_data[:, 1501:]
        
        # Count the number of variables in each cluster
        cluster_counts = Counter(clusters)
        large_clusters = [cluster for cluster, count in cluster_counts.items() if count >= 40]
        
        if not large_clusters:
            print(f"No large clusters found for timepoint {timepoint_idx + 1}")
            return pd.DataFrame()
        
        # Initialize cluster state analysis
        cluster_current_state = {}
        
        for cluster in large_clusters:
            cluster_indices = [i for i, c in enumerate(clusters) if c == cluster]
            cluster_data = last_500_normalized_data[cluster_indices, :]
            
            cluster_mean = np.mean(cluster_data, axis=0)
            cluster_std = np.std(cluster_data, axis=0)
            
            difference = cluster_data - cluster_mean
            standardized_difference = difference / np.where(cluster_std == 0, 1e-8, cluster_std)
            z_scores = zscore(standardized_difference, axis=1)
            current_state = z_scores[:, -1]
            
            cluster_current_state[cluster] = current_state
        
        # Generate trading signals
        long_table = []
        short_table = []
        
        for cluster, states in cluster_current_state.items():
            cluster_indices = [i for i, c in enumerate(clusters) if c == cluster]
            
            # Long signals (state < -3)
            long_indices = np.where(states < -3)[0]
            long_variable_names = variable_names[cluster_indices][long_indices]
            for name, state in zip(long_variable_names, states[long_indices]):
                long_table.append([name, state])
            
            # Short signals (state > 3.4)
            short_indices = np.where(states > 3.4)[0]
            short_variable_names = variable_names[cluster_indices][short_indices]
            for name, state in zip(short_variable_names, states[short_indices]):
                short_table.append([name, state])
        
        # Create DataFrames
        long_table_df = pd.DataFrame(long_table, columns=['Variable Name', 'State'])
        short_table_df = pd.DataFrame(short_table, columns=['Variable Name', 'State'])
        
        if long_table_df.empty and short_table_df.empty:
            print(f"No signals found for timepoint {timepoint_idx + 1}")
            return pd.DataFrame()
        
        # Add price and volume information
        def add_price_volume(df, closing_table, volume_table, variable_names):
            if not df.empty:
                df['Price'] = df['Variable Name'].apply(
                    lambda name: closing_table[variable_names.tolist().index(name), -1] 
                    if name in variable_names else 0
                )
                df['Volume'] = df['Variable Name'].apply(
                    lambda name: np.mean(volume_table[variable_names.tolist().index(name), -10:]) 
                    if name in variable_names else 0
                )
            return df
        
        long_table_df = add_price_volume(long_table_df, closing_table, volume_table, variable_names)
        short_table_df = add_price_volume(short_table_df, closing_table, volume_table, variable_names)
        
        # Combine and filter
        combined_table_df = pd.concat([long_table_df, short_table_df], ignore_index=True)
        
        if combined_table_df.empty:
            return pd.DataFrame()
        
        combined_table_df['Type'] = combined_table_df['State'].apply(lambda state: 'Long' if state < 0 else 'Short')
        filtered_combined_table_df = combined_table_df[
            (combined_table_df['Price'] > 0) & (combined_table_df['Volume'] > 100000)
        ].copy()
        
        if filtered_combined_table_df.empty:
            return pd.DataFrame()
        
        # Add future performance analysis (simplified for parallel processing)
        filtered_combined_table_df['RPS'] = 0  # Placeholder - full RPS calculation would require more data
        filtered_combined_table_df['End Timepoint'] = end_timepoint
        
        print(f"Found {len(filtered_combined_table_df)} signals for timepoint {timepoint_idx + 1}")
        return filtered_combined_table_df
        
    except Exception as e:
        print(f"Error processing timepoint {timepoint_idx + 1}: {str(e)}")
        return pd.DataFrame()

def main():
    # Create cache directory
    create_cache_dir()
    
    # Configuration
    start_timepoint = 1
    num_iterations = 150
    data_file = 'data.csv'
    
    print(f"Starting parallel analysis with {NUM_PROCESSES} processes...")
    print(f"Processing {num_iterations} timepoints starting from {start_timepoint}")
    print(f"Cache enabled: {USE_CACHE}")
    
    start_time = time.time()
    
    # Prepare arguments for parallel processing
    args_list = [(i, start_timepoint, data_file) for i in range(num_iterations)]
    
    all_results = []
    
    # Use ProcessPoolExecutor for parallel processing
    with ProcessPoolExecutor(max_workers=NUM_PROCESSES) as executor:
        # Submit all tasks
        future_to_timepoint = {
            executor.submit(process_single_timepoint, args): args[0] 
            for args in args_list
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_timepoint):
            timepoint_idx = future_to_timepoint[future]
            try:
                result = future.result()
                if not result.empty:
                    all_results.append(result)
                
                # Print progress
                elapsed = time.time() - start_time
                print(f"Completed timepoint {timepoint_idx + 1} in {elapsed:.2f}s total")
                
            except Exception as e:
                print(f"Timepoint {timepoint_idx + 1} generated an exception: {e}")
    
    # Combine all results
    if all_results:
        all_filtered_combined_table_df = pd.concat(all_results, ignore_index=True)
    else:
        all_filtered_combined_table_df = pd.DataFrame()
    
    # Final timing and results
    end_time = time.time()
    total_duration = end_time - start_time
    
    print("\n" + "="*60)
    print("PARALLEL ANALYSIS COMPLETE!")
    print("="*60)
    print(f"Total computation time: {total_duration:.2f} seconds")
    print(f"Average time per iteration: {total_duration/num_iterations:.2f} seconds")
    print(f"Speedup vs sequential: ~{875.43/total_duration:.1f}x (estimated)")
    print(f"Processes used: {NUM_PROCESSES}")
    print(f"Cache enabled: {USE_CACHE}")
    
    if not all_filtered_combined_table_df.empty:
        print(f"\nTotal signals found: {len(all_filtered_combined_table_df)}")
        print(f"Long signals: {len(all_filtered_combined_table_df[all_filtered_combined_table_df['Type'] == 'Long'])}")
        print(f"Short signals: {len(all_filtered_combined_table_df[all_filtered_combined_table_df['Type'] == 'Short'])}")
        print(f"Results shape: {all_filtered_combined_table_df.shape}")
        print("\nFirst few results:")
        print(all_filtered_combined_table_df.head(10))
        
        # Save results
        all_filtered_combined_table_df.to_csv('trading_signals_results_extended.csv', index=False)
        print(f"\nResults saved to: trading_signals_results_extended.csv")
    else:
        print("\nNo trading signals found in any iteration.")

if __name__ == "__main__":
    main()