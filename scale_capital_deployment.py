"""
Scale Capital Deployment Analysis

Models realistic returns when deploying various capital amounts (up to $10B)
accounting for:
- Volume constraints (can't buy more than X% of daily volume)
- Price impact (larger positions move markets)
- Position size limits (diversification requirements)
- Execution slippage

Uses actual volume data from events to determine feasible position sizes.
"""

import pandas as pd
import numpy as np
from scipy.stats import trim_mean

def load_event_data():
    """Load events with features including volume data"""
    print("Loading event data with volume information...")
    df = pd.read_csv('events_sliding_window_features.csv')
    
    # Load model predictions
    import joblib
    model = joblib.load('ml_event_model_sliding_drop_lr.pkl')
    
    # Use exact features the model was trained on
    model_features = list(model.feature_names_in_)
    
    X = df[model_features].fillna(0)
    df['model_probability'] = model.predict_proba(X)[:, 1]
    
    # Rename columns for compatibility
    df['Symbol'] = df['Security']
    df['Block_ID'] = df['Block']
    df['Forward_Return_500'] = df['Future_Return']
    
    # Add volume features if not present
    if 'Prior_Volume_20' not in df.columns:
        # Estimate volume from volatility (rough proxy: higher vol = higher volume)
        df['Prior_Volume_20'] = df['vol_20'].fillna(10) * 100000  # Arbitrary scaling
    
    return df

def calculate_feasible_position(row, max_volume_pct=0.10, avg_volume_days=20):
    """
    Calculate maximum feasible position size based on volume constraints.
    
    Parameters:
    - max_volume_pct: Maximum % of average daily volume to trade (default 10%)
    - avg_volume_days: Number of days to accumulate position
    
    Returns: Maximum position size in USD
    """
    # Use Prior_Volume_20 as proxy for recent trading volume
    avg_daily_volume_shares = row.get('Prior_Volume_20', 0)
    
    if avg_daily_volume_shares <= 0:
        return 0
    
    # Assume we can trade max_volume_pct of daily volume over avg_volume_days days
    total_shares = avg_daily_volume_shares * max_volume_pct * avg_volume_days
    
    # Assume current price is implied by forward return calculation
    # If we don't have price, use volume as rough proxy (higher volume = more liquid = lower price impact)
    # For now, use a conservative $50 average stock price
    avg_price = 50.0
    
    max_position_usd = total_shares * avg_price
    
    return max_position_usd

def estimate_price_impact(position_size_usd, avg_daily_volume_usd, volatility):
    """
    Estimate price impact (slippage) as a function of position size relative to volume.
    
    Uses square-root price impact model:
    Impact = volatility * sqrt(position_size / avg_daily_volume)
    
    Returns: Expected slippage as % of position
    """
    if avg_daily_volume_usd <= 0:
        return 0.50  # 50% slippage for illiquid stocks
    
    volume_ratio = position_size_usd / avg_daily_volume_usd
    
    # Square root impact model with volatility scaling
    base_impact = np.sqrt(volume_ratio) * volatility * 0.01  # Convert volatility to decimal
    
    # Add fixed component for small trades (bid-ask spread ~ 0.1%)
    total_impact = 0.001 + base_impact
    
    return min(total_impact, 0.50)  # Cap at 50%

def run_scaled_backtest(total_capital, 
                        top_pct=0.01,
                        max_volume_pct=0.10,
                        accumulation_days=20,
                        max_position_pct=0.05):
    """
    Run backtest with capital constraints.
    
    Parameters:
    - total_capital: Total capital to deploy (USD)
    - top_pct: Top percentile of events to trade
    - max_volume_pct: Max % of daily volume per trade
    - accumulation_days: Days to accumulate each position
    - max_position_pct: Max % of total capital per position
    
    Returns: DataFrame with results
    """
    df = load_event_data()
    
    # Filter to dropout events only (higher signal)
    df = df[df['Event_Type'] == 'DROP'].copy()
    
    # Split into train/test by Block_ID
    unique_blocks = sorted(df['Block_ID'].unique())
    n_train = int(len(unique_blocks) * 0.7)
    train_blocks = unique_blocks[:n_train]
    test_blocks = unique_blocks[n_train:]
    
    test_df = df[df['Block_ID'].isin(test_blocks)].copy()
    
    print(f"\nTest set: {len(test_df)} events across {len(test_blocks)} blocks")
    
    # Calculate feasible position sizes
    test_df['max_position_volume'] = test_df.apply(
        lambda r: calculate_feasible_position(r, max_volume_pct, accumulation_days),
        axis=1
    )
    
    # Calculate max position based on capital constraint
    max_position_capital = total_capital * max_position_pct
    
    # Rank by model probability
    test_df = test_df.sort_values('model_probability', ascending=False)
    
    # Select top percentile
    n_select = max(1, int(len(test_df) * top_pct))
    selected = test_df.head(n_select).copy()
    
    print(f"Selected top {top_pct*100}%: {len(selected)} events")
    
    # Determine actual position sizes (constrained by volume and capital)
    selected['position_size'] = np.minimum(
        selected['max_position_volume'],
        max_position_capital
    )
    
    # Calculate how many positions we can actually fund
    selected = selected.sort_values('model_probability', ascending=False)
    selected['cumulative_capital'] = selected['position_size'].cumsum()
    
    # Only fund positions until we run out of capital
    funded = selected[selected['cumulative_capital'] <= total_capital].copy()
    
    if len(funded) < len(selected):
        print(f"Capital constraint: Only funded {len(funded)}/{len(selected)} positions")
    
    # Calculate expected slippage for each position
    funded['avg_daily_volume_usd'] = funded['Prior_Volume_20'] * 50.0  # Assume $50 avg price
    funded['volatility'] = funded['vol_20'].fillna(funded['vol_20'].median())
    
    funded['slippage_pct'] = funded.apply(
        lambda r: estimate_price_impact(r['position_size'], r['avg_daily_volume_usd'], r['volatility']),
        axis=1
    )
    
    # Adjust returns for slippage (applied on entry and exit)
    funded['gross_return_pct'] = funded['Forward_Return_500']
    funded['slippage_cost_pct'] = funded['slippage_pct'] * 2  # Entry + exit
    funded['net_return_pct'] = funded['gross_return_pct'] - funded['slippage_cost_pct']
    
    # Calculate dollar returns
    funded['gross_pnl'] = funded['position_size'] * (funded['gross_return_pct'] / 100)
    funded['net_pnl'] = funded['position_size'] * (funded['net_return_pct'] / 100)
    
    # Summary statistics
    total_deployed = funded['position_size'].sum()
    total_gross_pnl = funded['gross_pnl'].sum()
    total_net_pnl = funded['net_pnl'].sum()
    total_slippage_cost = funded['gross_pnl'].sum() - funded['net_pnl'].sum()
    
    gross_return_pct = (total_gross_pnl / total_deployed) * 100 if total_deployed > 0 else 0
    net_return_pct = (total_net_pnl / total_deployed) * 100 if total_deployed > 0 else 0
    
    utilization = (total_deployed / total_capital) * 100
    
    # Positive rate
    positive_trades = (funded['net_pnl'] > 0).sum()
    win_rate = (positive_trades / len(funded)) * 100 if len(funded) > 0 else 0
    
    # Average position size and slippage
    avg_position = funded['position_size'].mean()
    avg_slippage = funded['slippage_cost_pct'].mean()
    median_slippage = funded['slippage_cost_pct'].median()
    
    results = {
        'total_capital': total_capital,
        'capital_deployed': total_deployed,
        'utilization_pct': utilization,
        'n_positions': len(funded),
        'avg_position_size': avg_position,
        'gross_pnl': total_gross_pnl,
        'net_pnl': total_net_pnl,
        'slippage_cost': total_slippage_cost,
        'gross_return_pct': gross_return_pct,
        'net_return_pct': net_return_pct,
        'win_rate_pct': win_rate,
        'avg_slippage_pct': avg_slippage,
        'median_slippage_pct': median_slippage,
        'top_pct': top_pct
    }
    
    return results, funded

def main():
    print("="*80)
    print("SCALED CAPITAL DEPLOYMENT ANALYSIS")
    print("="*80)
    print("\nModeling returns across various capital levels")
    print("Accounting for: volume constraints, price impact, position limits\n")
    
    # Test multiple capital levels
    capital_levels = [
        1e6,      # $1M
        10e6,     # $10M
        50e6,     # $50M
        100e6,    # $100M
        250e6,    # $250M
        500e6,    # $500M
        1e9,      # $1B
        2.5e9,    # $2.5B
        5e9,      # $5B
        10e9,     # $10B
    ]
    
    results_list = []
    
    for capital in capital_levels:
        print(f"\n{'='*80}")
        print(f"Testing with ${capital/1e9:.2f}B capital" if capital >= 1e9 else f"Testing with ${capital/1e6:.0f}M capital")
        print('='*80)
        
        result, positions = run_scaled_backtest(
            total_capital=capital,
            top_pct=0.01,  # Top 1% events
            max_volume_pct=0.10,  # 10% of daily volume
            accumulation_days=20,  # 20-day accumulation
            max_position_pct=0.05  # 5% max per position
        )
        
        results_list.append(result)
        
        # Print summary
        print(f"\nResults:")
        print(f"  Capital deployed: ${result['capital_deployed']/1e6:.1f}M ({result['utilization_pct']:.1f}% utilization)")
        print(f"  Positions: {result['n_positions']}")
        print(f"  Avg position size: ${result['avg_position_size']/1e6:.2f}M")
        print(f"  Gross return: {result['gross_return_pct']:.1f}%")
        print(f"  Net return: {result['net_return_pct']:.1f}%")
        print(f"  Slippage cost: ${result['slippage_cost']/1e6:.1f}M ({result['avg_slippage_pct']:.2f}% avg)")
        print(f"  Win rate: {result['win_rate_pct']:.1f}%")
        print(f"  Net P&L: ${result['net_pnl']/1e6:.1f}M")
    
    # Create summary DataFrame
    summary_df = pd.DataFrame(results_list)
    summary_df['capital_label'] = summary_df['total_capital'].apply(
        lambda x: f"${x/1e9:.1f}B" if x >= 1e9 else f"${x/1e6:.0f}M"
    )
    
    # Save results
    output_file = 'capital_scaling_analysis.csv'
    summary_df.to_csv(output_file, index=False)
    print(f"\n{'='*80}")
    print(f"Results saved to: {output_file}")
    print('='*80)
    
    # Print capacity analysis
    print("\n" + "="*80)
    print("STRATEGY CAPACITY ANALYSIS")
    print("="*80)
    
    # Find optimal capital (where returns start degrading)
    summary_df['return_per_dollar'] = summary_df['net_pnl'] / summary_df['capital_deployed']
    peak_efficiency = summary_df['return_per_dollar'].max()
    threshold_efficiency = peak_efficiency * 0.75  # 75% of peak
    
    optimal_row = summary_df[summary_df['return_per_dollar'] >= threshold_efficiency].iloc[-1]
    
    print(f"\nOptimal capacity: ~{optimal_row['capital_label']}")
    print(f"  Net return: {optimal_row['net_return_pct']:.1f}%")
    print(f"  Total P&L: ${optimal_row['net_pnl']/1e6:.1f}M")
    print(f"  Return per dollar deployed: {optimal_row['return_per_dollar']:.2f}")
    
    # Show how returns degrade with scale
    print("\n" + "="*80)
    print("RETURN DEGRADATION WITH SCALE")
    print("="*80)
    print(f"\n{'Capital':<15} {'Net Return':<15} {'Net P&L':<15} {'Slippage':<15}")
    print("-" * 60)
    for _, row in summary_df.iterrows():
        print(f"{row['capital_label']:<15} {row['net_return_pct']:>10.1f}%    ${row['net_pnl']/1e6:>10.1f}M    {row['avg_slippage_pct']:>10.2f}%")
    
    return summary_df

if __name__ == '__main__':
    results = main()
