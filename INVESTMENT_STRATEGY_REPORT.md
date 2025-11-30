# Multi-Timeframe Quality Event Investment Strategy Report

## Executive Summary
Based on quality event clustering analysis across multiple recency horizons, we identified **18 high-conviction consensus stocks** that appear in the top 20 across all four timing strategies (Short, Medium, Long-Term, and Equal-Weight).

**Consensus Portfolio Performance:**
- **Mean Forward Return:** 223.0%
- **Median Forward Return:** 130.7%
- **Top Performer:** ASLRF (1,006.7%)
- **Portfolio Count:** 18 securities

---

## Investment Strategies by Timeframe

### 1. CONSERVATIVE (Long-Term Focus)
**Strategy:** `Long_Term` (λ=0.02)
- **Philosophy:** Emphasizes sustained quality improvement over entire clustering period
- **Characteristics:** 
  - Low recency bias favors long-term accumulators
  - Higher momentum score (667.1 avg for top 50)
  - Lower average return (236.9%) but potentially more stable
- **Use Case:** Core portfolio holdings, retirement accounts, lower turnover
- **Output:** `quality_ranking_Long_Term_top50.csv`

### 2. BALANCED (Medium-Term Focus)
**Strategy:** `Medium_Term` (λ=0.05)
- **Philosophy:** Moderate recency weighting balances recent momentum with historical performance
- **Characteristics:**
  - Best overall metrics: 604.8 momentum score, 513.4% avg return
  - Strong balance between quality improvement and returns
- **Use Case:** General equity allocation, tactical positions
- **Output:** `quality_ranking_Medium_Term_top50.csv`

### 3. OPPORTUNISTIC (Short-Term Focus)
**Strategy:** `Short_Term` (λ=0.15)
- **Philosophy:** Heavy emphasis on recent block quality transitions
- **Characteristics:**
  - Recent momentum plays (381.1% avg return)
  - Lower momentum score (426.7) suggests faster-moving opportunities
  - Higher recency sensitivity
- **Use Case:** Swing trading, momentum strategies, shorter holding periods
- **Output:** `quality_ranking_Short_Term_top50.csv`

### 4. EQUAL-WEIGHT BASELINE
**Strategy:** `Equal_Weight` (λ=0.0)
- **Philosophy:** No temporal decay, all blocks weighted equally
- **Characteristics:**
  - Highest momentum score (806.0) from full historical accumulation
  - Moderate return (370.3%)
- **Use Case:** Benchmark comparison, understanding pure quality signal
- **Output:** `quality_ranking_Equal_Weight_top50.csv`

---

## High-Conviction Consensus Picks (4/4 Strategy Agreement)

### Tier 1: Superior Returns (>200%)
| Security | Avg Return | Strategy Profile |
|----------|-----------|------------------|
| ASLRF | 1,006.7% | Exceptional quality momentum across all horizons |
| APCX | 621.4% | Strong acquisition events, minimal losses |
| AAEEF | 536.6% | Consistent quality improvement pattern |
| BFNH | 395.6% | Robust multi-block quality accumulation |
| AYASF | 342.5% | Recent quality acceleration validated |
| ACCR | 203.3% | Steady quality trajectory |

### Tier 2: Solid Returns (100-200%)
| Security | Avg Return | Strategy Profile |
|----------|-----------|------------------|
| ABEPF | 157.2% | Balanced acquisition/loss profile |
| AMLC | 133.3% | Long-term quality accumulator |
| AMXEF | 131.2% | Multi-cluster quality breadth |
| ATHJF | 130.1% | Stable event quality pattern |
| AMKAF | 128.6% | Moderate recency emphasis |
| ALLT | 102.9% | Consistent quality maintenance |

### Tier 3: Moderate Returns (0-100%)
| Security | Avg Return | Strategy Profile |
|----------|-----------|------------------|
| ASRE | 32.2% | Quality stable with lower volatility |
| AMSU | 32.0% | Recent quality improvements |
| AWWI | 28.3% | Defensive quality characteristics |
| ALL | 18.6% | Conservative quality profile |
| AEYGQ | 13.5% | Early-stage quality improvement |
| AUB | 0.2% | Placeholder/defensive |

---

## Portfolio Construction Recommendations

### Aggressive Growth Portfolio
- **Allocation:** 70% Tier 1 + 30% Short-Term top 50 (non-consensus)
- **Expected Profile:** High return, high turnover, momentum-driven
- **Rebalance:** Monthly using Short_Term rankings

### Balanced Growth Portfolio
- **Allocation:** 50% Consensus (Tier 1+2), 30% Medium-Term top 50, 20% Long-Term top 50
- **Expected Profile:** Strong returns with moderate stability
- **Rebalance:** Quarterly using Medium-Term rankings

### Conservative Growth Portfolio
- **Allocation:** 60% Long-Term top 50, 40% Consensus (Tier 2+3)
- **Expected Profile:** Steady quality-driven appreciation
- **Rebalance:** Semi-annually using Long-Term rankings

### Core-Satellite Approach
- **Core (70%):** All 18 consensus stocks (4/4 agreement)
- **Satellite (30%):** Rotate among strategy-specific top 20s based on market regime
- **Rebalance:** Core holds steady, satellite adjusts monthly

---

## Risk Considerations

### Concentration Risk
- Consensus portfolio has only 18 names — consider expanding to top 50 4/4 agreement (40 names) for diversification
- Top performer (ASLRF) represents significant outlier; consider capping position size

### Quality Event Limitations
- Historical quality events may not predict future transitions
- Clustering methodology assumes pattern persistence
- Market cap data not yet integrated (size bias unknown)

### Recency Trade-offs
- Short-Term strategy vulnerable to reversal after recent jumps
- Long-Term may miss emerging quality inflections
- Equal-Weight ignores structural regime shifts

---

## Methodology Notes

### Winsorization Impact
- Returns trimmed at 1%/99% percentiles to reduce extreme outlier distortion
- Mean return reduced ~77% (from 702.6% to 160.4%) in enhanced rankings
- Top securities validated with robust median-based metrics

### Recency Weighting Formula
- Weight = exp(-λ × (max_block - Block_ID))
- λ = 0.15 (Short), 0.05 (Medium), 0.02 (Long), 0.0 (Equal)
- Higher λ → exponentially higher weight on recent blocks

### Composite Rank Weights (All Strategies)
- 30% Net Quality Delta (Recency-Weighted)
- 30% Quality Momentum Score (Adjusted)
- 20% Weighted Winsor Final Return (Recency)
- 10% Event Balance Ratio
- 10% Events Per Block

---

## Next Steps

1. **Market Cap Integration:** Once data available, normalize quality scores by company size and add cap-weighted strategy
2. **Sector Overlay:** Analyze consensus picks by sector for diversification optimization
3. **Dynamic Lambda:** Test adaptive λ based on market volatility regime
4. **Backtesting:** Simulate historical portfolio performance with transaction costs
5. **Drawdown Analysis:** Assess maximum drawdown for each strategy during stress periods

---

## File Outputs

### Strategy Rankings (Full Detail)
- `quality_ranking_Short_Term.csv`
- `quality_ranking_Medium_Term.csv`
- `quality_ranking_Long_Term.csv`
- `quality_ranking_Equal_Weight.csv`

### Top 50 Picks per Strategy
- `quality_ranking_Short_Term_top50.csv`
- `quality_ranking_Medium_Term_top50.csv`
- `quality_ranking_Long_Term_top50.csv`
- `quality_ranking_Equal_Weight_top50.csv`

### Analysis Outputs
- `quality_ranking_consensus.csv` (stocks appearing in multiple strategies)
- `quality_ranking_strategy_comparison.csv` (aggregate metrics per strategy)

### Supporting Analysis
- `quality_event_decile_summary.csv` (original decile breakdown)
- `QUALITY_EVENT_RANKING_GUIDE.md` (methodology documentation)

---

## Quick Start Guide

**Conservative Investor:**
```bash
# Review long-term top picks
cat quality_ranking_Long_Term_top50.csv
```

**Balanced Investor:**
```bash
# Start with consensus stocks
cat quality_ranking_consensus.csv | grep "4/4"
# Supplement with medium-term picks
cat quality_ranking_Medium_Term_top50.csv
```

**Aggressive Investor:**
```bash
# Focus on recent momentum
cat quality_ranking_Short_Term_top50.csv
# Monitor Tier 1 consensus for core positions
```

---

**Disclaimer:** Past quality event performance does not guarantee future results. These rankings reflect clustering-derived quality transitions and should be combined with fundamental analysis, valuation metrics, and risk management protocols before investment decisions.
