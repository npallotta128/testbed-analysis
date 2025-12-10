# Azure Validation Pipeline - Quick Start

## Overview
End-to-end validation pipeline that chains:
1. Azure SQL data fetch
2. Sliding window event generation (stride=50)
3. ML model training (Logistic Regression)
4. Capital allocation backtest

## Files Created
- `azure_validation_pipeline.py` - Main orchestration script
- `azure_validation_backtest.csv` - Backtest results output

## Usage

### Test with Existing Data (Skip Azure Fetch)
```bash
SKIP_FETCH=1 python azure_validation_pipeline.py
```

### Full Run with Azure Data (Requires ODBC Drivers)
```bash
# Install drivers first (Ubuntu/Debian):
# sudo apt-get install -y unixodbc unixodbc-dev msodbcsql17 mssql-tools

# Full table
python azure_validation_pipeline.py

# Limited rows for testing
AZURE_LIMIT=500000 python azure_validation_pipeline.py

# Chunked fetch
CHUNKED_FETCH=1 MAX_ROWS=1000000 python azure_validation_pipeline.py
```

## Expected Results (Local data.csv validation)
Based on current local run:

| Tier | Model Mean Return | vs Quality Heuristic | vs Random |
|------|-------------------|----------------------|-----------|
| Top 1% | 27,276% | 655x | 23x |
| Top 5% | 5,862% | 2.7x | 5.9x |
| Top 10% | 3,129% | 2.8x | 6.9x |

## Pipeline Steps

### Step 1: Data Fetch
- Connects to Azure SQL `MarketValues` table
- Saves to `data.csv`
- Supports chunked fetch for large tables
- Driver detection with helpful error messages

### Step 2: Event Generation
- Sliding window clustering (block_size=200, stride=50)
- Hierarchical clustering with Ward linkage
- Quality scoring based on avg_return
- Detects dropout/acquisition transitions

### Step 3: ML Training
- Vectorized return/volatility computation
- Feature engineering (temporal, block percentiles)
- Logistic Regression with class balancing
- Trains on top decile forward returns

### Step 4: Allocation Backtest
- Test set selection (30% of blocks)
- Equal-weight allocation simulation
- Comparison vs quality heuristic and random
- Metrics: mean/median returns, positive %, improvement ratios

## Output Interpretation

### Success Indicators
- ✓ symbols indicate successful step completion
- Improvement ratios >1.0 indicate model outperforms baselines
- High positive percentages (>60%) at top tiers indicate precision

### Warning Signs
- Improvement ratios <1.0 suggest model underperforms
- Low positive percentages (<40%) indicate weak signal
- Large std deviation suggests unstable returns

## Next Steps After Validation
1. If Azure results match local performance:
   - Deploy sliding window event generation
   - Use LR model probabilities for ranking
   - Implement top 1-5% allocation rule

2. If Azure results diverge:
   - Check data quality differences
   - Verify timepoint count and coverage
   - Re-optimize stride parameter
   - Consider regime-specific models

## Troubleshooting

### ODBC Driver Missing
```
ERROR: Azure connection failed (missing ODBC drivers)
```
**Solution:** Install drivers or run with `SKIP_FETCH=1`

### Memory Issues
**Solution:** Use `AZURE_LIMIT` or `CHUNKED_FETCH=1`

### Model Training Fails
Check for:
- Insufficient events (<100)
- All NaN returns
- Feature dimension mismatch

## Performance Notes
- Local data (2557 timepoints): ~5-10 minutes total
- Azure full table: depends on row count and network
- Chunked fetch reduces memory but increases time
