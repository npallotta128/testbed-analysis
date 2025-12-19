"""
IMPLEMENTATION GUIDE: Integrating Layer 1 & Layer 2 Enhancements

This document outlines the specific code changes needed to integrate the two
enhancement modules into the existing monte_carlo_scalability.py workflow.

Timeline: ~2-3 hours implementation + 2-3 hours testing + ~4-6 hours Monte Carlo runs

LAYER 1: Enhanced Cluster Quality Scoring
===========================================

STEP 1A: Extract Block Results in load_data()
----------------------------------------------
Current code loads cluster_jumps and merges market data. We need to also
capture cluster composition and quality scores from each block.

CHANGE 1.1: In load_data(), after calculating cluster_quality:
    
    # NEW: Store all block information for later quality adjustment
    all_block_results = []
    for block_id, group_df in signals_df.groupby('Block_ID'):
        clusters = {}
        cluster_quality = {}
        
        for cluster_id, cluster_group in group_df.groupby('Cluster_ID'):
            securities = set(cluster_group['Security'].unique())
            clusters[cluster_id] = securities
            
            # Calculate base quality for this block/cluster
            quality = cluster_group['Return'].mean()
            cluster_quality[cluster_id] = quality
        
        all_block_results.append({
            'block_id': block_id,
            'clusters': clusters,
            'cluster_quality': cluster_quality
        })
    
    return signals_df, market_data, market_cap_data, all_block_results


STEP 1B: Add Quality Adjustment in simulate_single_backtest()
-------------------------------------------------------------
Current code uses base cluster quality. Layer 1 adjusts this based on 
dropout/acquisition weighting.

CHANGE 1.2: In simulate_single_backtest() function signature:
    
    OLD: def simulate_single_backtest(signals_df, market_data, market_cap_data, ...):
    NEW: def simulate_single_backtest(signals_df, market_data, market_cap_data, all_block_results=None, 
                                       use_enhanced_quality=False, ...):


STEP 1C: Calculate Adjusted Quality in simulate_single_backtest()
-----------------------------------------------------------------

CHANGE 1.3: After loading base cluster quality, add:
    
    if use_enhanced_quality and all_block_results is not None:
        try:
            from cluster_quality_enhanced import (
                calculate_cluster_transitions,
                calculate_cluster_stability,
                adjust_cluster_quality
            )
            
            loss_df, acquisition_df, quality_threshold = calculate_cluster_transitions(all_block_results)
            stability_metrics = calculate_cluster_stability(all_block_results)
            
            cluster_quality = adjust_cluster_quality(
                base_quality=cluster_quality,
                stability_metrics=stability_metrics,
                dropout_df=loss_df,
                acquisition_df=acquisition_df,
                stability_weight=0.15,
                dropout_weight=0.20,
                acquisition_weight=0.10
            )
            
            print(f"  Quality adjustment applied: {len(cluster_quality)} clusters adjusted")
        except Exception as e:
            print(f"  Warning: Quality adjustment failed: {e} - using base quality")
    else:
        print(f"  Using base cluster quality")


STEP 1D: Update Main Monte Carlo Loop
--------------------------------------

CHANGE 1.4: In main_monte_carlo_simulation():
    
    OLD: 
        signals_df, market_data, market_cap_data = load_data()
        all_capital_results = {}
        for capital in CAPITAL_TIERS:
            ...
            for sim in range(num_simulations):
                returns = simulate_single_backtest(signals_df, market_data, market_cap_data, ...)
    
    NEW:
        signals_df, market_data, market_cap_data, all_block_results = load_data()
        
        use_layer1 = True  # Toggle for Layer 1 enhancement
        all_capital_results = {}
        
        for capital in CAPITAL_TIERS:
            ...
            for sim in range(num_simulations):
                returns = simulate_single_backtest(
                    signals_df, 
                    market_data, 
                    market_cap_data,
                    all_block_results=all_block_results,
                    use_enhanced_quality=use_layer1,
                    ...
                )


---

LAYER 2: Dynamic Exit Signals  
=============================

STEP 2A: Track Cluster Membership During Hold
----------------------------------------------
Current code: Entry date + 250-day hold (fixed)
Layer 2: Check exit signals each trading day

CHANGE 2.1: Modify position tracking in simulate_single_backtest():

Instead of:
    positions[pos_id] = {
        'entry_date': date,
        'entry_price': price,
        'security': security,
        'cluster_id': cluster_id,
        'hold_until': date + timedelta(days=250)
    }

Use:
    positions[pos_id] = {
        'entry_date': date,
        'entry_price': price,
        'security': security,
        'cluster_id': cluster_id,
        'hold_until': date + timedelta(days=250),  # Fallback for fixed hold
        'exit_signal': None,  # Will store exit reason/signal
        'exit_date': None
    }


STEP 2B: Initialize Exit Monitor
---------------------------------

CHANGE 2.2: At start of simulate_single_backtest(), add:
    
    from monte_carlo_dynamic_exits import PositionExitMonitor
    
    use_dynamic_exits = True  # Toggle for Layer 2
    
    if use_dynamic_exits:
        exit_monitor = PositionExitMonitor(
            quality_threshold=0.0,      # Minimum cluster quality to hold
            max_hold_days=500           # Fallback hold period
        )
    else:
        exit_monitor = None


STEP 2C: Check Exit Signals in Daily Loop
------------------------------------------

CHANGE 2.3: In the main daily loop where positions are evaluated:
    
    for pos_id, pos in list(positions.items()):
        # ... existing logic to get current price ...
        
        if use_dynamic_exits and exit_monitor is not None:
            # Get current cluster quality (from signals_df)
            current_cluster_quality = cluster_quality.get(pos['cluster_id'], 0)
            
            # Check if security still in entry cluster
            # (in production, track cluster membership changes)
            current_cluster_id = pos['cluster_id']  # Simplified for MVP
            
            should_exit, exit_reason, exit_price = exit_monitor.check_exit_signal(
                position=pos,
                current_date=date,
                current_price=price,
                cluster_quality=current_cluster_quality,
                cluster_membership=set(),
                purchase_cluster_id=pos['cluster_id'],
                current_cluster_id=current_cluster_id
            )
            
            if should_exit:
                pnl = (exit_price - pos['entry_price']) / pos['entry_price']
                portfolio_returns.append(pnl)
                pos['exit_signal'] = exit_reason
                pos['exit_date'] = date
                del positions[pos_id]
                continue
        
        # ... existing fixed-hold logic ...
        if date >= pos['hold_until']:
            pnl = (price - pos['entry_price']) / pos['entry_price']
            portfolio_returns.append(pnl)
            del positions[pos_id]


---

INTEGRATION ROADMAP (Incremental Implementation)
==================================================

Option A: Sequential (Lower Risk)
-----------
1. Week 1: Implement Layer 1 only
   - Add all_block_results tracking in load_data()
   - Add use_enhanced_quality flag to simulate_single_backtest()
   - Run baseline vs. layer1 comparison at single capital tier
   - Verify quality adjustments are reasonable

2. Week 2: Test Layer 1 across all capital tiers
   - Run full 4-tier Monte Carlo with Layer 1
   - Generate comparison vs. current baseline
   - Document impact on returns/Sharpe ratio

3. Week 3: Implement Layer 2
   - Add exit_monitor initialization
   - Add daily exit signal checking
   - Run baseline vs. layer2 comparison

4. Week 4: Run full Layer 1+2
   - Combine both enhancements
   - Generate 4-mode comparison report


Option B: Parallel (Faster)
-----------
1. Implement both changes simultaneously in separate feature branch
2. Create test fixtures for Layer 1 & Layer 2
3. Run parallel Monte Carlo jobs:
   - Baseline (current code) @ $100k
   - Layer 1 @ $100k  
   - Layer 2 @ $100k
   - Layer 1+2 @ $100k
4. Compare results → decide which enhancements to keep
5. If positive, scale to all capital tiers


---

TESTING STRATEGY
================

Test Suite Components:
1. Unit Tests (15-30 min)
   - test_cluster_transitions(): Verify dropout/acquisition detection
   - test_quality_adjustment(): Check quality formula correctness
   - test_exit_signals(): Verify each exit reason triggers correctly

2. Integration Tests (30 min)
   - test_single_simulation_layer1(): One 100-position backtest with enhanced quality
   - test_single_simulation_layer2(): One 100-position backtest with dynamic exits
   - test_both_layers(): Combined enhancement

3. Regression Tests (1-2 hours)
   - Run 10 simulations each mode at $100k capital
   - Verify returns are in expected ranges
   - Check for crashes/errors

4. Validation
   - Baseline results match current monte_carlo_scalability.py
   - Layer 1 mean return vs. baseline (expect ±5-15% change)
   - Layer 2 mean return vs. baseline (expect ±10-20% change, lower volatility)
   - Sharpe ratio changes are monotonic with improvement


---

OUTPUT FILES & NAMING
======================

New outputs after full implementation:

monte_carlo_scalability_BASELINE.csv         # Current results (baseline)
monte_carlo_scalability_LAYER1.csv           # Enhanced quality metric
monte_carlo_scalability_LAYER2.csv           # Dynamic exits
monte_carlo_scalability_LAYER1_AND_2.csv     # Both enhancements combined

mode_comparison_layer1.csv                   # Baseline vs. Layer 1 stats
mode_comparison_layer2.csv                   # Baseline vs. Layer 2 stats
mode_comparison_layer1_and_2.csv             # Baseline vs. Layer 1+2 stats

enhancement_comparison_report.txt            # Comprehensive comparison across modes
enhancement_analysis.png                     # Visualization of all 4 modes


---

EXPECTED PERFORMANCE CHANGES
============================

Layer 1 (Enhanced Quality):
  Expected Impact: +2% to +8% mean return improvement
  Rationale: Penalizes clusters with high dropout rates; rewards stable clusters
  Risk: Could be negative if dropout/acquisition signals are too aggressive

Layer 2 (Dynamic Exits):
  Expected Impact: -5% to +10% mean return; -10% to -30% volatility reduction
  Rationale: Earlier exits capture gains, avoid extended losses; may miss big wins
  Risk: Stop-loss could be too tight; take-profit could leave money on table

Layer 1+2 Combined:
  Expected Impact: Best of both (high quality signals + intelligent exits)
  Rationale: Compound effects of better entry quality + better exit timing
  Risk: Could overfit to historical patterns


---

ROLLBACK PLAN
=============

If enhancements degrade performance:

1. Add feature flags to main simulation:
   USE_ENHANCED_QUALITY = False
   USE_DYNAMIC_EXITS = False

2. Keep all data saved:
   - monte_carlo_scalability_results.csv (all 4 modes)
   - enhancement_comparison_report.txt (full analysis)

3. Can switch back to baseline production by flipping flags

4. No changes to core backtest logic if layer modules fail

---

NEXT STEPS
==========

1. Review this implementation guide for gaps
2. Choose Option A (sequential) or Option B (parallel)
3. Implement changes in feature branch
4. Create test fixtures and run unit tests
5. Run small-scale integration tests (10 sims per mode @ $100k)
6. If tests pass, run full Monte Carlo (1000 sims per mode @ all tiers)
7. Generate comparison report
8. Document findings and next steps
"""

if __name__ == "__main__":
    print(__doc__)
