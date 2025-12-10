# Strategy Summary and Tier Capacity Table

## Strategy Overview
- Objective: Allocate equal capital per position across model-selected tiers and hold for 2 years (500 trading days) per position.
- Allocation: Flat per-position sizing ($10k–$500k tested), fund all available positions in a tier.
- Constraints (for this simplified view):
  - No liquidity constraints (ADV) applied in this table.
  - No capital reuse during the 2-year hold for cohort-average interpretation.
- Returns metric: Use tier-level average 2-year returns from `backtest_sliding_allocation.csv`.
  - Mean, Median, and Trimmed Mean are provided. Trimmed mean is more robust to outliers.

## Interpreting Returns
- Mean: Sensitive to outliers; can overstate typical performance when tails are heavy.
- Median: Robust to outliers; reflects the middle position’s return.
- Trimmed Mean: Average after discarding extremes; recommended for stability.

## Time Span
- Portfolio span = (last entry time − first entry time) + 500 trading days.
- Example from recent run: ~503 trading days when entries are clustered.

## Tier Capacity and Returns Table
This table shows, for each tier and per-position allocation, the maximum tier capital (fund-all assumption) and average 2-year returns.
The CSV source is saved at `tier_allocations_10k_to_500k_with_returns.csv`.

| tier     | per_position_alloc | n_events | max_capital | avg_2yr_return_pct_mean | avg_2yr_return_pct_median | avg_2yr_return_pct_trimmed_mean |
|----------|---------------------|----------|-------------|--------------------------|----------------------------|----------------------------------|
| top_1pct | $10,000             | 63       | $630,000    | 27276.14                 | 126.67                     | 27276.14                         |
| top_1pct | $25,000             | 63       | $1,575,000  | 27276.14                 | 126.67                     | 27276.14                         |
| top_1pct | $50,000             | 63       | $3,150,000  | 27276.14                 | 126.67                     | 27276.14                         |
| top_1pct | $100,000            | 63       | $6,300,000  | 27276.14                 | 126.67                     | 27276.14                         |
| top_1pct | $250,000            | 63       | $15,750,000 | 27276.14                 | 126.67                     | 27276.14                         |
| top_1pct | $500,000            | 63       | $31,500,000 | 27276.14                 | 126.67                     | 27276.14                         |
| top_5pct | $10,000             | 318      | $3,180,000  | 1295.62                  | 49.52                      | 1295.62                          |
| top_5pct | $25,000             | 318      | $7,950,000  | 1295.62                  | 49.52                      | 1295.62                          |
| top_5pct | $50,000             | 318      | $15,900,000 | 1295.62                  | 49.52                      | 1295.62                          |
| top_5pct | $100,000            | 318      | $31,800,000 | 1295.62                  | 49.52                      | 1295.62                          |
| top_5pct | $250,000            | 318      | $79,500,000 | 1295.62                  | 49.52                      | 1295.62                          |
| top_5pct | $500,000            | 318      | $159,000,000| 1295.62                  | 49.52                      | 1295.62                          |
| top_10pct| $10,000             | 636      | $6,360,000  | 560.79                   | 29.92                      | 560.79                           |
| top_10pct| $25,000             | 636      | $15,900,000 | 560.79                   | 29.92                      | 560.79                           |
| top_10pct| $50,000             | 636      | $31,800,000 | 560.79                   | 29.92                      | 560.79                           |
| top_10pct| $100,000            | 636      | $63,600,000 | 560.79                   | 29.92                      | 560.79                           |
| top_10pct| $250,000            | 636      | $159,000,000| 560.79                   | 29.92                      | 560.79                           |
| top_10pct| $500,000            | 636      | $318,000,000| 560.79                   | 29.92                      | 560.79                           |

Notes:
- Max capital scales linearly with per-position allocation.
- Consider emphasizing median or trimmed mean for expected performance to avoid outlier distortion.
- This table does not apply liquidity caps (e.g., 5% of median dollar ADV). Capacity under liquidity constraints will be lower.

## Files
- `backtest_sliding_allocation.csv`: Tier statistics and average 2-year returns.
- `tier_allocations_10k_to_500k_with_returns.csv`: Generated tier allocation/returns table.

## Next Steps
- Optional: Add expected dollar P&L columns using median or trimmed mean (`max_capital × return_pct`).
- Optional: Recompute capacity with liquidity constraints (e.g., 5% of median dollar ADV) once market-cap data is available.
