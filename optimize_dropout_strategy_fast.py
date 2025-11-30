"""
PERFORMANCE-OPTIMIZED version of dropout strategy optimization

Key optimizations:
1. Load CSV data ONCE and cache in memory
2. Pre-calculate all price pivots for different block sizes
3. Vectorize return calculations using numpy
4. Remove redundant data loading in calculate_post_event_returns
5. Use efficient pandas operations instead of loops
6. Parallel processing with multiprocessing

Expected speedup: 10-20x faster
"""

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage, fcluster
from collections import defaultdict
from itertools import product
import time
from multiprocessing import Pool, cpu_count

# GLOBAL CACHE for data
_DATA_CACHE = None
_CLOSING_TABLE_CACHE = None

def load_data_once(data_file):
    """Load data into memory ONCE and cache it"""
    global _DATA_CACHE, _CLOSING_TABLE_CACHE
    
    if _DATA_CACHE is None:
        print("Loading data into memory (one-time operation)...")
        start = time.time()
        _DATA_CACHE = pd.read_csv(data_file)
        
        _CLOSING_TABLE_CACHE = _DATA_CACHE.pivot_table(
            index='Date', 
            columns='Symbol', 
            values='Closing', 
            aggfunc='first'
        )
        _CLOSING_TABLE_CACHE = _CLOSING_TABLE_CACHE.fillna(method='ffill').fillna(method='bfill')
        
        print(f"Data loaded: {len(_CLOSING_TABLE_CACHE)} timepoints, {len(_CLOSING_TABLE_CACHE.columns)} securities")
        print(f"Load time: {time.time() - start:.2f}s")
    
    return _DATA_CACHE, _CLOSING_TABLE_CACHE

def load_and_prepare_data(data_file, start_idx, block_size):
    """Load and prepare data for a specific block of timepoints - OPTIMIZED"""
    _, closing_table = load_data_once(data_file)
    
    # Slice the cached data
    end_idx = start_idx + block_size
    block_data = closing_table.iloc[start_idx:end_idx]
    
    securities = block_data.columns.to_numpy()
    timepoints = block_data.index.to_numpy()
    
    # Convert to numpy array (securities x timepoints)
    price_matrix = block_data.T.to_numpy()
    
    return price_matrix, securities, timepoints, block_data

def perform_zscore_normalization(price_matrix, securities):
    """Perform z-score normalization on the price matrix - VECTORIZED"""
    # Vectorized normalization
    means = np.mean(price_matrix, axis=1, keepdims=True)
    stds = np.std(price_matrix, axis=1, keepdims=True)
    
    # Avoid division by zero
    stds = np.where(stds == 0, 1, stds)
    
    normalized_matrix = (price_matrix - means) / stds
    
    # Remove securities with all zeros or infinite values
    finite_mask = np.all(np.isfinite(normalized_matrix), axis=1)
    clean_matrix = normalized_matrix[finite_mask]
    clean_securities = securities[finite_mask]
    
    return clean_matrix, clean_securities

def perform_hierarchical_clustering(normalized_matrix, securities, distance_threshold, min_cluster_size=5):
    """Perform hierarchical clustering on normalized price data"""
    linkage_matrix = linkage(normalized_matrix, method='ward')
    cluster_labels = fcluster(linkage_matrix, distance_threshold, criterion='distance') - 1
    
    # Create cluster mapping
    cluster_dict = defaultdict(list)
    for security_idx, cluster_id in enumerate(cluster_labels):
        cluster_dict[cluster_id].append(securities[security_idx])
    
    # Convert to regular dict and filter small clusters
    clusters = {}
    for cluster_id, security_list in cluster_dict.items():
        if len(security_list) >= min_cluster_size:
            clusters[cluster_id] = security_list
    
    return clusters, cluster_labels

def calculate_cluster_quality_scores(clusters, price_data, securities, quality_metric='avg_return'):
    """
    Calculate quality score for each cluster - OPTIMIZED
    Uses vectorized operations for speed
    """
    cluster_quality = {}
    cluster_returns = {}
    
    for cluster_id, cluster_securities in clusters.items():
        returns_list = []
        volatilities = []
        
        # Get all prices at once
        cluster_prices = price_data[cluster_securities].dropna(axis=1, how='all')
        
        if cluster_prices.shape[1] < 5:
            cluster_quality[cluster_id] = 0
            cluster_returns[cluster_id] = []
            continue
        
        for security in cluster_prices.columns:
            security_prices = cluster_prices[security].dropna()
            
            if len(security_prices) < 20:
                continue
            
            # Calculate return within the block (vectorized)
            block_length = len(security_prices)
            start_window = max(int(block_length * 0.1), 5)
            end_window = max(int(block_length * 0.1), 5)
            
            start_prices = security_prices.iloc[:start_window].values
            start_prices = start_prices[start_prices > 0]
            
            end_prices = security_prices.iloc[-end_window:].values
            end_prices = end_prices[end_prices > 0]
            
            if len(start_prices) < 3 or len(end_prices) < 3:
                continue
            
            start_price = np.mean(start_prices)
            end_price = np.mean(end_prices)
            
            if start_price == 0:
                continue
            
            pct_return = ((end_price - start_price) / start_price) * 100
            returns_list.append(pct_return)
            
            # Volatility calculation
            daily_returns = security_prices.pct_change().dropna() * 100
            if len(daily_returns) > 1:
                volatilities.append(daily_returns.std())
        
        # Calculate quality score
        if len(returns_list) >= 5:
            if quality_metric == 'avg_return':
                cluster_quality[cluster_id] = np.mean(returns_list)
            elif quality_metric == 'median_return':
                cluster_quality[cluster_id] = np.median(returns_list)
            elif quality_metric == 'positive_pct':
                cluster_quality[cluster_id] = (np.array(returns_list) > 0).sum() / len(returns_list) * 100
            elif quality_metric == 'sharpe' and len(volatilities) > 0:
                avg_return = np.mean(returns_list)
                avg_vol = np.mean(volatilities)
                cluster_quality[cluster_id] = avg_return / avg_vol if avg_vol > 0 else 0
            else:
                cluster_quality[cluster_id] = np.mean(returns_list)
            
            cluster_returns[cluster_id] = returns_list
        else:
            cluster_quality[cluster_id] = 0
            cluster_returns[cluster_id] = []
    
    return cluster_quality, cluster_returns

def detect_cluster_transitions(all_block_results, quality_threshold_percentile=75):
    """Detect when stocks transition between clusters of different quality levels"""
    
    loss_events = []
    acquisition_events = []
    
    # Track each security's cluster and quality across blocks
    security_history = defaultdict(list)
    
    for result in all_block_results:
        block_id = result['block_id']
        clusters = result['clusters']
        cluster_quality = result['cluster_quality']
        
        # Create reverse mapping: security -> (cluster_id, quality)
        for cluster_id, securities in clusters.items():
            quality = cluster_quality.get(cluster_id, 0)
            for security in securities:
                security_history[security].append({
                    'block': block_id,
                    'cluster_id': cluster_id,
                    'quality': quality
                })
    
    # Determine quality threshold
    all_qualities = []
    for result in all_block_results:
        all_qualities.extend(result['cluster_quality'].values())
    
    if len(all_qualities) == 0:
        return pd.DataFrame(), pd.DataFrame(), 0
    
    quality_threshold = np.percentile(all_qualities, quality_threshold_percentile)
    
    # Detect transitions
    for security, history in security_history.items():
        if len(history) < 2:
            continue
        
        for i in range(1, len(history)):
            prev = history[i-1]
            curr = history[i]
            
            prev_quality = prev['quality']
            curr_quality = curr['quality']
            
            # Loss event
            if prev_quality >= quality_threshold and curr_quality < prev_quality:
                quality_loss = prev_quality - curr_quality
                if quality_loss >= 5:
                    loss_events.append({
                        'Security': security,
                        'Block': curr['block'],
                        'Prev_Quality': prev_quality,
                        'New_Quality': curr_quality,
                        'Quality_Loss': quality_loss
                    })
            
            # Acquisition event
            elif curr_quality > prev_quality and curr_quality >= quality_threshold:
                quality_jump = curr_quality - prev_quality
                if quality_jump >= 5:
                    acquisition_events.append({
                        'Security': security,
                        'Block': curr['block'],
                        'Prev_Quality': prev_quality,
                        'New_Quality': curr_quality,
                        'Quality_Jump': quality_jump
                    })
    
    loss_df = pd.DataFrame(loss_events)
    acquisition_df = pd.DataFrame(acquisition_events)
    
    return loss_df, acquisition_df, quality_threshold

def calculate_post_event_returns_fast(events_df, block_size, forward_periods=500):
    """
    Calculate returns after dropout/acquisition events - OPTIMIZED
    Uses cached data instead of reloading CSV
    """
    if len(events_df) == 0:
        return events_df
    
    # Use cached closing table
    _, closing_table = load_data_once(None)
    
    # Vectorized return calculation
    returns = []
    
    for idx, row in events_df.iterrows():
        security = row['Security']
        block = row['Block']
        
        if security not in closing_table.columns:
            returns.append(np.nan)
            continue
        
        # Event happens at end of this block
        event_timepoint = (block + 1) * block_size
        
        if event_timepoint >= len(closing_table) - 10:
            returns.append(np.nan)
            continue
        
        # Vectorized price extraction
        start_slice = closing_table[security].iloc[event_timepoint:event_timepoint+10]
        start_prices = start_slice.dropna()
        start_prices = start_prices[start_prices > 0]
        
        if len(start_prices) < 5:
            returns.append(np.nan)
            continue
        
        start_price = start_prices.mean()
        
        # End prices
        end_timepoint = min(event_timepoint + forward_periods, len(closing_table) - 1)
        end_slice = closing_table[security].iloc[max(0, end_timepoint-10):end_timepoint]
        end_prices = end_slice.dropna()
        end_prices = end_prices[end_prices > 0]
        
        if len(end_prices) < 5:
            returns.append(np.nan)
            continue
        
        end_price = end_prices.mean()
        
        # Calculate percent return
        percent_return = ((end_price - start_price) / start_price) * 100
        returns.append(percent_return)
    
    events_df['Future_Return'] = returns
    return events_df

def test_dropout_parameters(data_file, 
                            block_size=125, 
                            num_blocks=10, 
                            distance_threshold=50,
                            quality_metric='avg_return',
                            quality_threshold_percentile=75,
                            min_quality_change=5):
    """Test a specific parameter combination for dropout detection - OPTIMIZED"""
    
    # Preload data
    load_data_once(data_file)
    
    start_timepoint = 0
    all_results = []
    
    # Process each block
    for block_id in range(num_blocks):
        block_start = start_timepoint + (block_id * block_size)
        
        try:
            # Load and prepare data
            price_matrix, securities, timepoints, price_data = load_and_prepare_data(
                data_file, block_start, block_size
            )
            
            # Perform z-score normalization
            normalized_matrix, clean_securities = perform_zscore_normalization(
                price_matrix, securities
            )
            
            # Perform hierarchical clustering
            clusters, cluster_labels = perform_hierarchical_clustering(
                normalized_matrix, clean_securities, distance_threshold
            )
            
            # Calculate cluster quality scores
            cluster_quality, cluster_returns = calculate_cluster_quality_scores(
                clusters, price_data, clean_securities, quality_metric
            )
            
            all_results.append({
                'block_id': block_id,
                'clusters': clusters,
                'cluster_quality': cluster_quality,
                'num_clusters': len(clusters)
            })
            
        except Exception as e:
            print(f"Error processing block {block_id}: {str(e)}")
            continue
    
    if len(all_results) == 0:
        return None, None, None
    
    # Detect dropout and acquisition events
    loss_df, acquisition_df, quality_threshold = detect_cluster_transitions(
        all_results, quality_threshold_percentile
    )
    
    # Calculate future returns (FAST version with cached data)
    loss_df = calculate_post_event_returns_fast(loss_df, block_size, forward_periods=500)
    acquisition_df = calculate_post_event_returns_fast(acquisition_df, block_size, forward_periods=500)
    
    # Calculate performance metrics
    result = {
        'Block_Size': block_size,
        'Num_Blocks': num_blocks,
        'Distance_Threshold': distance_threshold,
        'Quality_Metric': quality_metric,
        'Quality_Threshold_Percentile': quality_threshold_percentile,
        'Quality_Threshold_Value': quality_threshold,
        'Min_Quality_Change': min_quality_change,
        
        # DROPOUT events (leaving high-quality clusters) - PRIMARY SIGNAL
        'Num_Dropout_Events': len(loss_df),
        'Dropout_Avg_Return': loss_df['Future_Return'].mean() if len(loss_df) > 0 else np.nan,
        'Dropout_Median_Return': loss_df['Future_Return'].median() if len(loss_df) > 0 else np.nan,
        'Dropout_Positive_Pct': (loss_df['Future_Return'] > 0).sum() / len(loss_df) * 100 if len(loss_df) > 0 else np.nan,
        'Dropout_Negative_Pct': (loss_df['Future_Return'] < 0).sum() / len(loss_df) * 100 if len(loss_df) > 0 else np.nan,
        'Dropout_Std_Return': loss_df['Future_Return'].std() if len(loss_df) > 0 else np.nan,
        
        # Acquisition events
        'Num_Acquisition_Events': len(acquisition_df),
        'Acq_Avg_Return': acquisition_df['Future_Return'].mean() if len(acquisition_df) > 0 else np.nan,
        'Acq_Median_Return': acquisition_df['Future_Return'].median() if len(acquisition_df) > 0 else np.nan,
        'Acq_Positive_Pct': (acquisition_df['Future_Return'] > 0).sum() / len(acquisition_df) * 100 if len(acquisition_df) > 0 else np.nan,
        'Acq_Std_Return': acquisition_df['Future_Return'].std() if len(acquisition_df) > 0 else np.nan,
        
        # Signal strength metrics
        'Dropout_Signal_Strength': (loss_df['Future_Return'].mean() / loss_df['Future_Return'].std()) if len(loss_df) > 0 and loss_df['Future_Return'].std() > 0 else np.nan,
        'Dropout_Sharpe_Like': (loss_df['Future_Return'].mean() / loss_df['Future_Return'].std()) * np.sqrt(len(loss_df)) if len(loss_df) > 0 and loss_df['Future_Return'].std() > 0 else np.nan,
        
        # Combined metrics
        'Total_Events': len(loss_df) + len(acquisition_df),
        'Avg_Clusters_Per_Block': np.mean([r['num_clusters'] for r in all_results])
    }
    
    return result, loss_df, acquisition_df

def _test_single_config(args):
    """
    Worker function for parallel processing
    Tests a single configuration
    """
    data_file, block_size, num_blocks, distance_threshold, quality_metric, quality_percentile, idx, total = args
    
    iter_start = time.time()
    
    print(f"[{idx}/{total}] Testing: Block={block_size}, Blocks={num_blocks}, Dist={distance_threshold}, "
          f"Metric={quality_metric}, Percentile={quality_percentile}")
    
    result, loss_df, acq_df = test_dropout_parameters(
        data_file,
        block_size=block_size,
        num_blocks=num_blocks,
        distance_threshold=distance_threshold,
        quality_metric=quality_metric,
        quality_threshold_percentile=quality_percentile
    )
    
    if result:
        iter_time = time.time() - iter_start
        print(f"  → Dropout events: {result['Num_Dropout_Events']}, "
              f"Avg return: {result['Dropout_Avg_Return']:.2f}%, "
              f"Time: {iter_time:.1f}s")
    
    return result

def optimize_dropout_detection(data_file,
                               block_sizes=[100, 125, 150],
                               num_blocks_list=[10],
                               distance_thresholds=[40, 50, 60],
                               quality_metrics=['avg_return', 'median_return'],
                               quality_threshold_percentiles=[70, 75, 80],
                               use_parallel=True,
                               n_processes=None,
                               forward_window=500):
    """
    Optimize parameters for dropout detection strategy - OPTIMIZED with PARALLEL PROCESSING
    
    Parameters:
    -----------
    use_parallel : bool
        Whether to use parallel processing (default: True)
    n_processes : int
        Number of processes to use. If None, uses cpu_count() - 1
    forward_window : int
        Number of timepoints needed after blocks for forward returns (default: 500)
    """
    
    # Preload data ONCE before all tests
    print("="*80)
    print("DROPOUT STRATEGY PARAMETER OPTIMIZATION - FAST VERSION (PARALLEL)")
    print("="*80)
    _, closing_table = load_data_once(data_file)
    
    total_timepoints = len(closing_table)
    usable_timepoints = total_timepoints - forward_window
    
    print(f"Total timepoints: {total_timepoints}")
    print(f"Forward return window: {forward_window}")
    print(f"Usable timepoints for blocks: {usable_timepoints}")
    
    # Determine number of processes
    if n_processes is None:
        n_processes = max(1, cpu_count() - 1)
    
    print(f"Using {n_processes} parallel processes")
    
    # Generate all parameter combinations
    all_combinations = list(product(
        block_sizes,
        num_blocks_list,
        distance_thresholds,
        quality_metrics,
        quality_threshold_percentiles
    ))
    
    # Filter out unsafe combinations (block_size * num_blocks must fit in usable timepoints)
    param_combinations = []
    filtered_out = []
    
    for combo in all_combinations:
        block_size, num_blocks = combo[0], combo[1]
        total_used = block_size * num_blocks
        
        if total_used <= usable_timepoints:
            param_combinations.append(combo)
        else:
            filtered_out.append((block_size, num_blocks, total_used))
    
    if filtered_out:
        print(f"\nFiltered out {len(filtered_out)} unsafe configurations:")
        for bs, nb, used in filtered_out:
            print(f"  - {nb} blocks × {bs} = {used} (exceeds {usable_timepoints})")
    
    total_combinations = len(param_combinations)
    print(f"\nTesting {total_combinations} safe parameter combinations...")
    if use_parallel:
        estimated_time = total_combinations * 0.4 / n_processes
        print(f"Expected time with {n_processes} processes: ~{estimated_time:.0f}-{estimated_time*1.5:.0f} seconds")
    else:
        print(f"Expected time (sequential): ~{total_combinations * 0.4:.0f}-{total_combinations * 0.6:.0f} seconds")
    print("="*80)
    
    results = []
    start_time = time.time()
    
    if use_parallel:
        # Prepare arguments for parallel processing
        work_args = [
            (data_file, block_size, num_blocks, distance_threshold, quality_metric, quality_percentile, idx, total_combinations)
            for idx, (block_size, num_blocks, distance_threshold, quality_metric, quality_percentile) 
            in enumerate(param_combinations, 1)
        ]
        
        # Run parallel processing
        with Pool(processes=n_processes) as pool:
            results_raw = pool.map(_test_single_config, work_args)
        
        # Filter out None results
        results = [r for r in results_raw if r is not None]
    else:
        # Sequential processing (for debugging)
        for idx, (block_size, num_blocks, distance_threshold, quality_metric, quality_percentile) in enumerate(param_combinations, 1):
            iter_start = time.time()
            
            print(f"\n[{idx}/{total_combinations}] Testing: Block={block_size}, Blocks={num_blocks}, Dist={distance_threshold}, "
                  f"Metric={quality_metric}, Percentile={quality_percentile}")
            
            result, loss_df, acq_df = test_dropout_parameters(
                data_file,
                block_size=block_size,
                num_blocks=num_blocks,
                distance_threshold=distance_threshold,
                quality_metric=quality_metric,
                quality_threshold_percentile=quality_percentile
            )
            
            if result:
                results.append(result)
                iter_time = time.time() - iter_start
                print(f"  → Dropout events: {result['Num_Dropout_Events']}, "
                      f"Avg return: {result['Dropout_Avg_Return']:.2f}%, "
                      f"Time: {iter_time:.1f}s")
    
    total_time = time.time() - start_time
    
    # Convert to DataFrame
    summary_df = pd.DataFrame(results)
    
    # Save results
    summary_df.to_csv('dropout_optimization_results_fast.csv', index=False)
    print(f"\nResults saved to: dropout_optimization_results_fast.csv")
    
    # Analysis
    print("\n" + "="*80)
    print("OPTIMIZATION ANALYSIS")
    print("="*80)
    
    # Top 5 by average return
    print("\n1. HIGHEST AVERAGE RETURN (Top 5):")
    print("-" * 80)
    top_return = summary_df.nlargest(5, 'Dropout_Avg_Return')[
        ['Block_Size', 'Num_Blocks', 'Distance_Threshold', 'Quality_Metric', 
         'Quality_Threshold_Percentile', 'Num_Dropout_Events', 'Dropout_Avg_Return', 
         'Dropout_Positive_Pct', 'Dropout_Signal_Strength']
    ]
    print(top_return.to_string(index=False))
    
    # Top 5 by signal strength
    print("\n2. STRONGEST SIGNAL (Return/Volatility, Top 5):")
    print("-" * 80)
    top_signal = summary_df.nlargest(5, 'Dropout_Signal_Strength')[
        ['Block_Size', 'Num_Blocks', 'Distance_Threshold', 'Quality_Metric',
         'Quality_Threshold_Percentile', 'Dropout_Signal_Strength', 
         'Dropout_Avg_Return', 'Dropout_Std_Return', 'Num_Dropout_Events']
    ]
    print(top_signal.to_string(index=False))
    
    # Top 5 by positive percentage
    print("\n3. HIGHEST % POSITIVE RETURNS (Top 5):")
    print("-" * 80)
    top_positive = summary_df.nlargest(5, 'Dropout_Positive_Pct')[
        ['Block_Size', 'Num_Blocks', 'Distance_Threshold', 'Quality_Metric',
         'Quality_Threshold_Percentile', 'Dropout_Positive_Pct', 
         'Dropout_Avg_Return', 'Num_Dropout_Events']
    ]
    print(top_positive.to_string(index=False))
    
    print(f"\nTotal optimization time: {total_time:.2f} seconds ({total_time/60:.1f} minutes)")
    print(f"Average time per configuration: {total_time/total_combinations:.2f} seconds")
    print("="*80)
    
    return summary_df

def main():
    """Main function"""
    data_file = 'data.csv'
    
    # EXTENDED BOUNDARY TEST
    # Safe configurations (accounting for 500-point forward window):
    # Total timepoints: 2557, Forward: 500, Usable: 2057
    # 8 blocks: 150✓, 175✓, 200✓
    # 10 blocks: 150✓, 175✓, 200✓
    # 12 blocks: 150✓, 175✗, 200✗
    # Expected: 7×4×2×3 = 168 total, filtered to 112 safe combinations
    
    print("Running EXTENDED BOUNDARY optimization test (FAST PARALLEL VERSION)...")
    summary_df = optimize_dropout_detection(
        data_file,
        block_sizes=[150, 175, 200],  # Testing extended range
        num_blocks_list=[8, 10, 12],  # Will auto-filter unsafe combinations
        distance_thresholds=[25, 30, 35, 40],  # Extended down from floor at 40
        quality_metrics=['avg_return', 'median_return'],
        quality_threshold_percentiles=[70, 75, 80],
        use_parallel=True,  # Enable parallel processing
        n_processes=None,  # Auto-detect (uses cpu_count - 1)
        forward_window=500  # Reserve 500 points for forward returns
    )
    
    return summary_df

if __name__ == "__main__":
    summary_df = main()
