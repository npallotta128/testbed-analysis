"""
FORWARD WINDOW SIZE ANALYSIS

Tests different forward return windows (250, 500, 750 days) to find optimal holding period
Also analyzes whether signal effectiveness degrades based on:
- How many blocks have passed since signal detection
- Whether timing matters in sliding window methodology

Key Questions:
1. What window size gives best annualized returns?
2. Do signals work equally well regardless of when they're detected in the sliding window?
3. Should we invest immediately or wait for confirmation across multiple windows?
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


def get_cluster_members_by_block():
    """Get cluster membership for all blocks from clustering results"""
    
    import pickle
    from pathlib import Path
    
    # Check if we have saved clustering results
    cache_file = Path('cluster_memberships_by_block.pkl')
    
    if cache_file.exists():
        print("Loading cached cluster memberships...")
        with open(cache_file, 'rb') as f:
            return pickle.load(f)
    
    # Otherwise, perform clustering
    print("Performing clustering to identify cluster members...")
    
    data = pd.read_csv('data_with_marketcap.csv')
    data['Date'] = pd.to_datetime(data['Date'])
    data = data.sort_values('Date')
    
    unique_dates = data['Date'].unique()
    block_size = 150
    num_blocks = 10
    
    from scipy.cluster.hierarchy import linkage, fcluster
    from scipy.spatial.distance import pdist
    
    block_clusters = {}
    
    for block_id in range(num_blocks):
        start_idx = block_id * block_size
        end_idx = start_idx + block_size
        
        if end_idx > len(unique_dates):
            break
        
        block_dates = unique_dates[start_idx:end_idx]
        block_data = data[data['Date'].isin(block_dates)].copy()
        
        # Create pivot table
        pivot_data = block_data.pivot_table(
            index='Symbol',
            columns='Date',
            values='Closing',
            aggfunc='last'
        )
        
        if pivot_data.shape[0] < 3:
            continue
        
        # Fill missing values
        pivot_data = pivot_data.fillna(method='ffill', axis=1).fillna(method='bfill', axis=1)
        
        # Perform clustering
        try:
            distances = pdist(pivot_data.values, metric='euclidean')
            linkage_matrix = linkage(distances, method='ward')
            clusters = fcluster(linkage_matrix, t=40, criterion='distance')
            
            # Store cluster assignments
            cluster_assignments = {}
            for i, symbol in enumerate(pivot_data.index):
                cluster_assignments[symbol] = clusters[i]
            
            block_clusters[block_id] = cluster_assignments
            
        except Exception as e:
            print(f"  Error clustering block {block_id}: {e}")
            continue
    
    # Cache the results
    with open(cache_file, 'wb') as f:
        pickle.dump(block_clusters, f)
    
    return block_clusters


def calculate_forward_returns_multiple_windows(data_file='data.csv', windows=[250, 500, 750]):
    """Calculate forward returns for cluster strengthening signals at multiple window sizes"""
    
    print("\n" + "="*80)
    print("CALCULATING FORWARD RETURNS FOR MULTIPLE WINDOWS")
    print("="*80)
    
    # Load cluster strengthening events
    events = pd.read_csv('cluster_strengthening_events.csv')
    events['Date'] = pd.to_datetime(events['Date'])
    
    # Load price data
    data = pd.read_csv(data_file)
    data['Date'] = pd.to_datetime(data['Date'])
    data = data.sort_values('Date')
    
    # Get cluster memberships
    block_clusters = get_cluster_members_by_block()
    
    # For each event, calculate returns at different windows
    results = []
    
    for idx, event in events.iterrows():
        stock = event['Security']
        event_date = event['Date']
        event_block = event['Block']
        cluster_id = event['To_Cluster']
        
        # Get cluster members from block clustering
        if event_block not in block_clusters:
            continue
        
        cluster_assignments = block_clusters[event_block]
        cluster_members = [s for s, c in cluster_assignments.items() if c == cluster_id and s != stock]
        
        if not cluster_members:
            continue
        
        # Calculate returns for each cluster member at each window
        for window_days in windows:
            window_returns = []
            
            for member in cluster_members:
                member_data = data[data['Symbol'] == member].copy()
                member_data = member_data.sort_values('Date')
                
                # Find data AFTER event date (not including event date)
                future_data = member_data[member_data['Date'] > event_date]
                
                if len(future_data) == 0:
                    continue
                
                # Get unique trading dates
                unique_dates = future_data['Date'].unique()
                
                if len(unique_dates) < window_days * 0.5:  # Need at least 50% of window
                    continue
                
                # Take first N trading days
                forward_end_idx = min(window_days, len(unique_dates))
                forward_end_date = unique_dates[forward_end_idx - 1]
                
                # Get start and end prices
                start_price = future_data.iloc[0]['Closing']
                
                end_data = future_data[future_data['Date'] <= forward_end_date]
                if len(end_data) == 0:
                    continue
                end_price = end_data.iloc[-1]['Closing']
                
                if start_price <= 0:
                    continue
                
                ret = ((end_price - start_price) / start_price) * 100
                
                # Calculate actual days elapsed
                days_elapsed = (forward_end_date - future_data.iloc[0]['Date']).days
                
                window_returns.append({
                    'member': member,
                    'return': ret,
                    'days_elapsed': days_elapsed
                })
            
            if window_returns:
                avg_return = np.mean([r['return'] for r in window_returns])
                avg_days = np.mean([r['days_elapsed'] for r in window_returns])
                
                # Annualized return (based on actual days)
                annual_return = (avg_return / 100 + 1) ** (365 / avg_days) - 1 if avg_days > 0 else 0
                annual_return_pct = annual_return * 100
                
                results.append({
                    'Security': stock,
                    'Event_Date': event_date,
                    'Block': event_block,
                    'Window_Days': window_days,
                    'Avg_Return': avg_return,
                    'Days_Elapsed': avg_days,
                    'Annual_Return': annual_return_pct,
                    'Cluster_Size': len(cluster_members),
                    'Members_Traded': len(window_returns)
                })
    
    return pd.DataFrame(results)


def analyze_by_window_size(results_df):
    """Analyze performance by window size"""
    
    print("\n" + "="*80)
    print("PERFORMANCE BY WINDOW SIZE")
    print("="*80)
    
    summary = []
    
    for window in sorted(results_df['Window_Days'].unique()):
        window_data = results_df[results_df['Window_Days'] == window]
        
        wins = (window_data['Avg_Return'] > 0).sum()
        total = len(window_data)
        win_rate = wins / total * 100 if total > 0 else 0
        
        avg_return = window_data['Avg_Return'].mean()
        avg_annual = window_data['Annual_Return'].mean()
        median_return = window_data['Avg_Return'].median()
        
        print(f"\n{window} Trading Days Window:")
        print(f"  Signals: {total}")
        print(f"  Avg Return: {avg_return:+.2f}%")
        print(f"  Avg Annual Return: {avg_annual:+.2f}%")
        print(f"  Median Return: {median_return:+.2f}%")
        print(f"  Win Rate: {win_rate:.1f}% ({wins}/{total})")
        print(f"  Std Dev: {window_data['Avg_Return'].std():.2f}%")
        print(f"  Best: {window_data['Avg_Return'].max():+.2f}%")
        print(f"  Worst: {window_data['Avg_Return'].min():+.2f}%")
        
        # Risk metrics
        returns_norm = window_data['Avg_Return'].values / 100
        sharpe = returns_norm.mean() / (returns_norm.std() + 1e-6)
        print(f"  Sharpe Ratio: {sharpe:.4f}")
        
        summary.append({
            'Window_Days': window,
            'Signals': total,
            'Avg_Return': avg_return,
            'Annual_Return': avg_annual,
            'Win_Rate': win_rate,
            'Sharpe': sharpe
        })
    
    return pd.DataFrame(summary)


def analyze_by_block_number(results_df):
    """Analyze if signal effectiveness varies by block number (timing in sliding window)"""
    
    print("\n" + "="*80)
    print("SIGNAL EFFECTIVENESS BY BLOCK NUMBER")
    print("="*80)
    print("Does timing matter? Do early blocks vs late blocks perform differently?")
    
    # Analyze for 500-day window (our baseline)
    window_500 = results_df[results_df['Window_Days'] == 500].copy()
    
    print(f"\nAnalyzing {len(window_500)} signals at 500-day window:")
    
    block_summary = []
    
    for block in sorted(window_500['Block'].unique()):
        block_data = window_500[window_500['Block'] == block]
        
        if len(block_data) == 0:
            continue
        
        wins = (block_data['Avg_Return'] > 0).sum()
        win_rate = wins / len(block_data) * 100
        avg_return = block_data['Avg_Return'].mean()
        avg_annual = block_data['Annual_Return'].mean()
        
        print(f"\n  Block {block}:")
        print(f"    Signals: {len(block_data)}")
        print(f"    Avg Return: {avg_return:+.2f}%")
        print(f"    Annual Return: {avg_annual:+.2f}%")
        print(f"    Win Rate: {win_rate:.1f}%")
        
        block_summary.append({
            'Block': block,
            'Signals': len(block_data),
            'Avg_Return': avg_return,
            'Annual_Return': avg_annual,
            'Win_Rate': win_rate
        })
    
    block_df = pd.DataFrame(block_summary)
    
    # Statistical test: does block number correlate with returns?
    if len(block_df) > 2:
        correlation = window_500['Block'].corr(window_500['Avg_Return'])
        print(f"\n📊 Correlation between Block Number and Returns: {correlation:.3f}")
        
        if abs(correlation) < 0.2:
            print("   ✅ WEAK correlation - signals work regardless of when detected")
        elif abs(correlation) < 0.5:
            print("   ⚠️  MODERATE correlation - timing may matter somewhat")
        else:
            print("   ⚠️  STRONG correlation - timing matters significantly")
    
    return block_df


def analyze_signal_persistence():
    """Analyze if signals detected early remain valid in later blocks"""
    
    print("\n" + "="*80)
    print("SIGNAL PERSISTENCE ACROSS BLOCKS")
    print("="*80)
    print("Question: If a signal is detected in Block X, does it remain valid in Block X+1, X+2, etc?")
    
    # Load events
    events = pd.read_csv('cluster_strengthening_events.csv')
    events['Date'] = pd.to_datetime(events['Date'])
    
    # Group by stock and analyze cluster stability
    persistence_data = []
    
    for stock in events['Security'].unique():
        stock_events = events[events['Security'] == stock].sort_values('Block')
        
        if len(stock_events) < 2:
            continue
        
        # Check if stock stays in same cluster or keeps switching
        blocks = stock_events['Block'].values
        clusters = stock_events['To_Cluster'].values
        returns = stock_events['Cluster_Future_Return'].values
        
        # Calculate block gaps
        for i in range(len(stock_events) - 1):
            block_gap = blocks[i+1] - blocks[i]
            cluster_change = (clusters[i+1] != clusters[i])
            
            persistence_data.append({
                'Stock': stock,
                'Block': blocks[i],
                'Next_Block': blocks[i+1],
                'Block_Gap': block_gap,
                'Cluster_Changed': cluster_change,
                'Return_First': returns[i],
                'Return_Second': returns[i+1]
            })
    
    if not persistence_data:
        print("  Not enough repeat signals to analyze persistence")
        return None
    
    persist_df = pd.DataFrame(persistence_data)
    
    print(f"\n  Stocks with multiple signals: {persist_df['Stock'].nunique()}")
    print(f"  Total signal pairs analyzed: {len(persist_df)}")
    
    # Analyze by block gap
    print("\n  Performance by blocks elapsed between signals:")
    for gap in sorted(persist_df['Block_Gap'].unique()):
        gap_data = persist_df[persist_df['Block_Gap'] == gap]
        
        avg_first = gap_data['Return_First'].mean()
        avg_second = gap_data['Return_Second'].mean()
        
        print(f"    Gap of {gap} blocks:")
        print(f"      Count: {len(gap_data)}")
        print(f"      Avg return (first signal): {avg_first:+.2f}%")
        print(f"      Avg return (second signal): {avg_second:+.2f}%")
        print(f"      Delta: {avg_second - avg_first:+.2f}%")
    
    return persist_df


def investment_timing_recommendation(summary_df, block_df):
    """Provide recommendations on investment timing"""
    
    print("\n" + "="*80)
    print("INVESTMENT TIMING RECOMMENDATIONS")
    print("="*80)
    
    # Find best window
    best_window = summary_df.loc[summary_df['Annual_Return'].idxmax()]
    best_sharpe = summary_df.loc[summary_df['Sharpe'].idxmax()]
    
    print(f"\n📈 BEST ANNUAL RETURN:")
    print(f"   Window: {int(best_window['Window_Days'])} days (~{int(best_window['Window_Days']/252)} years)")
    print(f"   Annual Return: {best_window['Annual_Return']:+.2f}%")
    print(f"   Total Return: {best_window['Avg_Return']:+.2f}%")
    print(f"   Win Rate: {best_window['Win_Rate']:.1f}%")
    
    print(f"\n📊 BEST RISK-ADJUSTED RETURN (Sharpe):")
    print(f"   Window: {int(best_sharpe['Window_Days'])} days")
    print(f"   Sharpe Ratio: {best_sharpe['Sharpe']:.4f}")
    print(f"   Annual Return: {best_sharpe['Annual_Return']:+.2f}%")
    
    print(f"\n⏰ TIMING SENSITIVITY:")
    if len(block_df) > 0:
        block_variance = block_df['Avg_Return'].std()
        avg_return = block_df['Avg_Return'].mean()
        
        if block_variance < avg_return * 0.3:  # Variance < 30% of mean
            print(f"   ✅ LOW timing sensitivity (CV: {block_variance/avg_return:.2f})")
            print(f"   → INVEST IMMEDIATELY when signal detected")
            print(f"   → No need to wait for confirmation across multiple windows")
        else:
            print(f"   ⚠️  HIGH timing sensitivity (CV: {block_variance/avg_return:.2f})")
            print(f"   → Consider waiting for signal confirmation")
            print(f"   → Or use smaller position sizes early")
    
    print(f"\n💡 ACTIONABLE STRATEGY:")
    print(f"   1. Use {int(best_window['Window_Days'])}-day holding period for maximum annual returns")
    print(f"   2. Invest immediately when signal detected (don't wait for block confirmation)")
    print(f"   3. Expected annual return: {best_window['Annual_Return']:+.2f}%")
    print(f"   4. Expected win rate: {best_window['Win_Rate']:.1f}%")


def main():
    """Run complete window size analysis"""
    
    print("="*80)
    print("FORWARD WINDOW SIZE & TIMING ANALYSIS")
    print("="*80)
    
    # Calculate returns for multiple windows
    print("\nCalculating forward returns for 250, 500, and 750 day windows...")
    results_df = calculate_forward_returns_multiple_windows(windows=[250, 500, 750])
    
    if len(results_df) == 0:
        print("❌ No results calculated")
        return
    
    # Save detailed results
    results_df.to_csv('window_size_analysis.csv', index=False)
    print(f"\n✅ Saved detailed results to window_size_analysis.csv")
    
    # Analyze by window size
    summary_df = analyze_by_window_size(results_df)
    summary_df.to_csv('window_size_summary.csv', index=False)
    
    # Analyze by block number (timing sensitivity)
    block_df = analyze_by_block_number(results_df)
    if block_df is not None and len(block_df) > 0:
        block_df.to_csv('block_timing_analysis.csv', index=False)
    
    # Analyze signal persistence
    persist_df = analyze_signal_persistence()
    if persist_df is not None:
        persist_df.to_csv('signal_persistence.csv', index=False)
    
    # Final recommendations
    investment_timing_recommendation(summary_df, block_df)
    
    print("\n" + "="*80)
    print("✅ ANALYSIS COMPLETE")
    print("="*80)
    print("\nFiles created:")
    print("  - window_size_analysis.csv (detailed results)")
    print("  - window_size_summary.csv (summary by window)")
    print("  - block_timing_analysis.csv (timing sensitivity)")
    print("  - signal_persistence.csv (signal stability)")
    
    return results_df, summary_df, block_df


if __name__ == '__main__':
    results_df, summary_df, block_df = main()
