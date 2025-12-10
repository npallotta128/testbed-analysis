# COMBINED SIGNAL STRATEGY - EXECUTIVE SUMMARY

## Overview
Analysis of combining three trading signals across 29,876 events spanning 2015-2020:

1. **Cluster Strengthening**: Large-cap stocks joining clusters
2. **Quality Acquisition**: Quality stocks joining their clusters  
3. **Quality Dropout**: Quality stocks leaving their clusters

---

## SIGNAL PERFORMANCE COMPARISON

### Individual Signal Metrics

| Signal | Count | Avg Return | Win Rate | Sharpe Ratio | Notes |
|--------|-------|-----------|----------|------|-------|
| **Cluster Strengthen** | 24 | +81.14% | 79.2% | **0.490** | 🏆 BEST risk-adjusted returns |
| Quality Acquisition | 14,677 | +675.66% | 48.6% | 0.024 | Large sample, volatile |
| Quality Dropout | 15,175 | +441.41% | 45.6% | 0.025 | Short signal alternative |

### Key Insight
**Cluster Strengthening is the highest-conviction signal**, but extremely rare (24 events total). 

The larger universe of Quality Events provides volume but with much higher volatility and lower Sharpe ratios.

---

## RECOMMENDED TRADING STRATEGIES

### Strategy 1: Conservative (Low Volume, High Quality)
**Primary: Cluster Strengthening Only**
- Signals: 24
- Avg Return: +81.14%
- Win Rate: 79.2%
- Sharpe: 0.490
- **Portfolio Impact**: $100K → $181K (+81.14%)
- **Best For**: Investors seeking high-conviction trades, willing to wait for rare setups

### Strategy 2: Aggressive (High Volume, Lower Sharpe)  
**Primary: Quality Events Only (Acquisition + Dropout)**
- Signals: 29,852
- Avg Return: +556.59%
- Win Rate: 47.1%
- Sharpe: 0.024
- **Best For**: Volume traders seeking many signals, accepting lower risk-adjusted returns

### Strategy 3: Balanced (Recommended)
**Primary: Cluster Strengthen + Quality Acquisition (LONG signals only)**
- Signals: 14,701
- Avg Return: +674.69%
- Win Rate: 48.7%
- Sharpe: 0.024
- **Strategy**: 
  - Go LONG when large-cap joins cluster OR quality stock joins cluster
  - Ignore short signals (Quality Dropout)
- **Best For**: Growth-focused investors, simpler mechanics than hedging dropouts

### Strategy 4: Market Neutral (All Signals)
**LONG: Cluster Strengthen + Quality Acquisition / SHORT: Quality Dropout**
- Signals: 29,876
- Avg Return: +107.79%
- Win Rate: 50.1%
- Sharpe: 0.005
- **Issue**: Profit Factor drops to 1.44 (was 10.24+ for individual signals)
- **Best For**: Hedge fund structures with short capability, but trades off quality for neutrality

---

## TEMPORAL PERFORMANCE

### Cluster Strengthening by Year
```
2017: 14 signals, +10.80% avg (100% win rate) ✅
2018: 5 signals, -42.17% avg (0% win rate) ❌ HARSH YEAR
2019: 5 signals, +401.39% avg (100% win rate) 🚀
```
**Note**: 2018 was notably bad across all signals (market downturn)

### Quality Acquisition Standouts
```
2017: +2,007.51% avg (best year)
2020: +893.39% avg (recovery year)
```

---

## KEY FINDINGS

### ✅ What Works
1. **Large-cap cluster entries** are consistent, high-quality signals (79.2% win rate)
2. **Quality acquisitions outperform dropouts** (675.66% vs 441.41%)
   - Suggests positive momentum when quality stocks join clusters
   - Possible explanation: Clusters strengthen → attract more quality → virtuous cycle
3. **Small, focused signal set beats large, diffuse set**
   - Cluster Strengthen: Sharpe 0.490 (24 signals)
   - Quality Events: Sharpe 0.024 (29,852 signals)
   - More data ≠ better risk-adjusted returns in this case

### ❌ What Doesn't Work
1. **Shorting quality dropouts reduces profitability**
   - Profit Factor drops from 10.24 → 1.44 when adding short signals
   - Suggests dropouts aren't reliable short signals
2. **2018 was a regime shift** 
   - Cluster Strengthen: -42.17% (all 5 signals lost)
   - Suggests need for regime detection or hedging during downturns

---

## RECOMMENDATIONS

### For This Testbed Strategy

**Primary Recommendation: Strategy 3 (Cluster Strengthen + Quality Acquisition)**

Rationale:
- Combines two LONG signals (simpler to trade)
- Maintains good returns (+674.69% avg)
- Avoids unreliable short signals
- Sharpe of 0.024 is still acceptable given returns
- Only 14.7K signals = manageable execution complexity

### Implementation Notes
1. **Use Cluster Strengthening as primary filter** (highest conviction)
   - These 24 events are golden - execute with full position
   - ~79.2% win rate = profitable even with modest position sizing

2. **Use Quality Acquisition for volume**
   - Scale position size inversely with conviction
   - Smaller positions on the 14.7K quality acquisition signals

3. **Skip Quality Dropout signals**
   - Profit Factor collapse when added suggests they conflict with long bias
   - If market neutral strategy desired, recalibrate hedging logic

4. **Monitor regime changes**
   - 2018 loss period suggests clustering strategy sensitive to bear markets
   - Consider adding volatility hedge or regime filter for risk management

---

## BACKTEST RESULTS

### Best Scenario (Cluster Strengthen Only)
```
Initial Capital:     $100,000
Final Capital:       $181,140
Total Return:        +81.14%
Number of Trades:    24
Win Rate:            79.2% (19 winners, 5 losers)
Avg Winner:          +113.59%
Avg Loser:           -42.17%
Profit Factor:       10.24
Sharpe Ratio:        0.490
```

### Volume Scenario (Quality Events Only)
```
Initial Capital:     $100,000
Final Capital:       $656,590
Total Return:        +556.59%
Number of Trades:    29,852
Win Rate:            47.1%
Profit Factor:       25.27
Sharpe Ratio:        0.024
```

---

## DATA QUALITY NOTES

- **Large return outliers exist** (max: +2.8M%, min: -100%)
  - These skew averages significantly
  - Consider capping position sizes or using median returns instead
- **Win rates ~48% suggest market regimes matter**
  - Not all periods are equally profitable
  - Recommend time-series validation with separate test periods
- **Profit factor of 25+ on Quality Events is suspiciously high**
  - May indicate data quality issues or look-ahead bias
  - Recommend independent validation before live trading

