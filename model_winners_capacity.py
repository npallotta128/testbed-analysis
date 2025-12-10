"""
Winners Capacity Analysis (5% ADV)

For each model tier (top 1%, 5%, 10%) on the test set:
- Filter winners: Future_Return > 0
- Compute capacity: avg_price × avg_volume × 5%
- Aggregate totals and per-event stats

Outputs:
- model_winners_capacity_by_tier.csv
- Prints concise summary to stdout
"""

import pandas as pd
import numpy as np
import joblib

MODEL_FILE = 'ml_event_model_sliding_drop_lr.pkl'
EVENTS_FILE = 'events_sliding_window_features.csv'
DATA_FILE = 'data.csv'
ADV_PCT = 0.05


def load_events_and_model():
    model = joblib.load(MODEL_FILE)
    events = pd.read_csv(EVENTS_FILE)
    events = events[events['Event_Type'] == 'DROP'].copy()
    return model, events


def merge_symbol_adv(events):
    data = pd.read_csv(DATA_FILE)
    stats = data.groupby('Symbol').agg({'Closing': 'mean', 'Volume': 'mean'}).reset_index()
    stats.columns = ['Security', 'avg_price', 'avg_volume']
    merged = events.merge(stats, on='Security', how='left')
    merged['avg_price'] = merged['avg_price'].fillna(50.0)
    merged['avg_volume'] = merged['avg_volume'].fillna(1_000_000.0)
    return merged


def get_features(df, model):
    cols = list(model.feature_names_in_)
    for c in cols:
        if c not in df.columns:
            df[c] = 0
    return df[cols].fillna(0)


def split_train_test(df):
    blocks = sorted(df['Block'].unique())
    train_blocks = blocks[:int(len(blocks) * 0.7)]
    train_df = df[df['Block'].isin(train_blocks)].copy()
    test_df = df[~df['Block'].isin(train_blocks)].copy()
    return train_df, test_df


def rank_test_by_model(test_df, model):
    X = get_features(test_df, model)
    test_df['model_proba'] = model.predict_proba(X)[:, 1]
    test_df = test_df.sort_values('model_proba', ascending=False).reset_index(drop=True)
    return test_df


def winners_capacity_by_tier(test_df):
    n = len(test_df)
    tiers = [
        ('top_1pct', int(np.ceil(n * 0.01))),
        ('top_5pct', int(np.ceil(n * 0.05))),
        ('top_10pct', int(np.ceil(n * 0.10))),
    ]
    
    rows = []
    for name, k in tiers:
        subset = test_df.iloc[:k].copy()
        # Identify winners
        subset = subset.dropna(subset=['Future_Return'])
        winners = subset[subset['Future_Return'] > 0].copy()
        winners['capacity_5pct_adv'] = winners['avg_price'] * winners['avg_volume'] * ADV_PCT
        
        total_capacity = winners['capacity_5pct_adv'].sum()
        avg_capacity = winners['capacity_5pct_adv'].mean() if len(winners) else 0
        median_capacity = winners['capacity_5pct_adv'].median() if len(winners) else 0
        
        rows.append({
            'tier': name,
            'events_in_tier': k,
            'winners_count': len(winners),
            'winners_capacity_total_usd': total_capacity,
            'winners_capacity_avg_usd': avg_capacity,
            'winners_capacity_median_usd': median_capacity,
            'winners_avg_forward_return_pct': winners['Future_Return'].mean() if len(winners) else np.nan,
            'winners_median_forward_return_pct': winners['Future_Return'].median() if len(winners) else np.nan,
        })
    
    return pd.DataFrame(rows)


def main():
    print("Loading events and model...")
    model, events = load_events_and_model()
    events = merge_symbol_adv(events)
    train_df, test_df = split_train_test(events)
    test_df = rank_test_by_model(test_df, model)
    
    print(f"Test events: {len(test_df)}")
    summary = winners_capacity_by_tier(test_df)
    summary.to_csv('model_winners_capacity_by_tier.csv', index=False)
    
    print("\nWinners Capacity by Tier (5% ADV):")
    print(summary.to_string(index=False, formatters={
        'winners_capacity_total_usd': lambda x: f"${x:,.0f}",
        'winners_capacity_avg_usd': lambda x: f"${x:,.0f}",
        'winners_capacity_median_usd': lambda x: f"${x:,.0f}",
        'winners_avg_forward_return_pct': lambda x: f"{x:.1f}%" if pd.notna(x) else "",
        'winners_median_forward_return_pct': lambda x: f"{x:.1f}%" if pd.notna(x) else "",
    }))
    
    print("\n✓ Saved model_winners_capacity_by_tier.csv")


if __name__ == '__main__':
    main()
