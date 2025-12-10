"""
Backtesting Framework: MarketCap Sliding Window Events

Demonstrates how to use the detected dropout/acquisition events for backtesting
and strategy validation with market cap metrics.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from collections import defaultdict

def run_event_based_backtest(events_file='marketcap_pipeline_results/marketcap_sliding_events.csv'):
    """
    Simple backtest framework using detected events
    """
    
    results_dir = Path('marketcap_pipeline_results')
    if not results_dir.exists():
        print("❌ Pipeline results not found. Run pipeline first.")
        return
    
    print("\n" + "="*80)
    print("MARKETCAP EVENT-BASED BACKTESTING FRAMEWORK")
    print("="*80)
    
    # Load events
    events = pd.read_csv(events_file)
    events['Future_Return'] = pd.to_numeric(events['Future_Return'], errors='coerce')
    
    print("\n1️⃣  BASIC STRATEGY: ALL DETECTED EVENTS")
    print("-" * 80)
    
    all_events = events[events['Future_Return'].notna()].copy()
    strategy_return = all_events['Future_Return'].mean()
    strategy_win_rate = (all_events['Future_Return'] > 0).mean()
    strategy_sharpe = all_events['Future_Return'].mean() / (all_events['Future_Return'].std() + 1e-6)
    
    print(f"  Events analyzed: {len(all_events):,}")
    print(f"  Average return: {strategy_return:+.2f}%")
    print(f"  Win rate: {strategy_win_rate*100:.1f}%")
    print(f"  Sharpe ratio (rough): {strategy_sharpe:.3f}")
    print(f"  Std dev: {all_events['Future_Return'].std():.2f}%")
    
    # Simulate $100k portfolio
    print(f"\n  💰 Portfolio Simulation ($100,000 initial):")
    n_positions = len(all_events)
    position_size = 100_000 / n_positions
    total_gain = (all_events['Future_Return'].sum() / 100) * position_size
    final_portfolio = 100_000 + total_gain
    print(f"    Position size: ${position_size:,.0f}")
    print(f"    Total gain: ${total_gain:,.0f}")
    print(f"    Final portfolio: ${final_portfolio:,.0f}")
    print(f"    Return: {(final_portfolio/100_000 - 1)*100:.1f}%")
    
    print("\n2️⃣  STRATIFIED STRATEGY: BY EVENT TYPE")
    print("-" * 80)
    
    for event_type in ['DROP', 'ACQ']:
        subset = events[events['Event_Type'] == event_type].copy()
        subset = subset[subset['Future_Return'].notna()]
        
        if len(subset) > 0:
            avg_ret = subset['Future_Return'].mean()
            win_rate = (subset['Future_Return'] > 0).mean()
            print(f"\n  {event_type} Events (n={len(subset)}):")
            print(f"    Avg return: {avg_ret:+.2f}%")
            print(f"    Win rate: {win_rate*100:.1f}%")
            print(f"    Std dev: {subset['Future_Return'].std():.2f}%")
    
    print("\n3️⃣  QUALITY-LOSS FILTERED STRATEGY")
    print("-" * 80)
    
    # Only use dropout events with quality loss (more reliable)
    dropout = events[events['Event_Type'] == 'DROP'].copy()
    dropout = dropout[dropout['Quality_Loss'].notna()]
    dropout = dropout[dropout['Future_Return'].notna()]
    
    if len(dropout) > 0:
        # Top quality loss events (most dramatic)
        top_loss = dropout.nlargest(int(len(dropout) * 0.25), 'Quality_Loss')
        avg_ret = top_loss['Future_Return'].mean()
        win_rate = (top_loss['Future_Return'] > 0).mean()
        
        print(f"\n  Top 25% by Quality Loss (n={len(top_loss)}):")
        print(f"    Avg return: {avg_ret:+.2f}%")
        print(f"    Win rate: {win_rate*100:.1f}%")
        
        # Compare to bottom quality loss
        bottom_loss = dropout.nsmallest(int(len(dropout) * 0.25), 'Quality_Loss')
        avg_ret_b = bottom_loss['Future_Return'].mean()
        win_rate_b = (bottom_loss['Future_Return'] > 0).mean()
        
        print(f"\n  Bottom 25% by Quality Loss (n={len(bottom_loss)}):")
        print(f"    Avg return: {avg_ret_b:+.2f}%")
        print(f"    Win rate: {win_rate_b*100:.1f}%")
    
    print("\n4️⃣  RETURN-BASED PERCENTILE STRATEGY")
    print("-" * 80)
    
    percentiles = [10, 25, 50, 75, 90]
    for pct in percentiles:
        threshold = events['Future_Return'].quantile(pct/100)
        above_threshold = events[events['Future_Return'] >= threshold]
        
        if len(above_threshold) > 0:
            avg_ret = above_threshold['Future_Return'].mean()
            print(f"  Top {100-pct}% performers (return >= {threshold:+.1f}%): {len(above_threshold):4d} events, avg: {avg_ret:+7.2f}%")
    
    print("\n5️⃣  CORRELATION ANALYSIS")
    print("-" * 80)
    
    # Check if quality loss predicts returns
    dropout_with_both = dropout[['Quality_Loss', 'Future_Return']].copy()
    if len(dropout_with_both) > 2:
        corr = dropout_with_both.corr().iloc[0, 1]
        print(f"\n  Quality_Loss vs Future_Return correlation: {corr:.3f}")
        if abs(corr) > 0.1:
            print(f"    → Meaningful signal: higher quality loss {'predicts higher' if corr > 0 else 'predicts lower'} returns")
        else:
            print(f"    → Weak signal: quality loss and returns weakly correlated")
    
    print("\n6️⃣  RISK ANALYSIS")
    print("-" * 80)
    
    all_returns = events['Future_Return'].dropna()
    positive = all_returns[all_returns > 0]
    negative = all_returns[all_returns < 0]
    
    print(f"\n  Positive outcomes (n={len(positive)}):")
    print(f"    Avg gain: {positive.mean():+.2f}%")
    print(f"    Max gain: {positive.max():+.2f}%")
    print(f"    Min gain: {positive.min():+.2f}%")
    
    print(f"\n  Negative outcomes (n={len(negative)}):")
    print(f"    Avg loss: {negative.mean():+.2f}%")
    print(f"    Max loss: {negative.min():+.2f}%")
    print(f"    Min loss: {negative.max():+.2f}%")
    
    # Profit factor
    if len(positive) > 0 and len(negative) > 0:
        gross_profit = positive.sum()
        gross_loss = abs(negative.sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else np.inf
        print(f"\n  Profit Factor: {profit_factor:.2f}")
        print(f"    (Gross profit / Gross loss ratio)")
    
    print("\n7️⃣  MONTE CARLO SIMULATION")
    print("-" * 80)
    
    print(f"\n  Simulating random portfolio selections...")
    n_sims = 1000
    n_positions_sim = min(50, len(all_returns) // 2)
    
    sim_returns = []
    for _ in range(n_sims):
        sample = np.random.choice(all_returns.values, size=n_positions_sim, replace=False)
        sim_returns.append(sample.mean())
    
    sim_returns = np.array(sim_returns)
    print(f"  Simulations: {n_sims}")
    print(f"  Positions per portfolio: {n_positions_sim}")
    print(f"  Expected return (mean): {sim_returns.mean():+.2f}%")
    print(f"  Expected return (median): {np.median(sim_returns):+.2f}%")
    print(f"  Return distribution:")
    print(f"    5th percentile: {np.percentile(sim_returns, 5):+.2f}%")
    print(f"    25th percentile: {np.percentile(sim_returns, 25):+.2f}%")
    print(f"    75th percentile: {np.percentile(sim_returns, 75):+.2f}%")
    print(f"    95th percentile: {np.percentile(sim_returns, 95):+.2f}%")
    print(f"  Probability of positive return: {(sim_returns > 0).mean()*100:.1f}%")
    
    print("\n8️⃣  SECURITY-LEVEL STATISTICS")
    print("-" * 80)
    
    security_stats = []
    for symbol in events['Security'].unique():
        symbol_events = events[events['Security'] == symbol]
        symbol_returns = symbol_events['Future_Return'].dropna()
        
        if len(symbol_returns) > 2:
            security_stats.append({
                'Symbol': symbol,
                'Event_Count': len(symbol_events),
                'Avg_Return': symbol_returns.mean(),
                'Win_Rate': (symbol_returns > 0).mean(),
                'Std_Dev': symbol_returns.std()
            })
    
    stats_df = pd.DataFrame(security_stats).sort_values('Event_Count', ascending=False)
    
    print(f"\n  Top 5 most active securities:")
    for idx, row in stats_df.head(5).iterrows():
        print(f"    {row['Symbol']:8s} - Events: {int(row['Event_Count']):3d}  Avg Ret: {row['Avg_Return']:+7.2f}%  Win Rate: {row['Win_Rate']*100:5.1f}%")
    
    print(f"\n  Best performers (by avg return, min 10 events):")
    best = stats_df[stats_df['Event_Count'] >= 10].nlargest(5, 'Avg_Return')
    for idx, row in best.iterrows():
        print(f"    {row['Symbol']:8s} - Events: {int(row['Event_Count']):3d}  Avg Ret: {row['Avg_Return']:+7.2f}%  Win Rate: {row['Win_Rate']*100:5.1f}%")
    
    print("\n" + "="*80)
    print("✅ BACKTEST ANALYSIS COMPLETE")
    print("="*80)
    
    return {
        'all_events': all_events,
        'strategy_return': strategy_return,
        'strategy_win_rate': strategy_win_rate,
        'simulation_results': sim_returns
    }

if __name__ == '__main__':
    run_event_based_backtest()
