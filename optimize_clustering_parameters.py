import numpy as np
from scipy.cluster.hierarchy import linkage, fcluster
from collections import defaultdict
import pandas as pd
import time
import os
from itertools import product

def load_and_prepare_data(data_file, start_idx, block_size):
    """Load and prepare data for a specific block of timepoints"""
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
    
    return price_matrix, securities, timepoints

def perform_zscore_normalization(price_matrix, securities):
    """Perform z-score normalization on the price matrix"""
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
    
    return clean_matrix, clean_securities

def perform_hierarchical_clustering(normalized_matrix, securities, distance_threshold, min_cluster_size=5):
    """Perform hierarchical clustering on normalized price data"""
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
        if len(security_list) >= min_cluster_size:
            clusters[cluster_id] = security_list
    
    return clusters, cluster_labels

def test_parameter_combination(data_file, block_size, num_blocks, distance_threshold, min_cluster_size=5):
    """Test a single parameter combination"""
    
    start_timepoint = 0
    all_clusters_found = []
    total_securities = 0
    
    # Process each block
    for block_id in range(num_blocks):
        block_start = start_timepoint + (block_id * block_size)
        
        try:
            # Load and prepare data
            price_matrix, securities, timepoints = load_and_prepare_data(
                data_file, block_start, block_size
            )
            
            # Perform z-score normalization
            normalized_matrix, clean_securities = perform_zscore_normalization(
                price_matrix, securities
            )
            
            # Perform hierarchical clustering
            clusters, cluster_labels = perform_hierarchical_clustering(
                normalized_matrix, clean_securities, distance_threshold, min_cluster_size
            )
            
            # Record results
            for cluster_id, security_list in clusters.items():
                all_clusters_found.append({
                    'Block_ID': block_id,
                    'Cluster_ID': cluster_id,
                    'Cluster_Size': len(security_list),
                    'Block_Start': block_start,
                    'Block_End': block_start + block_size - 1
                })
            
            total_securities += len(clean_securities)
            
        except Exception as e:
            print(f"Error processing block {block_id}: {str(e)}")
            continue
    
    # Calculate summary statistics
    if len(all_clusters_found) > 0:
        clusters_df = pd.DataFrame(all_clusters_found)
        
        total_clusters = len(clusters_df)
        unique_clusters_per_block = clusters_df.groupby('Block_ID')['Cluster_ID'].count()
        avg_clusters_per_block = unique_clusters_per_block.mean()
        min_clusters_per_block = unique_clusters_per_block.min()
        max_clusters_per_block = unique_clusters_per_block.max()
        avg_cluster_size = clusters_df['Cluster_Size'].mean()
        min_cluster_size_found = clusters_df['Cluster_Size'].min()
        max_cluster_size_found = clusters_df['Cluster_Size'].max()
        
        return {
            'Block_Size': block_size,
            'Num_Blocks': num_blocks,
            'Distance_Threshold': distance_threshold,
            'Total_Timepoints': block_size * num_blocks,
            'Total_Clusters': total_clusters,
            'Avg_Clusters_Per_Block': avg_clusters_per_block,
            'Min_Clusters_Per_Block': min_clusters_per_block,
            'Max_Clusters_Per_Block': max_clusters_per_block,
            'Avg_Cluster_Size': avg_cluster_size,
            'Min_Cluster_Size': min_cluster_size_found,
            'Max_Cluster_Size': max_cluster_size_found,
            'Total_Securities_Processed': total_securities,
            'Clusters_Detail': clusters_df
        }
    else:
        return {
            'Block_Size': block_size,
            'Num_Blocks': num_blocks,
            'Distance_Threshold': distance_threshold,
            'Total_Timepoints': block_size * num_blocks,
            'Total_Clusters': 0,
            'Avg_Clusters_Per_Block': 0,
            'Min_Clusters_Per_Block': 0,
            'Max_Clusters_Per_Block': 0,
            'Avg_Cluster_Size': 0,
            'Min_Cluster_Size': 0,
            'Max_Cluster_Size': 0,
            'Total_Securities_Processed': total_securities,
            'Clusters_Detail': pd.DataFrame()
        }

def optimize_parameters(data_file, 
                       block_sizes=[50, 100, 125, 150, 200],
                       num_blocks_list=[5, 10, 15, 20],
                       distance_thresholds=[20, 30, 40, 50, 60, 75, 100]):
    """
    Test different parameter combinations to find optimal clustering configuration
    
    Parameters:
    -----------
    data_file : str
        Path to the data CSV file
    block_sizes : list
        List of block sizes to test (number of timepoints per block)
    num_blocks_list : list
        List of number of blocks to test
    distance_thresholds : list
        List of distance thresholds to test for clustering
    """
    
    print("="*80)
    print("CLUSTERING PARAMETER OPTIMIZATION")
    print("="*80)
    print(f"Data file: {data_file}")
    print(f"Block sizes to test: {block_sizes}")
    print(f"Number of blocks to test: {num_blocks_list}")
    print(f"Distance thresholds to test: {distance_thresholds}")
    print(f"Total combinations: {len(block_sizes) * len(num_blocks_list) * len(distance_thresholds)}")
    print("="*80)
    
    start_time = time.time()
    results = []
    
    total_combinations = len(block_sizes) * len(num_blocks_list) * len(distance_thresholds)
    current_combination = 0
    
    # Test all combinations
    for block_size, num_blocks, distance_threshold in product(block_sizes, num_blocks_list, distance_thresholds):
        current_combination += 1
        
        print(f"\n[{current_combination}/{total_combinations}] Testing: Block Size={block_size}, Num Blocks={num_blocks}, Distance={distance_threshold}")
        print("-" * 80)
        
        result = test_parameter_combination(data_file, block_size, num_blocks, distance_threshold)
        
        # Print summary for this combination
        print(f"Results: Total Clusters={result['Total_Clusters']}, "
              f"Avg Clusters/Block={result['Avg_Clusters_Per_Block']:.1f}, "
              f"Avg Cluster Size={result['Avg_Cluster_Size']:.1f}")
        
        # Show detailed cluster breakdown
        if result['Total_Clusters'] > 0:
            print(f"Cluster distribution across blocks:")
            clusters_detail = result['Clusters_Detail']
            for block_id in sorted(clusters_detail['Block_ID'].unique()):
                block_clusters = clusters_detail[clusters_detail['Block_ID'] == block_id]
                print(f"  Block {block_id}: {len(block_clusters)} clusters, "
                      f"sizes: {block_clusters['Cluster_Size'].tolist()}")
        else:
            print("  WARNING: No clusters found!")
        
        results.append(result)
        
        elapsed = time.time() - start_time
        avg_time_per_combo = elapsed / current_combination
        remaining_combos = total_combinations - current_combination
        est_remaining_time = avg_time_per_combo * remaining_combos
        
        print(f"Progress: {current_combination}/{total_combinations} "
              f"({100*current_combination/total_combinations:.1f}%), "
              f"Elapsed: {elapsed:.1f}s, "
              f"Est. Remaining: {est_remaining_time:.1f}s")
    
    # Create summary DataFrame
    summary_df = pd.DataFrame([
        {k: v for k, v in r.items() if k != 'Clusters_Detail'}
        for r in results
    ])
    
    # Save results
    summary_df.to_csv('clustering_optimization_results.csv', index=False)
    print("\n" + "="*80)
    print("Optimization results saved to: clustering_optimization_results.csv")
    
    # Save detailed cluster information for each configuration
    all_details = []
    for i, result in enumerate(results):
        if result['Total_Clusters'] > 0:
            detail_df = result['Clusters_Detail'].copy()
            detail_df['Block_Size'] = result['Block_Size']
            detail_df['Num_Blocks'] = result['Num_Blocks']
            detail_df['Distance_Threshold'] = result['Distance_Threshold']
            detail_df['Config_ID'] = i
            all_details.append(detail_df)
    
    if all_details:
        detailed_clusters_df = pd.concat(all_details, ignore_index=True)
        detailed_clusters_df.to_csv('clustering_optimization_detailed_clusters.csv', index=False)
        print("Detailed cluster data saved to: clustering_optimization_detailed_clusters.csv")
    
    # Print analysis
    print("\n" + "="*80)
    print("OPTIMIZATION ANALYSIS")
    print("="*80)
    
    # Sort by total clusters (descending)
    print("\nTop 10 configurations by total clusters found:")
    print(summary_df.nlargest(10, 'Total_Clusters')[
        ['Block_Size', 'Num_Blocks', 'Distance_Threshold', 'Total_Clusters', 
         'Avg_Clusters_Per_Block', 'Avg_Cluster_Size']
    ])
    
    # Sort by average clusters per block
    print("\nTop 10 configurations by average clusters per block:")
    print(summary_df.nlargest(10, 'Avg_Clusters_Per_Block')[
        ['Block_Size', 'Num_Blocks', 'Distance_Threshold', 'Total_Clusters', 
         'Avg_Clusters_Per_Block', 'Avg_Cluster_Size']
    ])
    
    # Analyze by distance threshold
    print("\nAverage clusters found by distance threshold:")
    dist_analysis = summary_df.groupby('Distance_Threshold').agg({
        'Total_Clusters': 'mean',
        'Avg_Clusters_Per_Block': 'mean',
        'Avg_Cluster_Size': 'mean'
    }).round(2)
    print(dist_analysis)
    
    # Analyze by block size
    print("\nAverage clusters found by block size:")
    block_analysis = summary_df.groupby('Block_Size').agg({
        'Total_Clusters': 'mean',
        'Avg_Clusters_Per_Block': 'mean',
        'Avg_Cluster_Size': 'mean'
    }).round(2)
    print(block_analysis)
    
    # Analyze by number of blocks
    print("\nAverage clusters found by number of blocks:")
    num_blocks_analysis = summary_df.groupby('Num_Blocks').agg({
        'Total_Clusters': 'mean',
        'Avg_Clusters_Per_Block': 'mean',
        'Avg_Cluster_Size': 'mean'
    }).round(2)
    print(num_blocks_analysis)
    
    # Find configurations with good balance
    print("\nConfigurations with best balance (many clusters, reasonable size):")
    # Score based on having many clusters but not too small
    summary_df['Balance_Score'] = (
        summary_df['Avg_Clusters_Per_Block'] * 
        (summary_df['Avg_Cluster_Size'] / 100)  # Normalize cluster size
    )
    print(summary_df.nlargest(10, 'Balance_Score')[
        ['Block_Size', 'Num_Blocks', 'Distance_Threshold', 'Total_Clusters', 
         'Avg_Clusters_Per_Block', 'Avg_Cluster_Size', 'Balance_Score']
    ])
    
    total_time = time.time() - start_time
    print(f"\n{'='*80}")
    print(f"Total optimization time: {total_time:.2f} seconds")
    print(f"Average time per configuration: {total_time/total_combinations:.2f} seconds")
    print(f"{'='*80}")
    
    return summary_df, results

def main():
    """Main function"""
    data_file = 'data.csv'
    
    # Test a smaller set first (for quick testing, uncomment this)
    # summary_df, results = optimize_parameters(
    #     data_file,
    #     block_sizes=[100, 125],
    #     num_blocks_list=[5, 10],
    #     distance_thresholds=[30, 50, 75]
    # )
    
    # Full optimization (may take a while)
    summary_df, results = optimize_parameters(
        data_file,
        block_sizes=[50, 100, 125, 150, 200],
        num_blocks_list=[5, 10, 15, 20],
        distance_thresholds=[20, 30, 40, 50, 60, 75, 100]
    )
    
    return summary_df, results

if __name__ == "__main__":
    summary_df, results = main()
