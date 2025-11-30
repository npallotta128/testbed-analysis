import pandas as pd
import numpy as np

def load_data():
    acquisitions = pd.read_csv('cluster_acquisition_events.csv')
    assignments = pd.read_csv('detailed_cluster_assignments.csv')
    characteristics = pd.read_csv('cluster_characteristics.csv')
    returns = pd.read_csv('post_clustering_returns.csv')
    return acquisitions, assignments, characteristics, returns

def prepare(acquisitions, assignments):
    # Standardize column names for merge
    acquisitions = acquisitions.rename(columns={'Block': 'Block_ID'})
    # Drop rows missing Security or Block_ID
    acquisitions = acquisitions.dropna(subset=['Security', 'Block_ID'])
    # Ensure numeric types where applicable
    for col in ['Prev_Quality', 'New_Quality', 'Quality_Jump', 'Final_Return']:
        if col in acquisitions.columns:
            acquisitions[col] = pd.to_numeric(acquisitions[col], errors='coerce')
    merged = acquisitions.merge(assignments, on=['Security', 'Block_ID'], how='left')
    return merged

def cluster_level_summary(merged):
    grp = merged.groupby(['Block_ID', 'Cluster_ID'])
    summary = grp.agg(
        Acquisition_Count=('Security', 'count'),
        Avg_Quality_Jump=('Quality_Jump', 'mean'),
        Median_Quality_Jump=('Quality_Jump', 'median'),
        Avg_Final_Return=('Final_Return', 'mean'),
        Median_Final_Return=('Final_Return', 'median')
    ).reset_index()
    return summary

def integrate_characteristics(summary, characteristics):
    # Merge on block and cluster
    integrated = summary.merge(
        characteristics[['Block_ID','Cluster_ID','Cluster_Size','Post_Clustering_Avg_Return','Post_Clustering_Median_Return']],
        on=['Block_ID','Cluster_ID'],
        how='left'
    )
    return integrated

def compute_correlations(integrated):
    cols = {
        'Acquisition_Count':'Post_Clustering_Avg_Return',
        'Avg_Quality_Jump':'Post_Clustering_Avg_Return',
        'Median_Quality_Jump':'Post_Clustering_Avg_Return',
        'Avg_Final_Return':'Post_Clustering_Avg_Return',
        'Median_Final_Return':'Post_Clustering_Avg_Return'
    }
    results = []
    for x,y in cols.items():
        xvals = integrated[x]
        yvals = integrated[y]
        valid = (~xvals.isna()) & (~yvals.isna())
        if valid.sum() > 2:
            corr = np.corrcoef(xvals[valid], yvals[valid])[0,1]
        else:
            corr = np.nan
        results.append({'Metric': x, 'Correlation_With_'+y: corr, 'Samples': int(valid.sum())})
    return pd.DataFrame(results)

def top_clusters(integrated, n=15):
    # Score: acquisition intensity * average quality jump * post return
    score = (
        integrated['Acquisition_Count'].fillna(0) *
        integrated['Avg_Quality_Jump'].fillna(0) *
        integrated['Post_Clustering_Avg_Return'].fillna(0)
    )
    integrated = integrated.assign(Acquisition_Impact_Score=score)
    return integrated.sort_values('Acquisition_Impact_Score', ascending=False).head(n)

def main():
    acquisitions, assignments, characteristics, returns = load_data()
    merged = prepare(acquisitions, assignments)
    summary = cluster_level_summary(merged)
    integrated = integrate_characteristics(summary, characteristics)
    correlations = compute_correlations(integrated)
    leaders = top_clusters(integrated)

    summary.to_csv('cluster_acquisition_cluster_summary.csv', index=False)
    integrated.to_csv('cluster_acquisition_integrated_summary.csv', index=False)
    correlations.to_csv('cluster_acquisition_correlations.csv', index=False)
    leaders.to_csv('cluster_acquisition_top_clusters.csv', index=False)

    print("Saved: cluster_acquisition_cluster_summary.csv")
    print("Saved: cluster_acquisition_integrated_summary.csv")
    print("Saved: cluster_acquisition_correlations.csv")
    print("Saved: cluster_acquisition_top_clusters.csv")
    print("Correlation overview:\n", correlations)
    print("Top clusters by Acquisition_Impact_Score:\n", leaders[['Block_ID','Cluster_ID','Acquisition_Count','Avg_Quality_Jump','Post_Clustering_Avg_Return','Acquisition_Impact_Score']])

if __name__ == '__main__':
    main()
