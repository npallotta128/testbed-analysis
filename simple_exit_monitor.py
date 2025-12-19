"""
Simplified Position Exit Monitor for Monte Carlo Integration

This version stores purchase information at initialization and only needs
current cluster/quality data for exit checks.
"""

import pandas as pd
from typing import Optional


class SimplePositionExitMonitor:
    """
    Simplified exit monitor that stores purchase info and checks exit signals.
    """
    
    def __init__(
        self,
        purchase_cluster_id: int,
        purchase_quality: float,
        purchase_date: pd.Timestamp,
        quality_threshold: float = 0.0,
        max_hold_days: int = 500
    ):
        """
        Parameters:
            purchase_cluster_id: Cluster ID where position was opened
            purchase_quality: Quality of cluster at purchase
            purchase_date: Date position was opened
            quality_threshold: Minimum quality to stay in position
            max_hold_days: Maximum hold period
        """
        self.purchase_cluster_id = purchase_cluster_id
        self.purchase_quality = purchase_quality
        self.purchase_date = pd.Timestamp(purchase_date)
        self.quality_threshold = quality_threshold
        self.max_hold_days = max_hold_days
    
    def check_exit_signal(
        self,
        current_date: pd.Timestamp,
        current_cluster_id: Optional[int] = None,
        current_quality: Optional[float] = None
    ) -> str:
        """
        Check if position should exit based on dynamic signals.
        
        Parameters:
            current_date: Current trading date
            current_cluster_id: Current cluster membership (None if dropped out entirely)
            current_quality: Current cluster quality
        
        Returns:
            Exit signal string: 'HOLDING', 'DROPOUT', 'QUALITY_COLLAPSE', or 'MAX_HOLD'
        """
        
        days_held = (pd.Timestamp(current_date) - self.purchase_date).days
        
        # Signal 1: DROPOUT - Security changed clusters
        if self.purchase_cluster_id != current_cluster_id:
            return "DROPOUT"
        
        # Signal 2: QUALITY_COLLAPSE - Cluster quality dropped below threshold
        if current_quality is not None and current_quality < self.quality_threshold:
            return "QUALITY_COLLAPSE"
        
        # Signal 3: MAX_HOLD - Held for maximum period
        if days_held >= self.max_hold_days:
            return "MAX_HOLD"
        
        # No exit signal
        return "HOLDING"
