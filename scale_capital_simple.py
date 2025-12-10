"""
Simplified Capital Scaling Analysis

Uses actual volume and return data from events to model capacity constraints.
"""

import pandas as pd
import numpy as np

def load_data_with_volume():
    """Merge events with volume data from original dataset"""
    print("Loading events and volume data...")
    
    # Load events
    events = pd.read_csv('events_sliding_window_features.csv')
    events = events[events['Event_Type'] == 'DROP'].copy()  # Focus on dropout events
    
    # Load volume data
    data = pd.read_csv('data.csv')
    data = data.dropna(subset=['Symbol'])  # Drop NaN symbols
    data['Date'] = pd.to_datetime(data['Date'])
    data = data.sort_values(['Symbol', 'Date'])
    
    # Add timepoint index to data
    symbols = sorted([s for s in data['Symbol'].unique() if isinstance(s, str)])
    symbol_to_idx = {s: i for i, s in enumerate(symbols)}
    data['symbol_idx'] = data['Symbol'].map(symbol_to_idx)
    
    # Group by symbol and add row number as timepoint
    data['Timepoint'] = data.groupby('Symbol').cumcount()
    
    #Merge volume onto events (match on Security/Block)
    # For simplicity, use Block as approximate timepoint
    events['Timepoint'] = events['Block'] * 200  # Assuming block_size=200
    
    # Merge with data to get volume and price
    merged = events.merge(
        data[['Symbol', 'Timepoint', 'Volume', 'Closing']],
        left_on=['Security', 'Timepoint'],
        right_on=['Symbol', 'Timepoint'],
        how='left'
    )
    
    # For events without exact match, use avg volume
    avg_volume = data.groupby('Symbol')['Volume'].mean().to_dict()
    avg_price = data.groupby('Symbol')['Closing'].mean().to_dict()
    
    merged['Volume'] = merged['Volume'].fillna(merged['Security'].map(avg_volume))
    merged['Price'] = merged['Closing'].fillna(merged['Security'].map(avg_price))
    
    # Drop events with missing volume/price
    merged = merged.dropna(subset=['Volume', 'Price'])
    
    print(f"Loaded {len(merged)} events with volume data")
    
    # Load model probabilities
    import joblib
    model = joblib.load('ml_event_model_sliding_drop_lr.pkl')
    model_features = list(model.feature_names_in_)
    
    X = merged[model_features].fillna(0)
    merged['model_prob'] = model.predict_proba(X)[:, 1]
    
    # Use Future_Return as forward return
    merged['forward_return_pct'] = merged['Future_Return']
    
    # Drop events without forward return data
    merged = merged.dropna(subset=['forward_return_pct'])
    
    print(f"After filtering NaN returns: {len(merged)} events")
    
    return merged

def run_backtest(df, total_capital, max_position_pct=0.05, max_volume_pct=0.10):
    """
    Backtest with capital and volume constraints.
    
    Parameters:
    - total_capital: Total USD to deploy
    - max_position_pct: Max % of capital per position (5% = max $500M for $10B fund)
    - max_volume_pct: Max % of 20-day avg volume to trade (10% default)
    """
    
    # Split train/test by Block
    blocks = sorted(df['Block'].unique())
    n_train = int(len(blocks) * 0.7)
    test_blocks = blocks[n_train:]
    
    test = df[df['Block'].isin(test_blocks)].copy()
    print(f"\nTest set: {len(test)} events")
    
    # Rank by model probability
    test = test.sort_values('model_prob', ascending=False).head(int(len(test) * 0.01))
    print(f"Top 1%: {len(test)} events")
    
    # Calculate volume-constrained position sizes
    # Assume we accumulate over 20 days at 10% of daily volume
    test['max_shares_volume'] = test['Volume'] * max_volume_pct * 20
    test['max_usd_volume'] = test['max_shares_volume'] * test['Price']
    
    # Capital-constrained position size
    max_position_usd = total_capital * max_position_pct
    
    # Take minimum of volume and capital constraints
    test['position_size'] = np.minimum(test['max_usd_volume'], max_position_usd)
    
    # Sort by probability and allocate capital
    test = test.sort_values('model_prob', ascending=False)
    test['cum_capital'] = test['position_size'].cumsum()
    
    # Only fund positions within capital budget
    funded = test[test['cum_capital'] <= total_capital].copy()
    
    if len(funded) == 0:
        return {
            'total_capital': total_capital,
            'deployed': 0,
            'n_positions': 0,
            'mean_return_pct': 0,
            'total_pnl': 0,
            'win_rate_pct': 0
        }
    
    print(f"Funded: {len(funded)}/{len(test)} positions")
    
    # Calculate returns (no slippage adjustment for now - add later)
    funded['pnl'] = funded['position_size'] * (funded['forward_return_pct'] / 100)
    
    total_deployed = funded['position_size'].sum()
    total_pnl = funded['pnl'].sum()
    mean_return = (total_pnl / total_deployed) * 100 if total_deployed > 0 else 0
    win_rate = (funded['pnl'] > 0).sum() / len(funded) * 100
    
    return {
        'total_capital': total_capital,
        'deployed': total_deployed,
        'utilization_pct': (total_deployed / total_capital) * 100,
        'n_positions': len(funded),
        'avg_position': total_deployed / len(funded),
        'mean_return_pct': mean_return,
        'total_pnl': total_pnl,
        'win_rate_pct': win_rate
    }

def main():
    df = load_data_with_volume()
    
    capitals = [1e6, 10e6, 50e6, 100e6, 250e6, 500e6, 1e9, 2.5e9, 5e9, 10e9]
    
    results = []
    
    print("\n" + "="*80)
    print("CAPITAL SCALING ANALYSIS")
    print("="*80)
    
    for cap in capitals:
        label = f"${cap/1e9:.1f}B" if cap >= 1e9 else f"${cap/1e6:.0f}M"
        print(f"\n{label}:")
        print("-" * 40)
        
        result = run_backtest(df, cap)
        results.append(result)
        
        print(f"  Deployed: ${result['deployed']/1e6:.1f}M ({result['utilization_pct']:.1f}%)")
        print(f"  Positions: {result['n_positions']}")
        print(f"  Avg size: ${result['avg_position']/1e6:.2f}M" if result['n_positions'] > 0 else "  Avg size: $0M")
        print(f"  Return: {result['mean_return_pct']:.1f}%")
        print(f"  P&L: ${result['total_pnl']/1e6:.1f}M")
        print(f"  Win rate: {result['win_rate_pct']:.1f}%")
    
    # Save results
    results_df = pd.DataFrame(results)
    results_df.to_csv('capital_scaling_simple.csv', index=False)
    
    print("\n" + "="*80)
    print(f"Results saved to: capital_scaling_simple.csv")
    print("="*80)
    
    return results_df

if __name__ == '__main__':
    results = main()
