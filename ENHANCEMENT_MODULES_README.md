# Layer 1 & Layer 2 Enhancement Modules

## Overview

Two new enhancement modules have been created to improve the cluster jumping strategy:

**Layer 1: Enhanced Cluster Quality Metric**
- Incorporates dropout/acquisition signals to measure cluster stability
- Adjusts base quality scores based on resilience: `Adjusted Quality = Base × (1 + Stability Bonus) × (1 - Dropout Penalty) × (1 + Acquisition Bonus)`
- Files: `cluster_quality_enhanced.py`

**Layer 2: Dynamic Exit Signals**
- Replaces fixed 250-day holds with intelligent position exits
- Detects: Dropout (exits cluster), Quality Collapse, Stop Loss, Take Profit
- Files: `monte_carlo_dynamic_exits.py`

**Integration**: `monte_carlo_enhanced_integration.py` orchestrates both layers with configurable modes

## Files Created

### 1. `cluster_quality_enhanced.py` (400 lines)

Core functions for Layer 1 enhancement:

#### `calculate_cluster_transitions(all_block_results)`
- Detects when securities exit high-quality clusters (dropout events)
- Detects when securities enter high-quality clusters (acquisition events)
- Threshold: 75th percentile quality across all blocks
- Returns: dropout_events_df, acquisition_events_df, quality_threshold

#### `calculate_cluster_stability(all_block_results)`
- Calculates retention rate: % of securities staying in cluster
- Calculates dropout rate: % leaving the cluster
- Calculates acquisition rate: % of new securities entering
- Returns: Dict[cluster_id] -> {'retention_rate', 'dropout_rate', 'acquisition_rate', 'observations'}

#### `adjust_cluster_quality(base_quality, stability_metrics, dropout_df, acquisition_df, ...)`
- Main quality adjustment function
- Formula: `Adjusted = Base × (1 + retention_weight×retention_rate) × (1 - dropout_weight×dropout_rate) × (1 + acquisition_weight×acquisition_rate)`
- Default weights: stability=0.15, dropout=0.20, acquisition=0.10
- Returns: Dict[cluster_id] -> adjusted_quality

#### `analyze_quality_impact(dropout_df, acquisition_df, quality_threshold)`
- Analyzes performance implications of transitions
- Calculates: avg quality loss per dropout, avg quality gain per acquisition
- Returns: Statistics dict with transition insights

### 2. `monte_carlo_dynamic_exits.py` (350 lines)

Core functions for Layer 2 enhancement:

#### `PositionExitMonitor` Class
Exit signal detection system with configurable thresholds:

```python
exit_monitor = PositionExitMonitor(
    quality_threshold=0.0,        # Min cluster quality to hold
    max_hold_days=500             # Fallback hold period
)
```

##### `check_exit_signal()` Method
- **Signal 1**: Dropout Detection — security exits its entry cluster
- **Signal 2**: Quality Collapse — cluster quality drops below threshold
- **Signal 3**: Stop Loss — price down ≥ configured %
- **Signal 4**: Take Profit — price up ≥ configured %
- **Signal 5**: Max Hold Time — reached 250-day fallback

Returns: (should_exit, reason, exit_price)

#### `compare_exit_strategies(fixed_hold_returns, dynamic_exit_returns)`
- Compares baseline fixed-hold vs. dynamic-exit strategy
- Metrics: mean, median, std dev, Sharpe ratio, win rate
- Returns: Comprehensive comparison statistics

#### `generate_exit_summary_report(exits_df)`
- Creates human-readable exit analysis report
- Breakdown by exit reason (Dropout, Quality Collapse, Stop Loss, etc.)
- Counts, avg hold times, avg PnL by reason

### 3. `monte_carlo_enhanced_integration.py` (350 lines)

Orchestration module for coordinating both layers:

#### `EnhancedMonteCarloRunner` Class
Main runner supporting 4 modes:

**Modes:**
- `baseline`: Current implementation (no enhancements)
- `layer1`: Enhanced quality + fixed 250d hold
- `layer2`: Base quality + dynamic exits
- `layer1_and_2`: Both enhancements combined

**Methods:**
- `prepare_quality_metrics()`: Adjusts cluster quality based on mode
- `prepare_exit_monitor()`: Creates exit monitor if needed
- `compare_modes()`: Generates mode comparison statistics
- `generate_mode_report()`: Creates comprehensive comparison report

### 4. `IMPLEMENTATION_GUIDE.md` (350 lines)

Detailed integration instructions for modifying `monte_carlo_scalability.py`:

**LAYER 1 Implementation:**
1. Extract block results in load_data() — capture cluster composition/quality per block
2. Add use_enhanced_quality flag to simulate_single_backtest()
3. Calculate adjusted quality inside simulation loop
4. Update main Monte Carlo loop to pass all_block_results

**LAYER 2 Implementation:**
1. Track positions with exit_signal and exit_date fields
2. Initialize PositionExitMonitor at start of backtest
3. Check exit signals in daily loop (before fixed-hold check)
4. Exit position if any signal triggers

**Implementation Options:**
- **Option A (Sequential)**: Implement Layer 1, test, then Layer 2 (lower risk)
- **Option B (Parallel)**: Implement both simultaneously (faster)

**Testing Strategy:**
- Unit tests (15-30 min): Quality formula, exit signals
- Integration tests (30 min): Single backtest per mode
- Regression tests (1-2 hrs): 10 sims per mode @ $100k
- Validation: Verify baseline matches current code

**Expected Performance Changes:**
- Layer 1: +2% to +8% mean return improvement
- Layer 2: -5% to +10% return; -10% to -30% volatility reduction
- Layer 1+2: Best of both effects

## Usage Examples

### Example 1: Analyze Quality Transitions

```python
from cluster_quality_enhanced import (
    calculate_cluster_transitions,
    calculate_cluster_stability,
    adjust_cluster_quality
)

# Assuming all_block_results from existing clustering analysis
loss_df, acquisition_df, quality_threshold = calculate_cluster_transitions(all_block_results)
stability = calculate_cluster_stability(all_block_results)

# Adjust quality scores
adjusted_q = adjust_cluster_quality(
    base_quality=base_q,
    stability_metrics=stability,
    dropout_df=loss_df,
    acquisition_df=acquisition_df,
    stability_weight=0.15,
    dropout_weight=0.20,
    acquisition_weight=0.10
)
```

### Example 2: Detect Exit Signals

```python
from monte_carlo_dynamic_exits import PositionExitMonitor

monitor = PositionExitMonitor(
    stop_loss_pct=0.15,
    take_profit_pct=0.50,
    max_hold_days=250
)

position = {
    'entry_date': '2024-01-15',
    'entry_price': 100.0,
    'cluster_id': 5
}

should_exit, reason, exit_price = monitor.check_exit_signal(
    position=position,
    current_date='2024-02-15',
    current_price=85.0,
    cluster_quality=0.5,
    cluster_membership={1, 2, 3, 4},
    purchase_cluster_id=5,
    current_cluster_id=3  # Exited to lower-quality cluster
)

print(f"Exit: {should_exit}, Reason: {reason}")
# Output: Exit: True, Reason: DROPOUT: Security exited cluster
```

### Example 3: Run Enhanced Monte Carlo

```python
from monte_carlo_enhanced_integration import EnhancedMonteCarloRunner

# Layer 1 only (enhanced quality)
runner_l1 = EnhancedMonteCarloRunner(
    mode='layer1',
    capital=100000,
    num_simulations=100,  # Use 100 for testing, 1000 for production
    quality_adjustment_weights={
        'stability_weight': 0.15,
        'dropout_weight': 0.20,
        'acquisition_weight': 0.10
    }
)

# Layer 1+2 (full enhancements)
runner_both = EnhancedMonteCarloRunner(
    mode='layer1_and_2',
    capital=100000,
    num_simulations=100,
    exit_signal_params={
        'quality_threshold': 0.0,
        'stop_loss_pct': 0.15,
        'take_profit_pct': 0.50,
        'max_hold_days': 250
    }
)
```

## Key Concepts

### Layer 1: Quality Adjustment Formula

```
Adjusted Quality = Base Quality × (1 + Stability Bonus) × (1 - Dropout Penalty) × (1 + Acquisition Bonus)

Where:
  Stability Bonus = retention_rate × stability_weight (0.15)
  Dropout Penalty = dropout_rate × dropout_weight (0.20)
  Acquisition Bonus = acquisition_rate × acquisition_weight (0.10)
```

**Intuition:**
- Clusters with high security retention get boosted (stability bonus)
- Clusters with high security exits get penalized (dropout penalty)
- Clusters attracting quality securities get small boost (acquisition bonus)
- Net effect: Prioritizes stable, durable high-quality clusters

### Layer 2: Exit Signal Hierarchy

Positions are checked in this order each trading day:

1. **DROPOUT**: Security no longer in entry cluster → Exit immediately
2. **QUALITY_COLLAPSE**: Cluster quality falls below threshold → Exit
3. **MAX_HOLD**: 250 days elapsed → Exit (fallback)
4. **HOLDING**: None triggered → Hold another day

**Tuning Parameters:**
- Adjust `quality_threshold` to control quality-based exits (default 0.0)
- Adjust `max_hold_days` to control maximum position duration (default 250)

## Integration Checklist

To integrate into `monte_carlo_scalability.py`:

- [ ] **Step 1A**: Extract block results in `load_data()`
- [ ] **Step 1B**: Add `use_enhanced_quality` parameter to `simulate_single_backtest()`
- [ ] **Step 1C**: Calculate adjusted quality when flag is set
- [ ] **Step 1D**: Update main Monte Carlo loop to pass all_block_results
- [ ] **Step 2A**: Track exit_signal/exit_date in position dict
- [ ] **Step 2B**: Initialize PositionExitMonitor at backtest start
- [ ] **Step 2C**: Check exit signals in daily loop before hold check
- [ ] **Testing**: Run 10-sim test suite at $100k for each mode
- [ ] **Validation**: Confirm baseline matches current results
- [ ] **Production**: Run 1000-sim Monte Carlo across all capital tiers

## Performance Expectations

### Baseline (Current)
- $100k: 42.9% mean return, 0.976 Sharpe
- $1M: 33.3% mean return, 0.817 Sharpe

### Layer 1 (Enhanced Quality)
- Expected: +2% to +8% mean return improvement
- Rationale: Better quality signal clustering removes weak clusters

### Layer 2 (Dynamic Exits)
- Expected: -5% to +10% return; -10% to -30% volatility reduction
- Rationale: Earlier exits protect upside; may miss big winners

### Layer 1+2 (Both)
- Expected: Compound improvements (best of both effects)
- Higher quality entries + better exit timing

## Next Steps

1. **Review** this documentation for gaps/clarifications
2. **Choose** implementation approach (Sequential vs. Parallel)
3. **Implement** code changes following IMPLEMENTATION_GUIDE.md
4. **Test** with small-scale runs (10 simulations per mode)
5. **Validate** baseline matches current code exactly
6. **Run** full Monte Carlo (1000 sims × 4 capital tiers × 4 modes)
7. **Compare** results across all modes
8. **Document** findings and performance impact
9. **Deploy** best-performing mode(s) to production

## Files Summary

| File | Lines | Purpose |
|------|-------|---------|
| `cluster_quality_enhanced.py` | 400 | Layer 1: Quality metric with dropout/acquisition weighting |
| `monte_carlo_dynamic_exits.py` | 350 | Layer 2: Dynamic exit signals (dropout, stop-loss, take-profit, etc.) |
| `monte_carlo_enhanced_integration.py` | 350 | Runner orchestrating both layers with mode selection |
| `IMPLEMENTATION_GUIDE.md` | 350 | Detailed integration steps for monte_carlo_scalability.py |
| `ENHANCEMENT_MODULES_README.md` | (this file) | Overview and usage documentation |

## Questions & Support

- **Layer 1 concept unclear?** See "Quality Adjustment Formula" section
- **Layer 2 tuning?** See "Exit Signal Hierarchy" and adjust parameters
- **Integration errors?** Check "Integration Checklist" and IMPLEMENTATION_GUIDE.md
- **Performance comparison?** See "Performance Expectations" for expected ranges
