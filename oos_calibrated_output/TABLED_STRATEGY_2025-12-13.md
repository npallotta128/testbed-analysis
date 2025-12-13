# Strategy: Tabled — 2025-12-13

Decision: Table this calibrated / cluster-distance / slippage strategy for now.

Reasoning summary:
- Monte Carlo with square-root slippage shows single-event dominance: `k=1` policies occasionally produce very large ROI but are high-variance and fragile.
- Multi-position policies (`k>=3` or `k=5`) generally produced negative median ROI after slippage in the sampled folds.
- Several parameter cells returned `n_test_events=0` in Monte Carlo (no deployable trades), indicating the policy is often infeasible under current constraints.
- Given the fragility and lack of robust, repeatable performance, the team decided to table this strategy and revisit later with more data or improved execution models.

Key artifacts (location: `oos_calibrated_output/`):
- `scalability_by_floor_full_table.csv` — aggregated scaling results (floor × initial_capital × k) used to build heatmaps.
- `montecarlo_summary_by_param.csv` — Monte Carlo (slippage) summary for AUM runs (most recently re-run for AUM = $1,000,000 on 2025-12-13).
- Per-parameter Monte Carlo outputs (one file per tested param): `mc_floor_<floor>_k_<k>.csv` (multiple files).
- Heatmap PNGs: `plots/heatmap_floor_1000000_roi.png`, `plots/heatmap_floor_10000000_roi.png`, `plots/heatmap_floor_100000000_roi.png`, and matching `*_total_pnl.png`, `*_total_invested.png`.
- Calibrated selection and cluster optimization outputs: `oos_calibrated_output/oos_calibrated_all_selected_cal.csv`, `oos_calibrated_output/dropout_optimization_results_calibrated.csv`, `oos_calibrated_output/dropout_events_calibrated_*.csv`.

Suggested next steps when you want to revisit:
- Add real per-symbol ADV time series and model multi-day accumulation to make slippage modeling more realistic.
- Increase Monte Carlo iterations and the event pool (more folds/blocks) to get smoother estimates and reduce sampling noise.
- Require `n_test_events >= X` or p10 ROI >= 0 when selecting policy to avoid single-event reliance.
- Optionally compress/archive `oos_calibrated_output/` to free workspace, or move to a `archive/` folder if you want to preserve artifacts.

If you want, I can:
- (A) Archive these files into `oos_calibrated_output/archive_<date>.zip` now.
- (B) Push a quick commit tagging these artifacts with a short note and create a branch for later work.
- (C) Delete intermediate per-iteration Monte Carlo CSVs to reduce clutter (they can be re-generated).

Recorded by: automated analysis agent
Date: 2025-12-13
