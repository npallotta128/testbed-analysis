import pandas as pd
import os

print("="*80)
print("CLUSTERING DIAGNOSIS")
print("="*80)

# Check if cache files exist
cache_dir = 'cache'
if os.path.exists(cache_dir):
    cache_files = [f for f in os.listdir(cache_dir) if f.endswith('.pkl')]
    print(f"\nFound {len(cache_files)} cache files in {cache_dir}/")
    for f in sorted(cache_files)[:10]:
        print(f"  {f}")
    
    if len(cache_files) > 10:
        print(f"  ... and {len(cache_files) - 10} more")
else:
    print(f"\nNo cache directory found at {cache_dir}/")

# Check recent output files
output_files = {
    'block_clustering_summary.csv': 'Block-level summary',
    'detailed_cluster_assignments.csv': 'Detailed cluster assignments',
    'post_clustering_cluster_returns.csv': 'Cluster returns',
    'security_stability_analysis.csv': 'Security stability',
}

print("\n" + "="*80)
print("CHECKING OUTPUT FILES")
print("="*80)

for filename, description in output_files.items():
    if os.path.exists(filename):
        df = pd.read_csv(filename)
        print(f"\n{description} ({filename}):")
        print(f"  Rows: {len(df)}")
        print(f"  Columns: {list(df.columns)}")
        
        if filename == 'block_clustering_summary.csv':
            print("\nBlock Summary:")
            print(df.to_string(index=False))
            
            # Check for the "only one cluster" issue
            if 'Num_Clusters' in df.columns:
                num_clusters = df['Num_Clusters'].values
                print(f"\nClusters per block: {num_clusters}")
                if all(num_clusters == 1):
                    print("⚠️  WARNING: All blocks show only 1 cluster!")
                    print("   This suggests the distance threshold is too high.")
                elif all(num_clusters <= 2):
                    print("⚠️  WARNING: Very few clusters per block!")
                    print("   Consider lowering the distance threshold.")
                else:
                    print("✓ Clustering appears to be working (multiple clusters found)")
        
        elif filename == 'detailed_cluster_assignments.csv':
            print("\nCluster distribution:")
            cluster_counts = df.groupby(['Block_ID', 'Cluster_ID']).size()
            for (block_id, cluster_id), count in cluster_counts.head(20).items():
                print(f"  Block {block_id}, Cluster {cluster_id}: {count} securities")
            
            if len(cluster_counts) > 20:
                print(f"  ... and {len(cluster_counts) - 20} more clusters")
            
            # Count unique clusters per block
            clusters_per_block = df.groupby('Block_ID')['Cluster_ID'].nunique()
            print(f"\nUnique clusters per block:")
            for block_id, count in clusters_per_block.items():
                print(f"  Block {block_id}: {count} clusters")
    else:
        print(f"\n{description} ({filename}): NOT FOUND")

print("\n" + "="*80)
print("DIAGNOSIS COMPLETE")
print("="*80)

# Provide recommendations
print("\nRECOMMENDATIONS:")
print("-" * 80)

if os.path.exists('block_clustering_summary.csv'):
    df = pd.read_csv('block_clustering_summary.csv')
    if 'Num_Clusters' in df.columns:
        avg_clusters = df['Num_Clusters'].mean()
        
        if avg_clusters < 2:
            print("❌ Very few clusters found. Try:")
            print("   1. LOWER the DISTANCE_THRESHOLD (try 20, 30, or 40)")
            print("   2. Increase BLOCK_SIZE to have more data per block")
            print("   3. Run: python optimize_clustering_parameters.py")
        elif avg_clusters < 5:
            print("⚠️  Few clusters found. Consider:")
            print("   1. Lowering DISTANCE_THRESHOLD slightly")
            print("   2. Run: python optimize_clustering_parameters.py")
        else:
            print("✓ Clustering seems healthy!")
            print("   Run optimize_clustering_parameters.py to find optimal settings")
else:
    print("❌ No results found. Try:")
    print("   1. Run: python block_clustering_strategy.py")
    print("   2. Or run: python optimize_clustering_parameters.py")
    print("   3. Check if data.csv exists in the current directory")
