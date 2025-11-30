# File Inventory - Trading Strategy Analysis Results

## Primary Data Files (Source)
- `data.csv` - Original financial dataset
- `TestBed.py` - Original clustering implementation

## Analysis Scripts
- `financial_analysis.py` - Original 10-timepoint analysis
- `financial_analysis_optimized.py` - Optimized version
- `financial_analysis_large_scale.py` - Large scale implementation  
- `optimized_parallel_analysis_original_criteria.py` - Final 250-timepoint parallel analysis
- `calculate_returns_for_montecarlo.py` - Return calculation for Monte Carlo
- `monte_carlo_simulations.py` - Original Monte Carlo strategies
- `monte_carlo_capital_allocation.py` - Capital allocation strategy

## Generated Results Files

### Signal Generation Results
- `trading_signals_results.csv` - Original 10-timepoint results (486 signals)
- `single_timepoint_test_results.csv` - Single timepoint test
- `trading_signals_250_timepoints_start75_original_criteria.csv` - Final dataset (14,285 signals)

### Return Calculation Results  
- `trading_signals_with_returns_250_timepoints_start75.csv` - All signals with calculated returns

### Monte Carlo Simulation Results
- `montecarlo_summary.csv` - Summary of all strategies
- `capital_allocation_results.csv` - Capital allocation strategy results

### Summary and Documentation
- `ANALYSIS_RESULTS_SUMMARY.md` - Complete analysis summary
- `FILE_INVENTORY.md` - This file inventory
- `README.md` - Project overview

## Results Stored on D Drive (/mnt/d/testbed_analysis/)

### Intermediate Processing Files
- `cache/` - Preprocessing cache files
- `results/` - Individual timepoint signal files (250 files)
- `returns/` - Return calculation results
- `montecarlo/` - Complete Monte Carlo simulation results

### Large Result Files
- `montecarlo_random_sample_1000_sims.csv` (7.4 MB)
- `montecarlo_sequential_chunks_1000_sims.csv` (8.9 MB) 
- `montecarlo_timepoint_windows_1000_sims.csv` (320 MB)
- `montecarlo_all_trades_1000_sims.csv` (2.3 GB)
- `capital_allocation_strategy_1000_sims.csv` 

### Visualization Files
- `montecarlo_analysis_plots.png` - Original strategy comparison plots
- `capital_allocation_strategy_plots.png` - Capital allocation analysis plots

## Key Statistics Summary

### Dataset Size
- **Total Signals Generated**: 14,285
- **Timepoints Analyzed**: 250 (start from timepoint 75)
- **Variables per Timepoint**: ~18,000
- **Price Data Points**: 2,557 dates × 18,131 symbols

### Computational Metrics  
- **Processing Time**: ~4 hours for signal generation
- **Monte Carlo Simulations**: 5,000 total (1,000 per strategy)
- **Parallel Processing**: 6-8 cores utilized
- **Memory Usage**: Peak ~560 MB for price data loading

### Performance Results
- **Best Strategy**: Capital Allocation (5% position sizing)
- **Mean Return**: 132.88%
- **Win Rate**: 100% (across 1,000 simulations)
- **Risk Level**: Minimal (worst case: +6.58%)

## File Sizes and Storage
- **Workspace Files**: ~50 MB
- **D Drive Cache/Results**: ~3 GB total
- **Key Working Files**: Available in workspace for analysis
- **Complete Dataset**: Preserved on D drive for future reference

## Access Instructions
- **Primary Results**: Available in workspace directory
- **Detailed Data**: Accessible via D drive mount (`/mnt/d/testbed_analysis/`)
- **Visualizations**: PNG files for strategy performance analysis
- **Raw Simulations**: CSV files with complete simulation details

---
*Last Updated: October 21, 2025*
*Total Files Generated: 260+ files*
*Primary Storage: D drive for large files, workspace for key results*