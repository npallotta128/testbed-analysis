"""
Cluster Strengthening Strategy - Backtesting Framework

Strategy: When large-cap stocks join clusters → trade that cluster
Signal interpretation: Strengthened clusters = BUY signal on ALL cluster members
"""

import pandas as pd
import numpy as np
from pathlib import Path


def analyze_cluster_strengthening(events_file='cluster_strengthening_events.csv'):
    """Analyze cluster strengthening signals"""
    
    print("\n" + "="*80)
    print("CLUSTER STRENGTHENING STRATEGY - BACKTEST ANALYSIS")
    print("="*80)
    
    events = pd.read_csv(events_file)
    events['Date'] = pd.to_datetime(events['Date'])
    events_with_returns = events[events['Cluster_Future_Return'].notna()].copy()
    
    if len(events_with_returns) == 0:
        print("No events with return data")
        return
    
    # Overall statistics
    print(f"\n📊 OVERALL PERFORMANCE")
    print(f"  Total signals: {len(events_with_returns)}")
    print(f"  Avg cluster return: {events_with_returns['Cluster_Future_Return'].mean():+.2f}%")
    print(f"  Median: {events_with_returns['Cluster_Future_Return'].median():+.2f}%")
    print(f"  Std dev: {events_with_returns['Cluster_Future_Return'].std():.2f}%")
    print(f"  Min return: {events_with_returns['Cluster_Future_Return'].min():+.2f}%")
    print(f"  Max return: {events_with_returns['Cluster_Future_Return'].max():+.2f}%")
    print(f"  Win rate: {(events_with_returns['Cluster_Future_Return'] > 0).mean()*100:.1f}%")
    print(f"  Sharpe ratio: {events_with_returns['Cluster_Future_Return'].mean() / (events_with_returns['Cluster_Future_Return'].std() + 1e-6):.3f}")
    
    # By security
    print(f"\n💼 BY SECURITY (signal quality)")
    stock_analysis = events_with_returns.groupby('Security').agg({
        'Cluster_Future_Return': ['count', 'mean', 'median', lambda x: (x > 0).mean() * 100],
        'Market_Cap': 'first'
    }).round(2)
    stock_analysis.columns = ['Count', 'Avg_Return', 'Median_Return', 'Win_Rate_%', 'Market_Cap']
    stock_analysis = stock_analysis.sort_values('Avg_Return', ascending=False)
    
    for idx, row in stock_analysis.iterrows():
        cap_str = f"${row['Market_Cap']/1e9:.1f}B" if row['Market_Cap'] > 0 else "N/A"
        print(f"  {idx:10} Signals={int(row['Count']):2}  Mean={row['Avg_Return']:+7.2f}%  "
              f"Median={row['Median_Return']:+7.2f}%  WinRate={row['Win_Rate_%']:5.1f}%  Cap={cap_str}")
    
    # Percentile analysis
    print(f"\n📈 RETURN DISTRIBUTION")
    percentiles = [10, 25, 50, 75, 90]
    for p in percentiles:
        val = np.percentile(events_with_returns['Cluster_Future_Return'], p)
        print(f"  {p}th percentile: {val:+7.2f}%")
    
    return events_with_returns


def simulate_portfolio(events_file='cluster_strengthening_events.csv', 
                       initial_capital=100000,
                       position_size_type='equal'):
    """
    Simulate trading signals from cluster strengthening
    
    Logic: When a large-cap stock joins a cluster,
    allocate capital to trade that cluster (buy cluster members)
    """
    
    print("\n" + "="*80)
    print("PORTFOLIO SIMULATION - CLUSTER STRENGTHENING SIGNALS")
    print("="*80)
    
    events = pd.read_csv(events_file)
    events['Date'] = pd.to_datetime(events['Date'])
    events_with_returns = events[events['Cluster_Future_Return'].notna()].copy()
    
    if len(events_with_returns) == 0:
        print("No valid events")
        return None
    
    print(f"\nSimulating {len(events_with_returns)} cluster signals...")
    
    # Each event is a signal to buy that cluster
    returns_pct = events_with_returns['Cluster_Future_Return'].values / 100
    
    if position_size_type == 'equal':
        # Equal weight each signal
        position_size = initial_capital / len(events_with_returns)
        position_gains = returns_pct * position_size
        
        print(f"Position sizing: EQUAL")
        print(f"  Per signal: ${position_size:,.0f}")
    
    elif position_size_type == 'market_cap_weighted':
        # Weight by market cap of triggering stock
        market_caps = events_with_returns['Market_Cap'].values
        weights = market_caps / market_caps.sum()
        position_gains = returns_pct * weights * initial_capital
        
        print(f"Position sizing: MARKET CAP WEIGHTED")
        print(f"  Weight range: {weights.min()*100:.1f}% - {weights.max()*100:.1f}%")
    
    else:
        raise ValueError(f"Unknown position_size_type: {position_size_type}")
    
    # Portfolio metrics
    total_gains = position_gains.sum()
    final_capital = initial_capital + total_gains
    total_return_pct = (total_gains / initial_capital) * 100
    
    winning = (returns_pct > 0).sum()
    losing = (returns_pct < 0).sum()
    
    print(f"\n💰 RESULTS")
    print(f"  Initial capital: ${initial_capital:,.0f}")
    print(f"  Total gains/losses: ${total_gains:,.0f}")
    print(f"  Final capital: ${final_capital:,.0f}")
    print(f"  Total return: {total_return_pct:+.2f}%")
    print(f"  Winning signals: {winning}/{len(events_with_returns)}")
    print(f"  Losing signals: {losing}/{len(events_with_returns)}")
    print(f"  Win rate: {(winning/len(events_with_returns))*100:.1f}%")
    
    if losing > 0:
        avg_winner = returns_pct[returns_pct > 0].mean() * 100 if winning > 0 else 0
        avg_loser = returns_pct[returns_pct < 0].mean() * 100
        profit_factor = abs(winning * avg_winner / (losing * avg_loser)) if avg_loser != 0 else np.inf
        
        print(f"\n📊 RISK METRICS")
        print(f"  Avg winner: {avg_winner:+.2f}%")
        print(f"  Avg loser: {avg_loser:+.2f}%")
        print(f"  Profit factor: {profit_factor:.2f}" if profit_factor != np.inf else "  Profit factor: ∞")
    
    return {
        'initial_capital': initial_capital,
        'final_capital': final_capital,
        'total_return': total_return_pct,
        'winning_signals': winning,
        'losing_signals': losing,
        'win_rate': (winning/len(events_with_returns))*100,
        'num_signals': len(events_with_returns)
    }


def compare_with_baseline(events_file='cluster_strengthening_events.csv'):
    """Compare cluster strengthening strategy vs simple baselines"""
    
    print("\n" + "="*80)
    print("STRATEGY COMPARISON")
    print("="*80)
    
    events = pd.read_csv(events_file)
    events_with_returns = events[events['Cluster_Future_Return'].notna()].copy()
    
    results = []
    
    # Strategy 1: Trade all signals
    print("\n1️⃣  CLUSTER STRENGTHENING SIGNALS (All)")
    r1 = simulate_portfolio(events_file, initial_capital=100000)
    results.append(('Cluster Strengthening', r1))
    
    # Strategy 2: Only positive signals (those that worked)
    print("\n2️⃣  CLUSTER STRENGTHENING SIGNALS (Positive Only - Hindsight)")
    positive_events = events_with_returns[events_with_returns['Cluster_Future_Return'] > 0]
    positive_return = positive_events['Cluster_Future_Return'].sum() / len(events_with_returns) * 100000 / 100
    positive_result = {
        'initial_capital': 100000,
        'final_capital': 100000 + positive_return,
        'total_return': (positive_return / 100000) * 100,
        'winning_signals': len(positive_events),
        'losing_signals': 0,
        'win_rate': 100.0,
        'num_signals': len(events_with_returns)
    }
    print(f"  Capital: $100,000 → ${positive_result['final_capital']:,.0f} ({positive_result['total_return']:+.2f}%)")
    results.append(('Positive Only (Hindsight)', positive_result))
    
    # Strategy 3: Random
    np.random.seed(42)
    random_returns = np.random.normal(0.05, 0.4, len(events_with_returns))
    random_gain = (random_returns.sum() / len(events_with_returns)) * 100000
    random_result = {
        'initial_capital': 100000,
        'final_capital': 100000 + random_gain,
        'total_return': (random_gain / 100000) * 100,
        'winning_signals': (random_returns > 0).sum(),
        'losing_signals': (random_returns < 0).sum(),
        'win_rate': (random_returns > 0).mean() * 100,
        'num_signals': len(events_with_returns)
    }
    print(f"  Capital: $100,000 → ${random_result['final_capital']:,.0f} ({random_result['total_return']:+.2f}%)")
    results.append(('Random (Baseline)', random_result))
    
    # Summary table
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    
    summary_df = pd.DataFrame([
        {
            'Strategy': name,
            'Final_Capital': r['final_capital'],
            'Total_Return_%': r['total_return'],
            'Win_Rate_%': r['win_rate'],
        }
        for name, r in results
    ])
    
    print("\n" + summary_df.to_string(index=False))
    
    return summary_df


def main():
    """Run all analyses"""
    
    events_file = Path('cluster_strengthening_events.csv')
    if not events_file.exists():
        print(f"❌ File not found: {events_file}")
        print("Run cluster_strengthening_strategy.py first")
        return
    
    # Analyze events
    events_df = analyze_cluster_strengthening(events_file)
    
    # Portfolio simulation
    simulate_portfolio(events_file, initial_capital=100000)
    
    # Compare strategies
    compare_with_baseline(events_file)
    
    print("\n" + "="*80)
    print("✅ BACKTEST COMPLETE")
    print("="*80)


if __name__ == '__main__':
    main()
