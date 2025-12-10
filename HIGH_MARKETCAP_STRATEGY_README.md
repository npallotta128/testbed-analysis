# High Market Cap Cluster Transition Strategy

## Overview

A revised clustering strategy that focuses on **high market capitalization stocks** as the primary signal source. Instead of detecting quality changes across all stocks, this strategy filters for stocks in the top 20-30% by market cap, then uses their cluster transitions as trading signals.

**Rationale:**
- High cap stocks have better liquidity and price stability
- Their cluster transitions may represent more meaningful market regime changes
- Reduces noise from micro-cap volatility and data quality issues
- Easier to trade at scale due to higher liquidity

---

## Strategy Architecture

### 1. **Data Preparation**
```
Market data (Price + Outstanding Shares)
         ↓
Calculate Market Cap (Shares × Price)
         ↓
Filter to high market cap stocks (70th+ percentile)
```

**Current high-cap universe (7 stocks):**
- AAGIY: $103.6B
- AAIGF: $103.2B
- A: $29.7B
- AAL: $12.7B
- AACAY: $6.8B
- AACAF: $6.6B
- AA: $6.2B

### 2. **Sliding Window Clustering**
- **Block size:** 150 trading days
- **Num blocks:** 10 (covers ~5 years of data)
- **Clustering method:** Hierarchical (Ward linkage)
- **Distance threshold:** 40 units
- **Quality metric:** Average block returns

### 3. **Signal Generation**

Two types of events are detected for high-cap stocks:

#### **LOSS Event (SELL Signal)**
- Stock moves from **high-quality cluster** to **lower-quality cluster**
- Quality score drops significantly
- Interpretation: Leading high-cap stock losing momentum
- **Current performance:** -27.41% avg return (21.4% win rate)

#### **GAIN Event (BUY Signal)**
- Stock moves to **higher-quality cluster**
- Quality score improves significantly
- Interpretation: High-cap stock gaining momentum
- **Current performance:** -9.31% avg return (35.7% win rate)

### 4. **Key Parameters**

| Parameter | Value | Description |
|-----------|-------|-------------|
| `cap_percentile` | 70 | Use stocks above 70th percentile (top 30%) |
| `block_size` | 150 | Trading days per block |
| `num_blocks` | 10 | Total blocks to analyze |
| `distance_threshold` | 40 | Hierarchical clustering distance |
| `quality_threshold_percentile` | 75 | What counts as "high quality" (75th percentile) |
| `min_quality_change` | 5 | Minimum quality change to trigger event |
| `forward_periods` | 500 | Days to calculate future returns |

---

## Results Summary (Initial Testing)

### Overall Performance
- **Total events detected:** 28 (14 BUY + 14 SELL)
- **Average return:** -18.36%
- **Win rate:** 28.6%
- **Correlation (quality change vs return):** 0.238 (weak)

### By Signal Type

**BUY Signals (Join high-quality clusters)**
- Events: 14
- Avg return: -9.31%
- Win rate: 35.7%
- Better performer than SELL signals

**SELL Signals (Leave high-quality clusters)**
- Events: 14
- Avg return: -27.41%
- Win rate: 21.4%
- Weaker signal quality

### By Stock

| Stock | Count | Avg Return | Market Cap |
|-------|-------|------------|------------|
| A | 4 | +21.76% | $29.7B ✅ |
| AAIGF | 4 | +2.53% | $103.2B |
| AAGIY | 4 | +1.69% | $103.6B |
| AA | 4 | -6.50% | $6.2B |
| AAL | 4 | -37.60% | $12.7B ❌ |
| AACAY | 4 | -55.02% | $6.8B ❌ |
| AACAF | 4 | -55.36% | $6.6B ❌ |

---

## Running the Strategy

### Step 1: Generate Events
```bash
python high_marketcap_cluster_strategy.py
```

**Outputs:**
- `high_cap_cluster_events.csv` - Detected transitions with returns

### Step 2: Backtest & Analyze
```bash
python backtest_high_marketcap_strategy.py
```

**Analyzes:**
- Per-stock performance
- Signal-type comparison (BUY vs SELL)
- Portfolio simulations
- Quality change correlation

### Step 3: Customize Parameters (Optional)
Edit in `high_marketcap_cluster_strategy.py`:
```python
strategy.select_high_cap_stocks(cap_percentile=70)  # Adjust percentile
block_results = strategy.perform_clustering(
    block_size=150,
    num_blocks=10,
    distance_threshold=40
)
events_df = strategy.detect_transitions(
    block_results,
    quality_threshold_percentile=75,
    min_quality_change=5
)
```

---

## Event CSV Schema

**File:** `high_cap_cluster_events.csv`

| Column | Description |
|--------|-------------|
| Security | Stock ticker |
| Market_Cap | Median market cap of stock ($USD) |
| Block | Sliding window block ID |
| Date | Date of transition |
| Prev_Cluster_Quality | Quality score before transition |
| New_Cluster_Quality | Quality score after transition |
| Quality_Change | Change in quality (positive=improvement) |
| Event_Type | 'LOSS' or 'GAIN' |
| Signal | 'SELL' or 'BUY' |
| Future_Return | Return % over 500-period forward window |

**Example row:**
```
A, 29731964950.56, 4, 2021-01-15, 72.50, 85.61, +13.11, GAIN, BUY, +25.48%
AAL, 12671382879.14, 6, 2019-12-20, 68.30, 35.10, -33.20, LOSS, SELL, -15.78%
```

---

## Strategy Optimization Ideas

### Current Issues
1. **Low overall win rate (28.6%)** - The strategy is not consistently profitable on this dataset
2. **Quality change correlation weak (0.238)** - Cluster transitions don't strongly predict returns
3. **SELL signals underperform** - LOSS events have -27% avg return (not useful for shorts)

### Next Steps to Improve

#### 1. **Adjust Market Cap Percentile**
- Current: 70th percentile (top 30%)
- Try: 80th percentile (top 20%), 60th percentile (top 40%)
- May reduce noise or capture more signals

#### 2. **Modify Quality Metrics**
- Current: Average block returns
- Try: Median returns (more robust to outliers)
- Try: Win rate % (% positive returns in cluster)
- Try: Market-cap weighted cluster returns

#### 3. **Optimize Clustering Parameters**
- Block size: 100-200 days
- Distance threshold: 30-60 units
- Quality threshold percentile: 70-85th

#### 4. **Add Market Context Filters**
- Only trade during certain market regimes (VIX levels)
- Filter by recent cluster volatility
- Require minimum quality gap between clusters

#### 5. **Post-Event Holding Period**
- Current: 500 periods ahead
- Try: 100, 200, 250 periods
- Different holding windows may work better

#### 6. **Combine with Acquisition Events**
- Current strategy only uses dropouts
- Acquisition events show +25.64% avg in earlier analysis
- May need different signal interpretation

---

## File Locations

| File | Purpose |
|------|---------|
| `high_marketcap_cluster_strategy.py` | Main strategy implementation |
| `backtest_high_marketcap_strategy.py` | Backtesting & analysis |
| `high_cap_cluster_events.csv` | Detected events (output) |
| `data_with_marketcap.csv` | Input data with market cap |

---

## Dependencies

- Python 3.7+
- pandas, numpy, scipy (hierarchical clustering)
- matplotlib (optional, for visualizations)

---

## Next Actions

1. **Test parameter variations** to improve win rate
2. **Compare with original strategy** (quality-based vs high-cap-based)
3. **Add market cap as feature** in clustering (cap-weighted cluster quality)
4. **Implement adaptive clustering** based on market regime
5. **Train ML model** to predict which high-cap cluster transitions lead to positive returns

---

**Status:** Initial implementation complete. Strategy detects meaningful cluster transitions for high market cap stocks, but returns are currently negative. Further optimization needed.

**Last Updated:** December 3, 2025
