# High Market Cap Cluster Strategy - Quick Reference

## What Was Changed

**Original Strategy:** Quality-based clustering on 199 stocks → 2,301 events
**New Strategy:** Market cap-filtered clustering on 7 high-cap stocks → 28 events

---

## Core Concept

```
High Market Cap Stocks (>$5.97B)
         ↓
Sliding Window Clustering (150-day blocks)
         ↓
Detect Cluster Transitions
         ↓
BUY Signal: Stock joins high-quality cluster
SELL Signal: Stock leaves high-quality cluster
```

---

## Key Files

| File | Purpose |
|------|---------|
| `high_marketcap_cluster_strategy.py` | Main implementation |
| `backtest_high_marketcap_strategy.py` | Backtesting |
| `optimize_high_marketcap_strategy.py` | Parameter optimization |
| `high_cap_cluster_events.csv` | Output: 28 detected events |
| `HIGH_MARKETCAP_STRATEGY_README.md` | Full documentation |

---

## Current Performance

- **Total events:** 28 (14 BUY + 14 SELL)
- **Average return:** -18.36% ❌ (Negative - needs improvement)
- **Win rate:** 28.6%
- **BUY signals:** -9.31% avg (better than average)
- **SELL signals:** -27.41% avg (worse than average)

**Best stock:** A (+21.76% avg)
**Worst stock:** AACAF (-55.36% avg)

---

## How to Use

### 1. Generate Events
```bash
python high_marketcap_cluster_strategy.py
```
Output: `high_cap_cluster_events.csv`

### 2. Analyze Results
```bash
python backtest_high_marketcap_strategy.py
```
Shows:
- Event statistics by signal type
- Portfolio simulations
- Strategy comparisons

### 3. Optimize Parameters (Optional)
```bash
python optimize_high_marketcap_strategy.py --quick
```
Tests different parameter combinations to find best configuration.

---

## Parameters to Tune

| Parameter | Current | Try | Effect |
|-----------|---------|-----|--------|
| `cap_percentile` | 70 | 60, 80 | Wider/narrower universe |
| `block_size` | 150 | 100-200 | Shorter/longer clustering windows |
| `distance_threshold` | 40 | 30-60 | More/fewer clusters |
| `quality_threshold_pct` | 75 | 70-85 | What counts as "high quality" |
| `min_quality_change` | 5 | 3-10 | How much change triggers signal |

---

## Next Steps to Improve Performance

**Priority 1 (Easy):**
- Run optimization script to test parameter combinations
- Try different market cap percentiles (60th, 80th)
- Try inverse signals (flip BUY/SELL)

**Priority 2 (Medium):**
- Use market-cap weighted cluster quality
- Add market regime filters
- Try different clustering methods

**Priority 3 (Hard):**
- Train ML model to predict which events work
- Implement adaptive clustering
- Combine with technical indicators

---

## Event CSV Format

```csv
Security,Market_Cap,Block,Date,Prev_Cluster_Quality,New_Cluster_Quality,Quality_Change,Event_Type,Signal,Future_Return
A,29731964950.56,4,2021-01-15,72.50,85.61,+13.11,GAIN,BUY,+25.48%
AAL,12671382879.14,6,2019-12-20,68.30,35.10,-33.20,LOSS,SELL,-15.78%
```

---

## Understanding the Output

**Event_Type:**
- `GAIN` = Stock moved to higher-quality cluster → BUY signal
- `LOSS` = Stock moved to lower-quality cluster → SELL signal

**Quality_Change:**
- Positive = Improvement (stock joining better cluster)
- Negative = Deterioration (stock leaving good cluster)

**Future_Return:**
- % return over next 500 trading days (~2 years)
- Positive = Made money
- Negative = Lost money

---

## Current Issues & Solutions

| Issue | Current | Potential Solution |
|-------|---------|-------------------|
| Negative returns | -18.36% avg | Optimize parameters, try inverse signals |
| Low win rate | 28.6% | Filter by quality change, market regime |
| SELL weak | -27.41% | Don't trade SELL, or try inverse |
| Weak correlation | 0.238 (quality vs return) | Add other features, use ML |

---

## Success Criteria

Target to achieve:
- ✅ Average return: +10% to +20%
- ✅ Win rate: 50%+
- ✅ Sharpe ratio: 0.5+

---

## Related Files

- `data_with_marketcap.csv` - Input data (price + shares + market cap)
- `optimize_dropout_strategy_safe.py` - Base clustering functions
- `MARKETCAP_README.md` - Earlier market cap analysis

---

**Status:** Implemented ✅ | Working but needs optimization 🔧

**Last Updated:** December 3, 2025
