"""
Winners Capacity Analysis on Labeled Subset (5% ADV)

Resolves discrepancy by using only events with known Future_Return.
Steps:
- Filter to labeled events (Future_Return not null)
- Rank by model probability
- For tiers (top 1%, 5%, 10%), compute capacity for winners (Future_Return>0)
Outputs:
- model_winners_capacity_labeled.csv
- Prints concise summary
"""

import pandas as pd
import numpy as np
import joblib

MODEL_FILE = 'ml_event_model_sliding_drop_lr.pkl'
EVENTS_FILE = 'events_sliding_window_features.csv'
DATA_FILE = 'data.csv'
ADV_PCT = 0.05


def load_and_prepare():
    model = joblib.load(MODEL_FILE)
    events = pd.read_csv(EVENTS_FILE)
    events = events[events['Event_Type'] == 'DROP'].copy()
    # Keep labeled rows only
    labeled = events.dropna(subset=['Future_Return']).copy()
    # Merge avg price/volume
    data = pd.read_csv(DATA_FILE)
    stats = data.groupby('Symbol').agg({'Closing': 'mean', 'Volume': 'mean'}).reset_index()
    stats.columns = ['Security', 'avg_price', 'avg_volume']
    labeled = labeled.merge(stats, on='Security', how='left')
    labeled['avg_price'] = labeled['avg_price'].fillna(50.0)
    labeled['avg_volume'] = labeled['avg_volume'].fillna(1_000_000.0)
    
    # Rank by model
    cols = list(model.feature_names_in_)
    for c in cols:
        if c not in labeled.columns:
            labeled[c] = 0
    X = labeled[cols].fillna(0)
    labeled['model_proba'] = model.predict_proba(X)[:, 1]
    labeled = labeled.sort_values('model_proba', ascending=False).reset_index(drop=True)
    return labeled


def winners_capacity_by_tier(labeled):
    n = len(labeled)
    tiers = [
        ('top_1pct', int(np.ceil(n * 0.01))),
        ('top_5pct', int(np.ceil(n * 0.05))),
        ('top_10pct', int(np.ceil(n * 0.10))),
    ]
    rows = []
    for name, k in tiers:
        subset = labeled.iloc[:k].copy()
        winners = subset[subset['Future_Return'] > 0].copy()
        winners['capacity_5pct_adv'] = winners['avg_price'] * winners['avg_volume'] * ADV_PCT
        rows.append({
            'tier': name,
            'events_in_tier': k,
            'winners_count': len(winners),
            'winners_capacity_total_usd': winners['capacity_5pct_adv'].sum(),
            'winners_capacity_avg_usd': winners['capacity_5pct_adv'].mean() if len(winners) else 0,
            'winners_capacity_median_usd': winners['capacity_5pct_adv'].median() if len(winners) else 0,
            'winners_avg_forward_return_pct': winners['Future_Return'].mean() if len(winners) else np.nan,
            'winners_median_forward_return_pct': winners['Future_Return'].median() if len(winners) else np.nan,
        })
    return pd.DataFrame(rows)


def main():
    print('Preparing labeled subset and ranking by model...')
    labeled = load_and_prepare()
    print(f'Labeled events: {len(labeled)}; positive returns: {(labeled["Future_Return"]>0).sum()}')
    summary = winners_capacity_by_tier(labeled)
    summary.to_csv('model_winners_capacity_labeled.csv', index=False)
    
    print('\nWinners Capacity by Tier (Labeled, 5% ADV):')
    print(summary.to_string(index=False, formatters={
        'winners_capacity_total_usd': lambda x: f"${x:,.0f}",
        'winners_capacity_avg_usd': lambda x: f"${x:,.0f}",
        'winners_capacity_median_usd': lambda x: f"${x:,.0f}",
        'winners_avg_forward_return_pct': lambda x: f"{x:.1f}%" if pd.notna(x) else "",
        'winners_median_forward_return_pct': lambda x: f"{x:.1f}%" if pd.notna(x) else "",
    }))
    print('\n✓ Saved model_winners_capacity_labeled.csv')

if __name__ == '__main__':
    main()
