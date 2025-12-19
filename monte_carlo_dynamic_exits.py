"""
Dynamic Exit Signals for Cluster Jumping Strategy

Implements intelligent position exit logic during the holding period:
1. Dropout Detection: Security exits the high-quality cluster it was bought from
2. Quality Collapse: Cluster quality drops below threshold  
3. Hold Fallback: 250d default hold if no exit triggered

This module extends monte_carlo_scalability.py with dynamic exit signals
instead of fixed 250-day holds.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta


class PositionExitMonitor:
    """
    Tracks cluster membership, quality changes, and price movements
    to determine optimal position exit timing.
    """
    
    def __init__(
        self,
        quality_threshold: float = 0.0,
        max_hold_days: int = 500
    ):
        """
        Parameters:
            quality_threshold: Minimum quality to consider cluster "safe"
            max_hold_days: Maximum hold period regardless of signals
        """
        self.quality_threshold = quality_threshold
        self.max_hold_days = max_hold_days
    
    def check_exit_signal(
        self,
        position: Dict,
        current_date: pd.Timestamp,
        current_price: float,
        cluster_quality: float,
        cluster_membership: set,
        purchase_cluster_id: int,
        current_cluster_id: Optional[int] = None
    ) -> Tuple[bool, str, float]:
        """
        Evaluate if position should be exited based on multiple signals.
        
        Parameters:
            position: Dict with entry_date, entry_price, cluster_id
            current_date: Current trading date
            current_price: Current security price
            cluster_quality: Quality score of cluster position is currently in
            cluster_membership: Current set of securities in cluster
            purchase_cluster_id: Cluster ID where security was purchased
            current_cluster_id: Current cluster ID (may differ from purchase cluster)
        
        Returns:
            (should_exit, reason, exit_price)
            - should_exit: Boolean whether to exit
            - reason: String explaining exit reason
            - exit_price: Price at which to exit (typically current_price)
        """
        
        entry_date = pd.Timestamp(position['entry_date'])
        entry_price = position['entry_price']
        days_held = (current_date - entry_date).days
        
        # Signal 1: Dropout Detection
        # Security no longer in cluster it was purchased from
        if purchase_cluster_id != current_cluster_id:
            return True, "DROPOUT: Security exited cluster", current_price
        
        # Signal 2: Quality Collapse
        # Cluster quality drops below safe threshold
        if cluster_quality < self.quality_threshold:
            return True, f"QUALITY_COLLAPSE: Cluster quality {cluster_quality:.1f} < {self.quality_threshold:.1f}", current_price
        
        # Signal 3: Max Hold Time
        # Reached maximum hold period
        if days_held >= self.max_hold_days:
            return True, f"MAX_HOLD: {days_held} days reached", current_price
        
        # No exit signal triggered
        return False, "HOLDING", current_price
    
    def evaluate_position_exit_metrics(
        self,
        positions: List[Dict],
        price_data: pd.DataFrame,
        cluster_history: Dict[Tuple[pd.Timestamp, int], set],
        cluster_quality_history: Dict[Tuple[pd.Timestamp, int], float],
        exit_analysis_path: Optional[str] = None
    ) -> Tuple[List[Dict], pd.DataFrame]:
        """
        Analyze exit signals for all positions across entire simulation.
        
        Parameters:
            positions: List of position dicts with entry_date, entry_price, security, cluster_id
            price_data: DataFrame with Date, Ticker, Close columns
            cluster_history: Dict[(date, cluster_id)] -> set of securities in cluster
            cluster_quality_history: Dict[(date, cluster_id)] -> quality score
            exit_analysis_path: Optional path to save exit analysis CSV
        
        Returns:
            (exits, exit_summary_df)
            - exits: List of exit records with timing and reason
            - exit_summary_df: DataFrame with aggregated exit statistics
        """
        
        exits = []
        exit_summary = []
        
        for pos in positions:
            security = pos['security']
            entry_date = pd.Timestamp(pos['entry_date'])
            entry_price = pos['entry_price']
            purchase_cluster = pos['cluster_id']
            
            # Get security's price history from entry date
            sec_prices = price_data[price_data['Ticker'] == security].copy()
            sec_prices = sec_prices.sort_values('Date')
            sec_prices = sec_prices[sec_prices['Date'] >= entry_date]
            
            if len(sec_prices) == 0:
                continue
            
            exited = False
            
            for _, row in sec_prices.iterrows():
                current_date = pd.Timestamp(row['Date'])
                current_price = row['Close']
                
                # Find cluster membership and quality at this date
                current_cluster_id = None
                cluster_quality = 0
                
                # Look up cluster info (would come from actual cluster assignments)
                key = (current_date, purchase_cluster)
                if key in cluster_quality_history:
                    cluster_quality = cluster_quality_history[key]
                
                # Check exit signals
                should_exit, reason, exit_price = self.check_exit_signal(
                    position=pos,
                    current_date=current_date,
                    current_price=current_price,
                    cluster_quality=cluster_quality,
                    cluster_membership=set(),
                    purchase_cluster_id=purchase_cluster,
                    current_cluster_id=current_cluster_id
                )
                
                if should_exit:
                    days_held = (current_date - entry_date).days
                    pnl = (exit_price - entry_price) / entry_price * 100
                    
                    exit_record = {
                        'Security': security,
                        'Entry_Date': entry_date,
                        'Entry_Price': entry_price,
                        'Exit_Date': current_date,
                        'Exit_Price': exit_price,
                        'Days_Held': days_held,
                        'PnL_%': pnl,
                        'Exit_Reason': reason,
                        'Entry_Cluster': purchase_cluster
                    }
                    
                    exits.append(exit_record)
                    exit_summary.append({
                        'Reason': reason.split(':')[0],
                        'Count': 1,
                        'Avg_Days_Held': days_held,
                        'Avg_PnL_%': pnl
                    })
                    
                    exited = True
                    break
            
            if not exited:
                # Reached end of data without exit signal
                last_price = sec_prices.iloc[-1]['Close']
                last_date = pd.Timestamp(sec_prices.iloc[-1]['Date'])
                days_held = (last_date - entry_date).days
                pnl = (last_price - entry_price) / entry_price * 100
                
                exit_record = {
                    'Security': security,
                    'Entry_Date': entry_date,
                    'Entry_Price': entry_price,
                    'Exit_Date': last_date,
                    'Exit_Price': last_price,
                    'Days_Held': days_held,
                    'PnL_%': pnl,
                    'Exit_Reason': 'DATA_END',
                    'Entry_Cluster': purchase_cluster
                }
                
                exits.append(exit_record)
        
        # Aggregate exit summary
        if exits:
            exits_df = pd.DataFrame(exits)
            
            # Group by exit reason
            summary_agg = exits_df.groupby('Exit_Reason').agg({
                'Security': 'count',
                'Days_Held': 'mean',
                'PnL_%': ['mean', 'median', 'std']
            }).rename(columns={'Security': 'Count'})
            
            if exit_analysis_path:
                exits_df.to_csv(exit_analysis_path, index=False)
        else:
            exits_df = pd.DataFrame()
            summary_agg = pd.DataFrame()
        
        return exits, exits_df


def compare_exit_strategies(
    fixed_hold_returns: List[float],
    dynamic_exit_returns: List[float],
    output_path: Optional[str] = None
) -> Dict:
    """
    Compare performance of fixed 250-day hold vs. dynamic exit strategy.
    
    Parameters:
        fixed_hold_returns: List of returns from fixed 250d hold strategy
        dynamic_exit_returns: List of returns from dynamic exit strategy
        output_path: Optional path to save comparison
    
    Returns:
        Dict with comparison statistics
    """
    
    fixed_array = np.array(fixed_hold_returns)
    dynamic_array = np.array(dynamic_exit_returns)
    
    comparison = {
        'Fixed_Hold_Mean': float(np.mean(fixed_array)),
        'Dynamic_Exit_Mean': float(np.mean(dynamic_array)),
        'Mean_Improvement_%': float((np.mean(dynamic_array) - np.mean(fixed_array)) / abs(np.mean(fixed_array)) * 100),
        
        'Fixed_Hold_Median': float(np.median(fixed_array)),
        'Dynamic_Exit_Median': float(np.median(dynamic_array)),
        'Median_Improvement_%': float((np.median(dynamic_array) - np.median(fixed_array)) / abs(np.median(fixed_array)) * 100),
        
        'Fixed_Hold_Std': float(np.std(fixed_array)),
        'Dynamic_Exit_Std': float(np.std(dynamic_array)),
        'Std_Reduction_%': float((1 - np.std(dynamic_array) / np.std(fixed_array)) * 100),
        
        'Fixed_Hold_Sharpe': float(np.mean(fixed_array) / np.std(fixed_array)) if np.std(fixed_array) > 0 else 0,
        'Dynamic_Exit_Sharpe': float(np.mean(dynamic_array) / np.std(dynamic_array)) if np.std(dynamic_array) > 0 else 0,
        
        'Fixed_Hold_Win_%': float((fixed_array > 0).sum() / len(fixed_array) * 100),
        'Dynamic_Exit_Win_%': float((dynamic_array > 0).sum() / len(dynamic_array) * 100),
        
        'Sample_Size': len(fixed_array)
    }
    
    if output_path:
        pd.DataFrame([comparison]).to_csv(output_path, index=False)
    
    return comparison


def generate_exit_summary_report(
    exits_df: pd.DataFrame,
    output_path: Optional[str] = None
) -> str:
    """
    Generate human-readable summary of exit signals across all positions.
    """
    
    if len(exits_df) == 0:
        return "No exits recorded."
    
    report = []
    report.append("=" * 80)
    report.append("DYNAMIC EXIT STRATEGY - SUMMARY REPORT")
    report.append("=" * 80)
    report.append("")
    
    # Overall statistics
    report.append(f"Total Positions Exited: {len(exits_df)}")
    report.append(f"Avg Days Held: {exits_df['Days_Held'].mean():.1f}")
    report.append(f"Avg PnL: {exits_df['PnL_%'].mean():.2f}%")
    report.append(f"Median PnL: {exits_df['PnL_%'].median():.2f}%")
    report.append(f"Win Rate: {(exits_df['PnL_%'] > 0).sum() / len(exits_df) * 100:.1f}%")
    report.append("")
    
    # Breakdown by exit reason
    report.append("Exit Reasons Breakdown:")
    report.append("-" * 80)
    
    for reason in exits_df['Exit_Reason'].unique():
        subset = exits_df[exits_df['Exit_Reason'] == reason]
        report.append(f"\n  {reason}:")
        report.append(f"    Count: {len(subset)}")
        report.append(f"    Avg Hold: {subset['Days_Held'].mean():.1f} days")
        report.append(f"    Avg PnL: {subset['PnL_%'].mean():.2f}%")
        report.append(f"    Win Rate: {(subset['PnL_%'] > 0).sum() / len(subset) * 100:.1f}%")
    
    report_str = "\n".join(report)
    
    if output_path:
        with open(output_path, 'w') as f:
            f.write(report_str)
    
    return report_str
