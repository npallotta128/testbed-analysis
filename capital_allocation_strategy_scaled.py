"""
Capital Allocation Strategy - Scaled Analysis ($1M to $1B)

Uses:
- Sliding window dropout events with ML model predictions
- 5% capital constraint per position
- 2% volume constraint (price * volume * 0.02)
- Real price/volume data from data.csv merged with events
- Tests capital levels from $1M to $1B

Outputs:
- scaled_capital_allocation_results.csv: Performance by capital level
- scaled_capital_allocation_details.csv: Per-position details for largest capital level
"""

import pandas as pd
import numpy as np
import joblib

# Constants
MAX_POSITION_PCT = 0.05  # 5% of equity
VOLUME_CONSTRAINT_PCT = float(__import__('os').environ.get('VOLUME_CONSTRAINT_PCT', '0.05'))  # default 5% of price*volume
MODEL_FILE = 'ml_event_model_sliding_drop_lr.pkl'
EVENTS_FILE = 'events_sliding_window_features.csv'
DATA_FILE = 'data.csv'

def load_model_and_events():
    """Load trained model and events with features"""
    print("Loading model and events...")
    model = joblib.load(MODEL_FILE)
    events = pd.read_csv(EVENTS_FILE)
    
    # Filter dropout events only
    dropout = events[events['Event_Type'] == 'DROP'].copy()
    dropout = dropout.dropna(subset=['Future_Return'])
    
    print(f"Loaded {len(dropout)} dropout events")
    return model, dropout

def get_features(df, model):
    """Extract feature columns matching training"""
    feature_cols = list(model.feature_names_in_)
    missing = [c for c in feature_cols if c not in df.columns]
    if missing:
        print(f"Warning: Missing features {missing[:5]}...")
        # Fill missing with 0
        for col in missing:
            df[col] = 0
    return df[feature_cols].fillna(0)

def merge_price_volume(events_df):
    """Merge price and volume from data.csv"""
    print("Loading price/volume data (sampling for efficiency)...")
    
    # Get unique security-block pairs from events
    event_keys = events_df[['Security', 'Block']].drop_duplicates()
    
    # Load data.csv in chunks and extract needed dates
    print("Merging price/volume data...")
    
    # For simplicity, we'll load a representative sample or use average metrics
    # In production, you'd merge on Security+Date, but with 34M rows, we'll use averages
    
    # Load sample to get average volume/price per symbol
    data = pd.read_csv(DATA_FILE)
    
    # Calculate average price and volume per symbol
    symbol_stats = data.groupby('Symbol').agg({
        'Closing': 'mean',
        'Volume': 'mean'
    }).reset_index()
    symbol_stats.columns = ['Security', 'avg_price', 'avg_volume']
    
    # Merge with events
    merged = events_df.merge(symbol_stats, on='Security', how='left')
    
    # Fill missing with conservative defaults
    merged['avg_price'] = merged['avg_price'].fillna(50.0)
    merged['avg_volume'] = merged['avg_volume'].fillna(1000000.0)
    
    print(f"Merged price/volume for {len(merged)} events")
    return merged

def split_train_test(df):
    """Split by block (70/30 train/test)"""
    blocks = sorted(df['Block'].unique())
    train_blocks = blocks[:int(len(blocks) * 0.7)]
    
    train_df = df[df['Block'].isin(train_blocks)].copy()
    test_df = df[~df['Block'].isin(train_blocks)].copy()
    
    print(f"Train: {len(train_df)} events, Test: {len(test_df)} events")
    return train_df, test_df

def rank_events_by_model(test_df, model):
    """Rank events by model probability"""
    X_test = get_features(test_df, model)
    test_df['model_proba'] = model.predict_proba(X_test)[:, 1]
    
    # Sort by probability descending
    test_df = test_df.sort_values('model_proba', ascending=False).reset_index(drop=True)
    
    return test_df

def simulate_capital_allocation(ranked_events, total_capital, max_position_pct=0.05, volume_pct=0.02):
    """
    Simulate capital allocation with constraints
    
    Returns: dict with performance metrics
    """
    current_equity = total_capital
    positions = []
    
    for idx, row in ranked_events.iterrows():
        # Calculate constraints
        capital_cap = current_equity * max_position_pct
        volume_cap = row['avg_price'] * row['avg_volume'] * volume_pct
        
        # Position size is minimum of both
        position_size = min(capital_cap, volume_cap)
        
        # Check if we have enough cash
        if position_size > current_equity:
            position_size = current_equity
        
        if position_size < 100:  # Minimum $100 position
            continue
        
        # Determine binding constraint
        binding = 'capital' if capital_cap <= volume_cap else 'volume'
        
        # Calculate P&L
        expected_return_pct = row['Future_Return']
        pnl = position_size * (expected_return_pct / 100.0)
        
        # Update equity (simulate immediate close)
        current_equity = current_equity - position_size + (position_size + pnl)
        
        positions.append({
            'security': row['Security'],
            'block': row['Block'],
            'model_proba': row['model_proba'],
            'avg_price': row['avg_price'],
            'avg_volume': row['avg_volume'],
            'position_size': position_size,
            'binding_constraint': binding,
            'capital_cap': capital_cap,
            'volume_cap': volume_cap,
            'expected_return_pct': expected_return_pct,
            'pnl': pnl,
            'cumulative_equity': current_equity
        })
        
        # Stop if we run out of capital
        if current_equity < 100:
            break
    
    positions_df = pd.DataFrame(positions)
    
    if len(positions_df) == 0:
        return None, None
    
    # Calculate metrics
    total_deployed = positions_df['position_size'].sum()
    total_pnl = positions_df['pnl'].sum()
    final_equity = current_equity
    total_return = ((final_equity - total_capital) / total_capital) * 100
    
    capital_constrained = (positions_df['binding_constraint'] == 'capital').sum()
    volume_constrained = (positions_df['binding_constraint'] == 'volume').sum()
    
    win_rate = (positions_df['pnl'] > 0).mean() * 100
    
    metrics = {
        'total_capital': total_capital,
        'final_equity': final_equity,
        'total_deployed': total_deployed,
        'total_pnl': total_pnl,
        'total_return_pct': total_return,
        'n_positions': len(positions_df),
        'avg_position_size': positions_df['position_size'].mean(),
        'median_position_size': positions_df['position_size'].median(),
        'max_position_size': positions_df['position_size'].max(),
        'capital_constrained_pct': (capital_constrained / len(positions_df)) * 100,
        'volume_constrained_pct': (volume_constrained / len(positions_df)) * 100,
        'win_rate_pct': win_rate,
        'avg_return_pct': positions_df['expected_return_pct'].mean(),
        'median_return_pct': positions_df['expected_return_pct'].median(),
    }
    
    return metrics, positions_df

def run_scaled_analysis():
    """Run capital allocation across multiple capital levels"""
    
    # Load model and events
    model, events = load_model_and_events()
    
    # Merge price/volume data
    events = merge_price_volume(events)
    
    # Split train/test
    train_df, test_df = split_train_test(events)
    
    # Rank test events by model probability
    test_df = rank_events_by_model(test_df, model)
    
    print(f"\nTest set has {len(test_df)} events ranked by model probability")
    print(f"Top event probability: {test_df['model_proba'].max():.4f}")
    print(f"Median event probability: {test_df['model_proba'].median():.4f}")
    
    # Capital levels to test
    capital_levels = [
        1_000_000,      # $1M
        5_000_000,      # $5M
        10_000_000,     # $10M
        25_000_000,     # $25M
        50_000_000,     # $50M
        100_000_000,    # $100M
        250_000_000,    # $250M
        500_000_000,    # $500M
        1_000_000_000,  # $1B
    ]
    
    results = []
    all_positions = {}
    
    print("\n" + "="*80)
    print("RUNNING SCALED CAPITAL ALLOCATION ANALYSIS")
    print("="*80)
    
    for idx, capital in enumerate(capital_levels, 1):
        print(f"\n[{idx}/{len(capital_levels)}] Testing ${capital/1e6:.0f}M capital...")
        metrics, positions_df = simulate_capital_allocation(test_df, capital)
        
        if metrics:
            results.append(metrics)
            
            # Store positions for largest capital level
            if capital == capital_levels[-1]:
                all_positions = positions_df
            
            print(f"\n${capital/1e6:.0f}M Capital:")
            print(f"  Final Equity: ${metrics['final_equity']/1e6:.2f}M")
            print(f"  Total Return: {metrics['total_return_pct']:.2f}%")
            print(f"  Positions: {metrics['n_positions']}")
            print(f"  Avg Position: ${metrics['avg_position_size']:,.0f}")
            print(f"  Capital Constrained: {metrics['capital_constrained_pct']:.1f}%")
            print(f"  Volume Constrained: {metrics['volume_constrained_pct']:.1f}%")
            print(f"  Win Rate: {metrics['win_rate_pct']:.1f}%")
    
    # Save results
    results_df = pd.DataFrame(results)
    results_df.to_csv('scaled_capital_allocation_results.csv', index=False)
    print(f"\n✓ Saved results to scaled_capital_allocation_results.csv")
    
    if len(all_positions) > 0:
        all_positions.to_csv('scaled_capital_allocation_details.csv', index=False)
        print(f"✓ Saved position details to scaled_capital_allocation_details.csv")
    
    # Print summary
    print("\n" + "="*80)
    print("SUMMARY - RETURNS BY CAPITAL LEVEL")
    print("="*80)
    print(results_df[['total_capital', 'total_return_pct', 'n_positions', 
                      'capital_constrained_pct', 'volume_constrained_pct']].to_string(index=False))
    
    return results_df

if __name__ == '__main__':
    results = run_scaled_analysis()
