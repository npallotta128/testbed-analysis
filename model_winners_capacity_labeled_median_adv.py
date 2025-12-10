"""
Winners Capacity Analysis (5% of MEDIAN Dollar ADV)

Fixes capacity inflation by:
- Computing per-symbol median daily dollar volume (Closing × Volume)
- Clipping extreme outliers at the 99th percentile
- Using capacity = 5% × median dollar ADV
- Evaluated on labeled events (Future_Return not null), ranked by model

Outputs:
- model_winners_capacity_labeled_median_adv.csv
- Prints concise summary
"""

import pandas as pd
import numpy as np
import joblib

MODEL_FILE = 'ml_event_model_sliding_drop_lr.pkl'
EVENTS_FILE = 'events_sliding_window_features.csv'
DATA_FILE = 'data.csv'
ADV_PCT = 0.05


def compute_symbol_median_dollar_adv():
    data = pd.read_csv(DATA_FILE)
    # Ensure correct dtypes
    data['Closing'] = pd.to_numeric(data['Closing'], errors='coerce')
    data['Volume'] = pd.to_numeric(data['Volume'], errors='coerce')
    data = data.dropna(subset=['Closing','Volume'])
    data['dollar_volume'] = data['Closing'] * data['Volume']
    
    sym_median = data.groupby('Symbol')['dollar_volume'].median().reset_index()
    sym_median.columns = ['Security','median_dollar_adv']
    
    # Clip extreme outliers to 99th percentile
    p99 = np.percentile(sym_median['median_dollar_adv'], 99)
    sym_median['median_dollar_adv_clipped'] = np.minimum(sym_median['median_dollar_adv'], p99)
    return sym_median


def load_labeled_ranked(model):
    events = pd.read_csv(EVENTS_FILE)
    events = events[events['Event_Type']=='DROP'].copy()
    labeled = events.dropna(subset=['Future_Return']).copy()
    cols = list(model.feature_names_in_)
    for c in cols:
        if c not in labeled.columns:
            labeled[c] = 0
    X = labeled[cols].fillna(0)
    labeled['model_proba'] = model.predict_proba(X)[:,1]
    labeled = labeled.sort_values('model_proba', ascending=False).reset_index(drop=True)
    return labeled


def winners_capacity_by_tier(labeled_with_adv):
    n = len(labeled_with_adv)
    tiers = [
        ('top_1pct', int(np.ceil(n * 0.01))),
        ('top_5pct', int(np.ceil(n * 0.05))),
        ('top_10pct', int(np.ceil(n * 0.10))),
    ]
    rows = []
    for name, k in tiers:
        subset = labeled_with_adv.iloc[:k].copy()
        winners = subset[subset['Future_Return'] > 0].copy()
        winners['capacity_5pct_adv_usd'] = winners['median_dollar_adv_clipped'] * ADV_PCT
        rows.append({
            'tier': name,
            'events_in_tier': k,
            'winners_count': len(winners),
            'winners_capacity_total_usd': winners['capacity_5pct_adv_usd'].sum(),
            'winners_capacity_avg_usd': winners['capacity_5pct_adv_usd'].mean() if len(winners) else 0,
            'winners_capacity_median_usd': winners['capacity_5pct_adv_usd'].median() if len(winners) else 0,
            'winners_avg_forward_return_pct': winners['Future_Return'].mean() if len(winners) else np.nan,
            'winners_median_forward_return_pct': winners['Future_Return'].median() if len(winners) else np.nan,
        })
    return pd.DataFrame(rows)


def main():
    print('Computing median dollar ADV per symbol (with 99th percentile clip)...')
    sym_adv = compute_symbol_median_dollar_adv()
    print(f'Symbols with ADV: {len(sym_adv)} (p99 clip applied)')
    
    print('Loading model and labeled events, ranking by model...')
    model = joblib.load(MODEL_FILE)
    labeled = load_labeled_ranked(model)
    
    labeled = labeled.merge(sym_adv, on='Security', how='left')
    # Fallback for missing ADV: set to modest default (e.g., $50 × 1,000,000 = $50M)
    default_dollar_adv = 50 * 1_000_000
    labeled['median_dollar_adv_clipped'] = labeled['median_dollar_adv_clipped'].fillna(default_dollar_adv)
    
    summary = winners_capacity_by_tier(labeled)
    summary.to_csv('model_winners_capacity_labeled_median_adv.csv', index=False)
    
    print('\nWinners Capacity by Tier (5% of Median Dollar ADV):')
    print(summary.to_string(index=False, formatters={
        'winners_capacity_total_usd': lambda x: f"${x:,.0f}",
        'winners_capacity_avg_usd': lambda x: f"${x:,.0f}",
        'winners_capacity_median_usd': lambda x: f"${x:,.0f}",
        'winners_avg_forward_return_pct': lambda x: f"{x:.1f}%" if pd.notna(x) else "",
        'winners_median_forward_return_pct': lambda x: f"{x:.1f}%" if pd.notna(x) else "",
    }))
    print('\n✓ Saved model_winners_capacity_labeled_median_adv.csv')

if __name__ == '__main__':
    main()
