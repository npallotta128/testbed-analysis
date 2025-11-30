# Dropout Signal Optimization - Quick Start

## Your Finding (Counterintuitive!)
**Stocks that DROP OUT of high-performing clusters tend to OUTPERFORM afterwards**

This is the signal you want to optimize!

## What This Script Optimizes

### Primary Parameters (Clustering):
1. **Block Size** - Length of each time window (75, 100, 125, 150, 200 timepoints)
2. **Number of Blocks** - How many periods to analyze (8, 10, 12)
3. **Distance Threshold** - Clustering granularity (30, 40, 50, 60, 75)

### Secondary Parameters (Signal Definition):
4. **Quality Forward Window** - How far ahead to look when rating cluster quality (50, 75, 100, 125, 150)
5. **Quality Threshold Percentile** - What defines "high-performing" (65, 70, 75, 80, 85)

## Key Metrics to Optimize

### Signal Strength (PRIMARY):
- **Dropout_Avg_Return** - Average return after dropout (want HIGH & POSITIVE)
- **Dropout_Signal_Strength** - Return/volatility ratio (higher = more consistent)
- **Dropout_Positive_Pct** - % of dropouts with positive returns (want >60%)

### Statistical Validity:
- **Num_Dropout_Events** - Need enough events (>50 minimum, >100 ideal)
- **Dropout_Std_Return** - Lower is better (more consistent signal)

## How to Run

### Option 1: Moderate Test (RECOMMENDED - 135 combinations, ~45-60 min)
```bash
python optimize_dropout_strategy.py
```

This will test:
- 3 block sizes (100, 125, 150)
- 1 num_blocks (10)
- 3 distance thresholds (40, 50, 60)
- 3 quality windows (75, 100, 125)
- 3 quality percentiles (70, 75, 80)

### Option 2: Quick Test (27 combinations, ~10-15 min)
Edit `main()` in the script to uncomment OPTION 1

### Option 3: Comprehensive Test (540 combinations, ~3-4 hours)
Edit `main()` in the script to uncomment OPTION 3

## Output

### File: `dropout_optimization_results.csv`
Contains all configurations ranked by performance

### Console Output Shows:
1. **Highest average return** configurations
2. **Strongest signal** (best signal-to-noise)
3. **Highest % positive** returns
4. **Most robust** (median-based)
5. **Best balanced** (return × sample size / volatility)

## What to Look For

### Excellent Configuration:
```
Block_Size: 125
Num_Blocks: 10
Distance_Threshold: 50
Quality_Forward_Window: 100
Quality_Threshold_Percentile: 75

Num_Dropout_Events: 150+
Dropout_Avg_Return: +20% to +50%
Dropout_Positive_Pct: >65%
Dropout_Signal_Strength: >0.5
```

### Red Flags:
- Dropout_Avg_Return < 5% (weak signal)
- Num_Dropout_Events < 30 (insufficient data)
- Dropout_Positive_Pct < 55% (barely better than random)
- High Dropout_Std_Return (inconsistent signal)

## After Optimization

1. **Identify best configuration** from results
2. **Update your clustering script** with optimal parameters
3. **Generate dropout events** with optimal settings
4. **Backtest** the strategy
5. **Calculate position sizing** based on signal strength

## Example Interpretation

If the optimizer finds:
```
Best by Signal Strength:
Block_Size: 150
Distance_Threshold: 40
Quality_Forward_Window: 125
Quality_Threshold_Percentile: 80

Dropout_Avg_Return: +32.5%
Dropout_Signal_Strength: 0.68
Num_Dropout_Events: 180
```

This means:
- Use 150-timepoint blocks
- Cluster with distance threshold of 40
- Define quality by looking 125 timepoints forward
- Only top 20% of clusters count as "high-performing"
- Expect ~32% average return per dropout signal
- Signal has strong consistency (0.68 ratio)
- ~180 trading opportunities in your dataset
