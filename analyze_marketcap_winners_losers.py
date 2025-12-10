"""
Analyze Winners vs Losers - WITH MARKET CAP
===========================================

Compare market cap differences between winners and losers
"""

import pandas as pd
import numpy as np

def analyze_marketcap_differences():
    """Analyze market cap differences between winners and losers"""
    
    print("="*80)
    print("MARKET CAP ANALYSIS: WINNERS vs LOSERS")
    print("="*80)
    
    # Load events
    print("\nLoading events...")
    events = pd.read_csv('events_sliding_window_250day_recalc.csv')
    events['Winner'] = events['Future_Return'] > 0
    
    print(f"  Total events: {len(events):,}")
    print(f"  Winners: {(events['Winner'] == True).sum():,} ({(events['Winner'] == True).mean()*100:.1f}%)")
    print(f"  Losers: {(events['Winner'] == False).sum():,} ({(events['Winner'] == False).mean()*100:.1f}%)")
    
    # Load market cap data
    print("\nLoading market cap data...")
    mc_data = pd.read_csv('data_with_marketcap.csv')
    mc_data['Date'] = pd.to_datetime(mc_data['Date'])
    mc_data = mc_data.sort_values(['Symbol', 'Date'])
    
    print(f"  Loaded {len(mc_data):,} records with market cap")
    
    # Create pivot table for market cap
    print("Creating market cap pivot table...")
    mc_pivot = mc_data.pivot_table(index='Date', columns='Symbol', values='MarketCap', aggfunc='first')
    mc_pivot = mc_pivot.ffill().bfill()
    
    print(f"  Market cap table: {len(mc_pivot)} timepoints, {len(mc_pivot.columns)} securities")
    
    # Calculate market cap metrics for each event
    print("\nCalculating market cap metrics during clustering period...")
    
    block_size = 200
    stride = 50
    
    metrics = []
    
    grouped = events.groupby('Security')
    total_securities = len(grouped)
    
    for idx, (security, sec_events) in enumerate(grouped):
        if idx % 1000 == 0:
            print(f"  Progress: {idx:,}/{total_securities:,} ({idx/total_securities*100:.1f}%)")
        
        if security not in mc_pivot.columns:
            continue
        
        mc_series = mc_pivot[security]
        
        for _, event in sec_events.iterrows():
            block_start = event['Block'] * stride
            block_end = block_start + block_size
            
            if block_end >= len(mc_series):
                continue
            
            # Get market cap during clustering period
            block_mc = mc_series.iloc[block_start:block_end]
            
            avg_mc = block_mc.mean()
            median_mc = block_mc.median()
            min_mc = block_mc.min()
            max_mc = block_mc.max()
            
            metrics.append({
                'Security': security,
                'Block': event['Block'],
                'Winner': event['Winner'],
                'Future_Return': event['Future_Return'],
                'Event_Type': event['Event_Type'],
                'Avg_MarketCap': avg_mc,
                'Median_MarketCap': median_mc,
                'Min_MarketCap': min_mc,
                'Max_MarketCap': max_mc
            })
    
    print(f"  Complete! Calculated metrics for {len(metrics):,} events")
    
    metrics_df = pd.DataFrame(metrics)
    
    # Save
    metrics_df.to_csv('marketcap_winners_losers.csv', index=False)
    print(f"\n✓ Saved to: marketcap_winners_losers.csv")
    
    # Analysis
    print("\n" + "="*80)
    print("MARKET CAP COMPARISON: WINNERS vs LOSERS")
    print("="*80)
    
    winners = metrics_df[metrics_df['Winner'] == True]
    losers = metrics_df[metrics_df['Winner'] == False]
    
    print(f"\nSample Size:")
    print(f"  Winners: {len(winners):,}")
    print(f"  Losers: {len(losers):,}")
    
    print(f"\n{'Metric':<25} {'Winners':<25} {'Losers':<25} {'Difference':<15}")
    print("-" * 90)
    
    # Average Market Cap
    w_avg_mc = winners['Avg_MarketCap'].mean()
    l_avg_mc = losers['Avg_MarketCap'].mean()
    avg_mc_pct = (w_avg_mc - l_avg_mc) / l_avg_mc * 100 if l_avg_mc > 0 else 0
    print(f"{'Avg Market Cap':<25} ${w_avg_mc/1e9:<24.2f}B ${l_avg_mc/1e9:<24.2f}B {avg_mc_pct:+.1f}%")
    
    # Median Market Cap
    w_med_mc = winners['Median_MarketCap'].median()
    l_med_mc = losers['Median_MarketCap'].median()
    med_mc_pct = (w_med_mc - l_med_mc) / l_med_mc * 100 if l_med_mc > 0 else 0
    
    if w_med_mc < 1e9 and l_med_mc < 1e9:
        print(f"{'Median Market Cap':<25} ${w_med_mc/1e6:<24.2f}M ${l_med_mc/1e6:<24.2f}M {med_mc_pct:+.1f}%")
    else:
        print(f"{'Median Market Cap':<25} ${w_med_mc/1e9:<24.2f}B ${l_med_mc/1e9:<24.2f}B {med_mc_pct:+.1f}%")
    
    # Key Findings
    print("\n" + "="*80)
    print("KEY FINDINGS")
    print("="*80)
    
    if abs(avg_mc_pct) > 10:
        print(f"• Winners have {abs(avg_mc_pct):.1f}% {'HIGHER' if avg_mc_pct > 0 else 'LOWER'} average market cap ⭐")
    
    if abs(med_mc_pct) > 10:
        print(f"• Winners have {abs(med_mc_pct):.1f}% {'HIGHER' if med_mc_pct > 0 else 'LOWER'} median market cap ⭐")
    
    # Market Cap Buckets
    print("\n" + "="*80)
    print("PERFORMANCE BY MARKET CAP RANGE")
    print("="*80)
    
    # Define market cap tiers
    metrics_df['MC_Bucket'] = pd.cut(
        metrics_df['Avg_MarketCap'],
        bins=[0, 50e6, 300e6, 2e9, 10e9, 100e9, float('inf')],
        labels=['Micro (<$50M)', 'Small ($50M-$300M)', 'Mid ($300M-$2B)', 
                'Large ($2B-$10B)', 'Mega ($10B-$100B)', 'Giant ($100B+)']
    )
    
    print(f"\n{'Market Cap Tier':<25} {'Count':<10} {'Win Rate':<12} {'Avg Return':<15}")
    print("-" * 65)
    
    for bucket in ['Micro (<$50M)', 'Small ($50M-$300M)', 'Mid ($300M-$2B)', 
                   'Large ($2B-$10B)', 'Mega ($10B-$100B)', 'Giant ($100B+)']:
        bucket_data = metrics_df[metrics_df['MC_Bucket'] == bucket]
        if len(bucket_data) > 0:
            win_rate = (bucket_data['Winner'] == True).mean() * 100
            avg_return = bucket_data['Future_Return'].mean()
            print(f"{bucket:<25} {len(bucket_data):<10,} {win_rate:<11.1f}% {avg_return:+14.2f}%")
    
    # Distribution statistics
    print("\n" + "="*80)
    print("MARKET CAP DISTRIBUTION")
    print("="*80)
    
    print(f"\nWinners:")
    print(f"  Min: ${winners['Avg_MarketCap'].min()/1e6:.2f}M")
    print(f"  25th %ile: ${winners['Avg_MarketCap'].quantile(0.25)/1e6:.2f}M")
    print(f"  Median: ${winners['Avg_MarketCap'].median()/1e6:.2f}M")
    print(f"  75th %ile: ${winners['Avg_MarketCap'].quantile(0.75)/1e9:.2f}B")
    print(f"  Max: ${winners['Avg_MarketCap'].max()/1e9:.2f}B")
    
    print(f"\nLosers:")
    print(f"  Min: ${losers['Avg_MarketCap'].min()/1e6:.2f}M")
    print(f"  25th %ile: ${losers['Avg_MarketCap'].quantile(0.25)/1e6:.2f}M")
    print(f"  Median: ${losers['Avg_MarketCap'].median()/1e6:.2f}M")
    print(f"  75th %ile: ${losers['Avg_MarketCap'].quantile(0.75)/1e9:.2f}B")
    print(f"  Max: ${losers['Avg_MarketCap'].max()/1e9:.2f}B")
    
    # Correlation analysis
    print("\n" + "="*80)
    print("CORRELATION ANALYSIS")
    print("="*80)
    
    corr = metrics_df[['Avg_MarketCap', 'Future_Return']].corr().iloc[0, 1]
    print(f"\nCorrelation between Market Cap and Future Return: {corr:.4f}")
    
    if abs(corr) < 0.1:
        print("  → Weak/no correlation")
    elif abs(corr) < 0.3:
        print("  → Moderate correlation")
    else:
        print("  → Strong correlation")
    
    print("\n" + "="*80)
    print("✅ ANALYSIS COMPLETE")
    print("="*80)
    
    return metrics_df

if __name__ == '__main__':
    metrics_df = analyze_marketcap_differences()
