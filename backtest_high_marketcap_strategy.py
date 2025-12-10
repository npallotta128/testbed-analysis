"""
High Market Cap Cluster Strategy - Backtesting & Analysis Framework

Provides tools to:
1. Analyze detected high-cap cluster transitions
2. Run portfolio simulations
3. Compare BUY/SELL signals
4. Optimize parameters
"""

import pandas as pd
import numpy as np
from pathlib import Path
from collections import defaultdict
import json


def analyze_events(events_file='high_cap_cluster_events.csv'):
    """Comprehensive analysis of high market cap cluster events"""
    
    print("\n" + "="*80)
    print("HIGH MARKET CAP CLUSTER TRANSITION - EVENT ANALYSIS")
    print("="*80)
    
    events = pd.read_csv(events_file)
    events['Date'] = pd.to_datetime(events['Date'])
    events_with_returns = events[events['Future_Return'].notna()].copy()
    
    if len(events_with_returns) == 0:
        print("No events with return data")
        return
    
    # Overall stats
    print(f"\n📊 OVERALL STATISTICS")
    print(f"  Total events: {len(events_with_returns)}")
    print(f"  Average return: {events_with_returns['Future_Return'].mean():+.2f}%")
    print(f"  Median return: {events_with_returns['Future_Return'].median():+.2f}%")
    print(f"  Std dev: {events_with_returns['Future_Return'].std():.2f}%")
    print(f"  Min return: {events_with_returns['Future_Return'].min():+.2f}%")
    print(f"  Max return: {events_with_returns['Future_Return'].max():+.2f}%")
    print(f"  Win rate: {(events_with_returns['Future_Return'] > 0).mean()*100:.1f}%")
    print(f"  Sharpe ratio: {events_with_returns['Future_Return'].mean() / (events_with_returns['Future_Return'].std() + 1e-6):.3f}")
    
    # By signal
    print(f"\n📈 BY SIGNAL TYPE")
    for signal in ['BUY', 'SELL']:
        subset = events_with_returns[events_with_returns['Signal'] == signal]
        if len(subset) == 0:
            continue
        
        print(f"\n  {signal} ({len(subset)} events):")
        print(f"    Avg return: {subset['Future_Return'].mean():+.2f}%")
        print(f"    Median return: {subset['Future_Return'].median():+.2f}%")
        print(f"    Win rate: {(subset['Future_Return'] > 0).mean()*100:.1f}%")
        print(f"    Sharpe: {subset['Future_Return'].mean() / (subset['Future_Return'].std() + 1e-6):.3f}")
    
    # By stock
    print(f"\n💼 BY SECURITY")
    stock_stats = events_with_returns.groupby('Security').agg({
        'Future_Return': ['count', 'mean', 'median'],
        'Market_Cap': 'first'
    }).round(2)
    stock_stats.columns = ['Count', 'Avg_Return', 'Median_Return', 'Market_Cap']
    stock_stats = stock_stats.sort_values('Avg_Return', ascending=False)
    
    for idx, row in stock_stats.iterrows():
        cap_str = f"${row['Market_Cap']/1e9:.1f}B" if row['Market_Cap'] > 0 else "N/A"
        print(f"  {idx:10} Count={int(row['Count']):2}  Mean={row['Avg_Return']:+7.2f}%  "
              f"Median={row['Median_Return']:+7.2f}%  Cap={cap_str}")
    
    # Quality change analysis
    print(f"\n🔄 QUALITY CHANGE ANALYSIS")
    events_sorted = events_with_returns.sort_values('Quality_Change', ascending=False)
    print(f"  Max quality change: {events_sorted['Quality_Change'].max():+.2f}")
    print(f"  Min quality change: {events_sorted['Quality_Change'].min():+.2f}")
    print(f"  Median quality change: {events_sorted['Quality_Change'].median():+.2f}")
    
    # Correlation analysis
    print(f"\n📊 CORRELATION ANALYSIS")
    correlation = events_with_returns['Quality_Change'].corr(events_with_returns['Future_Return'])
    print(f"  Quality change vs Future return correlation: {correlation:.3f}")
    
    return events_with_returns


def simulate_portfolio(events_file='high_cap_cluster_events.csv', initial_capital=100000,
                       position_size_type='equal', signal_filter=None, quality_threshold=None):
    """
    Simulate portfolio using detected signals
    
    Args:
        events_file: Path to events CSV
        initial_capital: Starting capital
        position_size_type: 'equal' or 'market_cap_weighted'
        signal_filter: 'BUY' or 'SELL' to filter signals
        quality_threshold: Minimum quality change to include event
    """
    
    print("\n" + "="*80)
    print("PORTFOLIO SIMULATION")
    print("="*80)
    
    events = pd.read_csv(events_file)
    events['Date'] = pd.to_datetime(events['Date'])
    events_with_returns = events[events['Future_Return'].notna()].copy()
    
    # Apply filters
    if signal_filter:
        events_with_returns = events_with_returns[events_with_returns['Signal'] == signal_filter]
    
    if quality_threshold is not None:
        events_with_returns = events_with_returns[abs(events_with_returns['Quality_Change']) >= quality_threshold]
    
    if len(events_with_returns) == 0:
        print("No events after filtering")
        return None
    
    print(f"\nFilters applied:")
    if signal_filter:
        print(f"  Signal: {signal_filter}")
    if quality_threshold:
        print(f"  Quality change >= {quality_threshold}")
    print(f"  Events selected: {len(events_with_returns)}")
    
    # Calculate position returns
    returns_pct = events_with_returns['Future_Return'].values / 100  # Convert to decimal
    
    if position_size_type == 'equal':
        # Equal weight positions
        position_size = initial_capital / len(events_with_returns)
        position_gains = returns_pct * position_size
        
        print(f"\nPosition sizing: EQUAL")
        print(f"  Per position: ${position_size:,.0f}")
    
    elif position_size_type == 'market_cap_weighted':
        # Market cap weighted
        market_caps = events_with_returns['Market_Cap'].values
        weights = market_caps / market_caps.sum()
        position_gains = returns_pct * weights * initial_capital
        
        print(f"\nPosition sizing: MARKET CAP WEIGHTED")
        print(f"  Weight range: {weights.min()*100:.1f}% - {weights.max()*100:.1f}%")
    
    else:
        raise ValueError(f"Unknown position_size_type: {position_size_type}")
    
    # Portfolio results
    total_gains = position_gains.sum()
    final_capital = initial_capital + total_gains
    total_return_pct = (total_gains / initial_capital) * 100
    
    # Win/loss stats
    winning_positions = (returns_pct > 0).sum()
    losing_positions = (returns_pct < 0).sum()
    
    print(f"\n💰 PORTFOLIO RESULTS")
    print(f"  Initial capital: ${initial_capital:,.0f}")
    print(f"  Total gains/losses: ${total_gains:,.0f}")
    print(f"  Final capital: ${final_capital:,.0f}")
    print(f"  Total return: {total_return_pct:+.2f}%")
    print(f"  Winning positions: {winning_positions}/{len(events_with_returns)}")
    print(f"  Losing positions: {losing_positions}/{len(events_with_returns)}")
    print(f"  Win rate: {(winning_positions/len(events_with_returns))*100:.1f}%")
    
    # Risk metrics
    avg_gain = returns_pct[returns_pct > 0].mean() * 100 if winning_positions > 0 else 0
    avg_loss = returns_pct[returns_pct < 0].mean() * 100 if losing_positions > 0 else 0
    profit_factor = abs(winning_positions * avg_gain / (losing_positions * avg_loss)) if losing_positions > 0 and avg_loss != 0 else np.inf
    
    print(f"\n📊 RISK METRICS")
    print(f"  Avg winner: {avg_gain:+.2f}%")
    print(f"  Avg loser: {avg_loss:+.2f}%")
    print(f"  Profit factor: {profit_factor:.2f}" if profit_factor != np.inf else "  Profit factor: ∞")
    print(f"  Position sharpe: {returns_pct.mean() / (returns_pct.std() + 1e-6):.3f}")
    
    return {
        'initial_capital': initial_capital,
        'final_capital': final_capital,
        'total_return': total_return_pct,
        'winning_positions': winning_positions,
        'losing_positions': losing_positions,
        'win_rate': (winning_positions/len(events_with_returns))*100,
        'num_positions': len(events_with_returns)
    }


def compare_strategies(events_file='high_cap_cluster_events.csv'):
    """Compare different strategy configurations"""
    
    print("\n" + "="*80)
    print("STRATEGY COMPARISON")
    print("="*80)
    
    results = []
    
    # Strategy 1: All events
    print("\n1️⃣  ALL EVENTS (No filters)")
    r1 = simulate_portfolio(events_file, initial_capital=100000)
    results.append(('All Events', r1))
    
    # Strategy 2: BUY only
    print("\n2️⃣  BUY SIGNALS ONLY")
    r2 = simulate_portfolio(events_file, initial_capital=100000, signal_filter='BUY')
    results.append(('BUY Only', r2))
    
    # Strategy 3: SELL only
    print("\n3️⃣  SELL SIGNALS ONLY")
    r3 = simulate_portfolio(events_file, initial_capital=100000, signal_filter='SELL')
    results.append(('SELL Only', r3))
    
    # Strategy 4: High quality changes
    print("\n4️⃣  HIGH QUALITY CHANGES (>20 points)")
    r4 = simulate_portfolio(events_file, initial_capital=100000, quality_threshold=20)
    results.append(('High Quality Change', r4))
    
    # Summary table
    print("\n" + "="*80)
    print("SUMMARY COMPARISON")
    print("="*80)
    
    summary_df = pd.DataFrame([
        {
            'Strategy': name,
            'Final_Capital': r['final_capital'],
            'Total_Return_%': r['total_return'],
            'Win_Rate_%': r['win_rate'],
            'Num_Positions': r['num_positions']
        }
        for name, r in results
    ])
    
    print("\n" + summary_df.to_string(index=False))
    
    return summary_df


def main():
    """Run all analyses"""
    
    # Check if events file exists
    events_file = Path('high_cap_cluster_events.csv')
    if not events_file.exists():
        print(f"❌ File not found: {events_file}")
        print("Run high_marketcap_cluster_strategy.py first to generate events")
        return
    
    # Analyze events
    events_with_returns = analyze_events(events_file)
    
    # Run portfolio simulations
    simulate_portfolio(events_file, initial_capital=100000)
    
    # Compare strategies
    summary = compare_strategies(events_file)
    
    print("\n" + "="*80)
    print("✅ ANALYSIS COMPLETE")
    print("="*80)


if __name__ == '__main__':
    main()
