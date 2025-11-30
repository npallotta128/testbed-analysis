import cuml
from cuml.cluster import AgglomerativeClustering
import numpy as np
from scipy.stats import zscore
from collections import Counter
import pandas as pd
import cupy as cp
import time

def detailed_clustering_test(start_timepoint, data):
    """Detailed test of clustering behavior for a single timepoint"""
    current_start_timepoint = start_timepoint
    end_timepoint = current_start_timepoint + 2001
    
    try:
        # Basic data preparation
        closing_table = data.pivot_table(index='Date', columns='Symbol', values='Closing', aggfunc='first').iloc[current_start_timepoint:end_timepoint]
        
        if closing_table.shape[0] < 2001:
            return f"Timepoint {start_timepoint}: Insufficient data ({closing_table.shape[0]} rows)"
        
        variable_names = closing_table.columns.to_numpy()
        
        closing_table.reset_index(drop=True, inplace=True)
        closing_table = closing_table.fillna(0).T.to_numpy()
        
        # Normalization
        means = np.mean(closing_table[:, :1501], axis=1, keepdims=True)
        stds = np.std(closing_table[:, :1501], axis=1, keepdims=True)
        stds = np.where(stds == 0, 1e-8, stds)
        
        normalized_data = np.copy(closing_table)
        normalized_data[:, :1501] = (closing_table[:, :1501] - means) / stds
        normalized_data[:, 1501:] = (closing_table[:, 1501:] - means) / stds
        
        finite_mask = np.all(np.isfinite(normalized_data), axis=1)
        normalized_data = normalized_data[finite_mask]
        variable_names = variable_names[finite_mask]
        
        print(f"\nTimepoint {start_timepoint} detailed analysis:")
        print(f"  Variables after filtering: {normalized_data.shape[0]}")
        print(f"  Data shape for clustering: {normalized_data[:, :1501].shape}")
        
        # Test different clustering parameters
        cluster_configs = [
            (5, 'single'),
            (10, 'single'), 
            (15, 'single'),
            (20, 'single')
        ]
        
        best_config = None
        best_distribution = None
        
        for n_clusters, linkage in cluster_configs:
            clustering_model = AgglomerativeClustering(n_clusters=n_clusters, linkage=linkage)
            clusters = clustering_model.fit_predict(cp.asarray(normalized_data[:, :1501]))
            clusters = cp.asnumpy(clusters)
            
            cluster_counts = Counter(clusters)
            large_clusters = [cluster for cluster, count in cluster_counts.items() if count >= 40]
            
            print(f"  {n_clusters} clusters: {len(large_clusters)} large clusters")
            print(f"    Distribution: {dict(sorted(cluster_counts.items()))}")
            
            # Check if this gives a better distribution
            if len(large_clusters) > 1:
                if best_config is None or len(large_clusters) > len(best_distribution):
                    best_config = (n_clusters, linkage)
                    best_distribution = large_clusters
        
        # Also test the data characteristics
        print(f"  Data statistics for first 1501 timepoints:")
        data_for_clustering = normalized_data[:, :1501]
        print(f"    Mean range: {np.mean(data_for_clustering, axis=1).min():.3f} to {np.mean(data_for_clustering, axis=1).max():.3f}")
        print(f"    Std range: {np.std(data_for_clustering, axis=1).min():.3f} to {np.std(data_for_clustering, axis=1).max():.3f}")
        print(f"    Data variance across variables: {np.var(np.mean(data_for_clustering, axis=1)):.6f}")
        
        # Sample a few time series to see if they're actually different
        if normalized_data.shape[0] >= 5:
            sample_indices = np.random.choice(normalized_data.shape[0], 5, replace=False)
            print(f"  Sample time series means (first 1501 points):")
            for i, idx in enumerate(sample_indices):
                ts_mean = np.mean(data_for_clustering[idx])
                ts_std = np.std(data_for_clustering[idx])
                print(f"    Series {idx}: mean={ts_mean:.3f}, std={ts_std:.3f}")
        
        return best_config, len(best_distribution) if best_distribution else 0
        
    except Exception as e:
        print(f"  Error: {str(e)}")
        return None, 0

def quick_cluster_test(start_timepoint, data):
    """Quick test just to get cluster counts"""
    current_start_timepoint = start_timepoint
    end_timepoint = current_start_timepoint + 2001
    
    try:
        closing_table = data.pivot_table(index='Date', columns='Symbol', values='Closing', aggfunc='first').iloc[current_start_timepoint:end_timepoint]
        
        if closing_table.shape[0] < 2001:
            return 0, "Insufficient data"
        
        closing_table.reset_index(drop=True, inplace=True)
        closing_table = closing_table.fillna(0).T.to_numpy()
        
        means = np.mean(closing_table[:, :1501], axis=1, keepdims=True)
        stds = np.std(closing_table[:, :1501], axis=1, keepdims=True)
        stds = np.where(stds == 0, 1e-8, stds)
        
        normalized_data = np.copy(closing_table)
        normalized_data[:, :1501] = (closing_table[:, :1501] - means) / stds
        normalized_data[:, 1501:] = (closing_table[:, 1501:] - means) / stds
        
        finite_mask = np.all(np.isfinite(normalized_data), axis=1)
        normalized_data = normalized_data[finite_mask]
        
        # Try with 15 clusters to see if we get better distribution
        clustering_model = AgglomerativeClustering(n_clusters=15, linkage='single')
        clusters = clustering_model.fit_predict(cp.asarray(normalized_data[:, :1501]))
        clusters = cp.asnumpy(clusters)
        
        cluster_counts = Counter(clusters)
        large_clusters = [cluster for cluster, count in cluster_counts.items() if count >= 40]
        
        return len(large_clusters), dict(sorted(cluster_counts.items()))
        
    except Exception as e:
        return 0, f"Error: {str(e)}"

# Load data
print("Loading data...")
data = pd.read_csv('data.csv')
print(f"Data shape: {data.shape}")

# Test range around timepoint 100
test_range = range(90, 111)

print(f"\nQuick scan of timepoints {test_range.start} to {test_range.stop-1}:")
print("="*70)

results = []
for timepoint in test_range:
    large_cluster_count, distribution = quick_cluster_test(timepoint, data)
    results.append((timepoint, large_cluster_count, distribution))
    
    if isinstance(distribution, dict):
        max_cluster_size = max(distribution.values())
        total_vars = sum(distribution.values())
        print(f"Timepoint {timepoint:3d}: {large_cluster_count} large clusters, "
              f"largest={max_cluster_size:5d}/{total_vars:5d} ({max_cluster_size/total_vars*100:.1f}%)")
    else:
        print(f"Timepoint {timepoint:3d}: {distribution}")

# Find the best timepoints for detailed analysis
print(f"\nDetailed analysis of promising timepoints:")
print("="*50)

# Test timepoints with the most large clusters
best_timepoints = sorted(results, key=lambda x: x[1], reverse=True)[:3]

for timepoint, large_count, _ in best_timepoints:
    if large_count > 0:
        config, best_large_count = detailed_clustering_test(timepoint, data)
        if config:
            print(f"  Best config for timepoint {timepoint}: {config} -> {best_large_count} large clusters")

# Also test a few specific timepoints around 100
print(f"\nSpecific detailed tests:")
print("="*30)

specific_tests = [95, 100, 105]
for timepoint in specific_tests:
    detailed_clustering_test(timepoint, data)