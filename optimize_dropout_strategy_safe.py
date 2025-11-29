"""
MEMORY-SAFE optimized dropout strategy optimization

Fixes:
1. NO multiprocessing (avoids memory explosion from copying data to each process)
2. Single data load with efficient chunking
3. Progress tracking
4. Memory-efficient operations

This version prioritizes stability over speed.
"""

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage, fcluster
from collections import defaultdict
from itertools import product
import time
import gc

# OPTIONAL: market cap cache
_MARKET_CAPS_CACHE = None

# GLOBAL CACHE for data (single process only)
_DATA_CACHE = None
_CLOSING_TABLE_CACHE = None

def load_data_once(data_file):
    """Load data into memory ONCE and cache it"""
    global _DATA_CACHE, _CLOSING_TABLE_CACHE
    
    if _DATA_CACHE is None:
        print("Loading data into memory (one-time operation)...")
        start = time.time()
        
        # Load with efficient dtypes to reduce memory
        _DATA_CACHE = pd.read_csv(
            data_file,
            dtype={'Date': str, 'Symbol': str, 'Closing': np.float32, 'Volume': np.float32}
        )
        
        print(f"Creating pivot table...")
        _CLOSING_TABLE_CACHE = _DATA_CACHE.pivot_table(
            index='Date', 
            columns='Symbol', 
            values='Closing', 
            aggfunc='first'
        )
        
        # Clean up and reduce memory
        _CLOSING_TABLE_CACHE = _CLOSING_TABLE_CACHE.fillna(method='ffill').fillna(method='bfill')
        _CLOSING_TABLE_CACHE = _CLOSING_TABLE_CACHE.astype(np.float32)  # Use float32 instead of float64
        
        print(f"Data loaded: {len(_CLOSING_TABLE_CACHE)} timepoints, {len(_CLOSING_TABLE_CACHE.columns)} securities")
        print(f"Memory usage: ~{_CLOSING_TABLE_CACHE.memory_usage(deep=True).sum() / 1024**3:.2f} GB")
        print(f"Load time: {time.time() - start:.2f}s")
        
        # Force garbage collection
        gc.collect()
    
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

def load_market_caps(cap_file='market_caps.csv'):
    """Attempt to load market cap data.
    Supported formats:
    1. Symbol,MarketCap (static latest cap)
    2. Date,Symbol,MarketCap (time series) – will average within block.
    Returns DataFrame or None if file missing.
    """
    global _MARKET_CAPS_CACHE
    if _MARKET_CAPS_CACHE is not None:
        return _MARKET_CAPS_CACHE
    try:
        df = pd.read_csv(cap_file)
        # Basic validation
        if 'Symbol' not in df.columns or 'MarketCap' not in df.columns:
            print(f"Market cap file '{cap_file}' missing required columns; ignoring.")
            _MARKET_CAPS_CACHE = None
            return None
        # Coerce MarketCap numeric
        df['MarketCap'] = pd.to_numeric(df['MarketCap'], errors='coerce')
        df = df.dropna(subset=['MarketCap'])
        _MARKET_CAPS_CACHE = df
        print(f"Loaded market cap data: {len(df['Symbol'].unique())} symbols")
        return _MARKET_CAPS_CACHE
    except FileNotFoundError:
        print("No market cap file found (market_caps.csv); proceeding without size metrics.")
        return None
    except Exception as e:
        print(f"Error loading market caps: {e}; proceeding without size metrics.")
        return None

def calculate_cluster_quality_scores(clusters, price_data, securities, quality_metric='avg_return', market_caps_df=None):
    """Calculate quality score for each cluster - OPTIMIZED
    Extended quality_metric options:
      - 'avg_return' (existing)
      - 'median_return'
      - 'positive_pct'
      - 'sharpe'
      - 'cap_weighted_return'
      - 'cap_weighted_positive_pct'
      - 'cap_weighted_sharpe'
    If a cap-weighted metric is requested but market_caps_df is None, falls back to non-weighted version.
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
        
        # Prepare market cap weights if available
        if market_caps_df is not None:
            if 'Date' in market_caps_df.columns:
                # Time-series: average cap within block per security
                block_caps = market_caps_df[market_caps_df['Date'].isin(cluster_prices.index)]
                avg_caps = block_caps.groupby('Symbol')['MarketCap'].mean()
            else:
                avg_caps = market_caps_df.groupby('Symbol')['MarketCap'].last()
            # Align to cluster securities
            caps_aligned = avg_caps.reindex(cluster_prices.columns)
            # Replace missing caps with median to avoid null weights
            caps_aligned = caps_aligned.fillna(caps_aligned.median())
            # Normalize weights
            cap_weights = caps_aligned / caps_aligned.sum() if caps_aligned.sum() > 0 else None
        else:
            cap_weights = None

        for idx_security, security in enumerate(cluster_prices.columns):
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
            arr_returns = np.array(returns_list)
            if cap_weights is not None:
                # Build weight array matching returns order
                weights = cap_weights.values if cap_weights is not None else None
            else:
                weights = None
            metric = quality_metric
            if metric == 'avg_return':
                score = arr_returns.mean()
            elif metric == 'median_return':
                score = np.median(arr_returns)
            elif metric == 'positive_pct':
                score = (arr_returns > 0).sum() / len(arr_returns) * 100
            elif metric == 'sharpe' and len(volatilities) > 0:
                score = arr_returns.mean() / np.mean(volatilities) if np.mean(volatilities) > 0 else 0
            elif metric == 'cap_weighted_return' and weights is not None and len(weights) == len(arr_returns):
                score = np.sum(arr_returns * weights)
            elif metric == 'cap_weighted_positive_pct' and weights is not None and len(weights) == len(arr_returns):
                pos = (arr_returns > 0).astype(float)
                score = np.sum(pos * weights) * 100
            elif metric == 'cap_weighted_sharpe' and weights is not None and len(weights) == len(arr_returns) and len(volatilities) > 0:
                weighted_return = np.sum(arr_returns * weights)
                avg_vol = np.mean(volatilities)
                score = weighted_return / avg_vol if avg_vol > 0 else 0
            else:
                # Fallback
                if metric.startswith('cap_weighted'):
                    score = arr_returns.mean()  # fallback if caps missing
                else:
                    score = arr_returns.mean()
            cluster_quality[cluster_id] = score
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
    """Calculate returns after dropout/acquisition events - OPTIMIZED"""
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
                            min_quality_change=5,
                            market_caps_df=None):
    """Test a specific parameter combination for dropout detection - OPTIMIZED"""
    
    # Preload data (cached, only loads once)
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
                clusters, price_data, clean_securities, quality_metric, market_caps_df=market_caps_df
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

def optimize_dropout_detection(data_file,
                               block_sizes=[100, 125, 150],
                               num_blocks_list=[10],
                               distance_thresholds=[40, 50, 60],
                               quality_metrics=['avg_return', 'median_return'],
                               quality_threshold_percentiles=[70, 75, 80],
                               forward_window=500):
    """
    Optimize parameters for dropout detection strategy - MEMORY-SAFE VERSION
    
    No multiprocessing to avoid memory explosion
    """
    
    # Preload data ONCE before all tests
    print("="*80)
    print("DROPOUT STRATEGY PARAMETER OPTIMIZATION - MEMORY-SAFE VERSION")
    print("="*80)
    _, closing_table = load_data_once(data_file)
    
    total_timepoints = len(closing_table)
    usable_timepoints = total_timepoints - forward_window
    
    print(f"Total timepoints: {total_timepoints}")
    print(f"Forward return window: {forward_window}")
    print(f"Usable timepoints for blocks: {usable_timepoints}")
    
    # Generate all parameter combinations
    all_combinations = list(product(
        block_sizes,
        num_blocks_list,
        distance_thresholds,
        quality_metrics,
        quality_threshold_percentiles
    ))
    
    # Filter out unsafe combinations
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
    print(f"Expected time: ~{total_combinations * 0.5:.0f}-{total_combinations * 1.0:.0f} seconds")
    print("="*80)
    
    results = []
    start_time = time.time()
    
    # Sequential processing (memory-safe)
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
            quality_threshold_percentile=quality_percentile,
            market_caps_df=load_market_caps()  # lazy load once
        )
        
        if result:
            results.append(result)
            iter_time = time.time() - iter_start
            elapsed = time.time() - start_time
            avg_time = elapsed / idx
            remaining = (total_combinations - idx) * avg_time
            print(f"  → Events: {result['Num_Dropout_Events']}, "
                  f"Avg return: {result['Dropout_Avg_Return']:.2f}%, "
                  f"Time: {iter_time:.1f}s (Est. remaining: {remaining/60:.1f}m)")
        
        # Periodic garbage collection to prevent memory buildup
        if idx % 10 == 0:
            gc.collect()
    
    total_time = time.time() - start_time
    
    # Convert to DataFrame
    summary_df = pd.DataFrame(results)
    
    # Save results
    summary_df.to_csv('dropout_optimization_results_extended.csv', index=False)
    print(f"\nResults saved to: dropout_optimization_results_extended.csv")
    
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
    # Total: 2557, Forward: 500, Usable: 2057
    # 8×150✓, 8×175✓, 8×200✓, 10×150✓, 10×175✓, 10×200✓, 12×150✓
    
    print("Running EXTENDED BOUNDARY optimization test (MEMORY-SAFE VERSION)...")
    summary_df = optimize_dropout_detection(
        data_file,
        block_sizes=[150, 175, 200],
        num_blocks_list=[8, 10, 12],
        distance_thresholds=[25, 30, 35, 40],
        quality_metrics=['avg_return', 'median_return'],
        quality_threshold_percentiles=[70, 75, 80],
        forward_window=500
    )
    
    return summary_df

if __name__ == "__main__":
    summary_df = main()
