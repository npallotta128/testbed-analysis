"""
Monte Carlo simulation to analyze variance in backtest outcomes.
Resamples signals with replacement and runs multiple simulations to understand
the distribution of returns, win rates, and other metrics.
"""

import pandas as pd
import numpy as np
from pathlib import Path
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import timedelta
import pickle

# Configuration
N_SIMULATIONS = 1000  # number of Monte Carlo runs
CAPITAL_TIER = 100_000  # focus on base capital tier
PER_TRADE_BASE = 100_000
MAX_CONCURRENT_TRADES = 20
HOLD_DAYS = 250
RANDOM_SEED = 42

INPUT_JUMPS_FILE = 'cluster_jumps_full_250d_winsorized.csv'

np.random.seed(RANDOM_SEED)


def load_data():
    """Load and prepare jump signals"""
    jumps = pd.read_csv(INPUT_JUMPS_FILE)
    if 'Date' in jumps.columns:
        jumps['Date'] = pd.to_datetime(jumps['Date'])
    return jumps


def build_trading_calendar(jumps_df):
    """Return sorted unique trading dates and index map"""
    if 'Date' not in jumps_df.columns:
        return None, None
    dates = sorted(pd.to_datetime(jumps_df['Date'].dropna().unique()))
    date_to_idx = {d: i for i, d in enumerate(dates)}
    return dates, date_to_idx


def add_trading_days(start_date, n_days, trading_dates, date_to_idx):
    """Advance by n trading days using provided calendar"""
    idx = date_to_idx.get(start_date, None)
    if idx is None:
        idx = next((i for i, d in enumerate(trading_dates) if d >= start_date), None)
        if idx is None:
            return start_date
    target_idx = min(idx + n_days, len(trading_dates) - 1)
    return trading_dates[target_idx]


def classify_signal(row):
    """Classify signal as BLUE_CHIP or SMALL_CAP_STORY"""
    delta = row.get('Quality_Delta', 0)
    continuity = row.get('Cluster_Continuity', 0)
    if pd.isna(delta):
        delta = 0
    if pd.isna(continuity):
        continuity = 0
    is_blue_chip = (delta > 0) and (continuity >= 0.6)
    return 'BLUE_CHIP' if is_blue_chip else 'SMALL_CAP_STORY'


def position_size(capital, signal_type, symbol_cap=None):
    """Calculate position size"""
    if signal_type == 'BLUE_CHIP':
        base = PER_TRADE_BASE
    else:
        base = PER_TRADE_BASE * 0.2
    
    cap_limited = min(base, capital * 0.05)
    
    if symbol_cap and symbol_cap > 0:
        liquidity_cap = symbol_cap * 0.005
        return min(cap_limited, liquidity_cap)
    return cap_limited


def simulate_single_backtest(capital, sampled_signals, trading_dates, date_to_idx):
    """Run a single backtest with resampled signals"""
    df = sampled_signals.copy()
    df['SignalType'] = df.apply(classify_signal, axis=1)
    
    # Sort by signal type priority then date
    df['Priority'] = (df['SignalType'] == 'BLUE_CHIP').astype(int)
    df = df.sort_values(['Priority', 'Date'], ascending=[False, True])
    
    cash = capital
    trades = []
    active_positions = []
    
    for _, row in df.iterrows():
        symbol = row['Symbol']
        signal_type = row['SignalType']
        trade_date = row['Date']
        
        # Get return (prefer winsorized)
        return_col = 'return_250d_winsorized' if 'return_250d_winsorized' in row.index else 'return_250d'
        ret = row.get(return_col, 0)
        if pd.isna(ret):
            ret = 0
        
        # Position size
        size = position_size(capital, signal_type, None)
        if size <= 0 or size > cash * 0.5:  # Don't spend > 50% cash on single trade
            continue
        
        # Calculate exit date (250 trading days forward)
        exit_date = add_trading_days(trade_date, HOLD_DAYS, trading_dates, date_to_idx)
        
        # Check max concurrent positions
        current_active = [p for p in active_positions if p['exit_date'] >= trade_date]
        if len(current_active) >= MAX_CONCURRENT_TRADES:
            # Force close oldest (real-world constraint)
            oldest = min(current_active, key=lambda x: x['entry_date'])
            active_positions.remove(oldest)
            cash += oldest['pnl']
        
        # Open position
        pnl = size * (ret / 100.0)  # returns are in percent
        active_positions.append({
            'symbol': symbol,
            'entry_date': trade_date,
            'exit_date': exit_date,
            'size': size,
            'return_pct': ret,
            'pnl': pnl
        })
        cash -= size
        
        trades.append({
            'symbol': symbol,
            'entry_date': trade_date,
            'exit_date': exit_date,
            'size': size,
            'return_pct': ret,
            'pnl': pnl,
            'signal_type': signal_type
        })
    
    # Close all remaining positions at exit date
    for pos in active_positions:
        trades.append({
            'symbol': pos['symbol'],
            'entry_date': pos['entry_date'],
            'exit_date': pos['exit_date'],
            'size': pos['size'],
            'return_pct': pos['return_pct'],
            'pnl': pos['pnl'],
            'signal_type': 'ACTIVE'
        })
        cash += pos['pnl']
    
    # Calculate metrics
    trades_df = pd.DataFrame(trades)
    
    if len(trades_df) == 0:
        return {
            'n_trades': 0,
            'total_pnl': 0,
            'total_return_pct': 0,
            'win_rate': 0,
            'avg_return_pct': 0,
            'median_return_pct': 0,
            'std_return_pct': 0,
            'final_capital': capital
        }
    
    winning_trades = (trades_df['return_pct'] > 0).sum()
    n_trades = len(trades_df)
    win_rate = winning_trades / n_trades if n_trades > 0 else 0
    total_pnl = trades_df['pnl'].sum()
    total_return_pct = (total_pnl / capital) * 100 if capital > 0 else 0
    
    return {
        'n_trades': n_trades,
        'total_pnl': total_pnl,
        'total_return_pct': total_return_pct,
        'win_rate': win_rate,
        'avg_return_pct': trades_df['return_pct'].mean(),
        'median_return_pct': trades_df['return_pct'].median(),
        'std_return_pct': trades_df['return_pct'].std(),
        'min_return_pct': trades_df['return_pct'].min(),
        'max_return_pct': trades_df['return_pct'].max(),
        'final_capital': capital + total_pnl
    }


def run_monte_carlo(jumps_df, n_simulations=1000):
    """Run Monte Carlo simulation"""
    print(f"Running {n_simulations} Monte Carlo simulations...")
    print(f"Total signals available: {len(jumps_df)}")
    print(f"Starting capital: ${CAPITAL_TIER:,.0f}")
    
    # Build trading calendar once
    trading_dates, date_to_idx = build_trading_calendar(jumps_df)
    print(f"Trading dates: {len(trading_dates)} ({trading_dates[0]} to {trading_dates[-1]})")
    
    results = []
    
    for sim_num in range(n_simulations):
        # Resample signals with replacement
        sampled_idx = np.random.choice(len(jumps_df), size=len(jumps_df), replace=True)
        sampled_signals = jumps_df.iloc[sampled_idx].reset_index(drop=True)
        
        # Run backtest on resampled signals
        metrics = simulate_single_backtest(CAPITAL_TIER, sampled_signals, trading_dates, date_to_idx)
        results.append(metrics)
        
        if (sim_num + 1) % 100 == 0:
            print(f"  Completed {sim_num + 1}/{n_simulations} simulations")
    
    return pd.DataFrame(results)


def analyze_results(results_df):
    """Analyze and display Monte Carlo results"""
    print("\n" + "="*70)
    print("MONTE CARLO SIMULATION RESULTS")
    print("="*70)
    
    print(f"\nNumber of simulations: {len(results_df)}")
    print(f"Sample size per simulation: {results_df['n_trades'].iloc[0]:.0f} trades (varies due to resampling)")
    
    print("\n--- FINAL CAPITAL (Starting: ${:,.0f}) ---".format(CAPITAL_TIER))
    print(f"  Mean:     ${results_df['final_capital'].mean():,.0f}")
    print(f"  Median:   ${results_df['final_capital'].median():,.0f}")
    print(f"  Std Dev:  ${results_df['final_capital'].std():,.0f}")
    print(f"  Min:      ${results_df['final_capital'].min():,.0f}")
    print(f"  Max:      ${results_df['final_capital'].max():,.0f}")
    print(f"  5th pct:  ${results_df['final_capital'].quantile(0.05):,.0f}")
    print(f"  95th pct: ${results_df['final_capital'].quantile(0.95):,.0f}")
    
    print("\n--- TOTAL RETURN % ---")
    print(f"  Mean:     {results_df['total_return_pct'].mean():.2f}%")
    print(f"  Median:   {results_df['total_return_pct'].median():.2f}%")
    print(f"  Std Dev:  {results_df['total_return_pct'].std():.2f}%")
    print(f"  Min:      {results_df['total_return_pct'].min():.2f}%")
    print(f"  Max:      {results_df['total_return_pct'].max():.2f}%")
    print(f"  5th pct:  {results_df['total_return_pct'].quantile(0.05):.2f}%")
    print(f"  95th pct: {results_df['total_return_pct'].quantile(0.95):.2f}%")
    
    print("\n--- WIN RATE ---")
    print(f"  Mean:     {results_df['win_rate'].mean()*100:.1f}%")
    print(f"  Median:   {results_df['win_rate'].median()*100:.1f}%")
    print(f"  Std Dev:  {results_df['win_rate'].std()*100:.1f}%")
    print(f"  Min:      {results_df['win_rate'].min()*100:.1f}%")
    print(f"  Max:      {results_df['win_rate'].max()*100:.1f}%")
    print(f"  5th pct:  {results_df['win_rate'].quantile(0.05)*100:.1f}%")
    print(f"  95th pct: {results_df['win_rate'].quantile(0.95)*100:.1f}%")
    
    print("\n--- AVG RETURN PER TRADE % ---")
    print(f"  Mean:     {results_df['avg_return_pct'].mean():.2f}%")
    print(f"  Median:   {results_df['avg_return_pct'].median():.2f}%")
    print(f"  Std Dev:  {results_df['avg_return_pct'].std():.2f}%")
    
    print("\n--- TRADES PER SIMULATION ---")
    print(f"  Mean:     {results_df['n_trades'].mean():.0f}")
    print(f"  Median:   {results_df['n_trades'].median():.0f}")
    print(f"  Std Dev:  {results_df['n_trades'].std():.0f}")
    
    print("\n" + "="*70)
    
    return results_df


def create_visualizations(results_df):
    """Create visualization of Monte Carlo results"""
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f'Monte Carlo Simulation Results ({len(results_df)} runs)', fontsize=16, fontweight='bold')
    
    # Final capital distribution
    ax = axes[0, 0]
    ax.hist(results_df['final_capital']/1000, bins=50, color='steelblue', alpha=0.7, edgecolor='black')
    ax.axvline(results_df['final_capital'].mean()/1000, color='red', linestyle='--', linewidth=2, label=f"Mean: ${results_df['final_capital'].mean()/1000:.0f}k")
    ax.axvline(results_df['final_capital'].median()/1000, color='orange', linestyle='--', linewidth=2, label=f"Median: ${results_df['final_capital'].median()/1000:.0f}k")
    ax.set_xlabel('Final Capital ($k)', fontsize=11)
    ax.set_ylabel('Frequency', fontsize=11)
    ax.set_title('Distribution of Final Capital', fontsize=12, fontweight='bold')
    ax.legend()
    ax.grid(alpha=0.3)
    
    # Total return distribution
    ax = axes[0, 1]
    ax.hist(results_df['total_return_pct'], bins=50, color='seagreen', alpha=0.7, edgecolor='black')
    ax.axvline(results_df['total_return_pct'].mean(), color='red', linestyle='--', linewidth=2, label=f"Mean: {results_df['total_return_pct'].mean():.1f}%")
    ax.axvline(results_df['total_return_pct'].median(), color='orange', linestyle='--', linewidth=2, label=f"Median: {results_df['total_return_pct'].median():.1f}%")
    ax.set_xlabel('Total Return (%)', fontsize=11)
    ax.set_ylabel('Frequency', fontsize=11)
    ax.set_title('Distribution of Total Return %', fontsize=12, fontweight='bold')
    ax.legend()
    ax.grid(alpha=0.3)
    
    # Win rate distribution
    ax = axes[1, 0]
    ax.hist(results_df['win_rate']*100, bins=50, color='coral', alpha=0.7, edgecolor='black')
    ax.axvline(results_df['win_rate'].mean()*100, color='red', linestyle='--', linewidth=2, label=f"Mean: {results_df['win_rate'].mean()*100:.1f}%")
    ax.axvline(results_df['win_rate'].median()*100, color='orange', linestyle='--', linewidth=2, label=f"Median: {results_df['win_rate'].median()*100:.1f}%")
    ax.set_xlabel('Win Rate (%)', fontsize=11)
    ax.set_ylabel('Frequency', fontsize=11)
    ax.set_title('Distribution of Win Rate', fontsize=12, fontweight='bold')
    ax.legend()
    ax.grid(alpha=0.3)
    
    # Scatter: Win Rate vs Total Return
    ax = axes[1, 1]
    scatter = ax.scatter(results_df['win_rate']*100, results_df['total_return_pct'], 
                        c=results_df['final_capital']/1000, cmap='viridis', alpha=0.6, s=50)
    ax.set_xlabel('Win Rate (%)', fontsize=11)
    ax.set_ylabel('Total Return (%)', fontsize=11)
    ax.set_title('Win Rate vs Total Return (color=Final Capital $k)', fontsize=12, fontweight='bold')
    cbar = plt.colorbar(scatter, ax=ax)
    cbar.set_label('Final Capital ($k)', fontsize=10)
    ax.grid(alpha=0.3)
    
    plt.tight_layout()
    output_file = 'monte_carlo_distributions.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"\nVisualization saved: {output_file}")
    plt.close()


def create_percentile_analysis(results_df):
    """Create percentile breakdown visualization"""
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # Create percentile data
    percentiles = np.arange(0, 101, 5)
    final_caps = [results_df['final_capital'].quantile(p/100) for p in percentiles]
    
    ax.fill_between(percentiles, 
                    np.array(final_caps)/1000, 
                    alpha=0.3, color='steelblue', label='Distribution')
    ax.plot(percentiles, np.array(final_caps)/1000, 'o-', linewidth=2, markersize=6, color='steelblue')
    
    # Add starting capital line
    ax.axhline(CAPITAL_TIER/1000, color='red', linestyle='--', linewidth=2, label=f'Starting Capital: ${CAPITAL_TIER/1000:.0f}k')
    
    # Add mean and median
    ax.axhline(results_df['final_capital'].mean()/1000, color='orange', linestyle='--', linewidth=2, alpha=0.7, label=f"Mean: ${results_df['final_capital'].mean()/1000:.0f}k")
    ax.axhline(results_df['final_capital'].median()/1000, color='green', linestyle='--', linewidth=2, alpha=0.7, label=f"Median: ${results_df['final_capital'].median()/1000:.0f}k")
    
    ax.set_xlabel('Percentile', fontsize=12)
    ax.set_ylabel('Final Capital ($k)', fontsize=12)
    ax.set_title('Percentile Distribution of Final Capital', fontsize=14, fontweight='bold')
    ax.legend(fontsize=11)
    ax.grid(alpha=0.3)
    
    plt.tight_layout()
    output_file = 'monte_carlo_percentiles.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"Percentile chart saved: {output_file}")
    plt.close()


if __name__ == '__main__':
    # Load data
    jumps_df = load_data()
    print(f"Loaded {len(jumps_df)} total signals")
    
    # Run Monte Carlo
    results_df = run_monte_carlo(jumps_df, n_simulations=N_SIMULATIONS)
    
    # Analyze and display results
    results_df = analyze_results(results_df)
    
    # Save results to CSV
    results_df.to_csv('monte_carlo_results.csv', index=False)
    print(f"\nResults saved to: monte_carlo_results.csv")
    
    # Create visualizations
    create_visualizations(results_df)
    create_percentile_analysis(results_df)
    
    print("\nMonte Carlo simulation complete!")
