# Cluster Jump Strategy - Quick Start Guide

## What You Need

### 1. Data Files (Required)
Place in `/mnt/d/` or update paths in scripts:

- **MarketValues.csv** (Price data)
  - Columns: `Symbol`, `Date`, `Close`
  - Example: 18,917 symbols × 2,595 dates
  
- **MarketCAPValues.csv** (Market cap data)
  - Columns: `Symbol`, `Date`, `OutstandingShares`
  - Example: 15,244 symbols with shares data

### 2. Python Environment
```bash
pip install pandas numpy scipy scikit-learn matplotlib seaborn
```

## Running the Strategy (4 Steps)

### Step 1: Build Price Cache (One-time, ~3-5 min)
```bash
python build_price_cache.py
```
Creates `price_data_cache.pkl` (486 MB) to speed up clustering.

### Step 2: Generate Signals (~45-60 min with cache)
```bash
python clustering_full_jumps_checkpointed.py
```
Outputs:
- `cluster_jumps_full_250d_corrected.csv` (145k signals)
- `cluster_jumps_full_250d_winsorized.csv` (same, with capped returns)

### Step 3: Run Backtests (~5-10 min each)
```bash
# Capital scaling analysis
python backtest_capital_scaling.py

# Equity curves
python backtest_capital_equity.py

# Monte Carlo (1000 runs)
python monte_carlo_simulation.py

# Yearly breakdown
python analyze_yearly_returns.py
```

### Step 4: Review Results
Check output files:
- `backtest_capital_scaling.csv` - Performance by capital tier
- `equity_curves.csv` - Portfolio value over time
- `monte_carlo_results.csv` - Variance analysis
- `yearly_returns_analysis.csv` - Year-by-year stats

## Key Results You'll See

**Overall Performance:**
- 145,028 signals detected
- 77.9% win rate
- 90.27% average return (250-day hold)
- 18.70% median return

**Monte Carlo (1000 simulations from $100k):**
- Mean outcome: $249,956 (150% return)
- Median: $190,960 (91% return)
- 90% confidence: $129k - $482k
- Zero losing scenarios

**Yearly Returns:**
| Year | Signals | Win Rate | Mean Return |
|------|---------|----------|-------------|
| 2021 | 14,835  | 78.9%    | 78.74%     |
| 2022 | 30,909  | 79.0%    | 77.94%     |
| 2023 | 48,355  | 77.6%    | 85.73%     |
| 2024 | 33,570  | 77.5%    | 102.05%    |
| 2025 | 17,359  | 76.9%    | 111.97%    |

## How to Customize

### Adjust Clustering Sensitivity
In `clustering_full_jumps_checkpointed.py`:
```python
DISTANCE_THRESHOLD = 50    # Lower = tighter clusters, fewer signals
MIN_CLUSTER_SIZE = 40      # Higher = larger clusters, fewer signals
HISTORY_WINDOW = 1501      # More history = stabler clusters
BLOCK_STRIDE = 100         # Smaller stride = more frequent checks
```

### Change Backtest Parameters
In `backtest_capital_scaling.py`:
```python
CAPITAL_TIERS = [100_000, 1_000_000, 10_000_000, 100_000_000]
PER_TRADE_BASE = 100_000   # Base position size for BLUE_CHIP
MAX_CONCURRENT_TRADES = 20  # Maximum open positions
HOLD_DAYS = 250            # Hold period (trading days)
```

### Adjust Monte Carlo
In `monte_carlo_simulation.py`:
```python
N_SIMULATIONS = 1000       # More runs = better confidence intervals
CAPITAL_TIER = 100_000     # Starting capital to test
```

## Understanding the Outputs

### Signal File Columns
`cluster_jumps_full_250d_winsorized.csv`:
- **Symbol**: Stock ticker
- **Date**: Signal date
- **Jump_Type**: UP/DOWN/LATERAL (quality change direction)
- **Quality_Delta**: Change in cluster quality
- **Cluster_Continuity**: % of stocks staying in new cluster
- **return_250d_winsorized**: 250-day forward return (capped at 99th pct)

### Signal Classification
- **BLUE_CHIP**: Quality_Delta > 0 AND Continuity ≥ 0.6 → $100k base
- **SMALL_CAP_STORY**: Others → $20k base

### Position Sizing Formula
```
Size = min(
    Base ($100k or $20k),
    5% of portfolio,
    0.5% of stock market cap
)
```

## Troubleshooting

### "FileNotFoundError: MarketValues.csv"
Update paths in scripts:
```python
PRICE_FILE = '/path/to/your/MarketValues.csv'
MCAP_FILE = '/path/to/your/MarketCAPValues.csv'
```

### "MemoryError during clustering"
Reduce data size:
```python
HISTORY_WINDOW = 1001  # Less history
symbols = symbols[:10000]  # Fewer symbols
```

### "Takes too long"
1. Build cache first: `python build_price_cache.py`
2. Reduce blocks: `BLOCK_STRIDE = 200` (5 blocks instead of 10)
3. Reduce symbols to top 10k by volume/market cap

### "No signals generated"
Check thresholds:
```python
DISTANCE_THRESHOLD = 70   # Looser clusters
MIN_CLUSTER_SIZE = 20     # Smaller minimum
```

## Files on GitHub

**Core Files:**
- `clustering_full_jumps_checkpointed.py` - Main signal generation
- `backtest_capital_scaling.py` - Backtest framework
- `backtest_capital_equity.py` - Equity curves
- `monte_carlo_simulation.py` - Variance analysis
- `analyze_yearly_returns.py` - Yearly stats
- `build_price_cache.py` - Data cache builder
- `ml_signal_optimizer.py` - ML filter (optional)

**Documentation:**
- `README.md` - Complete documentation
- `MONTE_CARLO_ANALYSIS.md` - Detailed Monte Carlo analysis

**Outputs (not in repo, generated locally):**
- `cluster_jumps_full_250d_winsorized.csv` - Signals (145k rows)
- `backtest_capital_scaling.csv` - Backtest results
- `equity_curves.csv` - Portfolio progression
- `monte_carlo_results.csv` - Monte Carlo outcomes
- Various PNG visualizations

## Next Steps

1. **Run the pipeline** end-to-end with your data
2. **Review results** in CSV files and visualizations
3. **Tune parameters** based on your risk tolerance
4. **Validate signals** out-of-sample if deploying live
5. **Add transaction costs** for realistic expectations

## Support

- Full documentation: See `README.md`
- GitHub: https://github.com/npallotta128/testbed-analysis
- Issues: Open a GitHub issue for questions

---

**Remember:** This is a backtest with forward-looking returns. Real trading requires:
- Live data feeds
- Order execution system
- Transaction cost modeling
- Slippage management
- Risk monitoring

Past performance does not guarantee future results.
