"""
Monte Carlo simulation across multiple capital tiers to analyze scalability.
Uses resampling methodology with realistic capital constraints.
"""

import pandas as pd
import numpy as np
from pathlib import Path
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import timedelta
import os
from cluster_quality_enhanced import calculate_cluster_transitions, calculate_cluster_stability
from cluster_quality_adapter import convert_jumps_to_blocks, apply_quality_adjustment_to_jumps

from simple_exit_monitor import SimplePositionExitMonitor as PositionExitMonitor
# Configuration
N_SIMULATIONS = 1000  # number of Monte Carlo runs per tier
CAPITAL_TIERS = [100_000, 1_000_000, 10_000_000, 100_000_000]
PER_TRADE_BASE = 100_000
MAX_CONCURRENT_TRADES = 20
HOLD_DAYS = 250
RANDOM_SEED = 42

INPUT_JUMPS_FILE = 'cluster_jumps_full_250d_winsorized.csv'
MARKET_CAP_FILE = '/mnt/d/MarketCAPValues.csv'
MARKET_VALUES_FILE = '/mnt/d/MarketValues.csv'

np.random.seed(RANDOM_SEED)


def load_data():
    """Load and prepare jump signals with market cap and volume data"""
    print("Loading jump signals...")
    jumps = pd.read_csv(INPUT_JUMPS_FILE)
    if 'Date' in jumps.columns:
        jumps['Date'] = pd.to_datetime(jumps['Date'])
    
    # Get unique symbols and dates from jumps
    needed_symbols = jumps['Symbol'].unique()
    needed_dates = jumps['Date'].unique()
    
    print(f"Need data for {len(needed_symbols)} symbols across {len(needed_dates)} dates")
    
    # Check if we have cached market data
    cache_file = 'monte_carlo_market_data_cache.parquet'
    if os.path.exists(cache_file):
        print(f"Loading cached market data from {cache_file}...")
        market_data = pd.read_parquet(cache_file)
    else:
        print("Building market data cache (one-time operation)...")
        print("  Loading market cap data (outstanding shares)...")
        market_cap_df = pd.read_csv(
            MARKET_CAP_FILE,
            usecols=['Symbol', 'Date', 'OutstandingShares']
        )
        market_cap_df['Date'] = pd.to_datetime(market_cap_df['Date'])
        market_cap_df = market_cap_df[market_cap_df['Symbol'].isin(needed_symbols)]
        
        print(f"  Loading market values for {len(needed_dates)} specific dates...")
        # Load market values in chunks, filtering by date
        chunks = []
        chunksize = 1_000_000
        for i, chunk in enumerate(pd.read_csv(
            MARKET_VALUES_FILE,
            usecols=['Symbol', 'Date', 'Closing', 'Volume'],
            chunksize=chunksize
        )):
            if i % 10 == 0:
                print(f"    Processing chunk {i}...")
            chunk['Date'] = pd.to_datetime(chunk['Date'])
            # Filter to needed dates first (much faster)
            chunk = chunk[chunk['Date'].isin(needed_dates)]
            if len(chunk) > 0:
                # Then filter by symbols
                chunk = chunk[chunk['Symbol'].isin(needed_symbols)]
                if len(chunk) > 0:
                    chunks.append(chunk)
        
        market_values_df = pd.concat(chunks, ignore_index=True)
        print(f"    Loaded {len(market_values_df):,} market value records")
        
        # For outstanding shares, use merge_asof to get closest prior value
        print("  Merging outstanding shares (asof)...")
        # Prepare for merge_asof: sort carefully
        market_cap_sorted = market_cap_df.sort_values(['Symbol', 'Date']).copy()
        
        # For each symbol+date in market_values, find the closest prior outstanding shares
        market_values_with_shares = []
        for symbol in needed_symbols:
            sym_market = market_values_df[market_values_df['Symbol'] == symbol].sort_values('Date').copy()
            sym_cap = market_cap_sorted[market_cap_sorted['Symbol'] == symbol].copy()
            
            if len(sym_market) > 0 and len(sym_cap) > 0:
                merged = pd.merge_asof(
                    sym_market,
                    sym_cap[['Date', 'OutstandingShares']],
                    on='Date',
                    direction='backward'
                )
                market_values_with_shares.append(merged)
            elif len(sym_market) > 0:
                # No outstanding shares data for this symbol
                sym_market['OutstandingShares'] = None
                market_values_with_shares.append(sym_market)
        
        market_data = pd.concat(market_values_with_shares, ignore_index=True)
        print(f"  Merged {len(market_data):,} records with outstanding shares")
        
        # Calculate derived fields
        market_data['MarketCap'] = market_data['Closing'] * market_data['OutstandingShares']
        market_data['ADV'] = market_data['Volume'] * market_data['Closing']
        
        # Cache for future runs
        print(f"  Saving cache to {cache_file}...")
        market_data.to_parquet(cache_file, index=False)
    
    # Merge with jumps
    print("Merging market data with jump signals...")
    jumps = jumps.merge(
        market_data[['Symbol', 'Date', 'Closing', 'Volume', 'MarketCap', 'ADV']],
        on=['Symbol', 'Date'],
        how='left'
    )
    
    print(f"Loaded {len(jumps)} signals with market data")
    print(f"  Signals with MarketCap: {jumps['MarketCap'].notna().sum()}")
    print(f"  Signals with ADV: {jumps['ADV'].notna().sum()}")
    
    # Layer 1: Enhanced cluster quality adjustment
    print("\nApplying Layer 1 cluster quality enhancements...")
    
    # Convert jump signals to block format
    block_results = convert_jumps_to_blocks(jumps)
    print(f"  Converted to {len(block_results)} time blocks")
    
    # Calculate cluster transitions (dropout/acquisition events)
    loss_df, acquisition_df, quality_threshold = calculate_cluster_transitions(block_results)
    print(f"  Found {len(loss_df)} dropout events, {len(acquisition_df)} acquisition events")
    print(f"  Quality threshold (75th percentile): {quality_threshold:.2f}")
    
    # Calculate cluster stability metrics
    stability_metrics = calculate_cluster_stability(block_results)
    print(f"  Calculated stability metrics for {len(stability_metrics)} clusters")
    
    # Adjust cluster quality based on stability
    jumps = apply_quality_adjustment_to_jumps(
        jumps, 
        stability_metrics,
        stability_weight=0.15,
        dropout_weight=0.20,
        acquisition_weight=0.10
    )
    print(f"  Adjusted quality scores (new column: 'Adjusted_Quality')")
    
    # Show quality adjustment impact
    if 'Adjusted_Quality' in jumps.columns and 'To_Quality' in jumps.columns:
        avg_base = jumps['To_Quality'].mean()
        avg_adjusted = jumps['Adjusted_Quality'].mean()
        print(f"  Average base quality: {avg_base:.4f}")
        print(f"  Average adjusted quality: {avg_adjusted:.4f}")
        print(f"  Quality boost: {((avg_adjusted/avg_base - 1)*100):.2f}%")
    
    
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


def position_size(capital, signal_type, symbol_cap=None, adv=None):
    """Calculate position size with capital and liquidity constraints
    
    Rules:
    - Max position: 0.5% of market cap
    - Can spread entry over up to 3 days
    - Max per-day trade: 5% of ADV (average daily volume)
    - Still respect 5% of portfolio capital constraint
    """
    # Portfolio capital constraint (max 5% per position)
    cap_limited = capital * 0.05

    # Market cap liquidity constraint (max 0.5% of stock market cap)
    if symbol_cap and symbol_cap > 0:
        max_position = symbol_cap * 0.005
    else:
        # If no market cap, use capital limit
        max_position = cap_limited

    # ADV constraint: max 5% of average daily volume per day, up to 3 days
    if adv and adv > 0:
        max_daily_trade = adv * 0.05
        max_via_adv = max_daily_trade * 3  # Can spread over 3 days
    else:
        # If no ADV data, allow full position
        max_via_adv = max_position

    # Final position size: minimum of all constraints
    return min(cap_limited, max_position, max_via_adv)


def simulate_single_backtest(capital, sampled_signals, trading_dates, date_to_idx):
    """Run a single backtest with resampled signals and Layer 2 dynamic exits

    Conservative rules to avoid over-counting:
    - Skip trade if max concurrent reached (no rolling close-and-reopen).
    - Skip trade if size exceeds available cash.
    - Positions exit based on dynamic signals: DROPOUT, QUALITY_COLLAPSE, or MAX_HOLD (500 days)
    """
    df = sampled_signals.copy()
    df['SignalType'] = df.apply(classify_signal, axis=1)

    # Sort by signal type priority then date
    df['Priority'] = (df['SignalType'] == 'BLUE_CHIP').astype(int)
    df = df.sort_values(['Priority', 'Date'], ascending=[False, True])

    # Create lookup for cluster data by (symbol, date)
    cluster_lookup = {}
    for _, row in df.iterrows():
        key = (row['Symbol'], row['Date'])
        cluster_lookup[key] = {
            'cluster_id': row.get('To_Cluster', None),
            'quality': row.get('Adjusted_Quality', row.get('To_Quality', 0))
        }

    cash = capital
    trades = []
    active_positions = []  # Each position has: symbol, entry_date, size, return_pct, pnl, exit_monitor, entry_cluster, entry_quality

    # Process all trading dates to check for exits
    all_dates = sorted(trading_dates)
    
    for current_date in all_dates:
        # Check for exits on active positions
        positions_to_close = []
        
        for i, pos in enumerate(active_positions):
            # Get current cluster/quality for this symbol
            lookup_key = (pos['symbol'], current_date)
            current_data = cluster_lookup.get(lookup_key, {'cluster_id': None, 'quality': None})
            
            # Check exit signal
            exit_signal = pos['exit_monitor'].check_exit_signal(
                current_date=current_date,
                current_cluster_id=current_data['cluster_id'],
                current_quality=current_data['quality']
            )
            
            if exit_signal != 'HOLDING':
                # Mark for exit
                positions_to_close.append({
                    'index': i,
                    'position': pos,
                    'exit_date': current_date,
                    'exit_signal': exit_signal
                })
        
        # Close positions that triggered exits
        for close_info in reversed(sorted(positions_to_close, key=lambda x: x['index'])):
            pos = close_info['position']
            exit_signal = close_info['exit_signal']
            
            # Return capital + PnL
            cash += pos['size'] + pos['pnl']
            
            # Record trade
            trades.append({
                'symbol': pos['symbol'],
                'entry_date': pos['entry_date'],
                'exit_date': close_info['exit_date'],
                'size': pos['size'],
                'return_pct': pos['return_pct'],
                'pnl': pos['pnl'],
                'signal_type': pos['signal_type'],
                'exit_signal': exit_signal,
                'hold_days': (close_info['exit_date'] - pos['entry_date']).days
            })
            
            # Remove from active positions
            active_positions.pop(close_info['index'])
        
        # Try to open new positions on this date
        current_date_signals = df[df['Date'] == current_date]
        
        for _, row in current_date_signals.iterrows():
            symbol = row['Symbol']
            signal_type = row['SignalType']
            trade_date = row['Date']

            # Get return (prefer winsorized)
            return_col = 'return_250d_winsorized' if 'return_250d_winsorized' in row.index else 'return_250d'
            ret = row.get(return_col, 0)
            if pd.isna(ret):
                ret = 0

            # Get market cap and ADV for position sizing
            market_cap = row.get('MarketCap', None)
            adv = row.get('ADV', None)
            
            # Position size
            size = position_size(capital, signal_type, market_cap, adv)
            if size <= 0:
                continue

            # Enforce cash and concurrency limits
            if size > cash:
                continue

            # Check concurrency limit
            if len(active_positions) >= MAX_CONCURRENT_TRADES:
                continue

            # Get entry cluster and quality
            entry_cluster = row.get('To_Cluster', None)
            entry_quality = row.get('Adjusted_Quality', row.get('To_Quality', 0))
            
            # Initialize exit monitor for this position
            exit_monitor = PositionExitMonitor(
                purchase_cluster_id=entry_cluster,
                purchase_quality=entry_quality,
                purchase_date=trade_date,
                quality_threshold=0.0,  # Exit if quality drops below 0
                max_hold_days=500
            )

            # Open position
            pnl = size * (ret / 100.0)  # returns are in percent
            active_positions.append({
                'symbol': symbol,
                'entry_date': trade_date,
                'size': size,
                'return_pct': ret,
                'pnl': pnl,
                'signal_type': signal_type,
                'exit_monitor': exit_monitor,
                'entry_cluster': entry_cluster,
                'entry_quality': entry_quality
            })
            cash -= size

    # Close all remaining positions at end
    for pos in active_positions:
        cash += pos['size'] + pos['pnl']
        
        trades.append({
            'symbol': pos['symbol'],
            'entry_date': pos['entry_date'],
            'exit_date': trading_dates[-1],  # Last trading date
            'size': pos['size'],
            'return_pct': pos['return_pct'],
            'pnl': pos['pnl'],
            'signal_type': pos['signal_type'],
            'exit_signal': 'END_OF_DATA',
            'hold_days': (trading_dates[-1] - pos['entry_date']).days
        })

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
            'final_capital': capital,
            'avg_hold_days': 0,
            'exit_signal_counts': {}
        }

    winning_trades = (trades_df['return_pct'] > 0).sum()
    n_trades = len(trades_df)
    win_rate = winning_trades / n_trades if n_trades > 0 else 0
    total_pnl = trades_df['pnl'].sum()
    total_return_pct = (total_pnl / capital) * 100 if capital > 0 else 0
    
    # Exit signal analysis
    exit_signal_counts = trades_df['exit_signal'].value_counts().to_dict()

    return {
        'n_trades': n_trades,
        'total_pnl': total_pnl,
        'total_return_pct': total_return_pct,
        'win_rate': win_rate,
        'avg_return_pct': trades_df['return_pct'].mean(),
        'median_return_pct': trades_df['return_pct'].median(),
        'std_return_pct': trades_df['return_pct'].std(),
        'final_capital': cash,
        'avg_hold_days': trades_df['hold_days'].mean(),
        'exit_signal_counts': exit_signal_counts
    }
def run_monte_carlo_for_tier(jumps_df, capital, n_simulations, trading_dates, date_to_idx):
    """Run Monte Carlo simulations for a specific capital tier"""
    print(f"  Running {n_simulations} simulations for ${capital:,.0f}...")
    
    results = []
    
    for sim_num in range(n_simulations):
        # Resample signals with replacement
        sampled_idx = np.random.choice(len(jumps_df), size=len(jumps_df), replace=True)
        sampled_signals = jumps_df.iloc[sampled_idx].reset_index(drop=True)
        
        # Run backtest on resampled signals
        metrics = simulate_single_backtest(capital, sampled_signals, trading_dates, date_to_idx)
        metrics['capital_tier'] = capital
        results.append(metrics)
        
        if (sim_num + 1) % 200 == 0:
            print(f"    Completed {sim_num + 1}/{n_simulations}")
    
    return pd.DataFrame(results)


def analyze_tier_results(tier_df, capital):
    """Analyze results for a specific capital tier"""
    print(f"\n{'='*80}")
    print(f"CAPITAL TIER: ${capital:,.0f}")
    print(f"{'='*80}")
    
    print(f"\n--- FINAL CAPITAL ---")
    print(f"  Mean:     ${tier_df['final_capital'].mean():,.0f}")
    print(f"  Median:   ${tier_df['final_capital'].median():,.0f}")
    print(f"  Std Dev:  ${tier_df['final_capital'].std():,.0f}")
    print(f"  5th pct:  ${tier_df['final_capital'].quantile(0.05):,.0f}")
    print(f"  95th pct: ${tier_df['final_capital'].quantile(0.95):,.0f}")
    
    print(f"\n--- TOTAL RETURN % ---")
    print(f"  Mean:     {tier_df['total_return_pct'].mean():.2f}%")
    print(f"  Median:   {tier_df['total_return_pct'].median():.2f}%")
    print(f"  Std Dev:  {tier_df['total_return_pct'].std():.2f}%")
    print(f"  5th pct:  {tier_df['total_return_pct'].quantile(0.05):.2f}%")
    print(f"  95th pct: {tier_df['total_return_pct'].quantile(0.95):.2f}%")
    
    print(f"\n--- WIN RATE ---")
    print(f"  Mean:     {tier_df['win_rate'].mean()*100:.1f}%")
    print(f"  Median:   {tier_df['win_rate'].median()*100:.1f}%")


if __name__ == '__main__':
    # Load data
    jumps_df = load_data()
    print(f"Loaded {len(jumps_df)} total signals")
    
    # Build trading calendar once
    trading_dates, date_to_idx = build_trading_calendar(jumps_df)
    print(f"Trading dates: {len(trading_dates)} ({trading_dates[0]} to {trading_dates[-1]})")
    
    print(f"\n{'='*80}")
    print(f"MONTE CARLO SCALABILITY ANALYSIS")
    print(f"{'='*80}")
    print(f"Simulations per tier: {N_SIMULATIONS}")
    print(f"Capital tiers: {len(CAPITAL_TIERS)}")
    
    # Run Monte Carlo for each capital tier
    all_results = []
    
    for capital in CAPITAL_TIERS:
        tier_results = run_monte_carlo_for_tier(jumps_df, capital, N_SIMULATIONS, 
                                                trading_dates, date_to_idx)
        all_results.append(tier_results)
        analyze_tier_results(tier_results, capital)
    
    # Combine all results
    combined_df = pd.concat(all_results, ignore_index=True)
    
    # Create summary by tier
    print(f"\n{'='*80}")
    print(f"SCALABILITY SUMMARY")
    print(f"{'='*80}")
    
    summary_data = []
    for capital in CAPITAL_TIERS:
        tier_data = combined_df[combined_df['capital_tier'] == capital]
        summary_data.append({
            'Capital': capital,
            'Mean_Final': tier_data['final_capital'].mean(),
            'Median_Final': tier_data['final_capital'].median(),
            'Mean_Return_Pct': tier_data['total_return_pct'].mean(),
            'Median_Return_Pct': tier_data['total_return_pct'].median(),
            'Std_Return_Pct': tier_data['total_return_pct'].std(),
            'Mean_Win_Rate': tier_data['win_rate'].mean() * 100,
            'Pct_5': tier_data['total_return_pct'].quantile(0.05),
            'Pct_95': tier_data['total_return_pct'].quantile(0.95)
        })
    
    summary_df = pd.DataFrame(summary_data)
    
    print(f"\n{summary_df.to_string(index=False)}")
    
    # Calculate ROI multiples
    summary_df['Mean_ROI_Multiple'] = summary_df['Mean_Final'] / summary_df['Capital']
    summary_df['Median_ROI_Multiple'] = summary_df['Median_Final'] / summary_df['Capital']
    
    print(f"\n{'='*80}")
    print(f"ROI MULTIPLES BY TIER")
    print(f"{'='*80}")
    print(f"\n{'Capital':<15} {'Mean ROI':<15} {'Median ROI':<15} {'90% CI Return %':<30}")
    print(f"{'-'*80}")
    
    for _, row in summary_df.iterrows():
        cap_str = f"${row['Capital']:,.0f}"
        mean_roi = f"{row['Mean_ROI_Multiple']:.2f}x"
        median_roi = f"{row['Median_ROI_Multiple']:.2f}x"
        ci = f"{row['Pct_5']:.1f}% to {row['Pct_95']:.1f}%"
        print(f"{cap_str:<15} {mean_roi:<15} {median_roi:<15} {ci:<30}")
    
    # Save results
    combined_df.to_csv('monte_carlo_scalability_results.csv', index=False)
    summary_df.to_csv('monte_carlo_scalability_summary.csv', index=False)
    
    print(f"\n{'='*80}")
    print(f"Results saved:")
    print(f"  - monte_carlo_scalability_results.csv ({len(combined_df)} simulations)")
    print(f"  - monte_carlo_scalability_summary.csv (summary by tier)")
    print(f"{'='*80}")
    
    # Create visualizations
    print(f"\nGenerating visualizations...")
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f'Monte Carlo Scalability Analysis ({N_SIMULATIONS} sims per tier)', 
                 fontsize=16, fontweight='bold')
    
    # Plot 1: Return distribution by tier
    ax = axes[0, 0]
    tier_labels = [f"${c/1e6:.0f}M" if c < 1e9 else f"${c/1e9:.1f}B" for c in CAPITAL_TIERS]
    positions = range(len(CAPITAL_TIERS))

    # Convert Series to numpy arrays to avoid float-on-Series warnings in matplotlib
    tier_returns = [combined_df[combined_df['capital_tier'] == c]['total_return_pct'].to_numpy()
                    for c in CAPITAL_TIERS]
    
    bp = ax.boxplot(tier_returns, tick_labels=tier_labels, patch_artist=True)
    
    for patch in bp['boxes']:
        patch.set_facecolor('steelblue')
        patch.set_alpha(0.7)
    
    ax.set_xlabel('Capital Tier', fontsize=11)
    ax.set_ylabel('Total Return (%)', fontsize=11)
    ax.set_title('Return Distribution by Capital Tier', fontsize=12, fontweight='bold')
    ax.grid(alpha=0.3, axis='y')
    
    # Plot 2: Mean ROI Multiple
    ax = axes[0, 1]
    ax.bar(range(len(summary_df)), summary_df['Mean_ROI_Multiple'], 
           color='seagreen', alpha=0.7, edgecolor='black')
    ax.set_xticks(range(len(summary_df)))
    ax.set_xticklabels(tier_labels, rotation=45)
    ax.set_xlabel('Capital Tier', fontsize=11)
    ax.set_ylabel('Mean ROI Multiple (x)', fontsize=11)
    ax.set_title('Mean ROI Multiple by Tier', fontsize=12, fontweight='bold')
    ax.set_yscale('log')
    ax.grid(alpha=0.3, axis='y')
    
    # Plot 3: 90% Confidence intervals
    ax = axes[1, 0]
    x_pos = range(len(summary_df))
    means = summary_df['Mean_Return_Pct'].to_numpy()
    pct_5 = summary_df['Pct_5'].to_numpy()
    pct_95 = summary_df['Pct_95'].to_numpy()
    yerr = np.vstack((means - pct_5, pct_95 - means))

    ax.errorbar(x_pos, means, yerr=yerr,
                fmt='o-', linewidth=2, markersize=8, capsize=5, color='coral')
    ax.set_xticks(x_pos)
    ax.set_xticklabels(tier_labels, rotation=45)
    ax.set_xlabel('Capital Tier', fontsize=11)
    ax.set_ylabel('Return (%)', fontsize=11)
    ax.set_title('Mean Return with 90% Confidence Interval', fontsize=12, fontweight='bold')
    ax.grid(alpha=0.3)
    
    # Plot 4: Win rate consistency
    ax = axes[1, 1]
    win_rates = [combined_df[combined_df['capital_tier'] == c]['win_rate'].mean() * 100 
                 for c in CAPITAL_TIERS]
    win_stds = [combined_df[combined_df['capital_tier'] == c]['win_rate'].std() * 100 
                for c in CAPITAL_TIERS]
    
    ax.bar(range(len(CAPITAL_TIERS)), win_rates, yerr=win_stds,
           color='mediumpurple', alpha=0.7, edgecolor='black', capsize=5)
    ax.set_xticks(range(len(CAPITAL_TIERS)))
    ax.set_xticklabels(tier_labels, rotation=45)
    ax.set_xlabel('Capital Tier', fontsize=11)
    ax.set_ylabel('Win Rate (%)', fontsize=11)
    ax.set_title('Win Rate Consistency Across Tiers', fontsize=12, fontweight='bold')
    ax.set_ylim([70, 85])
    ax.grid(alpha=0.3, axis='y')
    
    plt.tight_layout()
    output_file = 'monte_carlo_scalability_analysis.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"Visualization saved: {output_file}")
    plt.close()
    
    print(f"\nMonte Carlo scalability analysis complete!")
