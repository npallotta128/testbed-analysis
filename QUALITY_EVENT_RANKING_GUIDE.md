## Quality Event Ranking Guide

### Purpose
Rank securities based on the structure and impact of quality-related clustering events (acquisition quality jumps and dropout/loss quality declines) over the available block timeframe. This complements raw return metrics by emphasizing sustained quality improvements and resilience to quality losses.

### Source Files
Input datasets:
- `cluster_acquisition_events.csv` (Security, Block, Prev_Quality, New_Quality, Quality_Jump, Final_Return)
- `cluster_loss_events.csv` (Security, Block, Prev_Quality, New_Quality, Quality_Loss, Final_Return)
- `detailed_cluster_assignments.csv` (Block_ID, Cluster_ID, Security)

### Key Aggregations (Per Security)
- Acquisition_Event_Count: Number of acquisition (quality jump) events.
- Acquisition_Quality_Jump_Sum / Avg / Max.
- Acquisition_Final_Return_Mean / Median: Average/median of associated event final returns (if available).
- Loss_Event_Count: Number of dropout / quality loss events.
- Loss_Quality_Loss_Sum / Avg / Max.
- Loss_Final_Return_Mean / Median.
- Total_Event_Count = Acquisition_Event_Count + Loss_Event_Count.
- Net_Quality_Delta = Acquisition_Quality_Jump_Sum − Loss_Quality_Loss_Sum.
- Event_Balance_Ratio = Acquisition_Event_Count / Total_Event_Count (stability vs vulnerability proportion).
- Weighted_Avg_Final_Return = (Acq_mean * Acq_count + Loss_mean * Loss_count) / Total_Event_Count.
- Quality_Momentum_Score = Net_Quality_Delta × (Acquisition_Final_Return_Median − Loss_Final_Return_Median). Captures interaction of structural improvement and differential performance.
- Unique_Clusters / Unique_Blocks: Breadth of clustering contexts where events occurred.
- Events_Per_Block = Total_Event_Count / Unique_Blocks (intensity normalized by exposure).

### Percentile Transform & Composite Rank
For comparability across differently scaled features, select core metrics and convert to percentile ranks:
- Net_Quality_Delta_Percentile
- Quality_Momentum_Score_Percentile
- Weighted_Avg_Final_Return_Percentile
- Event_Balance_Ratio_Percentile
- Events_Per_Block_Percentile

Composite_Quality_Event_Rank = 0.25·Net_Quality_Delta + 0.25·Quality_Momentum_Score + 0.20·Weighted_Avg_Final_Return + 0.15·Event_Balance_Ratio + 0.15·Events_Per_Block (all are percentile values). Weights emphasize sustainable quality improvement and relative momentum while still incorporating breadth and intensity.

### Interpreting the Rankings
- A high Net_Quality_Delta with moderate Event_Balance_Ratio suggests net improvement even if losses occur.
- Extreme Weighted_Avg_Final_Return may reflect a few outliers—inspect median values for robustness.
- High Events_Per_Block indicates frequent structural reclassification; may signal volatility rather than quality—cross-check with momentum score.
- Low Loss_Event_Count combined with steady acquisition jumps often correlates with smoother forward performance regimes.

### Caveats
- Final_Return fields can be skewed by extreme outliers; consider winsorizing for risk-sensitive applications.
- Quality metrics assume numeric comparability across blocks; regime shifts in quality scale could bias jumps.
- Missing Final_Return values are treated as 0 in aggregations only where necessary; future refinement should separate missing vs true zero.
- Cluster assignment breadth does not currently weight cluster quality or size—future enhancement could incorporate cluster-level post return averages.

### Planned Enhancements
1. Outlier Handling: Introduce winsorized and log-transformed return variants, update momentum score accordingly.
2. Temporal Decay: Apply exponential decay to older events (recent improvements weighted more heavily).
3. Regime Segmentation: Recompute percentiles within volatility regimes or blocks to reduce cross-period bias.
4. Cluster Quality Overlay: Multiply Net_Quality_Delta by average cluster post-clustering returns where events occurred.
5. Sharpe-Like Adjustment: Divide momentum score by variability of event returns to prefer consistency.

### Implemented Enhancements (Current Version)
The enhanced script `analyze_quality_event_ranking.py` now includes:
- Winsorization of event-level final returns at 1% / 99% to dampen extreme outliers before aggregate statistics.
- Recency weighting using exponential decay: weight = exp(-λ*(max_block - Block_ID)), with default λ = 0.05.
- Recency-weighted quality delta metrics (`Net_Quality_Delta_Recency`) and winsorized return metrics (`Weighted_Winsor_Final_Return_Recency`).
- Adjusted momentum score (`Quality_Momentum_Score_Adj`) combining recency-weighted net quality change and robust (winsor median) return differential.
- Updated composite rank emphasizing recency-adjusted and outlier-robust metrics.

### New Key Columns
- `Acq_Winsor_Mean_Return` / `Loss_Winsor_Mean_Return`: Winsorized mean event returns.
- `Acq_Recency_Weighted_Jump_Sum` / `Loss_Recency_Weighted_Loss_Sum`: Decay-weighted sums of quality changes.
- `Net_Quality_Delta_Recency`: Recency-weighted net improvement.
- `Weighted_Winsor_Final_Return_Recency`: Combined recency-weighted, winsorized return performance.
- `Quality_Momentum_Score_Adj`: Robust momentum integrating recency and outlier control.

### Adjusting Parameters
Modify at top of script:
```python
WINSOR_LOWER = 0.01
WINSOR_UPPER = 0.99
DECAY_LAMBDA = 0.05
```
Lowering `DECAY_LAMBDA` (e.g., 0.02) spreads weight more evenly across historical blocks. Raising it (e.g., 0.1) concentrates ranking on the most recent block transitions.

### Suggested Next Extensions
- Dual-horizon scoring: Include both short-term (high decay) and long-term (low decay) composite ranks.
- Stability factor: Penalize very high Event_Balance_Ratio if accompanied by elevated volatility in returns.
- Cross-sectional normalization by cluster average return percentile to reduce cluster composition bias.


### Market Capitalization Integration (Future Data Needed)
When market cap becomes available:
- Size-Adjusted Quality: Normalize each quality jump by log(cap) or cap percentile to reward meaningful improvements in larger companies.
- Cap-Weighted Momentum: Quality_Momentum_Score × sqrt(cap_percentile) to modestly scale durable improvements in scalable names.
- Risk Buckets: Segment rankings into micro/small/mid/large cap tiers; recompute composite ranks within each tier to avoid small-cap bias.
- Dilution Check: Penalize securities with frequent high jumps but negligible market cap growth (possible illiquidity or data artifacts).

### Usage
Run:
```bash
python analyze_quality_event_ranking.py
```
Outputs:
- `quality_event_security_rankings.csv` (full metrics & ranks)
- `quality_event_top100.csv` (top composite ranks)
- `quality_event_leaderboard.csv` (concise leader snapshot)

### Next Steps for You
- Review top 50 for manual validation against qualitative expectations.
- Decide on outlier handling and temporal decay policy.
- Provide market cap data source spec so integration logic can be prototyped.

---
For adjustments or additional ranking dimensions (e.g., volatility suppression, drawdown resilience), request an extension and the script can be updated incrementally.
