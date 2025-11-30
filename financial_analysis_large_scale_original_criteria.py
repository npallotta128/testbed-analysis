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
import gc
import psutil

# Configuration for large-scale analysis - keeping original cluster criteria
D_DRIVE_PATH = '/mnt/d/testbed_analysis'
CACHE_DIR = os.path.join(D_DRIVE_PATH, 'cache')
RESULTS_DIR = os.path.join(D_DRIVE_PATH, 'results')
USE_CACHE = True
NUM_PROCESSES = min(6, mp.cpu_count())  # Conservative for stability
CHUNK_SIZE = 15  # Smaller chunks for better memory management

def create_directories():
    """Create necessary directories on D drive"""
    for directory in [D_DRIVE_PATH, CACHE_DIR, RESULTS_DIR]:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"Created directory: {directory}")

def get_memory_usage():
    """Get current memory usage"""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024  # MB

def log_memory_usage(stage):
    """Log memory usage at different stages"""
    memory_mb = get_memory_usage()
    print(f"Memory usage at {stage}: {memory_mb:.1f} MB")

def get_cache_filename(prefix, timepoint):
    """Generate cache filename on D drive"""
    return os.path.join(CACHE_DIR, f"{prefix}_timepoint_{timepoint}.pkl")

def get_results_filename(chunk_id):
    """Generate results filename on D drive"""
    return os.path.join(RESULTS_DIR, f"signals_chunk_{chunk_id}.csv")

def save_to_cache(data, filename):
    """Save data to cache with memory cleanup"""
    if USE_CACHE:
        try:
            with open(filename, 'wb') as f:
                pickle.dump(data, f)
        except Exception as e:
            print(f"Warning: Could not save to cache {filename}: {e}")

def load_from_cache(filename):
    """Load data from cache"""
    if USE_CACHE and os.path.exists(filename):
        try:
            with open(filename, 'rb') as f:
                return pickle.load(f)
        except Exception as e:
            print(f"Warning: Could not load from cache {filename}: {e}")
    return None

def preprocess_data_cached(data, start_timepoint, end_timepoint):
    """Preprocess data with caching - ORIGINAL METHOD PRESERVED"""
    cache_key = f"preprocessed_{start_timepoint}_{end_timepoint}"
    cache_file = get_cache_filename(cache_key, start_timepoint)
    
    # Try to load from cache
    cached_data = load_from_cache(cache_file)
    if cached_data is not None:
        print(f"Loaded preprocessed data from cache for timepoint {start_timepoint}")
        return cached_data
    
    print(f"Preprocessing data for timepoint {start_timepoint}...")
    
    # Pivot the data to create tables - ORIGINAL METHOD
    closing_table = data.pivot_table(index='Date', columns='Symbol', values='Closing', aggfunc='first').iloc[start_timepoint:end_timepoint]
    volume_table = data.pivot_table(index='Date', columns='Symbol', values='Volume', aggfunc='first').iloc[end_timepoint-10:end_timepoint]
    
    # Extract variable names from closing_table
    variable_names = closing_table.columns.to_numpy()
    
    # Remove the Date column and handle NaN values - ORIGINAL METHOD
    closing_table.reset_index(drop=True, inplace=True)
    volume_table.reset_index(drop=True, inplace=True)
    closing_table = closing_table.fillna(0)
    volume_table = volume_table.fillna(0)
    
    # Transpose and convert to numpy - ORIGINAL METHOD
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
    """Normalize data with caching - ORIGINAL METHOD PRESERVED"""
    cache_file = get_cache_filename("normalized", timepoint)
    
    # Try to load from cache
    cached_data = load_from_cache(cache_file)
    if cached_data is not None:
        print(f"Loaded normalized data from cache for timepoint {timepoint}")
        return cached_data
    
    print(f"Normalizing data for timepoint {timepoint}...")
    
    # Normalize the first 1501 time points using z-scores - ORIGINAL METHOD
    means = np.mean(closing_table[:, :1501], axis=1, keepdims=True)
    stds = np.std(closing_table[:, :1501], axis=1, keepdims=True)
    
    # Avoid division by zero - replace zero std with small value
    stds = np.where(stds == 0, 1e-8, stds)
    
    normalized_data = np.copy(closing_table)
    normalized_data[:, :1501] = (closing_table[:, :1501] - means) / stds
    normalized_data[:, 1501:] = (closing_table[:, 1501:] - means) / stds
    
    # Remove variables containing non-finite elements - ORIGINAL METHOD
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
    """Perform clustering with caching - ORIGINAL METHOD PRESERVED"""
    cache_file = get_cache_filename("clusters", timepoint)
    
    # Try to load from cache
    cached_clusters = load_from_cache(cache_file)
    if cached_clusters is not None:
        print(f"Loaded clustering results from cache for timepoint {timepoint}")
        return cached_clusters
    
    print(f"Performing clustering for timepoint {timepoint}...")
    
    # Use scipy's hierarchical clustering with ward linkage (ORIGINAL METHOD)
    clustering_data = normalized_data[:, :1501]
    
    # Perform hierarchical clustering with ward linkage - ORIGINAL DISTANCE THRESHOLD: 50
    linkage_matrix = linkage(clustering_data, method='ward')
    clusters = fcluster(linkage_matrix, 50, criterion='distance') - 1  # ORIGINAL: distance=50, 0-based indexing
    
    save_to_cache(clusters, cache_file)
    return clusters

def process_single_timepoint(args):
    """Process a single timepoint - ORIGINAL LOGIC WITH ORIGINAL CLUSTER CRITERIA"""
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
        
        # Step 4: Analyze clusters and generate signals - ORIGINAL CRITERIA PRESERVED
        last_500_normalized_data = normalized_data[:, 1501:]
        
        # Count the number of variables in each cluster - ORIGINAL CRITERIA
        cluster_counts = Counter(clusters)
        large_clusters = [cluster for cluster, count in cluster_counts.items() if count >= 40]  # ORIGINAL: >= 40
        
        if not large_clusters:
            print(f"No large clusters found for timepoint {timepoint_idx + 1}")
            return pd.DataFrame()
        
        # Initialize cluster state analysis - ORIGINAL METHOD
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
        
        # Generate trading signals - ORIGINAL THRESHOLDS PRESERVED
        long_table = []
        short_table = []
        
        for cluster, states in cluster_current_state.items():
            cluster_indices = [i for i, c in enumerate(clusters) if c == cluster]
            
            # Long signals (state < -3) - ORIGINAL THRESHOLD
            long_indices = np.where(states < -3)[0]
            long_variable_names = variable_names[cluster_indices][long_indices]
            for name, state in zip(long_variable_names, states[long_indices]):
                long_table.append([name, state])
            
            # Short signals (state > 3.4) - ORIGINAL THRESHOLD
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
        
        # Add price and volume information - ORIGINAL METHOD
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
        
        # Combine and filter - ORIGINAL CRITERIA
        combined_table_df = pd.concat([long_table_df, short_table_df], ignore_index=True)
        
        if combined_table_df.empty:
            return pd.DataFrame()
        
        combined_table_df['Type'] = combined_table_df['State'].apply(lambda state: 'Long' if state < 0 else 'Short')
        filtered_combined_table_df = combined_table_df[
            (combined_table_df['Price'] > 0) & (combined_table_df['Volume'] > 100000)  # ORIGINAL VOLUME THRESHOLD
        ].copy()
        
        if filtered_combined_table_df.empty:
            return pd.DataFrame()
        
        # Add future performance analysis
        filtered_combined_table_df['RPS'] = 0  # Placeholder
        filtered_combined_table_df['End Timepoint'] = end_timepoint
        filtered_combined_table_df['Start Timepoint'] = current_start_timepoint
        filtered_combined_table_df['Timepoint Index'] = timepoint_idx + 1
        
        print(f"Found {len(filtered_combined_table_df)} signals for timepoint {timepoint_idx + 1}")
        return filtered_combined_table_df
        
    except Exception as e:
        print(f"Error processing timepoint {timepoint_idx + 1}: {str(e)}")
        return pd.DataFrame()
    finally:
        # Clean up memory
        del data
        gc.collect()

def process_chunk(chunk_id, chunk_timepoints, start_timepoint, data_file):
    """Process a chunk of timepoints"""
    print(f"\n--- Processing chunk {chunk_id + 1} (timepoints {chunk_timepoints[0]+1}-{chunk_timepoints[-1]+1}) ---")
    
    # Prepare arguments for this chunk
    args_list = [(i, start_timepoint, data_file) for i in chunk_timepoints]
    
    chunk_results = []
    
    # Use ProcessPoolExecutor for parallel processing within chunk
    with ProcessPoolExecutor(max_workers=NUM_PROCESSES) as executor:
        future_to_timepoint = {
            executor.submit(process_single_timepoint, args): args[0] 
            for args in args_list
        }
        
        for future in as_completed(future_to_timepoint):
            timepoint_idx = future_to_timepoint[future]
            try:
                result = future.result()
                if not result.empty:
                    chunk_results.append(result)
                print(f"Completed timepoint {timepoint_idx + 1} in chunk {chunk_id + 1}")
            except Exception as e:
                print(f"Timepoint {timepoint_idx + 1} in chunk {chunk_id + 1} failed: {e}")
    
    # Combine chunk results and save
    if chunk_results:
        chunk_df = pd.concat(chunk_results, ignore_index=True)
        chunk_filename = get_results_filename(chunk_id)
        chunk_df.to_csv(chunk_filename, index=False)
        print(f"Saved chunk {chunk_id + 1} results to {chunk_filename}")
        print(f"Chunk {chunk_id + 1}: {len(chunk_df)} signals found")
        return len(chunk_df)
    else:
        print(f"No signals found in chunk {chunk_id + 1}")
        return 0

def main():
    """Main function for large-scale analysis with ORIGINAL clustering criteria"""
    print("="*80)
    print("LARGE-SCALE FINANCIAL ANALYSIS - ORIGINAL CLUSTER CRITERIA")
    print("="*80)
    
    # Create directories
    create_directories()
    
    # Configuration - start from timepoint where we're more likely to find >= 40 clusters
    start_timepoint = 200  # Start from original successful timepoint
    num_iterations = 150
    data_file = 'data.csv'
    
    print(f"Configuration:")
    print(f"  Start timepoint: {start_timepoint}")
    print(f"  Number of iterations: {num_iterations}")
    print(f"  Processes per chunk: {NUM_PROCESSES}")
    print(f"  Chunk size: {CHUNK_SIZE}")
    print(f"  ORIGINAL CLUSTERING PARAMETERS PRESERVED:")
    print(f"    - Cluster distance threshold: 50 (ORIGINAL)")
    print(f"    - Minimum cluster size: >= 40 variables (ORIGINAL)")
    print(f"    - Clustering method: ward linkage (ORIGINAL)")
    print(f"  ORIGINAL SIGNAL PARAMETERS PRESERVED:")
    print(f"    - Long signal threshold: < -3 (ORIGINAL)")
    print(f"    - Short signal threshold: > 3.4 (ORIGINAL)")
    print(f"    - Volume threshold: > 100,000 (ORIGINAL)")
    print(f"  Cache directory: {CACHE_DIR}")
    print(f"  Results directory: {RESULTS_DIR}")
    print(f"  Cache enabled: {USE_CACHE}")
    
    log_memory_usage("startup")
    
    start_time = time.time()
    
    # Split into chunks for memory management
    all_timepoints = list(range(num_iterations))
    chunks = [all_timepoints[i:i + CHUNK_SIZE] for i in range(0, len(all_timepoints), CHUNK_SIZE)]
    
    print(f"\nProcessing {len(chunks)} chunks of {CHUNK_SIZE} timepoints each")
    
    total_signals = 0
    
    # Process each chunk
    for chunk_id, chunk_timepoints in enumerate(chunks):
        chunk_start_time = time.time()
        
        signals_in_chunk = process_chunk(chunk_id, chunk_timepoints, start_timepoint, data_file)
        total_signals += signals_in_chunk
        
        chunk_duration = time.time() - chunk_start_time
        elapsed_total = time.time() - start_time
        
        print(f"Chunk {chunk_id + 1} completed in {chunk_duration:.2f}s")
        print(f"Total elapsed: {elapsed_total:.2f}s")
        
        if chunk_id > 0:
            remaining_chunks = len(chunks) - chunk_id - 1
            avg_chunk_time = elapsed_total / (chunk_id + 1)
            estimated_remaining = avg_chunk_time * remaining_chunks
            print(f"Estimated remaining: {estimated_remaining:.2f}s ({estimated_remaining/3600:.2f} hours)")
        
        # Force garbage collection between chunks
        gc.collect()
        log_memory_usage(f"after chunk {chunk_id + 1}")
    
    # Combine all chunk results
    print("\nCombining all chunk results...")
    all_results = []
    
    for chunk_id in range(len(chunks)):
        chunk_filename = get_results_filename(chunk_id)
        if os.path.exists(chunk_filename):
            chunk_df = pd.read_csv(chunk_filename)
            all_results.append(chunk_df)
            print(f"Loaded chunk {chunk_id + 1}: {len(chunk_df)} signals")
    
    if all_results:
        final_results = pd.concat(all_results, ignore_index=True)
        final_filename = os.path.join(RESULTS_DIR, 'trading_signals_150_timepoints_original_criteria.csv')
        final_results.to_csv(final_filename, index=False)
        print(f"Final results saved to: {final_filename}")
    else:
        final_results = pd.DataFrame()
    
    # Final timing and results
    end_time = time.time()
    total_duration = end_time - start_time
    
    print("\n" + "="*80)
    print("LARGE-SCALE ANALYSIS COMPLETE!")
    print("="*80)
    print(f"Total computation time: {total_duration:.2f} seconds ({total_duration/3600:.2f} hours)")
    print(f"Average time per timepoint: {total_duration/num_iterations:.2f} seconds")
    print(f"Processes used: {NUM_PROCESSES}")
    print(f"Cache enabled: {USE_CACHE}")
    print(f"Chunks processed: {len(chunks)}")
    
    if not final_results.empty:
        print(f"\nFINAL RESULTS:")
        print(f"Total signals found: {len(final_results)}")
        print(f"Long signals: {len(final_results[final_results['Type'] == 'Long'])}")
        print(f"Short signals: {len(final_results[final_results['Type'] == 'Short'])}")
        print(f"Results shape: {final_results.shape}")
        print(f"Timepoints covered: {final_results['Timepoint Index'].min()} to {final_results['Timepoint Index'].max()}")
        
        print(f"\nData stored on D drive:")
        print(f"  Results: {RESULTS_DIR}")
        print(f"  Cache: {CACHE_DIR}")
        
        # Sample results
        print("\nFirst 10 results:")
        sample_cols = ['Variable Name', 'Type', 'State', 'Price', 'Timepoint Index', 'End Timepoint']
        print(final_results.head(10)[sample_cols].to_string(index=False))
        
        print(f"\nReady for return calculation and Monte Carlo simulations!")
    else:
        print("\nNo trading signals found in any iteration.")
    
    log_memory_usage("completion")

if __name__ == "__main__":
    main()