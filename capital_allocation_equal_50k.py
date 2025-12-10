"""
Capital Allocation Trial - Equal $50k per position (ignore ADV)

Simplified trial:
- Fixed position size: up to $50,000 per event
- Ignore liquidity/ADV, ignore per-security caps
- Hold for 500 days (~2 years), realize Future_Return
- Events ranked by model; can filter by TOP_N
- Report returns across capital levels
"""

import os
import pandas as pd
import numpy as np
import joblib

HOLDING_PERIOD_DAYS = 500
FIXED_POSITION_CAP = 50_000  # USD

MODEL_FILE = 'ml_event_model_sliding_drop_lr.pkl'
EVENTS_FILE = 'events_sliding_window_features.csv'


def load_events_and_model():
    model = joblib.load(MODEL_FILE)
    events = pd.read_csv(EVENTS_FILE)
    events = events[events['Event_Type'] == 'DROP'].copy()
    events = events.dropna(subset=['Future_Return']).copy()
    return model, events


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


def rank_events(test_df, model):
    X = get_features(test_df, model)
    test_df['model_proba'] = model.predict_proba(X)[:, 1]
    test_df = test_df.sort_values('model_proba', ascending=False).reset_index(drop=True)
    return test_df

class EqualPositionSimulator:
    def __init__(self, initial_capital, fixed_position_cap=50_000):
        self.initial_capital = initial_capital
        self.fixed_position_cap = fixed_position_cap
        self.cash = initial_capital
        self.positions = []
        self.closed = []

    def equity(self):
        return self.cash + sum(p['current_value'] for p in self.positions)

    def open_position(self, event, day):
        # Allocate fixed size if cash available
        size = min(self.fixed_position_cap, self.cash)
        if size < 1000:  # skip tiny leftovers
            return False
        self.cash -= size
        pos = {
            'entry_day': day,
            'exit_day': day + HOLDING_PERIOD_DAYS,
            'size': size,
            'current_value': size,
            'future_return_pct': event['Future_Return'],
            'security': event['Security'],
            'model_proba': event['model_proba'],
        }
        self.positions.append(pos)
        return True

    def process_day(self, day):
        for p in self.positions[:]:
            held = day - p['entry_day']
            if held >= HOLDING_PERIOD_DAYS:
                final_value = p['size'] * (1 + p['future_return_pct'] / 100.0)
                pnl = final_value - p['size']
                self.cash += final_value
                self.closed.append({
                    'size': p['size'],
                    'final_value': final_value,
                    'pnl': pnl,
                    'return_pct': p['future_return_pct'],
                    'security': p['security'],
                    'model_proba': p['model_proba'],
                    'days_held': HOLDING_PERIOD_DAYS,
                })
                self.positions.remove(p)
            else:
                progress = held / HOLDING_PERIOD_DAYS
                p['current_value'] = p['size'] * (1 + (p['future_return_pct'] / 100.0) * progress)

    def run(self, ranked_events):
        positions_opened = 0
        for idx, (_, ev) in enumerate(ranked_events.iterrows()):
            day = idx
            self.process_day(day)
            if self.open_position(ev, day):
                positions_opened += 1
        # close remaining
        max_day = max([p['exit_day'] for p in self.positions], default=0)
        for d in range(day + 1, max_day + 1):
            self.process_day(d)
        return self.results()

    def results(self):
        if not self.closed:
            return None
        df = pd.DataFrame(self.closed)
        final_equity = self.equity()
        total_return_pct = ((final_equity - self.initial_capital) / self.initial_capital) * 100
        years = HOLDING_PERIOD_DAYS / 252
        annualized = ((final_equity / self.initial_capital) ** (1/years) - 1) * 100
        return {
            'initial_capital': self.initial_capital,
            'final_equity': final_equity,
            'n_positions': len(df),
            'avg_position_size': df['size'].mean(),
            'median_position_size': df['size'].median(),
            'win_rate_pct': (df['pnl'] > 0).mean() * 100,
            'avg_return_pct': df['return_pct'].mean(),
            'median_return_pct': df['return_pct'].median(),
            'total_return_pct': total_return_pct,
            'annualized_return_pct': annualized,
        }, df


def main():
    top_n_env = os.environ.get('TOP_N')
    top_n = int(top_n_env) if top_n_env else None

    model, events = load_events_and_model()
    train_df, test_df = split_train_test(events)
    test_df = rank_events(test_df, model)
    if top_n:
        test_df = test_df.head(top_n).copy()
        print(f"Using top {top_n} events")

    capital_levels = [
        1_000_000,
        5_000_000,
        10_000_000,
        25_000_000,
        50_000_000,
        100_000_000,
    ]

    results = []
    for cap in capital_levels:
        print(f"\nRunning equal $50k allocation with capital ${cap/1e6:.0f}M...")
        sim = EqualPositionSimulator(cap, FIXED_POSITION_CAP)
        res = sim.run(test_df)
        if res:
            metrics, positions = res
            results.append(metrics)
            print(f"Final Equity: ${metrics['final_equity']/1e6:.2f}M | Annualized: {metrics['annualized_return_pct']:.2f}% | Win Rate: {metrics['win_rate_pct']:.1f}% | Positions: {metrics['n_positions']}")
            if cap == capital_levels[-1]:
                positions.to_csv('equal_50k_positions_100M.csv', index=False)
    if results:
        pd.DataFrame(results).to_csv('equal_50k_results.csv', index=False)
        print("\n✓ Saved equal_50k_results.csv")

if __name__ == '__main__':
    main()
