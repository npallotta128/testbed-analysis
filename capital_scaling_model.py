"""
Realistic Capital Scaling Model

Takes proven backtest results (27,276% return @ top 1%) and models 
how returns degrade with increasing capital due to:
- Volume constraints (liquidity limits)
- Price impact / slippage
- Position concentration limits

Based on actual backtest: 63 events, $100k starting capital, 27,276% mean return
"""

import pandas as pd
import numpy as np

def model_capacity_degradation():
    """
    Model how strategy returns degrade with scale.
    
    Base case (from backtest_sliding_allocation.csv):
    - Capital: ~$100k (implied from 63 positions, equal weight)
    - Events: 63 (top 1%)
    - Gross return: 27,276%
    - Win rate: 68.3%
    
    Degradation factors:
    1. Slippage increases with position size (square-root impact)
    2. Can't access all events at larger scale (volume constraints)
    3. Diversification requirements limit concentration
    """
    
    # Base case parameters
    base_capital = 100_000  # Implied from backtest
    base_n_events = 63
    base_gross_return_pct = 27276
    base_win_rate = 68.3
    
    # Assume average stock metrics
    avg_stock_price = 50  # USD
    avg_daily_volume_shares = 500_000  # shares
    avg_daily_volume_usd = avg_stock_price * avg_daily_volume_shares  # $25M/day
    avg_volatility_pct = 30  # 30% annualized
    
    capital_levels = [
        100_000,      # Base case
        1_000_000,    # $1M
        10_000_000,   # $10M
        50_000_000,   # $50M
        100_000_000,  # $100M
        250_000_000,  # $250M
        500_000_000,  # $500M
        1_000_000_000, # $1B
        2_500_000_000, # $2.5B
        5_000_000_000, # $5B
        10_000_000_000 # $10B
    ]
    
    results = []
    
    print("="*80)
    print("CAPITAL SCALING WITH DEGRADATION MODEL")
    print("="*80)
    print(f"\nBase case: ${base_capital:,} capital, 63 events, {base_gross_return_pct:.0f}% return\n")
    
    for capital in capital_levels:
        # Position size per event (equal weight)
        position_size = capital / base_n_events
        
        # Calculate what % of daily volume this represents
        # Assume we accumulate over 20 days
        daily_purchase = position_size / 20
        volume_pct = (daily_purchase / avg_daily_volume_usd) * 100
        
        # Square-root price impact model
        # Impact = volatility * sqrt(volume_pct) 
        # Entry + exit = 2x impact
        if volume_pct < 0.01:  # < 1% of daily volume
            slippage_pct = 0.1  # Minimal slippage (bid-ask only)
        else:
            impact_pct = avg_volatility_pct * np.sqrt(volume_pct / 100) * 0.5
            slippage_pct = max(0.1, impact_pct * 2)  # Entry + exit
        
        # Market capacity constraint
        # Beyond certain position sizes, we can't access all 63 events
        max_feasible_position = avg_daily_volume_usd * 0.10 * 20  # 10% daily vol, 20 days
        
        if position_size > max_feasible_position:
            # Need to reduce number of positions or reduce size
            feasible_positions = int((capital * 0.95) / max_feasible_position)  # 95% utilization
            feasible_positions = min(feasible_positions, base_n_events)
            actual_capital_deployed = feasible_positions * max_feasible_position
            utilization = (actual_capital_deployed / capital) * 100
        else:
            feasible_positions = base_n_events
            actual_capital_deployed = capital
            utilization = 100.0
        
        # Return degradation
        # Gross return degrades with slippage
        # Also degrades if we can't access all events (lower diversification = lower sharpe)
        position_quality_factor = feasible_positions / base_n_events  # 1.0 at full access
        
        net_return_pct = base_gross_return_pct * position_quality_factor - slippage_pct
        
        # Dollar returns
        total_pnl = (actual_capital_deployed * net_return_pct) / 100
        
        # Win rate slightly decreases with fewer positions (less diversification)
        adjusted_win_rate = base_win_rate * position_quality_factor
        
        result = {
            'capital': capital,
            'capital_label': f"${capital/1e9:.1f}B" if capital >= 1e9 else f"${capital/1e6:.0f}M" if capital >= 1e6 else f"${capital/1e3:.0f}k",
            'deployed': actual_capital_deployed,
            'utilization_pct': utilization,
            'n_positions': feasible_positions,
            'position_size_avg': actual_capital_deployed / feasible_positions if feasible_positions > 0 else 0,
            'volume_pct_per_trade': volume_pct,
            'slippage_pct': slippage_pct,
            'gross_return_pct': base_gross_return_pct * position_quality_factor,
            'net_return_pct': net_return_pct,
            'total_pnl': total_pnl,
            'win_rate_pct': adjusted_win_rate,
            'return_per_dollar': total_pnl / actual_capital_deployed if actual_capital_deployed > 0 else 0
        }
        
        results.append(result)
    
    return pd.DataFrame(results)

def print_results(df):
    print("\n" + "="*80)
    print("RETURN DEGRADATION WITH SCALE")
    print("="*80)
    print(f"\n{'Capital':<12} {'Deployed':<12} {'Positions':<10} {'Avg Size':<12} {'Slippage':<10} {'Net Return':<12} {'Total P&L':<15}")
    print("-" * 95)
    
    for _, row in df.iterrows():
        deployed_label = f"${row['deployed']/1e9:.2f}B" if row['deployed'] >= 1e9 else f"${row['deployed']/1e6:.1f}M"
        pos_size_label = f"${row['position_size_avg']/1e6:.2f}M"
        pnl_label = f"${row['total_pnl']/1e9:.2f}B" if row['total_pnl'] >= 1e9 else f"${row['total_pnl']/1e6:.1f}M"
        
        print(f"{row['capital_label']:<12} {deployed_label:<12} {row['n_positions']:<10} {pos_size_label:<12} {row['slippage_pct']:>7.2f}%   {row['net_return_pct']:>10.1f}%   {pnl_label:<15}")
    
    # Find optimal capacity
    print("\n" + "="*80)
    print("STRATEGY CAPACITY ANALYSIS")
    print("="*80)
    
    # Where returns stay above 1000% and utilization > 50%
    viable = df[(df['net_return_pct'] > 1000) & (df['utilization_pct'] > 50)]
    
    if len(viable) > 0:
        optimal = viable.iloc[-1]
        print(f"\nOptimal capacity: {optimal['capital_label']}")
        print(f"  Net return: {optimal['net_return_pct']:.1f}%")
        print(f"  Total P&L: ${optimal['total_pnl']/1e6:.1f}M")
        print(f"  Positions: {optimal['n_positions']}")
        print(f"  Slippage: {optimal['slippage_pct']:.2f}%")
    
    # Economic capacity (where absolute P&L peaks)
    max_pnl_idx = df['total_pnl'].idxmax()
    max_pnl_row = df.loc[max_pnl_idx]
    
    print(f"\nMaximum P&L capacity: {max_pnl_row['capital_label']}")
    print(f"  Net return: {max_pnl_row['net_return_pct']:.1f}%")
    print(f"  Total P&L: ${max_pnl_row['total_pnl']/1e9:.2f}B" if max_pnl_row['total_pnl'] >= 1e9 else f"  Total P&L: ${max_pnl_row['total_pnl']/1e6:.1f}M")
    print(f"  Positions: {max_pnl_row['n_positions']}")
    
    # Show degradation
    print("\n" + "="*80)
    print("KEY FINDINGS")
    print("="*80)
    
    base_return = df.iloc[0]['net_return_pct']
    degradation_50pct = df[df['net_return_pct'] <= base_return * 0.5]
    
    if len(degradation_50pct) > 0:
        threshold = degradation_50pct.iloc[0]
        print(f"\n• Returns degrade 50% at: {threshold['capital_label']}")
        print(f"  (from {base_return:.0f}% to {threshold['net_return_pct']:.0f}%)")
    
    profitable = df[df['net_return_pct'] > 100]
    if len(profitable) > 0:
        max_profitable = profitable.iloc[-1]
        print(f"\n• Strategy remains profitable (>100% return) up to: {max_profitable['capital_label']}")
    
    print(f"\n• At $10B scale:")
    final = df.iloc[-1]
    print(f"  - Can deploy: ${final['deployed']/1e9:.2f}B ({final['utilization_pct']:.1f}% utilization)")
    print(f"  - Expected return: {final['net_return_pct']:.1f}%")
    print(f"  - Estimated P&L: ${final['total_pnl']/1e9:.2f}B")

def main():
    results_df = model_capacity_degradation()
    
    # Save results
    results_df.to_csv('capital_scaling_model.csv', index=False)
    print(f"\nResults saved to: capital_scaling_model.csv")
    
    # Print analysis
    print_results(results_df)
    
    return results_df

if __name__ == '__main__':
    df = main()
