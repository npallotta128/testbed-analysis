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

# Configuration for robust large-scale analysis
D_DRIVE_PATH = '/mnt/d/testbed_analysis'
CACHE_DIR = os.path.join(D_DRIVE_PATH, 'cache')
RESULTS_DIR = os.path.join(D_DRIVE_PATH, 'results')
INDIVIDUAL_RESULTS_DIR = os.path.join(D_DRIVE_PATH, 'individual_results')
USE_CACHE = True
NUM_PROCESSES = 4  # More conservative to prevent interruptions
SAVE_EVERY_TIMEPOINT = True  # Save after each timepoint

def create_directories():
    """Create necessary directories on D drive"""
    for directory in [D_DRIVE_PATH, CACHE_DIR, RESULTS_DIR, INDIVIDUAL_RESULTS_DIR]:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"Created directory: {directory}")

def get_cache_filename(prefix, timepoint):
    """Generate cache filename on D drive"""
    return os.path.join(CACHE_DIR, f"{prefix}_timepoint_{timepoint}.pkl")

def get_individual_results_filename(timepoint_idx):
    """Generate individual results filename"""
    return os.path.join(INDIVIDUAL_RESULTS_DIR, f"timepoint_{timepoint_idx}.csv")

def save_to_cache(data, filename):
    """Save data to cache"""
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
    
    cached_data = load_from_cache(cache_file)
    if cached_data is not None:
        return cached_data
    
    # ORIGINAL METHOD - Create pivot tables
    closing_table = data.pivot_table(index='Date', columns='Symbol', values='Closing', aggfunc='first').iloc[start_timepoint:end_timepoint]
    volume_table = data.pivot_table(index='Date', columns='Symbol', values='Volume', aggfunc='first').iloc[end_timepoint-10:end_timepoint]
    
    variable_names = closing_table.columns.to_numpy()
    
    # ORIGINAL METHOD - Process data
    closing_table.reset_index(drop=True, inplace=True)
    volume_table.reset_index(drop=True, inplace=True)
    closing_table = closing_table.fillna(0)
    volume_table = volume_table.fillna(0)
    
    closing_table = closing_table.T.to_numpy()
    volume_table = volume_table.T.to_numpy()
    
    result = {
        'closing_table': closing_table,
        'volume_table': volume_table,
        'variable_names': variable_names,
        'shapes': (closing_table.shape, volume_table.shape)
    }
    
    save_to_cache(result, cache_file)
    return result

def normalize_data_cached(closing_table, variable_names, timepoint):
    """Normalize data with caching - ORIGINAL METHOD PRESERVED"""
    cache_file = get_cache_filename("normalized", timepoint)
    
    cached_data = load_from_cache(cache_file)
    if cached_data is not None:
        return cached_data
    
    # ORIGINAL METHOD - Normalize using z-scores
    means = np.mean(closing_table[:, :1501], axis=1, keepdims=True)
    stds = np.std(closing_table[:, :1501], axis=1, keepdims=True)
    stds = np.where(stds == 0, 1e-8, stds)
    
    normalized_data = np.copy(closing_table)
    normalized_data[:, :1501] = (closing_table[:, :1501] - means) / stds
    normalized_data[:, 1501:] = (closing_table[:, 1501:] - means) / stds
    
    # ORIGINAL METHOD - Remove non-finite elements
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
    
    cached_clusters = load_from_cache(cache_file)
    if cached_clusters is not None:
        return cached_clusters
    
    # ORIGINAL METHOD - Hierarchical clustering with ward linkage
    clustering_data = normalized_data[:, :1501]
    linkage_matrix = linkage(clustering_data, method='ward')
    clusters = fcluster(linkage_matrix, 50, criterion='distance') - 1  # ORIGINAL: distance=50
    
    save_to_cache(clusters, cache_file)
    return clusters

def process_single_timepoint_robust(timepoint_idx, start_timepoint, data_file):
    """Process a single timepoint with robust saving"""
    
    # Check if already processed
    individual_file = get_individual_results_filename(timepoint_idx)
    if os.path.exists(individual_file):
        print(f"Timepoint {timepoint_idx + 1} already processed, loading from file")
        return pd.read_csv(individual_file)
    
    try:
        print(f"Processing timepoint {timepoint_idx + 1}...")
        
        # Load data
        data = pd.read_csv(data_file)
        
        current_start_timepoint = start_timepoint + timepoint_idx
        end_timepoint = current_start_timepoint + 2001
        
        # ORIGINAL PROCESSING STEPS
        # Step 1: Preprocess
        preprocessed = preprocess_data_cached(data, current_start_timepoint, end_timepoint)
        closing_table = preprocessed['closing_table']
        volume_table = preprocessed['volume_table']
        variable_names = preprocessed['variable_names']
        
        # Step 2: Normalize
        normalized = normalize_data_cached(closing_table, variable_names, current_start_timepoint)
        normalized_data = normalized['normalized_data']
        closing_table = normalized['closing_table']
        volume_table = volume_table[normalized['finite_mask']]
        variable_names = normalized['variable_names']
        
        # Step 3: Cluster
        clusters = perform_clustering_cached(normalized_data, current_start_timepoint)
        
        # Step 4: Analyze clusters - ORIGINAL CRITERIA
        last_500_normalized_data = normalized_data[:, 1501:]
        cluster_counts = Counter(clusters)
        large_clusters = [cluster for cluster, count in cluster_counts.items() if count >= 40]  # ORIGINAL: >= 40
        
        if not large_clusters:
            print(f"Timepoint {timepoint_idx + 1}: No large clusters found")
            # Save empty result to mark as processed
            empty_df = pd.DataFrame()
            empty_df.to_csv(individual_file, index=False)
            return empty_df
        
        # Generate signals - ORIGINAL THRESHOLDS
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
        
        # Create signal tables - ORIGINAL THRESHOLDS
        long_table = []
        short_table = []
        
        for cluster, states in cluster_current_state.items():
            cluster_indices = [i for i, c in enumerate(clusters) if c == cluster]
            
            # Long signals (state < -3) - ORIGINAL
            long_indices = np.where(states < -3)[0]
            long_variable_names = variable_names[cluster_indices][long_indices]
            for name, state in zip(long_variable_names, states[long_indices]):
                long_table.append([name, state])
            
            # Short signals (state > 3.4) - ORIGINAL
            short_indices = np.where(states > 3.4)[0]
            short_variable_names = variable_names[cluster_indices][short_indices]
            for name, state in zip(short_variable_names, states[short_indices]):
                short_table.append([name, state])
        
        # Process signals - ORIGINAL METHOD
        long_table_df = pd.DataFrame(long_table, columns=['Variable Name', 'State'])
        short_table_df = pd.DataFrame(short_table, columns=['Variable Name', 'State'])
        
        if long_table_df.empty and short_table_df.empty:
            print(f"Timepoint {timepoint_idx + 1}: No trading signals found")
            empty_df = pd.DataFrame()
            empty_df.to_csv(individual_file, index=False)
            return empty_df
        
        # Add price and volume - ORIGINAL METHOD
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
        
        # Filter - ORIGINAL CRITERIA
        combined_table_df = pd.concat([long_table_df, short_table_df], ignore_index=True)
        
        if combined_table_df.empty:
            empty_df = pd.DataFrame()
            empty_df.to_csv(individual_file, index=False)
            return empty_df
        
        combined_table_df['Type'] = combined_table_df['State'].apply(lambda state: 'Long' if state < 0 else 'Short')
        filtered_combined_table_df = combined_table_df[
            (combined_table_df['Price'] > 0) & (combined_table_df['Volume'] > 100000)  # ORIGINAL: > 100,000
        ].copy()
        
        if filtered_combined_table_df.empty:
            empty_df = pd.DataFrame()
            empty_df.to_csv(individual_file, index=False)
            return empty_df
        
        # Add metadata
        filtered_combined_table_df['RPS'] = 0
        filtered_combined_table_df['End Timepoint'] = end_timepoint
        filtered_combined_table_df['Start Timepoint'] = current_start_timepoint
        filtered_combined_table_df['Timepoint Index'] = timepoint_idx + 1
        
        # Save individual result
        filtered_combined_table_df.to_csv(individual_file, index=False)
        
        print(f"Timepoint {timepoint_idx + 1}: Found {len(filtered_combined_table_df)} signals (saved)")
        return filtered_combined_table_df
        
    except Exception as e:
        print(f"Error processing timepoint {timepoint_idx + 1}: {str(e)}")
        return pd.DataFrame()
    finally:
        if 'data' in locals():
            del data
        gc.collect()

def main():
    """Main function for robust large-scale analysis"""
    print("="*80)
    print("ROBUST LARGE-SCALE ANALYSIS - ORIGINAL CRITERIA")
    print("="*80)
    
    create_directories()
    
    # Configuration
    start_timepoint = 200
    num_iterations = 150
    data_file = 'data.csv'
    
    print(f"ORIGINAL PARAMETERS PRESERVED:")
    print(f"  - Cluster distance: 50")
    print(f"  - Min cluster size: >= 40 variables")
    print(f"  - Long threshold: < -3")
    print(f"  - Short threshold: > 3.4")
    print(f"  - Volume threshold: > 100,000")
    print(f"Start timepoint: {start_timepoint}")
    print(f"Number of iterations: {num_iterations}")
    print(f"Results saved individually to: {INDIVIDUAL_RESULTS_DIR}")
    
    start_time = time.time()
    
    # Process timepoints sequentially for reliability
    all_results = []
    
    for timepoint_idx in range(num_iterations):
        result = process_single_timepoint_robust(timepoint_idx, start_timepoint, data_file)
        
        if not result.empty:
            all_results.append(result)
        
        # Progress update
        elapsed = time.time() - start_time
        progress = (timepoint_idx + 1) / num_iterations
        estimated_total = elapsed / progress
        remaining = estimated_total - elapsed
        
        print(f"Progress: {timepoint_idx + 1}/{num_iterations} ({progress:.1%})")
        print(f"Elapsed: {elapsed:.1f}s, Estimated remaining: {remaining:.1f}s")
        print(f"Total signals so far: {sum(len(r) for r in all_results)}")
        
        # Save combined results every 10 timepoints
        if (timepoint_idx + 1) % 10 == 0:
            if all_results:
                partial_results = pd.concat(all_results, ignore_index=True)
                partial_filename = os.path.join(RESULTS_DIR, f'partial_results_up_to_{timepoint_idx + 1}.csv')
                partial_results.to_csv(partial_filename, index=False)
                print(f"Saved partial results to: {partial_filename}")
    
    # Combine all results
    if all_results:
        final_results = pd.concat(all_results, ignore_index=True)
        final_filename = os.path.join(RESULTS_DIR, 'trading_signals_150_timepoints_original_criteria.csv')
        final_results.to_csv(final_filename, index=False)
        
        print(f"\n" + "="*80)
        print("ANALYSIS COMPLETE!")
        print("="*80)
        print(f"Total signals: {len(final_results)}")
        print(f"Long signals: {len(final_results[final_results['Type'] == 'Long'])}")
        print(f"Short signals: {len(final_results[final_results['Type'] == 'Short'])}")
        print(f"Final results saved to: {final_filename}")
        print(f"Individual results in: {INDIVIDUAL_RESULTS_DIR}")
        
        # Show sample
        print(f"\nSample results:")
        sample_cols = ['Variable Name', 'Type', 'State', 'Price', 'Timepoint Index']
        print(final_results.head(10)[sample_cols].to_string(index=False))
        
    else:
        print("No results found")
    
    total_time = time.time() - start_time
    print(f"\nTotal time: {total_time:.1f}s ({total_time/3600:.2f} hours)")

if __name__ == "__main__":
    main()