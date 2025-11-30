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

# Configuration for large-scale analysis - optimized
D_DRIVE_PATH = '/mnt/d/testbed_analysis'
CACHE_DIR = os.path.join(D_DRIVE_PATH, 'cache')
RESULTS_DIR = os.path.join(D_DRIVE_PATH, 'results')
USE_CACHE = True
NUM_PROCESSES = min(6, mp.cpu_count())  # Conservative for stability
CHUNK_SIZE = 20  # Smaller chunks for better memory management

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

def preprocess_data_optimized(data, start_timepoint, end_timepoint):
    """Optimized preprocessing with better memory management"""
    cache_key = f"preprocessed_{start_timepoint}_{end_timepoint}"
    cache_file = get_cache_filename(cache_key, start_timepoint)
    
    # Try to load from cache
    cached_data = load_from_cache(cache_file)
    if cached_data is not None:
        return cached_data
    
    print(f"Preprocessing data for timepoint {start_timepoint}...")
    
    # More efficient data slicing
    # Calculate approximate row indices based on timepoint
    approx_start_row = start_timepoint * 80  # Rough estimate
    approx_end_row = (end_timepoint + 20) * 80
    
    # Load only the data we need
    data_chunk = data.iloc[max(0, approx_start_row):min(len(data), approx_end_row)]
    
    # Create pivot tables
    closing_pivot = data_chunk.pivot_table(
        index='Date', columns='Symbol', values='Closing', aggfunc='first'
    )
    
    volume_pivot = data_chunk.pivot_table(
        index='Date', columns='Symbol', values='Volume', aggfunc='first'
    )
    
    # Extract the specific timepoint ranges
    if start_timepoint < len(closing_pivot) and end_timepoint <= len(closing_pivot):
        closing_table = closing_pivot.iloc[start_timepoint:end_timepoint]
        volume_table = volume_pivot.iloc[max(0, end_timepoint-10):end_timepoint]
    else:
        print(f"Warning: Not enough data for timepoint {start_timepoint}")
        return None
    
    # Get variable names
    variable_names = closing_table.columns.to_numpy()
    
    # Process data
    closing_table = closing_table.fillna(0).T.to_numpy()
    volume_table = volume_table.fillna(0).T.to_numpy()
    
    result = {
        'closing_table': closing_table,
        'volume_table': volume_table,
        'variable_names': variable_names,
        'shapes': (closing_table.shape, volume_table.shape)
    }
    
    # Clean up
    del data_chunk, closing_pivot, volume_pivot
    gc.collect()
    
    save_to_cache(result, cache_file)
    return result

def normalize_data_optimized(closing_table, variable_names, timepoint):
    """Optimized normalization"""
    cache_file = get_cache_filename("normalized", timepoint)
    
    cached_data = load_from_cache(cache_file)
    if cached_data is not None:
        return cached_data
    
    print(f"Normalizing data for timepoint {timepoint}...")
    
    # Normalize using z-scores
    means = np.mean(closing_table[:, :1501], axis=1, keepdims=True)
    stds = np.std(closing_table[:, :1501], axis=1, keepdims=True)
    stds = np.where(stds == 0, 1e-8, stds)
    
    normalized_data = np.copy(closing_table)
    normalized_data[:, :1501] = (closing_table[:, :1501] - means) / stds
    normalized_data[:, 1501:] = (closing_table[:, 1501:] - means) / stds
    
    # Remove non-finite elements
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

def perform_clustering_optimized(normalized_data, timepoint, min_cluster_size=30):
    """Optimized clustering with adaptive cluster size"""
    cache_file = get_cache_filename("clusters", timepoint)
    
    cached_clusters = load_from_cache(cache_file)
    if cached_clusters is not None:
        return cached_clusters
    
    print(f"Performing clustering for timepoint {timepoint}...")
    
    # Use hierarchical clustering
    clustering_data = normalized_data[:, :1501]
    
    # Adaptive distance threshold based on data size
    n_vars = len(clustering_data)
    if n_vars < 1000:
        distance_threshold = 30
    elif n_vars < 5000:
        distance_threshold = 40
    else:
        distance_threshold = 50
    
    linkage_matrix = linkage(clustering_data, method='ward')
    clusters = fcluster(linkage_matrix, distance_threshold, criterion='distance') - 1
    
    # Clean up
    del linkage_matrix, clustering_data
    gc.collect()
    
    save_to_cache(clusters, cache_file)
    return clusters

def process_single_timepoint_optimized(args):
    """Optimized single timepoint processing"""
    timepoint_idx, start_timepoint, data_file, min_cluster_size = args
    
    try:
        print(f"Processing timepoint {timepoint_idx + 1}...")
        
        # Load only necessary data
        data = pd.read_csv(data_file)
        
        current_start_timepoint = start_timepoint + timepoint_idx
        end_timepoint = current_start_timepoint + 2001
        
        # Preprocessing
        preprocessed = preprocess_data_optimized(data, current_start_timepoint, end_timepoint)
        if preprocessed is None:
            return pd.DataFrame()
        
        closing_table = preprocessed['closing_table']
        volume_table = preprocessed['volume_table']
        variable_names = preprocessed['variable_names']
        
        # Check if we have enough variables
        if len(variable_names) < 100:
            print(f"Timepoint {timepoint_idx + 1}: Not enough variables ({len(variable_names)})")
            return pd.DataFrame()
        
        # Normalization
        normalized = normalize_data_optimized(closing_table, variable_names, current_start_timepoint)
        normalized_data = normalized['normalized_data']
        closing_table = normalized['closing_table']
        volume_table = volume_table[normalized['finite_mask']]
        variable_names = normalized['variable_names']
        
        # Clustering
        clusters = perform_clustering_optimized(normalized_data, current_start_timepoint, min_cluster_size)
        
        # Analyze clusters
        last_500_normalized_data = normalized_data[:, 1501:]
        cluster_counts = Counter(clusters)
        
        # Use adaptive cluster size threshold
        large_clusters = [cluster for cluster, count in cluster_counts.items() if count >= min_cluster_size]
        
        if not large_clusters:
            print(f"Timepoint {timepoint_idx + 1}: No large clusters (min size: {min_cluster_size})")
            return pd.DataFrame()
        
        # Generate trading signals
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
        
        # Create signal tables
        long_table = []
        short_table = []
        
        for cluster, states in cluster_current_state.items():
            cluster_indices = [i for i, c in enumerate(clusters) if c == cluster]
            
            # Long signals (state < -3)
            long_indices = np.where(states < -3)[0]
            long_variable_names = variable_names[cluster_indices][long_indices]
            for name, state in zip(long_variable_names, states[long_indices]):
                long_table.append([name, state, cluster])
            
            # Short signals (state > 3.4)
            short_indices = np.where(states > 3.4)[0]
            short_variable_names = variable_names[cluster_indices][short_indices]
            for name, state in zip(short_variable_names, states[short_indices]):
                short_table.append([name, state, cluster])
        
        # Create DataFrames
        long_table_df = pd.DataFrame(long_table, columns=['Variable Name', 'State', 'Cluster'])
        short_table_df = pd.DataFrame(short_table, columns=['Variable Name', 'State', 'Cluster'])
        
        if long_table_df.empty and short_table_df.empty:
            print(f"Timepoint {timepoint_idx + 1}: No trading signals found")
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
        
        # Filter by price and volume
        filtered_combined_table_df = combined_table_df[
            (combined_table_df['Price'] > 0) & (combined_table_df['Volume'] > 50000)  # Lower volume threshold
        ].copy()
        
        if filtered_combined_table_df.empty:
            return pd.DataFrame()
        
        # Add metadata
        filtered_combined_table_df['RPS'] = 0
        filtered_combined_table_df['End Timepoint'] = end_timepoint
        filtered_combined_table_df['Start Timepoint'] = current_start_timepoint
        filtered_combined_table_df['Timepoint Index'] = timepoint_idx + 1
        
        # Clean up memory
        del data, normalized_data, closing_table, volume_table, clusters
        gc.collect()
        
        print(f"Timepoint {timepoint_idx + 1}: Found {len(filtered_combined_table_df)} signals")
        return filtered_combined_table_df
        
    except Exception as e:
        print(f"Error processing timepoint {timepoint_idx + 1}: {str(e)}")
        return pd.DataFrame()

def main():
    """Main function for optimized large-scale analysis"""
    print("="*80)
    print("OPTIMIZED LARGE-SCALE FINANCIAL ANALYSIS")
    print("="*80)
    
    # Create directories
    create_directories()
    
    # Configuration - start from a later timepoint where more stocks are available
    start_timepoint = 100  # Start later to ensure sufficient stock universe
    num_iterations = 150
    data_file = 'data.csv'
    min_cluster_size = 25  # Reduced minimum cluster size
    
    print(f"Configuration:")
    print(f"  Start timepoint: {start_timepoint}")
    print(f"  Number of iterations: {num_iterations}")
    print(f"  Processes per chunk: {NUM_PROCESSES}")
    print(f"  Chunk size: {CHUNK_SIZE}")
    print(f"  Minimum cluster size: {min_cluster_size}")
    print(f"  Cache directory: {CACHE_DIR}")
    print(f"  Results directory: {RESULTS_DIR}")
    
    start_time = time.time()
    
    # Split into chunks
    all_timepoints = list(range(num_iterations))
    chunks = [all_timepoints[i:i + CHUNK_SIZE] for i in range(0, len(all_timepoints), CHUNK_SIZE)]
    
    print(f"\nProcessing {len(chunks)} chunks")
    
    total_signals = 0
    
    # Process each chunk
    for chunk_id, chunk_timepoints in enumerate(chunks):
        print(f"\n--- Processing chunk {chunk_id + 1}/{len(chunks)} ---")
        
        # Prepare arguments for this chunk
        args_list = [(i, start_timepoint, data_file, min_cluster_size) for i in chunk_timepoints]
        
        chunk_results = []
        
        # Process chunk in parallel
        with ProcessPoolExecutor(max_workers=NUM_PROCESSES) as executor:
            future_to_timepoint = {
                executor.submit(process_single_timepoint_optimized, args): args[0] 
                for args in args_list
            }
            
            for future in as_completed(future_to_timepoint):
                timepoint_idx = future_to_timepoint[future]
                try:
                    result = future.result()
                    if not result.empty:
                        chunk_results.append(result)
                except Exception as e:
                    print(f"Timepoint {timepoint_idx + 1} failed: {e}")
        
        # Save chunk results
        if chunk_results:
            chunk_df = pd.concat(chunk_results, ignore_index=True)
            chunk_filename = get_results_filename(chunk_id)
            chunk_df.to_csv(chunk_filename, index=False)
            total_signals += len(chunk_df)
            print(f"Chunk {chunk_id + 1}: {len(chunk_df)} signals saved")
        else:
            print(f"Chunk {chunk_id + 1}: No signals found")
        
        # Progress update
        elapsed = time.time() - start_time
        progress = (chunk_id + 1) / len(chunks)
        estimated_total = elapsed / progress
        remaining = estimated_total - elapsed
        
        print(f"Progress: {progress:.1%}, Elapsed: {elapsed:.1f}s, Estimated remaining: {remaining:.1f}s")
        
        # Memory cleanup
        gc.collect()
    
    # Combine all results
    print("\nCombining all results...")
    all_results = []
    
    for chunk_id in range(len(chunks)):
        chunk_filename = get_results_filename(chunk_id)
        if os.path.exists(chunk_filename):
            chunk_df = pd.read_csv(chunk_filename)
            all_results.append(chunk_df)
    
    if all_results:
        final_results = pd.concat(all_results, ignore_index=True)
        final_filename = os.path.join(RESULTS_DIR, 'trading_signals_150_timepoints_optimized.csv')
        final_results.to_csv(final_filename, index=False)
        
        print(f"\n" + "="*80)
        print("ANALYSIS COMPLETE!")
        print("="*80)
        print(f"Total signals: {len(final_results)}")
        print(f"Long signals: {len(final_results[final_results['Type'] == 'Long'])}")
        print(f"Short signals: {len(final_results[final_results['Type'] == 'Short'])}")
        print(f"Timepoints covered: {final_results['Timepoint Index'].min()} to {final_results['Timepoint Index'].max()}")
        print(f"Results saved to: {final_filename}")
        
        # Show sample results
        sample_results = final_results.head(10)[['Variable Name', 'Type', 'State', 'Price', 'Timepoint Index']]
        print("\nSample results:")
        print(sample_results.to_string(index=False))
    else:
        print("No results found")
    
    total_time = time.time() - start_time
    print(f"\nTotal processing time: {total_time:.1f} seconds ({total_time/3600:.2f} hours)")

if __name__ == "__main__":
    main()