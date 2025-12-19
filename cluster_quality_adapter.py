"""
Adapter to convert jump signals DataFrame to the format expected by cluster_quality_enhanced module.
"""

import pandas as pd
import numpy as np
from typing import Dict, List

def convert_jumps_to_blocks(jumps_df: pd.DataFrame) -> List[Dict]:
    """
    Convert jump signals DataFrame to block-based format for cluster quality analysis.
    
    Args:
        jumps_df: DataFrame with columns: Symbol, Date, To_Cluster, To_Quality
        
    Returns:
        List of dicts with format: {
            'block_id': date,
            'clusters': {cluster_id: [securities]},
            'cluster_quality': {cluster_id: quality}
        }
    """
    all_block_results = []
    
    # Group by date (each date represents a "block")
    for date in sorted(jumps_df['Date'].unique()):
        date_data = jumps_df[jumps_df['Date'] == date].copy()
        
        # Group by cluster
        clusters = {}
        cluster_quality = {}
        
        for cluster_id in date_data['To_Cluster'].unique():
            if pd.isna(cluster_id):
                continue
                
            cluster_data = date_data[date_data['To_Cluster'] == cluster_id]
            securities = cluster_data['Symbol'].tolist()
            
            # Use mean of To_Quality for cluster quality
            quality = cluster_data['To_Quality'].mean()
            
            clusters[int(cluster_id)] = securities
            cluster_quality[int(cluster_id)] = quality
        
        all_block_results.append({
            'block_id': date,
            'clusters': clusters,
            'cluster_quality': cluster_quality
        })
    
    return all_block_results


def apply_quality_adjustment_to_jumps(
    jumps_df: pd.DataFrame,
    stability_metrics: Dict,
    stability_weight: float = 0.15,
    dropout_weight: float = 0.20,
    acquisition_weight: float = 0.10
) -> pd.DataFrame:
    """
    Apply cluster stability-based quality adjustments to jump signals.
    
    Formula per cluster:
        Adjusted_Quality = Base_Quality × (1 + stability_bonus) × (1 - dropout_penalty) × (1 + acquisition_bonus)
    
    Args:
        jumps_df: DataFrame with To_Cluster and To_Quality columns
        stability_metrics: Dict mapping cluster_id -> {retention_rate, dropout_rate, acquisition_rate}
        stability_weight: Weight for retention bonus
        dropout_weight: Weight for dropout penalty
        acquisition_weight: Weight for acquisition bonus
        
    Returns:
        DataFrame with new 'Adjusted_Quality' column
    """
    df = jumps_df.copy()
    
    # Create adjusted quality column
    adjusted_qualities = []
    
    for idx, row in df.iterrows():
        cluster_id = row['To_Cluster']
        base_quality = row['To_Quality']
        
        if pd.isna(cluster_id) or pd.isna(base_quality):
            adjusted_qualities.append(base_quality)
            continue
        
        cluster_id = int(cluster_id)
        
        # Get stability metrics for this cluster
        metrics = stability_metrics.get(cluster_id, {
            'retention_rate': 0.5,
            'dropout_rate': 0.0,
            'acquisition_rate': 0.0
        })
        
        # Calculate adjustment factors
        stability_bonus = stability_weight * metrics['retention_rate']
        dropout_penalty = dropout_weight * metrics['dropout_rate']
        acquisition_bonus = acquisition_weight * metrics['acquisition_rate']
        
        # Apply formula
        adjusted_quality = base_quality * (1 + stability_bonus) * (1 - dropout_penalty) * (1 + acquisition_bonus)
        adjusted_qualities.append(adjusted_quality)
    
    df['Adjusted_Quality'] = adjusted_qualities
    
    return df
