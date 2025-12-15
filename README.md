# Cluster Jump Trading Strategy

A quantitative trading strategy that identifies cluster transitions in stock price behavior using hierarchical clustering and market-cap-weighted quality metrics. The strategy achieves **77.9% win rate** with **90.27% average returns** over 250-day holding periods.

## Overview

This strategy detects when stocks transition between behavioral clusters (groups of stocks moving similarly) and trades based on the quality improvement of the new cluster. The approach combines:

- **Hierarchical clustering** (Ward linkage) to group stocks by price behavior
- **Market-cap-weighted quality metrics** to assess cluster strength
- **Cluster jump detection** to identify transition events
- **250-day forward returns** with winsorization for realistic expectations

## Performance Summary

**Backtest Results (145,028 signals, 2021-12-15 to 2025-02-25):**
- Win Rate: **77.9%**
- Average Return: **90.27%** (250-day hold, winsorized)
- Median Return: **18.70%**
- Total Signals: **145,028** across 17,360 symbols

**Monte Carlo Analysis (1,000 simulations):**
- Mean Final Capital: **$249,956** (from $100k start)
- Median Return: **90.96%**
- 90% Confidence Interval: **$129k - $482k**
- Zero losing scenarios in 1,000 runs

**Yearly Performance:**
| Year | Signals | Win Rate | Mean Return | Median Return |
|------|---------|----------|-------------|---------------|
| 2021 | 14,835  | 78.9%    | 78.74%      | 12.47%        |
| 2022 | 30,909  | 79.0%    | 77.94%      | 21.21%        |
| 2023 | 48,355  | 77.6%    | 85.73%      | 17.81%        |
| 2024 | 33,570  | 77.5%    | 102.05%     | 20.62%        |
| 2025 | 17,359  | 76.9%    | 111.97%     | 20.00%        |

## Repository Structure

### Core Strategy Files
```
├── clustering_full_jumps_checkpointed.py   # Main clustering & signal generation
├── backtest_capital_scaling.py             # Backtest across capital tiers
├── backtest_capital_equity.py              # Generate equity curves
├── monte_carlo_simulation.py               # Monte Carlo variance analysis
├── analyze_yearly_returns.py               # Yearly performance breakdown
├── build_price_cache.py                    # Build price data cache
└── ml_signal_optimizer.py                  # ML-based signal filtering (optional)
```

### Analysis & Results
```
├── MONTE_CARLO_ANALYSIS.md                 # Monte Carlo detailed analysis
├── cluster_jumps_full_250d_winsorized.csv  # Generated signals (145k)
├── backtest_capital_scaling.csv            # Backtest results
├── monte_carlo_results.csv                 # Monte Carlo outcomes
└── yearly_returns_analysis.csv             # Yearly breakdown
```

## Quick Start

### Prerequisites

```bash
# Required Python packages
pip install pandas numpy scipy scikit-learn matplotlib seaborn
```

### Data Requirements

You need two CSV files:

1. **MarketValues.csv** - Price data with columns:
   - `Symbol`: Stock ticker
   - `Date`: Trading date (YYYY-MM-DD)
   - `Close`: Closing price

2. **MarketCAPValues.csv** - Market cap data with columns:
   - `Symbol`: Stock ticker
   - `Date`: Trading date
   - `OutstandingShares`: Number of shares outstanding

Place these files in `/mnt/d/` or update the paths in the scripts.

### Step 1: Build Price Cache (Optional but Recommended)

```bash
python build_price_cache.py
```

This creates `price_data_cache.pkl` (486 MB) which speeds up processing from ~30min to ~3min.

### Step 2: Generate Cluster Jump Signals

```bash
python clustering_full_jumps_checkpointed.py
```

**What it does:**
- Loads 18,917 symbols × 2,595 dates of price data
- Runs hierarchical clustering in 10 blocks (100-day stride, 1501-day history)
- Detects cluster transitions (FROM_CLUSTER → TO_CLUSTER)
- Calculates market-cap-weighted quality metrics
- Computes 250-day forward returns
- Saves signals to `cluster_jumps_full_250d_corrected.csv`

**Runtime:** ~45-60 minutes (with cache), ~2-3 hours (without)

**Output:** CSV file with columns:
- `Symbol`, `Date`, `Block`
- `From_Cluster`, `To_Cluster`, `Jump_Type` (UP/DOWN/LATERAL)
- `From_Quality`, `To_Quality`, `Quality_Delta`
- `Cluster_Continuity` (% of stocks that stayed in To_Cluster)
- `return_250d` (forward-looking return over 250 trading days)

### Step 3: Winsorize Returns (Recommended)

The script automatically creates a winsorized version capping extreme outliers:

```python
# Already included in clustering script
df['return_250d_winsorized'] = df['return_250d'].clip(upper=df['return_250d'].quantile(0.99))
df.to_csv('cluster_jumps_full_250d_winsorized.csv', index=False)
```

### Step 4: Run Backtests

```bash
# Capital scaling across tiers ($100k, $1M, $10M, $100M)
python backtest_capital_scaling.py

# Generate equity curves
python backtest_capital_equity.py

# Monte Carlo variance analysis
python monte_carlo_simulation.py

# Yearly returns breakdown
python analyze_yearly_returns.py
```

## How the Strategy Works

### 1. Clustering Methodology

**Hierarchical Clustering (Ward Linkage):**
- Groups stocks by 1501-day price history correlation patterns
- Distance threshold: 50 (creates ~40-100 clusters per block)
- Minimum cluster size: 40 stocks
- Processes in 10 blocks with 100-day stride

### 2. Quality Metric Calculation

Each cluster's quality is measured using **market-cap-weighted metrics**:

```
Quality = (Cap-Weighted Intrablock Returns) + (Cap-Weighted Average Correlation)
```

Where:
- **Intrablock Returns**: (Last Price / First Price - 1) for each stock in the cluster
- **Cap-Weighted Correlation**: Average pairwise correlation weighted by market caps
- **Market Cap**: Calculated from OutstandingShares × Current Price

### 3. Cluster Jump Detection

A "jump" occurs when a stock changes cluster membership between consecutive blocks:

- **UP**: Quality_Delta > 0 (stock moved to higher quality cluster)
- **DOWN**: Quality_Delta < 0 (stock moved to lower quality cluster)
- **LATERAL**: Quality_Delta ≈ 0 (similar quality cluster)

### 4. Signal Classification

Signals are classified for position sizing:

- **BLUE_CHIP**: Quality_Delta > 0 AND Cluster_Continuity ≥ 0.6
  - High confidence signals (stable cluster membership)
  - Larger position size ($100k base)
  
- **SMALL_CAP_STORY**: All other signals
  - Lower confidence signals
  - Smaller position size ($20k base)

### 5. Position Sizing Rules

```python
# Base allocation
base = $100k (BLUE_CHIP) or $20k (SMALL_CAP)

# Apply constraints
size = min(
    base,
    capital * 0.05,        # Max 5% of portfolio per trade
    market_cap * 0.005     # Max 0.5% of stock's market cap (liquidity)
)
```

### 6. Portfolio Management

- **Hold Period**: 250 trading days (~1 year)
- **Max Concurrent Positions**: 20
- **Entry Sequence**: BLUE_CHIP signals processed first (by date)
- **Position Management**: Force-close oldest position if max concurrent exceeded

## Configuration Parameters

### Clustering Parameters (`clustering_full_jumps_checkpointed.py`)

```python
HISTORY_WINDOW = 1501        # Days of price history for clustering
BLOCK_STRIDE = 100           # Days between blocks
DISTANCE_THRESHOLD = 50      # Hierarchical clustering cutoff
MIN_CLUSTER_SIZE = 40        # Minimum stocks per cluster
RETURN_WINDOW = 250          # Forward-looking return period
```

### Backtest Parameters (`backtest_capital_scaling.py`)

```python
CAPITAL_TIERS = [100_000, 1_000_000, 10_000_000, 100_000_000]
PER_TRADE_BASE = 100_000     # Base allocation for BLUE_CHIP
MAX_CONCURRENT_TRADES = 20   # Maximum open positions
HOLD_DAYS = 250              # Hold period in trading days
```

### Monte Carlo Parameters (`monte_carlo_simulation.py`)

```python
N_SIMULATIONS = 1000         # Number of resampling runs
CAPITAL_TIER = 100_000       # Starting capital
RANDOM_SEED = 42             # For reproducibility
```

## Outputs

### Cluster Jump Signals
**File:** `cluster_jumps_full_250d_winsorized.csv`
- 145,028 signals
- 17,360 unique symbols
- 2021-12-15 to 2025-02-25

### Backtest Results
**File:** `backtest_capital_scaling.csv`
- Performance across 4 capital tiers
- 145,028 trades executed
- 77.9% win rate, 90.27% avg return

### Equity Curves
**File:** `equity_curves.csv`
- Daily portfolio value progression
- Separate curves for each capital tier

### Monte Carlo Results
**File:** `monte_carlo_results.csv`
- 1,000 simulation outcomes
- Distribution of returns, win rates, final capital

### Visualizations
- `monte_carlo_distributions.png` - Histograms and scatter plots
- `monte_carlo_percentiles.png` - Percentile breakdown
- `equity_curves_100k_1m.png` - Equity progression charts

## Advanced Usage

### ML Signal Filtering (Optional)

Train an XGBoost classifier to filter signals:

```bash
python ml_signal_optimizer.py
```

**Note:** In testing, ML filtering provided marginal improvement (−4.3% vs unfiltered), so the full signal set is recommended.

### Custom Analysis

Modify clustering parameters to explore:

```python
# Tighter clusters (more selective signals)
DISTANCE_THRESHOLD = 30
MIN_CLUSTER_SIZE = 60

# Longer history window (more stable clusters)
HISTORY_WINDOW = 2001

# Shorter block stride (more frequent updates)
BLOCK_STRIDE = 50
```

## Key Insights

### Why This Works

1. **Behavioral Regime Shifts**: Stocks change behavioral patterns over time
2. **Quality Improvement**: Moving to better-correlated, higher-performing clusters signals momentum
3. **Market-Cap Weighting**: Prevents small-cap distortions in quality metrics
4. **Cluster Continuity**: Filters for stable cluster membership (not noise)
5. **Diversification**: 20 concurrent positions spread across sectors/clusters

### Risk Management

- **Winsorization**: Caps extreme outliers (99th percentile at 2,491%)
- **Position Limits**: Max 5% per trade, 0.5% of stock market cap
- **Max Concurrent**: Limits exposure to 20 positions
- **Signal Priority**: BLUE_CHIP processed first (higher quality)
- **Liquidity Constraints**: Prevents over-sizing in small stocks

### Limitations

1. **Forward-Looking Bias**: Returns calculated from future data (not live tradeable)
2. **Transaction Costs**: Not included in backtest (add ~0.5-1% drag)
3. **Slippage**: Assumes fills at close prices
4. **Market Impact**: 0.5% liquidity limit may not prevent all impact
5. **Data Requirements**: Needs complete price and market cap history

## Performance Attribution

### By Jump Type
- **UP jumps** (67,325): Higher win rates, targeting quality improvement
- **DOWN jumps** (74,914): Lower but still positive returns
- **LATERAL jumps** (2,789): Mixed performance

### By Signal Type
- **BLUE_CHIP** (~40% of signals): 80%+ win rate, higher mean returns
- **SMALL_CAP_STORY** (~60% of signals): 75%+ win rate, lower variance

### By Year
Returns trending upward: 79% (2021) → 112% (2025) mean returns

## Troubleshooting

### Memory Issues
If clustering runs out of memory:
```python
# Reduce history window
HISTORY_WINDOW = 1001

# Process fewer symbols
symbols = symbols[:10000]  # Top 10k by liquidity
```

### Slow Performance
1. Build price cache first: `python build_price_cache.py`
2. Reduce number of blocks
3. Use smaller symbol universe

### Missing Data
- Script handles missing prices with forward-fill
- Market cap lookups use binary search to nearest date
- Stocks without sufficient history are excluded

## Citation

If you use this strategy in research or production:

```
Cluster Jump Trading Strategy
Market-cap-weighted hierarchical clustering for momentum signals
https://github.com/npallotta128/testbed-analysis
```

## License

See LICENSE file for details.

## Contact

For questions or issues, please open a GitHub issue or contact the repository owner.

---

**Disclaimer**: This is a research backtest. Past performance does not guarantee future results. Use at your own risk.
