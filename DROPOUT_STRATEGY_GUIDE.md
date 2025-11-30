# Cluster Dropout Strategy - Optimization Guide

## Strategy Overview

This strategy identifies **cluster transition events** as trading signals:

### 1. **Loss Events** (Potential SHORT/SELL signals)
- Stocks that **DROP OUT** of high-performing clusters
- Move from high-quality cluster → low-quality cluster
- Hypothesis: These stocks may continue underperforming

### 2. **Acquisition Events** (Potential LONG/BUY signals)
- Stocks that **JOIN** high-performing clusters  
- Move from low-quality cluster → high-quality cluster
- Hypothesis: These stocks may continue outperforming

## Your Existing Data

You already have results from a previous run:
- **`cluster_loss_events.csv`** - 2,090 dropout events
- **`cluster_acquisition_events.csv`** - 2,088 acquisition events

### Sample Loss Event:
```
Security: ARHVF
Block: 6
Previous Quality: 62.07%
New Quality: 2.99%
Quality Loss: 59.07 points
Final Return: 41.22%
```

## Optimization Parameters

The new script **`optimize_dropout_strategy.py`** tests these parameters:

### 1. **Block Size** (timepoints per block)
- Affects how frequently we check for cluster transitions
- Default test: `[100, 125, 150]`

### 2. **Number of Blocks** (temporal coverage)
- How many time periods to analyze
- Default test: `[8, 10, 12]`

### 3. **Distance Threshold** (clustering granularity)
- Lower = more clusters, more specific groups
- Default test: `[40, 50, 60]`

### 4. **Quality Forward Window** (NEW!)
- How far forward (in timepoints) to look when calculating cluster "quality"
- Quality = % of stocks in cluster with positive returns over this window
- Default test: `[50, 100, 150]`
- **Lower values** = more reactive to recent performance
- **Higher values** = more stable, long-term quality assessment

### 5. **Quality Threshold Percentile** (NEW!)
- What percentile defines a "high-quality" cluster
- 75 = top 25% of clusters by quality
- Default test: `[70, 75, 80]`
- **Lower** = more events (easier to qualify as "high quality")
- **Higher** = fewer but stronger events

## What Gets Optimized

For each parameter combination, the script measures:

### Loss Events (Dropout Signals):
- **Number of events detected**
- **Average future return** (should be negative = good short signal)
- **% with negative returns** (higher = better short signals)

### Acquisition Events (Join Signals):
- **Number of events detected**
- **Average future return** (should be positive = good long signal)  
- **% with positive returns** (higher = better long signals)

### Balance Score:
- Combined metric: (Loss_Negative_% + Acq_Positive_%) / 2
- Higher = better overall strategy

## How to Run

### Quick Test (27 combinations, ~10-15 min):
```bash
python optimize_dropout_strategy.py
```

This tests:
- 1 block size (125)
- 1 num_blocks (10)
- 3 distance thresholds (40, 50, 60)
- 3 quality windows (75, 100, 125)
- 3 quality percentiles (70, 75, 80)

### Custom Test:
```python
from optimize_dropout_strategy import optimize_dropout_detection

summary_df = optimize_dropout_detection(
    'data.csv',
    block_sizes=[125, 150],
    num_blocks_list=[10],
    distance_thresholds=[40, 50, 60],
    quality_forward_windows=[75, 100, 125],
    quality_threshold_percentiles=[75, 80]
)
```

### Full Optimization (480 combinations, ~2-3 hours):
Edit the script's `main()` function and uncomment the full optimization section.

## Output Files

### `dropout_optimization_results.csv`
Contains all tested configurations with metrics:
- Number of events (loss & acquisition)
- Average returns
- Success rates (% negative for losses, % positive for acquisitions)
- Balance scores

## Interpreting Results

### What to Look For:

**For SHORT strategy (loss events):**
- High `Loss_Negative_Pct` (>60%)
- Negative `Loss_Avg_Return` (the more negative, the better)
- Reasonable `Num_Loss_Events` (>100 for statistical validity)

**For LONG strategy (acquisition events):**
- High `Acq_Positive_Pct` (>60%)
- Positive `Acq_Avg_Return` (the higher, the better)
- Reasonable `Num_Acquisition_Events` (>100 for statistical validity)

**For COMBINED strategy:**
- High `Balance_Score` (>60)
- Both event types work well

### Example Good Configuration:
```
Block_Size: 125
Distance_Threshold: 50
Quality_Forward_Window: 100
Quality_Threshold_Percentile: 75

Loss Events: 150
Loss_Avg_Return: -15.3%
Loss_Negative_Pct: 68%

Acq Events: 140
Acq_Avg_Return: +22.1%
Acq_Positive_Pct: 71%

Balance_Score: 69.5
```

## Next Steps After Optimization

1. **Review results** in `dropout_optimization_results.csv`
2. **Identify best configuration** based on your strategy goals:
   - Pure short strategy? → Optimize for Loss events
   - Pure long strategy? → Optimize for Acquisition events
   - Long/short combined? → Optimize for Balance Score
3. **Update your main script** with optimal parameters
4. **Backtest** with optimal settings
5. **Calculate position sizing** and risk metrics

## Key Differences from Basic Clustering

**Basic clustering optimization** (optimize_clustering_parameters.py):
- Goal: Find many well-distributed clusters
- Metrics: Number of clusters, cluster sizes

**Dropout strategy optimization** (optimize_dropout_strategy.py):
- Goal: Find cluster transitions that predict future returns
- Metrics: Event count, return prediction accuracy
- **This is what you want for a trading strategy!**
