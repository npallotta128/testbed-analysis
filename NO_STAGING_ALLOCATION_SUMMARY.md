# Capital Allocation Analysis - No Staging Results

## Executive Summary

Simplified capital allocation model using **immediate entry/exit** (no 10-day staging windows) while maintaining 2-year holding periods and 5% ADV constraint.

### Key Results

**$1M Capital (Successful Scenario):**
- Annualized Return: **+33.9%** 
- Total Return: +78.6% over 2 years
- Positions: 326 opened
- Win Rate: 21.8%
- Improvement vs Staged: **+21.6 percentage points**

**$1B Capital (Capacity-Constrained Scenario):**
- Annualized Return: **-17.3%**
- Total Return: -31.4% over 2 years
- Positions: 405 opened (max possible from top 1000 events)
- Win Rate: 21.0%
- Only 2.5% capital utilization due to volume constraints

---

## Allocation Rules

1. **Capital Constraint:** 5% of current equity per position
2. **Volume Constraint:** 5% of average daily volume (ADV)
3. **Per-Security Limit:** 5% total exposure across all concurrent positions
4. **Holding Period:** 500 days (~2 years)
5. **Event Selection:** Top 1000 events by model probability

**Constraint Binding Rates (at $1B):**
- Volume: **97.5%** of positions
- Capital: 1.7% of positions
- Security: 0.7% of positions

---

## Staging vs No-Staging Comparison

| Capital | Staged Annualized | No-Staging Annualized | Improvement |
|---------|------------------|-----------------------|-------------|
| $1M     | +12.4%           | +33.9%                | +21.6 pp    |
| $5M     | -13.9%           | -2.5%                 | +11.4 pp    |
| $10M    | -34.6%           | -26.2%                | +8.5 pp     |
| $100M   | -31.7%           | -32.6%                | -0.9 pp     |
| $1B     | -16.7%           | -17.3%                | -0.6 pp     |

**Why No-Staging Performs Better:**
- Immediate deployment → higher position count (13-27 more positions at small capital)
- No capital tied up during entry/exit windows
- At large capital ($100M+), both converge because all 405 possible positions get funded

---

## Position Capacity Analysis

### Size Distribution (at $1B)

| Size Bucket | Count | Percentage | Avg Return | Win Rate |
|-------------|-------|------------|------------|----------|
| <$25k       | 322   | 79.5%      | +16.6%     | 21.7%    |
| $25-100k    | 30    | 7.4%       | +173.8%    | 23.3%    |
| $100-500k   | 24    | 5.9%       | -33.2%     | 25.0%    |
| $500k-$1M   | 5     | 1.2%       | -25.7%     | 20.0%    |
| >$1M        | 24    | 5.9%       | -73.5%     | 4.2%     |

### Key Insight: Volume Constraint Bottleneck

**For volume-constrained positions (97.5% of total):**
- Average capital cap: **$46.5M** (what we *could* allocate)
- Average volume cap: **$249k** (what we *actually* allocate)
- **Capital headroom: 18,562%** above volume constraint

This means at $1B capital, we have ~185x more capital available than we can deploy due to liquidity constraints.

---

## Critical Performance Issues

### 1. Low Win Rate (21%)
- Only 85 of 405 positions are profitable
- 285 positions lose money (70% losing rate)
- Median return: **-60%** (most positions lose money)

### 2. Skewed Returns
- Winners average: **+332%** (handful of big winners)
- Losers average: **-71%** (many moderate losers)
- Top performers carry the portfolio, but not enough to offset losses

### 3. Event Quality Dilution
With only 1000 events available:
- At $1M: Opens 326 positions (top 33% of event set)
- At $1B: Opens 405 positions (top 41% of event set)
- As capital grows, forced to deploy into lower-quality events

### 4. Capital Efficiency
- **$1B capital deployed: $468M (47%)**
- Remaining $532M sits idle due to:
  - Volume constraints (97.5%)
  - All viable events exhausted (405 of 1000 funded)
  - 21% win rate creates losses even with partial deployment

---

## Recommendations

### Option 1: Increase ADV Tolerance
**Change:** 5% ADV → 10% ADV

**Impact:**
- Would ~double position sizes (currently $249k avg → ~$500k avg)
- Could deploy ~$936M instead of $468M
- **Risk:** Higher market impact, less liquid exits

### Option 2: Focus on Higher Quality Events
**Change:** TOP_N=1000 → TOP_N=300

**Impact:**
- Focus capital on top 30% of events (higher win rate expected)
- May improve from 21% → 30-40% win rate (based on tier analysis)
- Reduces total positions but improves quality
- **Trade-off:** Less diversification, lower total deployment

### Option 3: Reduce Capital Targets
**Change:** $1B → $10M maximum

**Impact:**
- At $10M: -26.2% annualized (still negative, but less severe)
- At $1M: **+33.9% annualized** (only profitable level)
- **Reality:** This strategy scales poorly beyond ~$5M

### Option 4: Improve Model Quality
**Change:** Retrain model or adjust features to improve precision

**Impact:**
- Current Precision@10%: 31.9%
- If improved to 50%, win rate could double
- Requires model development work

---

## Files Generated

1. **capital_allocation_no_staging.py** - Simplified allocation script (no staging)
2. **no_staging_allocation_results.csv** - Summary across capital levels
3. **no_staging_positions_1B.csv** - Detailed positions for $1B scenario
4. **compare_staging.py** - Comparison analysis script
5. **position_capacity_analysis.py** - Position size bucket analysis
6. **position_capacity_buckets.csv** - Detailed capacity breakdown

---

## Technical Notes

### Differences from Staged Model

**Removed:**
- `ENTRY_WINDOW_DAYS = 10` (gradual deployment)
- `EXIT_WINDOW_DAYS = 10` (gradual exit)
- 'entering' and 'exiting' position states
- Daily deployment calculations

**Kept:**
- 2-year holding period (500 days)
- 5% capital constraint per position
- 5% ADV volume constraint
- 5% per-security exposure limit
- Current equity = cash + mark-to-market position values

### Position Lifecycle
1. Event triggers → Calculate position size (min of capital cap, volume cap, security limit)
2. If sufficient cash → Deploy full position immediately
3. Hold for exactly 500 days, updating mark-to-market daily
4. Exit immediately at day 500 → Return capital + P&L to cash

---

## Next Steps

1. **Test TOP_N=300** to see if higher quality improves win rate
2. **Consider 10% ADV** if market impact is acceptable
3. **Analyze losing positions** to identify patterns (specific sectors, volatility profiles)
4. **Model improvement:** Feature engineering to boost precision beyond 31.9%

Current bottleneck is **event quality (21% win rate)**, not capital deployment mechanics.
