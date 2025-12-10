"""
Model Performance Capacity Analysis (5% ADV)

Goal: Show how much capital can be allocated per event using 5% ADV,
then aggregate by model tiers (top 1%, 5%, 10%) on the test set.

Outputs:
- model_capacity_by_tier.csv
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


def capacity_summary_by_tier(test_df):
    n = len(test_df)
    tiers = [
        ('top_1pct', int(np.ceil(n * 0.01))),
        ('top_5pct', int(np.ceil(n * 0.05))),
        ('top_10pct', int(np.ceil(n * 0.10))),
    ]
    
    rows = []
    for name, k in tiers:
        subset = test_df.iloc[:k].copy()
        subset['capacity_5pct_adv'] = subset['avg_price'] * subset['avg_volume'] * ADV_PCT
        total_capacity = subset['capacity_5pct_adv'].sum()
        avg_capacity = subset['capacity_5pct_adv'].mean()
        median_capacity = subset['capacity_5pct_adv'].median()
        
        # performance metrics if available
        if 'Future_Return' in subset.columns:
            win_rate = (subset['Future_Return'] > 0).mean() * 100
            avg_return = subset['Future_Return'].mean()
            median_return = subset['Future_Return'].median()
        else:
            win_rate = np.nan
            avg_return = np.nan
            median_return = np.nan
        
        rows.append({
            'tier': name,
            'events': k,
            'total_capacity_usd': total_capacity,
            'avg_capacity_usd': avg_capacity,
            'median_capacity_usd': median_capacity,
            'win_rate_pct': win_rate,
            'avg_forward_return_pct': avg_return,
            'median_forward_return_pct': median_return,
        })
    
    return pd.DataFrame(rows)


def main():
    print("Loading events and model...")
    model, events = load_events_and_model()
    events = merge_symbol_adv(events)
    train_df, test_df = split_train_test(events)
    test_df = rank_test_by_model(test_df, model)
    
    print(f"Test events: {len(test_df)}")
    summary = capacity_summary_by_tier(test_df)
    summary.to_csv('model_capacity_by_tier.csv', index=False)
    
    print("\nCapacity by Tier (5% ADV):")
    print(summary.to_string(index=False, formatters={
        'total_capacity_usd': lambda x: f"${x:,.0f}",
        'avg_capacity_usd': lambda x: f"${x:,.0f}",
        'median_capacity_usd': lambda x: f"${x:,.0f}",
        'win_rate_pct': lambda x: f"{x:.1f}%" if pd.notna(x) else "",
        'avg_forward_return_pct': lambda x: f"{x:.1f}%" if pd.notna(x) else "",
        'median_forward_return_pct': lambda x: f"{x:.1f}%" if pd.notna(x) else "",
    }))
    
    print("\n✓ Saved model_capacity_by_tier.csv")


if __name__ == '__main__':
    main()
