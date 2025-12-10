"""
COMBINED STRATEGY: Dropout Signals + Cluster Strengthening

Merges two signals:
1. Quality Stock Dropout: High-quality stock leaves its cluster (potential SHORT)
2. Cluster Strengthening: Large-cap stock joins cluster (potential LONG on other members)

Tests if combining signals improves performance
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import timedelta


def get_block_dates_mapping():
    """Create mapping from Block number to dates"""
    data = pd.read_csv('data.csv')
    data['Date'] = pd.to_datetime(data['Date'])
    unique_dates = sorted(data['Date'].unique())
    
    block_size = 150
    block_map = {}
    
    for block_id in range(10):
        start_idx = block_id * block_size
        end_idx = start_idx + block_size
        
        if start_idx < len(unique_dates):
            block_map[block_id] = unique_dates[start_idx]
    
    return block_map


def load_signals():
    """Load both signal types"""
    
    print("\n" + "="*80)
    print("LOADING SIGNALS")
    print("="*80)
    
    signals_list = []
    
    # Load block dates mapping
    block_dates = get_block_dates_mapping()
    
    # Load cluster strengthening signals (large-cap acquisitions)
    strengthening_file = Path('cluster_strengthening_events.csv')
    if strengthening_file.exists():
        strengthening = pd.read_csv(strengthening_file)
        strengthening['Date'] = pd.to_datetime(strengthening['Date'])
        strengthening['Signal_Type'] = 'CLUSTER_STRENGTHEN'
        strengthening['Trade_Type'] = 'BUY'  # Buy other cluster members
        strengthening = strengthening.rename(columns={'Cluster_Future_Return': 'Future_Return'})
        
        strengthening_with_ret = strengthening[strengthening['Future_Return'].notna()]
        print(f"\n  Cluster Strengthening (LONG) signals: {len(strengthening_with_ret)} events")
        print(f"    Avg return: {strengthening_with_ret['Future_Return'].mean():+.2f}%")
        print(f"    Win rate: {(strengthening_with_ret['Future_Return'] > 0).mean()*100:.1f}%")
        
        signals_list.append(strengthening)
    else:
        print(f"  {strengthening_file} not found")
    
    # Load quality stock dropout and acquisition signals from sliding window events
    events_file = Path('events_sliding_window.csv')
    if events_file.exists():
        events = pd.read_csv(events_file)
        
        # Add dates from block mapping
        events['Date'] = events['Block'].map(block_dates)
        events = events.dropna(subset=['Date'])
        events['Date'] = pd.to_datetime(events['Date'])
        
        # DROP events = quality dropout (SHORT signal)
        drop_events = events[events['Event_Type'] == 'DROP'].copy()
        drop_events = drop_events[drop_events['Future_Return'].notna()]
        drop_events['Signal_Type'] = 'QUALITY_DROPOUT'
        drop_events['Trade_Type'] = 'SELL'  # Short signal
        drop_events = drop_events.rename(columns={'Future_Return': 'Future_Return'})
        
        print(f"\n  Quality Dropout (SHORT) signals: {len(drop_events)} events")
        print(f"    Avg return: {drop_events['Future_Return'].mean():+.2f}%")
        print(f"    Win rate: {(drop_events['Future_Return'] > 0).mean()*100:.1f}%")
        
        signals_list.append(drop_events)
        
        # ACQ events = quality acquisition (could be LONG signal, or ignored)
        acq_events = events[events['Event_Type'] == 'ACQ'].copy()
        acq_events = acq_events[acq_events['Future_Return'].notna()]
        acq_events['Signal_Type'] = 'QUALITY_ACQUISITION'
        acq_events['Trade_Type'] = 'BUY'  # Long signal
        acq_events = acq_events.rename(columns={'Future_Return': 'Future_Return'})
        
        print(f"\n  Quality Acquisition (LONG) signals: {len(acq_events)} events")
        print(f"    Avg return: {acq_events['Future_Return'].mean():+.2f}%")
        print(f"    Win rate: {(acq_events['Future_Return'] > 0).mean()*100:.1f}%")
        
        signals_list.append(acq_events)
    else:
        print(f"  {events_file} not found")
    
    if len(signals_list) == 0:
        return None
    
    combined = pd.concat(signals_list, ignore_index=True)
    return combined


def combine_strategies():
    """Combine signals and analyze"""
    
    print("\n" + "="*80)
    print("COMBINED STRATEGY ANALYSIS")
    print("="*80)
    
    # Load signals
    strengthening = load_signals()
    
    if strengthening is None:
        return None
    
    # For now, we only have the cluster strengthening signals
    # The dropout signals would come from the original strategy
    # Let's analyze what we have
    
    combined = strengthening.copy()
    
    print(f"\n📊 COMBINED SIGNAL STATISTICS")
    print(f"  Total signals: {len(combined)}")
    
    # Split by signal type
    for signal_type in combined['Signal_Type'].unique():
        subset = combined[combined['Signal_Type'] == signal_type]
        subset_with_ret = subset[subset['Future_Return'].notna()]
        
        print(f"\n  {signal_type}:")
        print(f"    Count: {len(subset_with_ret)}")
        print(f"    Avg return: {subset_with_ret['Future_Return'].mean():+.2f}%")
        print(f"    Win rate: {(subset_with_ret['Future_Return'] > 0).mean()*100:.1f}%")
    
    # Split by trade type
    print(f"\n  By Trade Type:")
    for trade_type in combined['Trade_Type'].unique():
        subset = combined[combined['Trade_Type'] == trade_type]
        subset_with_ret = subset[subset['Future_Return'].notna()]
        
        if len(subset_with_ret) == 0:
            continue
        
        print(f"    {trade_type}:")
        print(f"      Count: {len(subset_with_ret)}")
        print(f"      Avg return: {subset_with_ret['Future_Return'].mean():+.2f}%")
        print(f"      Win rate: {(subset_with_ret['Future_Return'] > 0).mean()*100:.1f}%")
    
    return combined


def simulate_combined_portfolio(combined_df, initial_capital=100000):
    """Simulate trading combined signals"""
    
    print("\n" + "="*80)
    print("COMBINED PORTFOLIO SIMULATION")
    print("="*80)
    
    combined_with_ret = combined_df[combined_df['Future_Return'].notna()].copy()
    
    if len(combined_with_ret) == 0:
        print("No signals with returns")
        return None
    
    print(f"\nTrading {len(combined_with_ret)} signals:")
    
    # Equal weight positions
    position_size = initial_capital / len(combined_with_ret)
    
    # For BUY signals: long return
    # For SELL signals: short return (negate)
    returns_pct = []
    for idx, row in combined_with_ret.iterrows():
        ret = row['Future_Return'] / 100
        if row['Trade_Type'] == 'SELL':
            ret = -ret  # Short = inverse return
        returns_pct.append(ret)
    
    returns_pct = np.array(returns_pct)
    
    position_gains = returns_pct * position_size
    total_gains = position_gains.sum()
    final_capital = initial_capital + total_gains
    total_return_pct = (total_gains / initial_capital) * 100
    
    winning = (returns_pct > 0).sum()
    losing = (returns_pct < 0).sum()
    
    print(f"\nPortfolio Configuration:")
    print(f"  Initial capital: ${initial_capital:,.0f}")
    print(f"  Position size: ${position_size:,.0f} each")
    
    print(f"\n💰 RESULTS")
    print(f"  Total gains/losses: ${total_gains:,.0f}")
    print(f"  Final capital: ${final_capital:,.0f}")
    print(f"  Total return: {total_return_pct:+.2f}%")
    print(f"  Winning signals: {winning}/{len(combined_with_ret)}")
    print(f"  Losing signals: {losing}/{len(combined_with_ret)}")
    print(f"  Win rate: {(winning/len(combined_with_ret))*100:.1f}%")
    
    if losing > 0 and winning > 0:
        avg_winner = returns_pct[returns_pct > 0].mean() * 100
        avg_loser = returns_pct[returns_pct < 0].mean() * 100
        profit_factor = abs(winning * avg_winner / (losing * avg_loser)) if avg_loser != 0 else np.inf
        
        print(f"\n📊 RISK METRICS")
        print(f"  Avg winner: {avg_winner:+.2f}%")
        print(f"  Avg loser: {avg_loser:+.2f}%")
        print(f"  Profit factor: {profit_factor:.2f}" if profit_factor != np.inf else "  Profit factor: ∞")
        print(f"  Sharpe ratio: {returns_pct.mean() / (returns_pct.std() + 1e-6):.3f}")
    
    return {
        'initial_capital': initial_capital,
        'final_capital': final_capital,
        'total_return': total_return_pct,
        'winning_signals': winning,
        'losing_signals': losing,
        'win_rate': (winning/len(combined_with_ret))*100,
        'num_signals': len(combined_with_ret)
    }


def analyze_signal_combinations():
    """Look for opportunities where signals align"""
    
    print("\n" + "="*80)
    print("SIGNAL INTERACTION ANALYSIS")
    print("="*80)
    
    strengthening = load_signals()
    
    if strengthening is None:
        return
    
    strengthening_with_ret = strengthening[strengthening['Future_Return'].notna()].copy()
    
    print(f"\n📋 CLUSTERING SIGNALS")
    print(f"  Total events: {len(strengthening_with_ret)}")
    
    # Analyze by stock
    print(f"\n💼 BY STOCK")
    for stock in strengthening_with_ret['Security'].unique():
        stock_data = strengthening_with_ret[strengthening_with_ret['Security'] == stock]
        print(f"\n  {stock}:")
        print(f"    Events: {len(stock_data)}")
        print(f"    Avg return: {stock_data['Future_Return'].mean():+.2f}%")
        print(f"    Win rate: {(stock_data['Future_Return'] > 0).mean()*100:.1f}%")
    
    # Analyze temporal patterns
    print(f"\n📅 TEMPORAL PATTERNS")
    strengthening_with_ret['Year'] = strengthening_with_ret['Date'].dt.year
    
    for year in sorted(strengthening_with_ret['Year'].unique()):
        year_data = strengthening_with_ret[strengthening_with_ret['Year'] == year]
        if len(year_data) == 0:
            continue
        print(f"  {year}: {len(year_data)} events, avg return {year_data['Future_Return'].mean():+.2f}%")
    
    return strengthening_with_ret


def main():
    """Run combined strategy analysis"""
    
    print("="*80)
    print("COMBINED TRADING STRATEGY")
    print("Signal 1: Quality Stock Dropout (SHORT signal)")
    print("Signal 2: Large-Cap Cluster Strengthening (LONG signal)")
    print("="*80)
    
    # Combine strategies
    combined = combine_strategies()
    
    if combined is None:
        print("Cannot load required signals")
        return
    
    # Simulate combined portfolio
    portfolio = simulate_combined_portfolio(combined, initial_capital=100000)
    
    # Analyze interactions
    analyze_signal_combinations()
    
    print("\n" + "="*80)
    print("✅ COMBINED STRATEGY ANALYSIS COMPLETE")
    print("="*80)
    
    return combined, portfolio


if __name__ == '__main__':
    combined, portfolio = main()
