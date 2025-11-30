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
import threading

# Configuration for optimized parallel large-scale analysis
D_DRIVE_PATH = '/mnt/d/testbed_analysis'
CACHE_DIR = os.path.join(D_DRIVE_PATH, 'cache')
RESULTS_DIR = os.path.join(D_DRIVE_PATH, 'results')
INDIVIDUAL_RESULTS_DIR = os.path.join(D_DRIVE_PATH, 'individual_results')
USE_CACHE = True
NUM_PROCESSES = min(6, mp.cpu_count())  # Use multiple cores for parallel processing
CHUNK_SIZE = 15  # Process in chunks to manage memory - larger chunks for 250 timepoints
SAVE_EVERY_CHUNK = True

def create_directories():
    """Create necessary directories on D drive"""
    for directory in [D_DRIVE_PATH, CACHE_DIR, RESULTS_DIR, INDIVIDUAL_RESULTS_DIR]:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"Created directory: {directory}")

def get_memory_usage():
    """Get current memory usage"""
    try:
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024  # MB
    except:
        return 0

def log_memory_usage(stage):
    """Log memory usage at different stages"""
    memory_mb = get_memory_usage()
    print(f"Memory usage at {stage}: {memory_mb:.1f} MB")

def get_cache_filename(prefix, timepoint):
    """Generate cache filename on D drive"""
    return os.path.join(CACHE_DIR, f"{prefix}_timepoint_{timepoint}.pkl")

def get_individual_results_filename(timepoint_idx):
    """Generate individual results filename"""
    return os.path.join(INDIVIDUAL_RESULTS_DIR, f"timepoint_{timepoint_idx}.csv")

def save_to_cache(data, filename):
    """Save data to cache with thread safety"""
    if USE_CACHE:
        try:
            # Use a temporary file for atomic writes
            temp_filename = filename + '.tmp'
            with open(temp_filename, 'wb') as f:
                pickle.dump(data, f)
            os.rename(temp_filename, filename)
        except Exception as e:
            print(f"Warning: Could not save to cache {filename}: {e}")
            # Clean up temp file if it exists
            if os.path.exists(temp_filename):
                try:
                    os.remove(temp_filename)
                except:
                    pass

def load_from_cache(filename):
    """Load data from cache with error handling"""
    if USE_CACHE and os.path.exists(filename):
        try:
            with open(filename, 'rb') as f:
                return pickle.load(f)
        except Exception as e:
            print(f"Warning: Could not load from cache {filename}: {e}")
            # Remove corrupted cache file
            try:
                os.remove(filename)
            except:
                pass
    return None

def preprocess_data_cached(data, start_timepoint, end_timepoint):
    """Preprocess data with caching - ORIGINAL METHOD PRESERVED"""
    cache_key = f"preprocessed_{start_timepoint}_{end_timepoint}"
    cache_file = get_cache_filename(cache_key, start_timepoint)
    
    cached_data = load_from_cache(cache_file)
    if cached_data is not None:
        return cached_data
    
    try:
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
    
    except Exception as e:
        print(f"Error in preprocessing timepoint {start_timepoint}: {e}")
        return None

def normalize_data_cached(closing_table, variable_names, timepoint):
    """Normalize data with caching - ORIGINAL METHOD PRESERVED"""
    cache_file = get_cache_filename("normalized", timepoint)
    
    cached_data = load_from_cache(cache_file)
    if cached_data is not None:
        return cached_data
    
    try:
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
    
    except Exception as e:
        print(f"Error in normalization timepoint {timepoint}: {e}")
        return None

def perform_clustering_cached(normalized_data, timepoint):
    """Perform clustering with caching - ORIGINAL METHOD PRESERVED"""
    cache_file = get_cache_filename("clusters", timepoint)
    
    cached_clusters = load_from_cache(cache_file)
    if cached_clusters is not None:
        return cached_clusters
    
    try:
        # ORIGINAL METHOD - Hierarchical clustering with ward linkage
        clustering_data = normalized_data[:, :1501]
        linkage_matrix = linkage(clustering_data, method='ward')
        clusters = fcluster(linkage_matrix, 50, criterion='distance') - 1  # ORIGINAL: distance=50
        
        save_to_cache(clusters, cache_file)
        return clusters
    
    except Exception as e:
        print(f"Error in clustering timepoint {timepoint}: {e}")
        return None

def process_single_timepoint_parallel(args):
    """Process a single timepoint - optimized for parallel execution"""
    timepoint_idx, start_timepoint, data_file = args
    
    # Check if already processed
    individual_file = get_individual_results_filename(timepoint_idx)
    if os.path.exists(individual_file):
        try:
            result = pd.read_csv(individual_file)
            if not result.empty:
                return timepoint_idx, result, f"Timepoint {timepoint_idx + 1} loaded from cache"
        except:
            # If file is corrupted, reprocess
            pass
    
    try:
        # Load data for this process
        data = pd.read_csv(data_file)
        
        current_start_timepoint = start_timepoint + timepoint_idx
        end_timepoint = current_start_timepoint + 2001
        
        # ORIGINAL PROCESSING STEPS
        # Step 1: Preprocess
        preprocessed = preprocess_data_cached(data, current_start_timepoint, end_timepoint)
        if preprocessed is None:
            return timepoint_idx, pd.DataFrame(), f"Timepoint {timepoint_idx + 1} preprocessing failed"
        
        closing_table = preprocessed['closing_table']
        volume_table = preprocessed['volume_table']
        variable_names = preprocessed['variable_names']
        
        # Step 2: Normalize
        normalized = normalize_data_cached(closing_table, variable_names, current_start_timepoint)
        if normalized is None:
            return timepoint_idx, pd.DataFrame(), f"Timepoint {timepoint_idx + 1} normalization failed"
        
        normalized_data = normalized['normalized_data']
        closing_table = normalized['closing_table']
        volume_table = volume_table[normalized['finite_mask']]
        variable_names = normalized['variable_names']
        
        # Step 3: Cluster
        clusters = perform_clustering_cached(normalized_data, current_start_timepoint)
        if clusters is None:
            return timepoint_idx, pd.DataFrame(), f"Timepoint {timepoint_idx + 1} clustering failed"
        
        # Step 4: Analyze clusters - ORIGINAL CRITERIA
        last_500_normalized_data = normalized_data[:, 1501:]
        cluster_counts = Counter(clusters)
        large_clusters = [cluster for cluster, count in cluster_counts.items() if count >= 40]  # ORIGINAL: >= 40
        
        if not large_clusters:
            empty_df = pd.DataFrame()
            empty_df.to_csv(individual_file, index=False)
            return timepoint_idx, empty_df, f"Timepoint {timepoint_idx + 1}: No large clusters"
        
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
            empty_df = pd.DataFrame()
            empty_df.to_csv(individual_file, index=False)
            return timepoint_idx, empty_df, f"Timepoint {timepoint_idx + 1}: No signals"
        
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
            return timepoint_idx, empty_df, f"Timepoint {timepoint_idx + 1}: No valid signals"
        
        combined_table_df['Type'] = combined_table_df['State'].apply(lambda state: 'Long' if state < 0 else 'Short')
        filtered_combined_table_df = combined_table_df[
            (combined_table_df['Price'] > 0) & (combined_table_df['Volume'] > 100000)  # ORIGINAL: > 100,000
        ].copy()
        
        if filtered_combined_table_df.empty:
            empty_df = pd.DataFrame()
            empty_df.to_csv(individual_file, index=False)
            return timepoint_idx, empty_df, f"Timepoint {timepoint_idx + 1}: Filtered out"
        
        # Add metadata
        filtered_combined_table_df['RPS'] = 0
        filtered_combined_table_df['End Timepoint'] = end_timepoint
        filtered_combined_table_df['Start Timepoint'] = current_start_timepoint
        filtered_combined_table_df['Timepoint Index'] = timepoint_idx + 1
        
        # Save individual result atomically
        temp_file = individual_file + '.tmp'
        filtered_combined_table_df.to_csv(temp_file, index=False)
        os.rename(temp_file, individual_file)
        
        message = f"Timepoint {timepoint_idx + 1}: {len(filtered_combined_table_df)} signals"
        return timepoint_idx, filtered_combined_table_df, message
        
    except Exception as e:
        error_msg = f"Error processing timepoint {timepoint_idx + 1}: {str(e)}"
        return timepoint_idx, pd.DataFrame(), error_msg
    
    finally:
        # Clean up memory
        if 'data' in locals():
            del data
        gc.collect()

def process_chunk_parallel(chunk_id, chunk_timepoints, start_timepoint, data_file):
    """Process a chunk of timepoints in parallel"""
    print(f"\n--- Processing chunk {chunk_id + 1} (timepoints {[t+1 for t in chunk_timepoints]}) ---")
    
    # Prepare arguments for parallel processing
    args_list = [(timepoint_idx, start_timepoint, data_file) for timepoint_idx in chunk_timepoints]
    
    chunk_results = []
    
    # Process chunk in parallel
    with ProcessPoolExecutor(max_workers=NUM_PROCESSES) as executor:
        future_to_timepoint = {
            executor.submit(process_single_timepoint_parallel, args): args[0] 
            for args in args_list
        }
        
        for future in as_completed(future_to_timepoint):
            timepoint_idx = future_to_timepoint[future]
            try:
                idx, result, message = future.result()
                print(message)
                
                if not result.empty:
                    chunk_results.append(result)
                    
            except Exception as e:
                print(f"Timepoint {timepoint_idx + 1} failed: {e}")
    
    return chunk_results

def main():
    """Main function for optimized parallel large-scale analysis"""
    print("="*80)
    print("OPTIMIZED PARALLEL ANALYSIS - ORIGINAL CRITERIA PRESERVED")
    print("="*80)
    
    create_directories()
    
    # Configuration
    start_timepoint = 75
    num_iterations = 250
    data_file = 'data.csv'
    
    print(f"ORIGINAL PARAMETERS PRESERVED:")
    print(f"  - Cluster distance: 50")
    print(f"  - Min cluster size: >= 40 variables") 
    print(f"  - Long threshold: < -3")
    print(f"  - Short threshold: > 3.4")
    print(f"  - Volume threshold: > 100,000")
    print(f"")
    print(f"PARALLEL OPTIMIZATION:")
    print(f"  - Start timepoint: {start_timepoint}")
    print(f"  - Total iterations: {num_iterations}")
    print(f"  - Parallel processes: {NUM_PROCESSES}")
    print(f"  - Chunk size: {CHUNK_SIZE}")
    print(f"  - Caching enabled: {USE_CACHE}")
    print(f"  - Storage: {D_DRIVE_PATH}")
    
    log_memory_usage("startup")
    start_time = time.time()
    
    # Split into chunks for parallel processing
    all_timepoints = list(range(num_iterations))
    chunks = [all_timepoints[i:i + CHUNK_SIZE] for i in range(0, len(all_timepoints), CHUNK_SIZE)]
    
    print(f"\nProcessing {len(chunks)} chunks of {CHUNK_SIZE} timepoints each")
    
    all_results = []
    total_signals = 0
    
    # Process each chunk
    for chunk_id, chunk_timepoints in enumerate(chunks):
        chunk_start_time = time.time()
        
        chunk_results = process_chunk_parallel(chunk_id, chunk_timepoints, start_timepoint, data_file)
        
        if chunk_results:
            all_results.extend(chunk_results)
            chunk_signals = sum(len(r) for r in chunk_results)
            total_signals += chunk_signals
            
            # Save partial results
            if SAVE_EVERY_CHUNK and all_results:
                partial_df = pd.concat(all_results, ignore_index=True)
                partial_filename = os.path.join(RESULTS_DIR, f'partial_results_chunk_{chunk_id + 1}.csv')
                partial_df.to_csv(partial_filename, index=False)
                print(f"Saved partial results: {partial_filename} ({len(partial_df)} total signals)")
        
        # Progress update
        chunk_duration = time.time() - chunk_start_time
        elapsed_total = time.time() - start_time
        progress = (chunk_id + 1) / len(chunks)
        
        if progress > 0:
            estimated_total = elapsed_total / progress
            remaining = estimated_total - elapsed_total
            
            print(f"Chunk {chunk_id + 1}/{len(chunks)} completed in {chunk_duration:.2f}s")
            print(f"Progress: {progress:.1%}, Elapsed: {elapsed_total:.2f}s")
            print(f"Estimated remaining: {remaining:.2f}s ({remaining/3600:.2f} hours)")
            print(f"Total signals found: {total_signals}")
        
        # Memory cleanup
        gc.collect()
        log_memory_usage(f"after chunk {chunk_id + 1}")
    
    # Combine all results
    if all_results:
        final_results = pd.concat(all_results, ignore_index=True)
        final_filename = os.path.join(RESULTS_DIR, 'trading_signals_250_timepoints_start75_original_criteria.csv')
        final_results.to_csv(final_filename, index=False)
        
        print(f"\n" + "="*80)
        print("PARALLEL ANALYSIS COMPLETE!")
        print("="*80)
        print(f"Total signals: {len(final_results)}")
        print(f"Long signals: {len(final_results[final_results['Type'] == 'Long'])}")
        print(f"Short signals: {len(final_results[final_results['Type'] == 'Short'])}")
        print(f"Timepoints: {final_results['Timepoint Index'].min()}-{final_results['Timepoint Index'].max()}")
        print(f"Final results: {final_filename}")
        print(f"Individual results: {INDIVIDUAL_RESULTS_DIR}")
        
        # Show sample
        print(f"\nSample results:")
        sample_cols = ['Variable Name', 'Type', 'State', 'Price', 'Timepoint Index']
        print(final_results.head(10)[sample_cols].to_string(index=False))
        
    else:
        print("No results found")
    
    total_time = time.time() - start_time
    print(f"\nTotal time: {total_time:.1f}s ({total_time/3600:.2f} hours)")
    print(f"Average per timepoint: {total_time/num_iterations:.1f}s")
    
    log_memory_usage("completion")

if __name__ == "__main__":
    main()