"""
Optimization script for cluster dropout/acquisition event detection strategy.

IMPORTANT FINDING: Stocks that DROP OUT of high-performing clusters have been observed
to OUTPERFORM after the dropout event (counterintuitive signal).

This script tests different parameters to optimize:
1. Detection of dropout events (stocks leaving high-performing clusters)
2. Prediction strength of future positive returns after dropout
3. Cluster quality definition to maximize signal strength

Parameters to optimize:
- Block size (length of each time window)
- Number of blocks (how many periods to analyze)
- Distance threshold (clustering granularity)
- Quality forward window (how to measure cluster "quality")
- Quality threshold percentile (what defines "high-performing")
"""

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage, fcluster
from collections import defaultdict
from itertools import product
import time

def load_and_prepare_data(data_file, start_idx, block_size):
    """Load and prepare data for a specific block of timepoints"""
    data = pd.read_csv(data_file)
    
    # Create pivot table for the specific timepoint range
    end_idx = start_idx + block_size
    
    closing_table = data.pivot_table(
        index='Date', 
        columns='Symbol', 
        values='Closing', 
        aggfunc='first'
    ).iloc[start_idx:end_idx]
    
    securities = closing_table.columns.to_numpy()
    timepoints = closing_table.index.to_numpy()
    
    # Handle missing values
    closing_table = closing_table.fillna(method='ffill').fillna(method='bfill').fillna(0)
    
    # Convert to numpy array (securities x timepoints)
    price_matrix = closing_table.T.to_numpy()
    
    return price_matrix, securities, timepoints, closing_table

def perform_zscore_normalization(price_matrix, securities):
    """Perform z-score normalization on the price matrix"""
    normalized_matrix = np.zeros_like(price_matrix, dtype=float)
    
    for i, security in enumerate(securities):
        security_prices = price_matrix[i, :]
        non_zero_prices = security_prices[security_prices > 0]
        
        if len(non_zero_prices) > 1:
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
    Calculate quality score for each cluster based on WITHIN-BLOCK performance
    
    This uses only data available at the time (no forward-looking bias).
    Quality is based on how stocks performed during the block period.
    
    Quality metrics available:
    - 'avg_return': Average return within the block (default)
    - 'median_return': Median return within the block
    - 'positive_pct': % of stocks with positive returns within block
    - 'sharpe': Return/volatility ratio within block
    """
    cluster_quality = {}
    cluster_returns = {}
    
    for cluster_id, cluster_securities in clusters.items():
        positive_count = 0
        total_count = 0
        returns_list = []
        volatilities = []
        
        for security in cluster_securities:
            if security not in price_data.columns:
                continue
            
            # Get prices for this security during the block
            security_prices = price_data[security].dropna()
            
            if len(security_prices) < 20:  # Need minimum data points
                continue
            
            # Calculate return within the block (first 10% to last 10% of block)
            block_length = len(security_prices)
            start_window = int(block_length * 0.1)
            end_window = int(block_length * 0.1)
            
            # Start price: average of first 10% of block
            start_prices = security_prices.iloc[:max(start_window, 5)].values
            start_prices = start_prices[start_prices > 0]
            
            # End price: average of last 10% of block
            end_prices = security_prices.iloc[-max(end_window, 5):].values
            end_prices = end_prices[end_prices > 0]
            
            if len(start_prices) < 3 or len(end_prices) < 3:
                continue
            
            start_price = np.mean(start_prices)
            end_price = np.mean(end_prices)
            
            if start_price == 0:
                continue
            
            # Calculate return during the block
            pct_return = ((end_price - start_price) / start_price) * 100
            returns_list.append(pct_return)
            
            # Calculate volatility (standard deviation of daily returns)
            daily_returns = security_prices.pct_change().dropna() * 100
            if len(daily_returns) > 1:
                volatilities.append(daily_returns.std())
            
            # Check if positive return
            if pct_return > 0:
                positive_count += 1
            total_count += 1
        
        # Calculate quality score based on metric
        if total_count >= 5:  # Need at least 5 valid securities
            if quality_metric == 'avg_return':
                cluster_quality[cluster_id] = np.mean(returns_list)
            elif quality_metric == 'median_return':
                cluster_quality[cluster_id] = np.median(returns_list)
            elif quality_metric == 'positive_pct':
                cluster_quality[cluster_id] = (positive_count / total_count) * 100
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
    """
    Detect when stocks transition between clusters of different quality levels
    
    Returns:
    - loss_events: stocks dropping from high-quality to low-quality clusters
    - acquisition_events: stocks joining high-quality clusters from low-quality
    """
    
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
    
    # Determine quality threshold (what is "high quality"?)
    all_qualities = []
    for result in all_block_results:
        all_qualities.extend(result['cluster_quality'].values())
    
    if len(all_qualities) == 0:
        return pd.DataFrame(), pd.DataFrame()
    
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
            
            # Loss event: was in high-quality cluster, now in lower-quality
            if prev_quality >= quality_threshold and curr_quality < prev_quality:
                quality_loss = prev_quality - curr_quality
                if quality_loss >= 5:  # Minimum quality drop threshold
                    loss_events.append({
                        'Security': security,
                        'Block': curr['block'],
                        'Prev_Quality': prev_quality,
                        'New_Quality': curr_quality,
                        'Quality_Loss': quality_loss
                    })
            
            # Acquisition event: moved to higher-quality cluster
            elif curr_quality > prev_quality and curr_quality >= quality_threshold:
                quality_jump = curr_quality - prev_quality
                if quality_jump >= 5:  # Minimum quality jump threshold
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

def calculate_post_event_returns(events_df, data_file, forward_periods=500):
    """Calculate returns after dropout/acquisition events"""
    if len(events_df) == 0:
        return events_df
    
    # Load full price data
    data = pd.read_csv(data_file)
    closing_table = data.pivot_table(
        index='Date', 
        columns='Symbol', 
        values='Closing', 
        aggfunc='first'
    )
    closing_table = closing_table.fillna(method='ffill').fillna(method='bfill')
    
    returns = []
    
    for idx, row in events_df.iterrows():
        security = row['Security']
        block = row['Block']
        
        if security not in closing_table.columns:
            returns.append(np.nan)
            continue
        
        # Event happens at end of this block
        # Assume 125 timepoints per block (this should be parameterized)
        event_timepoint = (block + 1) * 125
        
        if event_timepoint >= len(closing_table) - 10:
            returns.append(np.nan)
            continue
        
        # Get price at event (average of 10 points after event)
        start_prices = []
        for i in range(10):
            idx_val = event_timepoint + i
            if idx_val < len(closing_table):
                price = closing_table[security].iloc[idx_val]
                if not pd.isna(price) and price > 0:
                    start_prices.append(price)
        
        if len(start_prices) < 5:
            returns.append(np.nan)
            continue
        
        start_price = np.mean(start_prices)
        
        # Get price after forward period
        end_timepoint = min(event_timepoint + forward_periods, len(closing_table) - 1)
        end_prices = []
        for i in range(max(0, end_timepoint - 10), end_timepoint):
            if i < len(closing_table):
                price = closing_table[security].iloc[i]
                if not pd.isna(price) and price > 0:
                    end_prices.append(price)
        
        if len(end_prices) < 5:
            returns.append(np.nan)
            continue
        
        end_price = np.mean(end_prices)
        
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
    """
    Test a specific parameter combination for dropout detection
    
    Parameters:
    -----------
    block_size : int
        Number of timepoints per block
    num_blocks : int
        Number of blocks to analyze
    distance_threshold : float
        Clustering distance threshold
    quality_metric : str
        How to measure cluster quality: 'avg_return', 'median_return', 'positive_pct', 'sharpe'
        Quality is based on within-block performance (no forward-looking bias)
    quality_threshold_percentile : float
        Percentile threshold for "high quality" clusters (75 = top 25%)
    min_quality_change : float
        Minimum quality change to count as dropout/acquisition event
    """
    
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
            
            # Calculate cluster quality scores (based on within-block performance)
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
        return None
    
    # Detect dropout and acquisition events
    loss_df, acquisition_df, quality_threshold = detect_cluster_transitions(
        all_results, quality_threshold_percentile
    )
    
    # Calculate future returns for events
    loss_df = calculate_post_event_returns(loss_df, data_file, forward_periods=500)
    acquisition_df = calculate_post_event_returns(acquisition_df, data_file, forward_periods=500)
    
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
        
        # Acquisition events (joining high-quality clusters) - SECONDARY SIGNAL
        'Num_Acquisition_Events': len(acquisition_df),
        'Acq_Avg_Return': acquisition_df['Future_Return'].mean() if len(acquisition_df) > 0 else np.nan,
        'Acq_Median_Return': acquisition_df['Future_Return'].median() if len(acquisition_df) > 0 else np.nan,
        'Acq_Positive_Pct': (acquisition_df['Future_Return'] > 0).sum() / len(acquisition_df) * 100 if len(acquisition_df) > 0 else np.nan,
        'Acq_Std_Return': acquisition_df['Future_Return'].std() if len(acquisition_df) > 0 else np.nan,
        
        # Signal strength metrics (KEY OPTIMIZATION TARGETS)
        'Dropout_Signal_Strength': (loss_df['Future_Return'].mean() / loss_df['Future_Return'].std()) if len(loss_df) > 0 and loss_df['Future_Return'].std() > 0 else np.nan,
        'Dropout_Sharpe_Like': (loss_df['Future_Return'].mean() / loss_df['Future_Return'].std()) * np.sqrt(len(loss_df)) if len(loss_df) > 0 and loss_df['Future_Return'].std() > 0 else np.nan,
        
        # Combined metrics
        'Total_Events': len(loss_df) + len(acquisition_df),
        'Avg_Clusters_Per_Block': np.mean([r['num_clusters'] for r in all_results])
    }
    
    return result, loss_df, acquisition_df

def optimize_dropout_detection(data_file,
                               block_sizes=[100, 125, 150],
                               num_blocks_list=[8, 10, 12],
                               distance_thresholds=[40, 50, 60],
                               quality_metrics=['avg_return', 'median_return'],
                               quality_threshold_percentiles=[70, 75, 80]):
    """
    Optimize parameters for dropout detection strategy
    
    PRIMARY GOAL: Find parameters that maximize POSITIVE returns after dropout events
    (Counterintuitive finding: stocks leaving high-performing clusters outperform)
    
    Quality is measured by WITHIN-BLOCK performance (no forward-looking bias):
    - avg_return: Average return during the block period
    - median_return: Median return during block (more robust to outliers)
    - positive_pct: % of stocks with positive returns in block
    - sharpe: Return/volatility ratio within block
    
    Optimization targets:
    1. Highest average return after dropout events
    2. Highest signal strength (return / volatility ratio)
    3. Sufficient number of events for statistical validity
    4. High % of dropout events with positive returns
    """
    
    print("="*80)
    print("DROPOUT STRATEGY PARAMETER OPTIMIZATION")
    print("="*80)
    print(f"Data file: {data_file}")
    print(f"Block sizes: {block_sizes}")
    print(f"Num blocks: {num_blocks_list}")
    print(f"Distance thresholds: {distance_thresholds}")
    print(f"Quality metrics: {quality_metrics}")
    print(f"Quality threshold percentiles: {quality_threshold_percentiles}")
    print("\nNOTE: Quality is measured by WITHIN-BLOCK performance (no look-ahead bias)")
    
    total_combinations = (len(block_sizes) * len(num_blocks_list) * 
                         len(distance_thresholds) * len(quality_metrics) *
                         len(quality_threshold_percentiles))
    
    print(f"Total combinations to test: {total_combinations}")
    print("="*80)
    
    start_time = time.time()
    results = []
    current = 0
    
    for params in product(block_sizes, num_blocks_list, distance_thresholds, 
                         quality_metrics, quality_threshold_percentiles):
        block_size, num_blocks, distance, quality_metric, quality_pct = params
        current += 1
        
        print(f"\n[{current}/{total_combinations}] Testing: BS={block_size}, NB={num_blocks}, "
              f"D={distance}, QM={quality_metric}, QP={quality_pct}")
        
        result, loss_df, acq_df = test_dropout_parameters(
            data_file, block_size, num_blocks, distance, quality_metric, quality_pct
        )
        
        if result is not None:
            print(f"  Dropout events: {result['Num_Dropout_Events']}, "
                  f"Avg return: {result['Dropout_Avg_Return']:.1f}%, "
                  f"Positive%: {result['Dropout_Positive_Pct']:.1f}%, "
                  f"Signal strength: {result['Dropout_Signal_Strength']:.3f}")
            print(f"  Acquisition events: {result['Num_Acquisition_Events']}, "
                  f"Avg return: {result['Acq_Avg_Return']:.1f}%, "
                  f"Positive%: {result['Acq_Positive_Pct']:.1f}%")
            
            results.append(result)
    
    # Create summary DataFrame
    summary_df = pd.DataFrame(results)
    
    # Save results
    summary_df.to_csv('dropout_optimization_results.csv', index=False)
    print("\n" + "="*80)
    print("Results saved to: dropout_optimization_results.csv")
    
    # Analysis
    print("\n" + "="*80)
    print("OPTIMIZATION ANALYSIS")
    print("="*80)
    
    print("\n" + "="*80)
    print("BEST CONFIGURATIONS FOR DROPOUT SIGNAL (PRIMARY STRATEGY)")
    print("="*80)
    
    print("\n1. By HIGHEST AVERAGE RETURN after dropout:")
    print(summary_df.nlargest(10, 'Dropout_Avg_Return')[
        ['Block_Size', 'Num_Blocks', 'Distance_Threshold', 'Quality_Metric', 
         'Quality_Threshold_Percentile', 'Num_Dropout_Events', 'Dropout_Avg_Return', 
         'Dropout_Positive_Pct', 'Dropout_Signal_Strength']
    ])
    
    print("\n2. By STRONGEST SIGNAL (highest signal-to-noise ratio):")
    valid_signal = summary_df[summary_df['Dropout_Signal_Strength'].notna()]
    if len(valid_signal) > 0:
        print(valid_signal.nlargest(10, 'Dropout_Signal_Strength')[
            ['Block_Size', 'Num_Blocks', 'Distance_Threshold', 'Quality_Metric', 
             'Quality_Threshold_Percentile', 'Num_Dropout_Events', 'Dropout_Avg_Return', 
             'Dropout_Std_Return', 'Dropout_Signal_Strength']
        ])
    
    print("\n3. By HIGHEST % POSITIVE RETURNS after dropout:")
    print(summary_df.nlargest(10, 'Dropout_Positive_Pct')[
        ['Block_Size', 'Num_Blocks', 'Distance_Threshold', 'Quality_Metric', 
         'Quality_Threshold_Percentile', 'Num_Dropout_Events', 'Dropout_Avg_Return', 
         'Dropout_Positive_Pct']
    ])
    
    print("\n4. By MEDIAN RETURN (more robust to outliers):")
    print(summary_df.nlargest(10, 'Dropout_Median_Return')[
        ['Block_Size', 'Num_Blocks', 'Distance_Threshold', 'Quality_Metric', 
         'Quality_Threshold_Percentile', 'Num_Dropout_Events', 'Dropout_Median_Return', 
         'Dropout_Avg_Return']
    ])
    
    print("\n5. BALANCED: Good returns + sufficient events:")
    # Score: avg_return * sqrt(num_events) / std_return (Sharpe-like with sample size)
    summary_df['Quality_Score'] = summary_df['Dropout_Sharpe_Like']
    valid_quality = summary_df[summary_df['Quality_Score'].notna() & (summary_df['Num_Dropout_Events'] >= 50)]
    if len(valid_quality) > 0:
        print(valid_quality.nlargest(10, 'Quality_Score')[
            ['Block_Size', 'Num_Blocks', 'Distance_Threshold', 'Quality_Metric', 
             'Quality_Threshold_Percentile', 'Num_Dropout_Events', 'Dropout_Avg_Return', 
             'Dropout_Positive_Pct', 'Quality_Score']
        ])
    
    print("\n" + "="*80)
    print("ACQUISITION EVENTS (SECONDARY ANALYSIS)")
    print("="*80)
    print("\nBest configurations for acquisition events:")
    print(summary_df.nlargest(5, 'Acq_Avg_Return')[
        ['Block_Size', 'Num_Blocks', 'Distance_Threshold', 'Quality_Metric', 
         'Quality_Threshold_Percentile', 'Num_Acquisition_Events', 'Acq_Avg_Return', 
         'Acq_Positive_Pct']
    ])
    
    total_time = time.time() - start_time
    print(f"\n{'='*80}")
    print(f"Total optimization time: {total_time:.2f} seconds")
    print(f"Average time per configuration: {total_time/total_combinations:.2f} seconds")
    print(f"{'='*80}")
    
    return summary_df

def main():
    """Main function"""
    data_file = 'data.csv'
    
    # Choose your optimization level:
    
    # OPTION 1: Quick test (18 combinations, ~8-12 minutes)
    # Tests one block configuration with varying quality metrics
    # print("Running QUICK optimization test...")
    # summary_df = optimize_dropout_detection(
    #     data_file,
    #     block_sizes=[125],
    #     num_blocks_list=[10],
    #     distance_thresholds=[40, 50, 60],
    #     quality_metrics=['avg_return', 'median_return'],
    #     quality_threshold_percentiles=[70, 75, 80]
    # )
    
    # OPTION 2: Extended optimization (108 combinations, ~45-60 minutes)
    # Tests EXTENDED ranges beyond previous boundaries to find true optimal
    # Previous optimal was at boundaries: Block_Size=150 (ceiling), Distance=40 (floor)
    # This extends Block_Size UP to 200 (data limit: 2557/10=255) and Distance DOWN to 25
    print("Running EXTENDED BOUNDARY optimization test...")
    summary_df = optimize_dropout_detection(
        data_file,
        block_sizes=[150, 175, 200],  # Extended from ceiling at 150 (max 255 with 10 blocks)
        num_blocks_list=[8, 10, 12],  # Test variation in block count
        distance_thresholds=[25, 30, 35, 40],  # Extended down from floor at 40
        quality_metrics=['avg_return', 'median_return'],
        quality_threshold_percentiles=[70, 75, 80]
    )
    
    # OPTION 3: Comprehensive test (600 combinations, ~3-5 hours)
    # Tests all parameter combinations including all quality metrics
    # print("Running COMPREHENSIVE optimization...")
    # summary_df = optimize_dropout_detection(
    #     data_file,
    #     block_sizes=[75, 100, 125, 150, 200],
    #     num_blocks_list=[8, 10, 12],
    #     distance_thresholds=[30, 40, 50, 60, 75],
    #     quality_metrics=['avg_return', 'median_return', 'positive_pct', 'sharpe'],
    #     quality_threshold_percentiles=[65, 70, 75, 80, 85]
    # )
    
    return summary_df

if __name__ == "__main__":
    summary_df = main()
