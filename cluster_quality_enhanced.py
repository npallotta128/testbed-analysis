"""
Enhanced Cluster Quality Metric with Dropout/Acquisition Integration

Incorporates cluster stability and transition analysis to create a richer
quality score that reflects not just current returns, but also the probability
of the stock staying in (or graduating to) the high-quality cluster.

Components:
1. Base Quality: Mean return + win rate (existing metric)
2. Stability Bonus: % of securities retained across consecutive periods
3. Dropout Penalty: % of securities exiting to lower-quality clusters
4. Acquisition Bonus: % of new securities entering from lower-quality clusters
"""

import pandas as pd
import numpy as np
from collections import defaultdict
from typing import Dict, List, Tuple

def calculate_cluster_transitions(all_block_results: List[Dict]) -> Tuple[pd.DataFrame, pd.DataFrame, float]:
    """
    Calculate cluster transition events (dropout and acquisition) from block results.
    
    Returns:
        - loss_events: DataFrame of dropout events (quality loss >= 5)
        - acquisition_events: DataFrame of acquisition events (quality gain >= 5)
        - quality_threshold: 75th percentile quality across all blocks
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
    
    # Determine quality threshold
    all_qualities = []
    for result in all_block_results:
        all_qualities.extend(result['cluster_quality'].values())
    
    if len(all_qualities) == 0:
        return pd.DataFrame(), pd.DataFrame(), 0
    
    quality_threshold = np.percentile(all_qualities, 75)
    
    # Detect transitions
    for security, history in security_history.items():
        if len(history) < 2:
            continue
        
        for i in range(1, len(history)):
            prev = history[i-1]
            curr = history[i]
            
            prev_quality = prev['quality']
            curr_quality = curr['quality']
            
            # Dropout event: exit from high-quality to lower quality
            if prev_quality >= quality_threshold and curr_quality < prev_quality:
                quality_loss = prev_quality - curr_quality
                if quality_loss >= 5:
                    loss_events.append({
                        'Security': security,
                        'Block': curr['block'],
                        'Prev_Quality': prev_quality,
                        'New_Quality': curr_quality,
                        'Quality_Loss': quality_loss,
                        'Prev_Cluster': prev['cluster_id'],
                        'New_Cluster': curr['cluster_id']
                    })
            
            # Acquisition event: enter high-quality cluster from lower quality
            elif curr_quality > prev_quality and curr_quality >= quality_threshold:
                quality_jump = curr_quality - prev_quality
                if quality_jump >= 5:
                    acquisition_events.append({
                        'Security': security,
                        'Block': curr['block'],
                        'Prev_Quality': prev_quality,
                        'New_Quality': curr_quality,
                        'Quality_Jump': quality_jump,
                        'Prev_Cluster': prev['cluster_id'],
                        'New_Cluster': curr['cluster_id']
                    })
    
    loss_df = pd.DataFrame(loss_events)
    acquisition_df = pd.DataFrame(acquisition_events)
    
    return loss_df, acquisition_df, quality_threshold


def calculate_cluster_stability(all_block_results: List[Dict]) -> Dict[int, Dict]:
    """
    Calculate stability metrics for each cluster:
    - Retention rate: % of securities that stay in the cluster
    - Dropout rate: % that exit to lower quality
    - Acquisition rate: % of new securities entering
    
    Returns:
        Dict mapping cluster_id -> {'retention_rate', 'dropout_rate', 'acquisition_rate'}
    """
    # Track cluster membership across blocks
    cluster_membership = defaultdict(lambda: {'securities': set(), 'history': []})
    
    for block_id, result in enumerate(all_block_results):
        clusters = result['clusters']
        for cluster_id, securities in clusters.items():
            cluster_membership[cluster_id]['history'].append({
                'block': block_id,
                'securities': set(securities)
            })
    
    stability_metrics = {}
    
    for cluster_id, data in cluster_membership.items():
        history = data['history']
        
        if len(history) < 2:
            stability_metrics[cluster_id] = {
                'retention_rate': 0.5,  # default for single-block clusters
                'dropout_rate': 0.0,
                'acquisition_rate': 0.0,
                'observations': 1
            }
            continue
        
        retention_counts = []
        dropout_counts = []
        acquisition_counts = []
        
        for i in range(1, len(history)):
            prev_secs = history[i-1]['securities']
            curr_secs = history[i]['securities']
            
            if len(prev_secs) == 0:
                continue
            
            # Retention: what % of previous members stayed?
            retained = len(prev_secs & curr_secs)
            retention_rate = retained / len(prev_secs) if len(prev_secs) > 0 else 0
            retention_counts.append(retention_rate)
            
            # Dropout: what % of previous members left?
            dropped = len(prev_secs - curr_secs)
            dropout_rate = dropped / len(prev_secs) if len(prev_secs) > 0 else 0
            dropout_counts.append(dropout_rate)
            
            # Acquisition: what % of new members are acquisitions?
            acquired = len(curr_secs - prev_secs)
            acquisition_rate = acquired / len(curr_secs) if len(curr_secs) > 0 else 0
            acquisition_counts.append(acquisition_rate)
        
        stability_metrics[cluster_id] = {
            'retention_rate': np.mean(retention_counts) if retention_counts else 0.5,
            'dropout_rate': np.mean(dropout_counts) if dropout_counts else 0.0,
            'acquisition_rate': np.mean(acquisition_counts) if acquisition_counts else 0.0,
            'observations': len(retention_counts)
        }
    
    return stability_metrics


def adjust_cluster_quality(
    base_quality: Dict[int, float],
    stability_metrics: Dict[int, Dict],
    dropout_df: pd.DataFrame,
    acquisition_df: pd.DataFrame,
    stability_weight: float = 0.15,
    dropout_weight: float = 0.20,
    acquisition_weight: float = 0.10
) -> Dict[int, float]:
    """
    Adjust cluster quality scores based on stability and transition metrics.
    
    Formula:
        Adjusted Quality = Base Quality × (1 + Stability Bonus) × (1 - Dropout Penalty) × (1 + Acquisition Bonus)
    
    Parameters:
        base_quality: Dict[cluster_id] -> base quality score
        stability_metrics: Dict[cluster_id] -> stability stats
        dropout_df: DataFrame of dropout events
        acquisition_df: DataFrame of acquisition events
        stability_weight: Weight for retention rate bonus (default 0.15)
        dropout_weight: Weight for dropout rate penalty (default 0.20)
        acquisition_weight: Weight for acquisition rate bonus (default 0.10)
    
    Returns:
        Dict[cluster_id] -> adjusted quality score
    """
    adjusted_quality = {}
    
    for cluster_id, base_q in base_quality.items():
        if cluster_id not in stability_metrics:
            adjusted_quality[cluster_id] = base_q
            continue
        
        metrics = stability_metrics[cluster_id]
        
        # Stability bonus: high retention is good
        retention_rate = metrics['retention_rate']
        stability_bonus = retention_rate * stability_weight
        
        # Dropout penalty: high dropout is bad
        dropout_rate = metrics['dropout_rate']
        dropout_penalty = dropout_rate * dropout_weight
        
        # Acquisition bonus: high acquisition of new talent is good
        acquisition_rate = metrics['acquisition_rate']
        acquisition_bonus = acquisition_rate * acquisition_weight
        
        # Calculate adjusted quality
        adjusted_q = base_q * (1 + stability_bonus) * (1 - dropout_penalty) * (1 + acquisition_bonus)
        
        adjusted_quality[cluster_id] = max(0, adjusted_q)  # Ensure non-negative
    
    return adjusted_quality


def analyze_quality_impact(
    dropout_df: pd.DataFrame,
    acquisition_df: pd.DataFrame,
    quality_threshold: float
) -> Dict:
    """
    Analyze the performance implications of dropouts and acquisitions.
    
    Returns:
        Dict with statistics on event outcomes and returns
    """
    if len(dropout_df) == 0 and len(acquisition_df) == 0:
        return {
            'dropout_count': 0,
            'acquisition_count': 0,
            'dropout_avg_quality_loss': 0,
            'acquisition_avg_quality_gain': 0,
            'threshold': quality_threshold
        }
    
    stats = {
        'dropout_count': len(dropout_df),
        'acquisition_count': len(acquisition_df),
        'dropout_avg_quality_loss': dropout_df['Quality_Loss'].mean() if len(dropout_df) > 0 else 0,
        'acquisition_avg_quality_gain': acquisition_df['Quality_Jump'].mean() if len(acquisition_df) > 0 else 0,
        'threshold': quality_threshold,
        'dropout_high_quality_exit_%': (dropout_df['Prev_Quality'] >= quality_threshold).sum() / len(dropout_df) if len(dropout_df) > 0 else 0,
        'acquisition_entering_high_quality_%': (acquisition_df['New_Quality'] >= quality_threshold).sum() / len(acquisition_df) if len(acquisition_df) > 0 else 0
    }
    
    return stats
