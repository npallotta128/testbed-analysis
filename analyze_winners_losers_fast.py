"""
Analyze Winners vs Losers - OPTIMIZED VERSION
==============================================

Uses vectorized operations and pre-loaded data
"""

import pandas as pd
import numpy as np
from optimize_dropout_strategy_safe import load_data_once

def analyze_winners_vs_losers_fast():
    """Fast vectorized analysis of winners vs losers"""
    
    print("="*80)
    print("WINNERS vs LOSERS ANALYSIS (250-day window) - FAST VERSION")
    print("="*80)
    
    # Load events
    print("\nLoading events...")
    events = pd.read_csv('events_sliding_window_250day_recalc.csv')
    print(f"  Total events: {len(events):,}")
    
    # Classify winners and losers
    events['Winner'] = events['Future_Return'] > 0
    winners = events[events['Winner'] == True]
    losers = events[events['Winner'] == False]
    
    print(f"  Winners: {len(winners):,} ({len(winners)/len(events)*100:.1f}%)")
    print(f"  Losers: {len(losers):,} ({len(losers)/len(events)*100:.1f}%)")
    
    # Load price data (already optimized)
    print("\nLoading price data...")
    _, closing_table = load_data_once('data.csv')
    print(f"  Loaded {len(closing_table)} timepoints, {len(closing_table.columns)} securities")
    
    # Load volume data efficiently
    print("\nLoading volume data...")
    data = pd.read_csv('data.csv', usecols=['Symbol', 'Date', 'Closing', 'Volume'])
    data['Date'] = pd.to_datetime(data['Date'])
    data = data.sort_values(['Symbol', 'Date'])
    
    # Create volume pivot table
    print("Creating volume pivot table...")
    volume_table = data.pivot_table(index='Date', columns='Symbol', values='Volume', aggfunc='first')
    volume_table = volume_table.fillna(method='ffill').fillna(method='bfill')
    
    print(f"  Volume table: {len(volume_table)} timepoints, {len(volume_table.columns)} securities")
    
    # Calculate metrics using vectorized operations
    print("\nCalculating metrics for all events (vectorized)...")
    
    block_size = 200
    stride = 50
    
    # Pre-calculate all block ranges
    events['block_start'] = events['Block'] * stride
    events['block_end'] = events['block_start'] + block_size
    
    metrics = []
    
    # Group by security for efficiency
    grouped = events.groupby('Security')
    total_securities = len(grouped)
    
    for idx, (security, sec_events) in enumerate(grouped):
        if idx % 1000 == 0:
            print(f"  Progress: {idx:,}/{total_securities:,} securities ({idx/total_securities*100:.1f}%)")
        
        # Skip if security not in price data
        if security not in closing_table.columns:
            continue
        
        # Get price and volume series for this security
        price_series = closing_table[security]
        volume_series = volume_table[security] if security in volume_table.columns else None
        
        # Process each event for this security
        for _, event in sec_events.iterrows():
            block_start = event['block_start']
            block_end = event['block_end']
            
            # Skip if block is out of range
            if block_end >= len(price_series):
                continue
            
            # Get block data
            block_prices = price_series.iloc[block_start:block_end]
            
            # Calculate price metrics
            avg_price = block_prices.mean()
            median_price = block_prices.median()
            price_volatility = block_prices.std() / avg_price if avg_price > 0 else 0
            
            # Calculate volume metrics
            avg_volume = None
            median_volume = None
            if volume_series is not None and block_end <= len(volume_series):
                block_volumes = volume_series.iloc[block_start:block_end]
                avg_volume = block_volumes.mean()
                median_volume = block_volumes.median()
            
            metrics.append({
                'Security': security,
                'Block': event['Block'],
                'Winner': event['Winner'],
                'Future_Return': event['Future_Return'],
                'Event_Type': event['Event_Type'],
                'Avg_Price': avg_price,
                'Median_Price': median_price,
                'Avg_Volume': avg_volume,
                'Median_Volume': median_volume,
                'Price_Volatility': price_volatility
            })
    
    print(f"  Complete! Calculated metrics for {len(metrics):,} events")
    
    # Convert to DataFrame
    metrics_df = pd.DataFrame(metrics)
    
    # Save
    metrics_df.to_csv('winners_losers_metrics_250d.csv', index=False)
    print(f"\n✓ Saved to: winners_losers_metrics_250d.csv")
    
    # Compare winners vs losers
    print("\n" + "="*80)
    print("COMPARISON: WINNERS vs LOSERS")
    print("="*80)
    
    winners_m = metrics_df[metrics_df['Winner'] == True]
    losers_m = metrics_df[metrics_df['Winner'] == False]
    
    print(f"\nSample Size:")
    print(f"  Winners: {len(winners_m):,}")
    print(f"  Losers: {len(losers_m):,}")
    
    print(f"\n{'Metric':<25} {'Winners':<20} {'Losers':<20} {'Difference':<15}")
    print("-" * 80)
    
    # Price
    w_price = winners_m['Avg_Price'].mean()
    l_price = losers_m['Avg_Price'].mean()
    price_pct = (w_price - l_price) / l_price * 100 if l_price > 0 else 0
    print(f"{'Avg Price':<25} ${w_price:<19.2f} ${l_price:<19.2f} {price_pct:+.1f}%")
    
    w_med_price = winners_m['Median_Price'].median()
    l_med_price = losers_m['Median_Price'].median()
    med_price_pct = (w_med_price - l_med_price) / l_med_price * 100 if l_med_price > 0 else 0
    print(f"{'Median Price':<25} ${w_med_price:<19.2f} ${l_med_price:<19.2f} {med_price_pct:+.1f}%")
    
    # Volume
    w_vol = winners_m['Avg_Volume'].mean()
    l_vol = losers_m['Avg_Volume'].mean()
    vol_pct = (w_vol - l_vol) / l_vol * 100 if l_vol > 0 else 0
    print(f"{'Avg Volume':<25} {w_vol:<20,.0f} {l_vol:<20,.0f} {vol_pct:+.1f}%")
    
    w_med_vol = winners_m['Median_Volume'].median()
    l_med_vol = losers_m['Median_Volume'].median()
    med_vol_pct = (w_med_vol - l_med_vol) / l_med_vol * 100 if l_med_vol > 0 else 0
    print(f"{'Median Volume':<25} {w_med_vol:<20,.0f} {l_med_vol:<20,.0f} {med_vol_pct:+.1f}%")
    
    # Volatility
    w_vola = winners_m['Price_Volatility'].mean()
    l_vola = losers_m['Price_Volatility'].mean()
    vola_pct = (w_vola - l_vola) / l_vola * 100 if l_vola > 0 else 0
    print(f"{'Price Volatility (CV)':<25} {w_vola:<20.4f} {l_vola:<20.4f} {vola_pct:+.1f}%")
    
    # Key findings
    print("\n" + "="*80)
    print("KEY FINDINGS")
    print("="*80)
    
    if abs(price_pct) > 10:
        print(f"• Winners have {abs(price_pct):.1f}% {'HIGHER' if price_pct > 0 else 'LOWER'} average price ⭐")
    
    if abs(vol_pct) > 10:
        print(f"• Winners have {abs(vol_pct):.1f}% {'HIGHER' if vol_pct > 0 else 'LOWER'} trading volume ⭐")
    
    if abs(vola_pct) > 10:
        print(f"• Winners are {abs(vola_pct):.1f}% {'MORE' if vola_pct > 0 else 'LESS'} volatile ⭐")
    
    # Distribution analysis
    print("\n" + "="*80)
    print("PERFORMANCE BY PRICE RANGE")
    print("="*80)
    
    metrics_df['Price_Bucket'] = pd.cut(metrics_df['Avg_Price'], 
                                         bins=[0, 5, 10, 20, 50, 100, float('inf')],
                                         labels=['$0-5', '$5-10', '$10-20', '$20-50', '$50-100', '$100+'])
    
    print(f"\n{'Price Range':<12} {'Count':<10} {'Win Rate':<12} {'Avg Return':<15}")
    print("-" * 50)
    for bucket in ['$0-5', '$5-10', '$10-20', '$20-50', '$50-100', '$100+']:
        bucket_data = metrics_df[metrics_df['Price_Bucket'] == bucket]
        if len(bucket_data) > 0:
            win_rate = (bucket_data['Winner'] == True).mean() * 100
            avg_return = bucket_data['Future_Return'].mean()
            print(f"{bucket:<12} {len(bucket_data):<10,} {win_rate:<11.1f}% {avg_return:+14.2f}%")
    
    print("\n" + "="*80)
    print("PERFORMANCE BY VOLUME RANGE")
    print("="*80)
    
    metrics_df['Volume_Bucket'] = pd.cut(metrics_df['Avg_Volume'], 
                                          bins=[0, 10000, 100000, 1000000, 10000000, float('inf')],
                                          labels=['<10K', '10K-100K', '100K-1M', '1M-10M', '10M+'])
    
    print(f"\n{'Volume Range':<12} {'Count':<10} {'Win Rate':<12} {'Avg Return':<15}")
    print("-" * 50)
    for bucket in ['<10K', '10K-100K', '100K-1M', '1M-10M', '10M+']:
        bucket_data = metrics_df[metrics_df['Volume_Bucket'] == bucket]
        if len(bucket_data) > 0:
            win_rate = (bucket_data['Winner'] == True).mean() * 100
            avg_return = bucket_data['Future_Return'].mean()
            print(f"{bucket:<12} {len(bucket_data):<10,} {win_rate:<11.1f}% {avg_return:+14.2f}%")
    
    print("\n" + "="*80)
    print("✅ ANALYSIS COMPLETE")
    print("="*80)
    
    return metrics_df

if __name__ == '__main__':
    metrics_df = analyze_winners_vs_losers_fast()
