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

# Configuration
CACHE_DIR = 'cache'
USE_CACHE = True
NUM_PROCESSES = min(6, mp.cpu_count())
BLOCK_SIZE = 150  # First 150 timepoints per block (optimized from 125)
DISTANCE_THRESHOLD = 40  # Optimized from 50 for more granular clustering
NUM_BLOCKS = 10  # This will give us 1500 timepoints total (150 * 10)

def create_cache_dir():
    """Create cache directory if it doesn't exist"""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)

def get_cache_filename(prefix, block_id):
    """Generate cache filename for block-based processing"""
    return os.path.join(CACHE_DIR, f"{prefix}_block_{block_id}.pkl")

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

def load_and_prepare_data(data_file, start_idx, block_size):
    """Load and prepare data for a specific block of timepoints"""
    print(f"Loading data for timepoints {start_idx} to {start_idx + block_size - 1}...")
    
    # Load the full dataset
    data = pd.read_csv(data_file)
    
    # Create pivot table for the specific timepoint range
    end_idx = start_idx + block_size
    
    # Pivot to get closing prices with Date as index and Symbol as columns
    closing_table = data.pivot_table(
        index='Date', 
        columns='Symbol', 
        values='Closing', 
        aggfunc='first'
    ).iloc[start_idx:end_idx]
    
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

def process_single_block(args):
    """Process a single block of timepoints"""
    block_id, start_timepoint, data_file = args
    
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
        
        # Step 1: Load and prepare data
        price_matrix, securities, timepoints = load_and_prepare_data(
            data_file, start_timepoint, BLOCK_SIZE
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
        return None

def analyze_cluster_evolution(all_results):
    """Analyze how clusters evolve across blocks"""
    print(f"\n{'='*60}")
    print("CLUSTER EVOLUTION ANALYSIS")
    print(f"{'='*60}")
    
    # Track securities across blocks
    security_cluster_history = defaultdict(list)
    
    # Collect cluster assignments for each security across blocks
    for result in all_results:
        if result is None:
            continue
            
        block_id = result['block_id']
        clusters = result['clusters']
        
        # Create reverse mapping: security -> cluster_id
        security_to_cluster = {}
        for cluster_id, securities in clusters.items():
            for security in securities:
                security_to_cluster[security] = cluster_id
        
        # Record cluster assignment for each security
        for security in result['securities']:
            cluster_id = security_to_cluster.get(security, -1)  # -1 for unclustered
            security_cluster_history[security].append((block_id, cluster_id))
    
    # Analyze stability
    stable_securities = {}
    volatile_securities = {}
    
    for security, history in security_cluster_history.items():
        if len(history) >= 3:  # Security appears in at least 3 blocks
            cluster_ids = [cluster_id for _, cluster_id in history]
            unique_clusters = set(cluster_ids)
            
            if len(unique_clusters) <= 2:
                stable_securities[security] = history
            else:
                volatile_securities[security] = history
    
    print(f"Securities with stable clustering: {len(stable_securities)}")
    print(f"Securities with volatile clustering: {len(volatile_securities)}")
    
    # Show examples
    print(f"\nStable securities examples:")
    for i, (security, history) in enumerate(list(stable_securities.items())[:5]):
        cluster_sequence = [cluster_id for _, cluster_id in history]
        print(f"  {security}: {cluster_sequence}")
    
    print(f"\nVolatile securities examples:")
    for i, (security, history) in enumerate(list(volatile_securities.items())[:5]):
        cluster_sequence = [cluster_id for _, cluster_id in history]
        print(f"  {security}: {cluster_sequence}")
    
    return security_cluster_history, stable_securities, volatile_securities

def calculate_post_clustering_returns(data_file, all_results, forward_periods=500):
    """Calculate percent returns for each stock over forward_periods after clustering"""
    print(f"\n{'='*60}")
    print("CALCULATING POST-CLUSTERING RETURNS")
    print(f"{'='*60}")
    print(f"Forward periods to analyze: {forward_periods}")
    
    # Load the full dataset
    print("Loading full dataset...")
    data = pd.read_csv(data_file)
    
    # Create pivot table with all data
    closing_table = data.pivot_table(
        index='Date', 
        columns='Symbol', 
        values='Closing', 
        aggfunc='first'
    )
    
    # Handle missing values
    closing_table = closing_table.fillna(method='ffill').fillna(method='bfill')
    
    # Get the last timepoint used in clustering
    last_clustering_timepoint = max(result['end_timepoint'] for result in all_results if result)
    
    print(f"Last clustering timepoint: {last_clustering_timepoint}")
    print(f"Analyzing returns from timepoint {last_clustering_timepoint + 1} to {last_clustering_timepoint + forward_periods}")
    
    # Calculate returns for all securities using averaged prices
    returns_data = []
    
    # Check if we have enough data for the forward period
    max_available_periods = len(closing_table) - last_clustering_timepoint - 1
    actual_forward_periods = min(forward_periods, max_available_periods)
    
    if actual_forward_periods < 20:
        print(f"Warning: Only {actual_forward_periods} periods available, need at least 20 for robust calculation")
        return pd.DataFrame()
    
    print(f"Actual forward periods available: {actual_forward_periods}")
    
    for result in all_results:
        if result is None:
            continue
        
        block_id = result['block_id']
        
        # For each cluster in this block
        for cluster_id, securities in result['clusters'].items():
            for security in securities:
                if security not in closing_table.columns:
                    continue
                
                # Get the initial price as average of first 10 data points in the 500-period window
                initial_prices = []
                for i in range(10):
                    idx = last_clustering_timepoint + 1 + i
                    if idx < len(closing_table):
                        price = closing_table.loc[closing_table.index[idx], security]
                        if not pd.isna(price) and price > 0:
                            initial_prices.append(price)
                
                if len(initial_prices) < 5:  # Need at least 5 valid prices
                    continue
                
                start_price = np.mean(initial_prices)
                
                # Get the end price as average of last 10 data points in the 500-period window
                end_prices = []
                for i in range(10):
                    idx = last_clustering_timepoint + actual_forward_periods - 9 + i
                    if idx < len(closing_table):
                        price = closing_table.loc[closing_table.index[idx], security]
                        if not pd.isna(price) and price > 0:
                            end_prices.append(price)
                
                if len(end_prices) < 5:  # Need at least 5 valid prices
                    continue
                
                end_price = np.mean(end_prices)
                
                # Skip if start price is zero
                if start_price == 0:
                    continue
                
                # Calculate percent return using averaged prices
                percent_return = ((end_price - start_price) / start_price) * 100
                
                returns_data.append({
                    'Security': security,
                    'Block_ID': block_id,
                    'Cluster_ID': cluster_id,
                    'Forward_Periods': actual_forward_periods,
                    'Start_Price_Avg': start_price,
                    'End_Price_Avg': end_price,
                    'Percent_Return': percent_return,
                    'Initial_Prices_Count': len(initial_prices),
                    'End_Prices_Count': len(end_prices)
                })
    
    # Create DataFrame
    returns_df = pd.DataFrame(returns_data)
    
    if len(returns_df) > 0:
        # Save detailed returns
        returns_df.to_csv('post_clustering_returns.csv', index=False)
        print(f"Detailed returns saved to: post_clustering_returns.csv")
        
        # Create summary statistics by security
        security_summary = returns_df.groupby('Security').agg({
            'Percent_Return': ['mean', 'std', 'min', 'max', 'count'],
            'Block_ID': 'first',
            'Cluster_ID': 'first',
            'Start_Price_Avg': 'first',
            'End_Price_Avg': 'first'
        }).reset_index()
        
        security_summary.columns = ['Security', 'Mean_Return', 'Std_Return', 'Min_Return', 
                                     'Max_Return', 'Num_Periods', 'Block_ID', 'Cluster_ID',
                                     'Start_Price_Avg', 'End_Price_Avg']
        security_summary = security_summary.sort_values('Mean_Return', ascending=False)
        security_summary.to_csv('post_clustering_returns_summary.csv', index=False)
        print(f"Returns summary saved to: post_clustering_returns_summary.csv")
        
        # Print top performers
        print(f"\nTop 10 securities by mean return:")
        print(security_summary.head(10)[['Security', 'Mean_Return', 'Start_Price_Avg', 'End_Price_Avg', 'Cluster_ID']])
        
        print(f"\nBottom 10 securities by mean return:")
        print(security_summary.tail(10)[['Security', 'Mean_Return', 'Start_Price_Avg', 'End_Price_Avg', 'Cluster_ID']])
        
        # Cluster-level summary
        cluster_summary = returns_df.groupby(['Block_ID', 'Cluster_ID']).agg({
            'Percent_Return': ['mean', 'std', 'count'],
            'Security': 'nunique'
        }).reset_index()
        
        cluster_summary.columns = ['Block_ID', 'Cluster_ID', 'Mean_Return', 'Std_Return', 
                                    'Num_Observations', 'Num_Securities']
        cluster_summary = cluster_summary.sort_values('Mean_Return', ascending=False)
        cluster_summary.to_csv('post_clustering_cluster_returns.csv', index=False)
        print(f"Cluster returns saved to: post_clustering_cluster_returns.csv")
        
        print(f"\nCluster performance summary:")
        print(cluster_summary)
        
    else:
        print("No return data calculated - check data availability")
    
    return returns_df

def analyze_top_performers_cluster_evolution(all_results, returns_df, top_percentile=1):
    """Analyze how top performing stocks moved between clusters across blocks"""
    print(f"\n{'='*60}")
    print(f"TOP {top_percentile}% PERFORMERS - CLUSTER EVOLUTION ANALYSIS")
    print(f"{'='*60}")
    
    if len(returns_df) == 0:
        print("No returns data available for analysis")
        return None
    
    # Identify top performers (highest percentile by return)
    threshold = np.percentile(returns_df['Percent_Return'], 100 - top_percentile)
    top_performers = returns_df[returns_df['Percent_Return'] >= threshold]['Security'].unique()
    
    print(f"Return threshold for top {top_percentile}%: {threshold:.2f}%")
    print(f"Number of top performing securities: {len(top_performers)}")
    
    # Track cluster assignments for top performers across all blocks
    cluster_evolution_data = []
    
    for security in top_performers:
        cluster_history = []
        
        for result in sorted(all_results, key=lambda x: x['block_id'] if x else float('inf')):
            if result is None:
                continue
            
            block_id = result['block_id']
            
            # Find which cluster this security belongs to in this block
            found_cluster = None
            for cluster_id, securities in result['clusters'].items():
                if security in securities:
                    found_cluster = cluster_id
                    break
            
            if found_cluster is not None:
                cluster_history.append({
                    'Block_ID': block_id,
                    'Cluster_ID': found_cluster
                })
        
        # Calculate cluster stability metrics
        if len(cluster_history) > 0:
            cluster_ids = [item['Cluster_ID'] for item in cluster_history]
            unique_clusters = len(set(cluster_ids))
            cluster_changes = sum(1 for i in range(1, len(cluster_ids)) if cluster_ids[i] != cluster_ids[i-1])
            
            # Get return info
            security_return = returns_df[returns_df['Security'] == security]['Percent_Return'].iloc[0]
            
            for item in cluster_history:
                cluster_evolution_data.append({
                    'Security': security,
                    'Block_ID': item['Block_ID'],
                    'Cluster_ID': item['Cluster_ID'],
                    'Total_Blocks_Appeared': len(cluster_history),
                    'Unique_Clusters': unique_clusters,
                    'Cluster_Changes': cluster_changes,
                    'Stability_Score': 1.0 - (cluster_changes / max(len(cluster_history) - 1, 1)),
                    'Percent_Return': security_return
                })
    
    evolution_df = pd.DataFrame(cluster_evolution_data)
    
    if len(evolution_df) > 0:
        # Save detailed evolution
        evolution_df.to_csv('top_performers_cluster_evolution.csv', index=False)
        print(f"Detailed evolution saved to: top_performers_cluster_evolution.csv")
        
        # Create summary by security
        summary_data = []
        for security in top_performers:
            sec_data = evolution_df[evolution_df['Security'] == security]
            if len(sec_data) > 0:
                cluster_sequence = sec_data.sort_values('Block_ID')['Cluster_ID'].tolist()
                summary_data.append({
                    'Security': security,
                    'Percent_Return': sec_data['Percent_Return'].iloc[0],
                    'Blocks_Appeared': sec_data['Total_Blocks_Appeared'].iloc[0],
                    'Unique_Clusters': sec_data['Unique_Clusters'].iloc[0],
                    'Cluster_Changes': sec_data['Cluster_Changes'].iloc[0],
                    'Stability_Score': sec_data['Stability_Score'].iloc[0],
                    'Cluster_Sequence': str(cluster_sequence)
                })
        
        summary_df = pd.DataFrame(summary_data)
        summary_df = summary_df.sort_values('Percent_Return', ascending=False)
        summary_df.to_csv('top_performers_summary.csv', index=False)
        print(f"Summary saved to: top_performers_summary.csv")
        
        # Print insights
        print(f"\n{'='*60}")
        print("TOP PERFORMERS INSIGHTS")
        print(f"{'='*60}")
        
        print(f"\nMost stable top performers (fewest cluster changes):")
        print(summary_df.nsmallest(10, 'Cluster_Changes')[['Security', 'Percent_Return', 'Cluster_Changes', 'Cluster_Sequence']])
        
        print(f"\nMost volatile top performers (most cluster changes):")
        print(summary_df.nlargest(10, 'Cluster_Changes')[['Security', 'Percent_Return', 'Cluster_Changes', 'Cluster_Sequence']])
        
        # Analyze cluster patterns
        avg_stability = summary_df['Stability_Score'].mean()
        avg_changes = summary_df['Cluster_Changes'].mean()
        avg_unique = summary_df['Unique_Clusters'].mean()
        
        print(f"\n{'='*60}")
        print("AGGREGATE STATISTICS")
        print(f"{'='*60}")
        print(f"Average stability score: {avg_stability:.3f}")
        print(f"Average cluster changes: {avg_changes:.2f}")
        print(f"Average unique clusters: {avg_unique:.2f}")
        
        # Cluster distribution analysis
        print(f"\n{'='*60}")
        print("CLUSTER DISTRIBUTION ACROSS BLOCKS")
        print(f"{'='*60}")
        
        cluster_size_evolution = []
        
        for block_id in sorted(evolution_df['Block_ID'].unique()):
            block_data = evolution_df[evolution_df['Block_ID'] == block_id]
            cluster_counts = block_data['Cluster_ID'].value_counts().sort_index()
            print(f"\nBlock {block_id}:")
            print(f"  Top performers distributed across {len(cluster_counts)} clusters")
            print(f"  Cluster distribution: {dict(cluster_counts.head(5))}")
            
            # Track size for each cluster
            for cluster_id, count in cluster_counts.items():
                cluster_size_evolution.append({
                    'Block_ID': block_id,
                    'Cluster_ID': cluster_id,
                    'Top_Performer_Count': count
                })
        
        # Create cluster size evolution DataFrame
        cluster_size_df = pd.DataFrame(cluster_size_evolution)
        
        # Pivot to show cluster sizes across blocks
        if len(cluster_size_df) > 0:
            pivot_table = cluster_size_df.pivot(index='Cluster_ID', columns='Block_ID', values='Top_Performer_Count')
            pivot_table = pivot_table.fillna(0).astype(int)
            
            # Calculate changes between blocks
            change_columns = {}
            block_ids = sorted(pivot_table.columns)
            for i in range(1, len(block_ids)):
                prev_block = block_ids[i-1]
                curr_block = block_ids[i]
                change_col_name = f'Change_{prev_block}_to_{curr_block}'
                change_columns[change_col_name] = pivot_table[curr_block] - pivot_table[prev_block]
            
            # Combine with pivot table
            for col_name, col_data in change_columns.items():
                pivot_table[col_name] = col_data
            
            # Calculate total variance and metrics
            block_cols = [col for col in pivot_table.columns if not str(col).startswith('Change_')]
            pivot_table['Total_Top_Performers'] = pivot_table[block_cols].sum(axis=1)
            pivot_table['Avg_Per_Block'] = pivot_table[block_cols].mean(axis=1)
            pivot_table['Std_Dev'] = pivot_table[block_cols].std(axis=1)
            pivot_table['Max_Change'] = max([abs(pivot_table[col]).max() for col in change_columns.keys()])
            
            # Sort by total top performers
            pivot_table = pivot_table.sort_values('Total_Top_Performers', ascending=False)
            
            # Save cluster size evolution
            pivot_table.to_csv('top_performers_cluster_size_evolution.csv')
            print(f"\nCluster size evolution saved to: top_performers_cluster_size_evolution.csv")
            
            # Display summary
            print(f"\n{'='*60}")
            print("CLUSTER SIZE EVOLUTION SUMMARY")
            print(f"{'='*60}")
            print(pivot_table)
            
            # Analyze patterns
            print(f"\n{'='*60}")
            print("CLUSTER DYNAMICS")
            print(f"{'='*60}")
            
            # Clusters with most consistent counts
            consistent_clusters = pivot_table.nsmallest(5, 'Std_Dev')[['Total_Top_Performers', 'Avg_Per_Block', 'Std_Dev']]
            print(f"\nMost consistent clusters (low variance):")
            print(consistent_clusters)
            
            # Clusters with most variable counts
            variable_clusters = pivot_table.nlargest(5, 'Std_Dev')[['Total_Top_Performers', 'Avg_Per_Block', 'Std_Dev']]
            print(f"\nMost variable clusters (high variance):")
            print(variable_clusters)
            
            # Track inflows and outflows
            print(f"\n{'='*60}")
            print("CLUSTER CHANGES (INFLOWS/OUTFLOWS)")
            print(f"{'='*60}")
            
            for cluster_id in pivot_table.index[:10]:  # Top 10 clusters by total
                change_cols = [col for col in pivot_table.columns if str(col).startswith('Change_')]
                changes = pivot_table.loc[cluster_id, change_cols]
                
                positive_changes = changes[changes > 0].sum()
                negative_changes = abs(changes[changes < 0].sum())
                net_change = changes.sum()
                
                print(f"\nCluster {cluster_id}:")
                print(f"  Total inflows: +{positive_changes:.0f}")
                print(f"  Total outflows: -{negative_changes:.0f}")
                print(f"  Net change: {net_change:+.0f}")
                print(f"  Average per block: {pivot_table.loc[cluster_id, 'Avg_Per_Block']:.1f}")
        
        return evolution_df, summary_df
    else:
        print("No cluster evolution data found for top performers")
        return None, None

def save_comprehensive_results(all_results, evolution_analysis):
    """Save comprehensive results to files"""
    print(f"\nSaving comprehensive results...")
    
    # Save block-by-block results
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
    block_df.to_csv('block_clustering_summary.csv', index=False)
    print(f"Block summary saved to: block_clustering_summary.csv")
    
    # Save detailed cluster information
    detailed_clusters = []
    for result in all_results:
        if result is None:
            continue
            
        for cluster_id, securities in result['clusters'].items():
            for security in securities:
                detailed_clusters.append({
                    'Block_ID': result['block_id'],
                    'Cluster_ID': cluster_id,
                    'Security': security,
                    'Cluster_Size': len(securities)
                })
    
    detailed_df = pd.DataFrame(detailed_clusters)
    detailed_df.to_csv('detailed_cluster_assignments.csv', index=False)
    print(f"Detailed clusters saved to: detailed_cluster_assignments.csv")
    
    # Save evolution analysis
    security_history, stable_securities, volatile_securities = evolution_analysis
    
    stability_data = []
    for security, history in security_history.items():
        cluster_changes = len(set([cluster_id for _, cluster_id in history]))
        stability_data.append({
            'Security': security,
            'Blocks_Appeared': len(history),
            'Unique_Clusters': cluster_changes,
            'Stability_Score': 1.0 / cluster_changes if cluster_changes > 0 else 0,
            'Classification': 'Stable' if security in stable_securities else 'Volatile'
        })
    
    stability_df = pd.DataFrame(stability_data)
    stability_df.to_csv('security_stability_analysis.csv', index=False)
    print(f"Stability analysis saved to: security_stability_analysis.csv")

def main():
    """Main function for block-based clustering strategy"""
    
    create_cache_dir()
    
    # Configuration
    data_file = 'data.csv'
    start_timepoint = 1
    
    print(f"{'='*80}")
    print("BLOCK-BASED CLUSTERING STRATEGY")
    print(f"{'='*80}")
    print(f"Block size: {BLOCK_SIZE} timepoints")
    print(f"Number of blocks: {NUM_BLOCKS}")
    print(f"Total timepoints: {NUM_BLOCKS * BLOCK_SIZE}")
    print(f"Distance threshold: {DISTANCE_THRESHOLD}")
    print(f"Parallel processes: {NUM_PROCESSES}")
    print(f"Cache enabled: {USE_CACHE}")
    
    start_time = time.time()
    
    # Prepare arguments for parallel processing
    args_list = []
    for block_id in range(NUM_BLOCKS):
        block_start = start_timepoint + (block_id * BLOCK_SIZE)
        args_list.append((block_id, block_start, data_file))
    
    all_results = []
    
    # Process blocks in parallel
    with ProcessPoolExecutor(max_workers=NUM_PROCESSES) as executor:
        future_to_block = {
            executor.submit(process_single_block, args): args[0] 
            for args in args_list
        }
        
        for future in as_completed(future_to_block):
            block_id = future_to_block[future]
            try:
                result = future.result()
                if result is not None:
                    all_results.append(result)
                
                elapsed = time.time() - start_time
                print(f"Completed block {block_id} - Total time: {elapsed:.2f}s")
                
            except Exception as e:
                print(f"Block {block_id} failed: {e}")
    
    # Sort results by block_id
    all_results.sort(key=lambda x: x['block_id'] if x else float('inf'))
    
    # Analyze cluster evolution
    evolution_analysis = analyze_cluster_evolution(all_results)
    
    # Save comprehensive results
    save_comprehensive_results(all_results, evolution_analysis)
    
    # Calculate post-clustering returns (500 timepoints forward)
    returns_df = calculate_post_clustering_returns(data_file, all_results, forward_periods=500)
    
    # Analyze cluster evolution for top performers
    if len(returns_df) > 0:
        top_perf_evolution, top_perf_summary = analyze_top_performers_cluster_evolution(
            all_results, returns_df, top_percentile=1
        )
    
    # Final summary
    end_time = time.time()
    total_duration = end_time - start_time
    
    print(f"\n{'='*80}")
    print("BLOCK-BASED CLUSTERING COMPLETE!")
    print(f"{'='*80}")
    print(f"Total execution time: {total_duration:.2f} seconds")
    print(f"Blocks processed: {len(all_results)}")
    print(f"Average time per block: {total_duration/len(all_results):.2f} seconds")
    
    # Summary statistics
    total_securities = sum(result['num_securities'] for result in all_results if result)
    total_clusters = sum(result['num_clusters'] for result in all_results if result)
    
    print(f"\nSUMMARY STATISTICS:")
    print(f"Total securities processed: {total_securities}")
    print(f"Total clusters found: {total_clusters}")
    print(f"Average securities per block: {total_securities/len(all_results):.1f}")
    print(f"Average clusters per block: {total_clusters/len(all_results):.1f}")
    
    print(f"\nResults saved:")
    print(f"  - block_clustering_summary.csv")
    print(f"  - detailed_cluster_assignments.csv") 
    print(f"  - security_stability_analysis.csv")
    print(f"  - post_clustering_returns.csv")
    print(f"  - post_clustering_returns_summary.csv")
    print(f"  - post_clustering_cluster_returns.csv")
    print(f"  - top_performers_cluster_evolution.csv")
    print(f"  - top_performers_summary.csv")
    print(f"  - top_performers_cluster_size_evolution.csv")

if __name__ == "__main__":
    main()