"""
Backtest capital allocation on dropout events using model-driven ranking vs baselines.
Strategy:
- Re-train Logistic Regression on training blocks (dropout events only) using existing feature set from `events_with_features.csv`.
- Compute probabilities on test blocks (last 2 blocks).
- Select top 1%, 5%, 10% dropout events by probability; equal-weight capital allocation; summarize forward returns.
Baselines:
- Random selection (same count, 50 trials) -> average metrics
- Quality_Change heuristic: top events by raw Quality_Change
Outputs:
- backtest_dropout_allocation.csv (per selection tier and method)
- Prints summary metrics
"""
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
import json

EVENTS_FILE = 'events_with_features.csv'
OUTPUT_FILE = 'backtest_dropout_allocation.csv'
SUMMARY_JSON = 'backtest_dropout_allocation_summary.json'
FORWARD_RET_COL = 'Future_Return'

# Feature groups (must align with ml_event_model.py)
BASE_FEATURES = [
    'Prev_Quality','New_Quality','Quality_Change','quality_change_relative_block_mean',
    'time_since_last_dropout','time_since_last_acquisition','dropout_to_acquisition_gap','acquisition_to_dropout_gap',
    'cumulative_dropout_count','cumulative_acquisition_count','cumulative_dropout_acq_ratio',
    'block_dropout_count','block_acquisition_count','block_ratio_dropout_acq',
    'ret_20','ret_60','ret_120','vol_20','vol_60','vol_120'
]
Z_FEATURES = [f + '_blk_z' for f in BASE_FEATURES]
PCT_FEATURES = [
    'Quality_Change_blk_pct','quality_change_relative_block_mean_blk_pct',
    'ret_20_blk_pct','ret_60_blk_pct','ret_120_blk_pct',
    'vol_20_blk_pct','vol_60_blk_pct','vol_120_blk_pct',
    'cumulative_dropout_count_blk_pct','cumulative_acquisition_count_blk_pct'
]
ONE_HOT = ['EventType_dropout','EventType_acquisition']
ALL_FEATURES = BASE_FEATURES + Z_FEATURES + PCT_FEATURES + ONE_HOT

def winsorize(series, lower=0.01, upper=0.99):
    if len(series) == 0:
        return series
    lo = series.quantile(lower)
    hi = series.quantile(upper)
    return series.clip(lo, hi)

def summary_metrics(returns):
    if len(returns) == 0:
        return {k: np.nan for k in ['count','mean','median','trimmed_mean','std','positive_pct']}
    returns = pd.Series(returns)
    trimmed = winsorize(returns)
    return {
        'count': int(len(returns)),
        'mean': float(returns.mean()),
        'median': float(returns.median()),
        'trimmed_mean': float(trimmed.mean()),
        'std': float(returns.std()),
        'positive_pct': float((returns > 0).mean()*100.0)
    }

def main():
    if not Path(EVENTS_FILE).exists():
        print(f'Missing {EVENTS_FILE}. Run ml_event_model.py first.')
        return
    df = pd.read_csv(EVENTS_FILE)

    # Filter valid future returns
    df = df[np.isfinite(df[FORWARD_RET_COL])]

    # Identify test blocks (last 2)
    all_blocks = sorted(df['Block'].unique())
    test_blocks = all_blocks[-2:]
    train_blocks = [b for b in all_blocks if b not in test_blocks]

    drop_train = df[(df['EventType'] == 'dropout') & (df['Block'].isin(train_blocks))].copy()
    drop_test = df[(df['EventType'] == 'dropout') & (df['Block'].isin(test_blocks))].copy()

    if len(drop_train) == 0 or len(drop_test) == 0:
        print('Insufficient dropout events for train/test split.')
        return

    # Features preparation
    for f in ALL_FEATURES:
        if f not in drop_train.columns:
            drop_train[f] = 0.0
            drop_test[f] = 0.0

    X_train = drop_train[ALL_FEATURES].astype(float).fillna(0.0)
    y_train = (drop_train[FORWARD_RET_COL] >= np.nanpercentile(drop_train[FORWARD_RET_COL], 90)).astype(int)
    X_test = drop_test[ALL_FEATURES].astype(float).fillna(0.0)
    y_test = (drop_test[FORWARD_RET_COL] >= np.nanpercentile(drop_train[FORWARD_RET_COL], 90)).astype(int)

    pipe = Pipeline([
        ('scaler', StandardScaler()),
        ('lr', LogisticRegression(max_iter=2000, class_weight='balanced'))
    ])
    pipe.fit(X_train, y_train)
    drop_test['prob'] = pipe.predict_proba(X_test)[:,1]

    tiers = {
        'top_1pct': 0.01,
        'top_5pct': 0.05,
        'top_10pct': 0.10
    }

    rows = []
    baseline_random_stats = {}
    baseline_quality_stats = {}

    # Precompute counts
    n_total = len(drop_test)

    for name, frac in tiers.items():
        k = max(1, int(n_total * frac))
        # Model selection
        sel_model = drop_test.sort_values('prob', ascending=False).head(k)
        met_model = summary_metrics(sel_model[FORWARD_RET_COL])
        rows.append({'method':'model','tier':name, **met_model})

        # Quality_Change heuristic
        sel_quality = drop_test.sort_values('Quality_Change', ascending=False).head(k)
        met_quality = summary_metrics(sel_quality[FORWARD_RET_COL])
        rows.append({'method':'quality_change','tier':name, **met_quality})

        # Random baseline (50 repeats)
        rand_metrics = []
        for _ in range(50):
            sel_rand = drop_test.sample(k, replace=False, random_state=None)
            rand_metrics.append(sel_rand[FORWARD_RET_COL].values)
        rand_returns = np.concatenate(rand_metrics)
        met_rand = summary_metrics(rand_returns)
        rows.append({'method':'random','tier':name, **met_rand})

    out_df = pd.DataFrame(rows)
    out_df.to_csv(OUTPUT_FILE, index=False)

    # Aggregate improvement ratios (model vs baselines at each tier)
    improvements = {}
    for name in tiers.keys():
        model_row = out_df[(out_df['method']=='model') & (out_df['tier']==name)].iloc[0]
        qc_row = out_df[(out_df['method']=='quality_change') & (out_df['tier']==name)].iloc[0]
        rand_row = out_df[(out_df['method']=='random') & (out_df['tier']==name)].iloc[0]
        improvements[name] = {
            'mean_vs_quality_change': model_row['mean'] / qc_row['mean'] if qc_row['mean'] else np.nan,
            'mean_vs_random': model_row['mean'] / rand_row['mean'] if rand_row['mean'] else np.nan,
            'positive_pct_vs_quality_change': model_row['positive_pct'] - qc_row['positive_pct'],
            'positive_pct_vs_random': model_row['positive_pct'] - rand_row['positive_pct']
        }

    with open(SUMMARY_JSON,'w') as f:
        json.dump({'tiers':tiers,'improvements':improvements,'results':rows}, f, indent=2)

    print('\n=== Backtest Summary (Dropout Events, Test Blocks) ===')
    print(out_df.to_string(index=False))
    print('\nImprovement Ratios:')
    for t, vals in improvements.items():
        print(t, vals)
    print(f'Outputs saved: {OUTPUT_FILE}, {SUMMARY_JSON}')

if __name__ == '__main__':
    main()
