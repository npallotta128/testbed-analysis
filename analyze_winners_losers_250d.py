"""
Analyze Winners vs Losers from 250-day Events
==============================================

Compare stocks that had positive returns vs negative returns
Look for differences in:
- Price during clustering period
- Volume during clustering period  
- Market cap during clustering period
"""

import pandas as pd
import numpy as np
from optimize_dropout_strategy_safe import load_data_once

def analyze_winners_vs_losers():
    """Analyze differences between winning and losing events"""
    
    print("="*80)
    print("WINNERS vs LOSERS ANALYSIS (250-day window)")
    print("="*80)
    
    # Load events
    print("\nLoading events...")
    events = pd.read_csv('events_sliding_window_250day_recalc.csv')
    print(f"  Total events: {len(events):,}")
    
    # Classify winners and losers
    events['Winner'] = events['Future_Return'] > 0
    winners = events[events['Winner'] == True]
    losers = events[events['Winner'] == False]
    
    print(f"  Winners (positive return): {len(winners):,} ({len(winners)/len(events)*100:.1f}%)")
    print(f"  Losers (negative return): {len(losers):,} ({len(losers)/len(events)*100:.1f}%)")
    
    # Load price data
    print("\nLoading price data...")
    _, closing_table = load_data_once('data.csv')
    
    # Also need volume data
    print("Loading full data with volume...")
    data = pd.read_csv('data.csv')
    data['Date'] = pd.to_datetime(data['Date'])
    
    print(f"  Loaded {len(data):,} price records")
    
    # Calculate metrics for each event during the clustering block
    print("\nCalculating clustering period metrics...")
    
    block_size = 200
    stride = 50
    
    metrics = []
    
    for idx, event in events.iterrows():
        if idx % 10000 == 0:
            print(f"  Progress: {idx:,}/{len(events):,} ({idx/len(events)*100:.1f}%)")
        
        security = event['Security']
        block = event['Block']
        
        # Calculate block timepoints
        block_start = block * stride
        block_end = block_start + block_size
        
        # Get security data during clustering period
        if security not in closing_table.columns:
            continue
            
        price_series = closing_table[security].iloc[block_start:block_end]
        
        # Filter data for this security and time period
        sec_data = data[data['Symbol'] == security].sort_values('Date')
        
        # Get the date range for the block
        if len(sec_data) == 0:
            continue
            
        all_dates = sec_data['Date'].unique()
        if block_end >= len(all_dates):
            continue
            
        block_dates = all_dates[block_start:block_end]
        block_data = sec_data[sec_data['Date'].isin(block_dates)]
        
        if len(block_data) == 0:
            continue
        
        # Calculate metrics
        avg_price = block_data['Closing'].mean()
        avg_volume = block_data['Volume'].mean()
        median_price = block_data['Closing'].median()
        median_volume = block_data['Volume'].median()
        price_volatility = block_data['Closing'].std() / block_data['Closing'].mean() if block_data['Closing'].mean() > 0 else 0
        
        # Market cap (if available)
        market_cap = None
        if 'MarketCap' in block_data.columns:
            market_cap = block_data['MarketCap'].mean()
        
        metrics.append({
            'Security': security,
            'Block': block,
            'Winner': event['Winner'],
            'Future_Return': event['Future_Return'],
            'Avg_Price': avg_price,
            'Median_Price': median_price,
            'Avg_Volume': avg_volume,
            'Median_Volume': median_volume,
            'Price_Volatility': price_volatility,
            'MarketCap': market_cap,
            'Event_Type': event['Event_Type']
        })
    
    print(f"  Complete! Calculated metrics for {len(metrics):,} events")
    
    # Convert to DataFrame
    metrics_df = pd.DataFrame(metrics)
    
    # Save detailed metrics
    metrics_df.to_csv('winners_losers_metrics_250d.csv', index=False)
    print(f"\n✓ Saved detailed metrics to: winners_losers_metrics_250d.csv")
    
    # Compare winners vs losers
    print("\n" + "="*80)
    print("COMPARISON: WINNERS vs LOSERS")
    print("="*80)
    
    winners_metrics = metrics_df[metrics_df['Winner'] == True]
    losers_metrics = metrics_df[metrics_df['Winner'] == False]
    
    print(f"\n{'Metric':<25} {'Winners':<20} {'Losers':<20} {'Difference':<15}")
    print("-" * 80)
    
    # Average Price
    winner_avg_price = winners_metrics['Avg_Price'].mean()
    loser_avg_price = losers_metrics['Avg_Price'].mean()
    price_diff = winner_avg_price - loser_avg_price
    price_pct = (price_diff / loser_avg_price * 100) if loser_avg_price > 0 else 0
    print(f"{'Avg Price':<25} ${winner_avg_price:<19.2f} ${loser_avg_price:<19.2f} {price_pct:+.1f}%")
    
    # Median Price
    winner_med_price = winners_metrics['Median_Price'].median()
    loser_med_price = losers_metrics['Median_Price'].median()
    med_price_diff = winner_med_price - loser_med_price
    med_price_pct = (med_price_diff / loser_med_price * 100) if loser_med_price > 0 else 0
    print(f"{'Median Price':<25} ${winner_med_price:<19.2f} ${loser_med_price:<19.2f} {med_price_pct:+.1f}%")
    
    # Average Volume
    winner_avg_vol = winners_metrics['Avg_Volume'].mean()
    loser_avg_vol = losers_metrics['Avg_Volume'].mean()
    vol_diff = winner_avg_vol - loser_avg_vol
    vol_pct = (vol_diff / loser_avg_vol * 100) if loser_avg_vol > 0 else 0
    print(f"{'Avg Volume':<25} {winner_avg_vol:<20,.0f} {loser_avg_vol:<20,.0f} {vol_pct:+.1f}%")
    
    # Median Volume
    winner_med_vol = winners_metrics['Median_Volume'].median()
    loser_med_vol = losers_metrics['Median_Volume'].median()
    med_vol_diff = winner_med_vol - loser_med_vol
    med_vol_pct = (med_vol_diff / loser_med_vol * 100) if loser_med_vol > 0 else 0
    print(f"{'Median Volume':<25} {winner_med_vol:<20,.0f} {loser_med_vol:<20,.0f} {med_vol_pct:+.1f}%")
    
    # Price Volatility
    winner_vol = winners_metrics['Price_Volatility'].mean()
    loser_vol = losers_metrics['Price_Volatility'].mean()
    vol_diff_pct = ((winner_vol - loser_vol) / loser_vol * 100) if loser_vol > 0 else 0
    print(f"{'Price Volatility (CV)':<25} {winner_vol:<20.4f} {loser_vol:<20.4f} {vol_diff_pct:+.1f}%")
    
    # Market Cap (if available)
    if metrics_df['MarketCap'].notna().any():
        winner_mc = winners_metrics['MarketCap'].mean()
        loser_mc = losers_metrics['MarketCap'].mean()
        mc_diff = winner_mc - loser_mc
        mc_pct = (mc_diff / loser_mc * 100) if loser_mc > 0 else 0
        print(f"{'Avg Market Cap':<25} ${winner_mc:<19,.0f} ${loser_mc:<19,.0f} {mc_pct:+.1f}%")
    
    # Statistical summary
    print("\n" + "="*80)
    print("KEY FINDINGS")
    print("="*80)
    
    findings = []
    
    if abs(price_pct) > 10:
        findings.append(f"• Winners have {abs(price_pct):.1f}% {'HIGHER' if price_pct > 0 else 'LOWER'} average price")
    
    if abs(vol_pct) > 10:
        findings.append(f"• Winners have {abs(vol_pct):.1f}% {'HIGHER' if vol_pct > 0 else 'LOWER'} average volume")
    
    if abs(vol_diff_pct) > 10:
        findings.append(f"• Winners have {abs(vol_diff_pct):.1f}% {'HIGHER' if vol_diff_pct > 0 else 'LOWER'} price volatility")
    
    if findings:
        for finding in findings:
            print(finding)
    else:
        print("• No major differences found between winners and losers")
    
    # Distribution analysis
    print("\n" + "="*80)
    print("DISTRIBUTION ANALYSIS")
    print("="*80)
    
    # Price buckets
    print("\nBy Price Range:")
    metrics_df['Price_Bucket'] = pd.cut(metrics_df['Avg_Price'], 
                                         bins=[0, 5, 10, 20, 50, 100, float('inf')],
                                         labels=['$0-5', '$5-10', '$10-20', '$20-50', '$50-100', '$100+'])
    
    for bucket in ['$0-5', '$5-10', '$10-20', '$20-50', '$50-100', '$100+']:
        bucket_data = metrics_df[metrics_df['Price_Bucket'] == bucket]
        if len(bucket_data) > 0:
            win_rate = (bucket_data['Winner'] == True).mean() * 100
            avg_return = bucket_data['Future_Return'].mean()
            print(f"  {bucket:<10} Win Rate: {win_rate:5.1f}%  Avg Return: {avg_return:+8.2f}%  Count: {len(bucket_data):,}")
    
    # Volume buckets
    print("\nBy Volume Range:")
    metrics_df['Volume_Bucket'] = pd.cut(metrics_df['Avg_Volume'], 
                                          bins=[0, 10000, 100000, 1000000, float('inf')],
                                          labels=['<10K', '10K-100K', '100K-1M', '1M+'])
    
    for bucket in ['<10K', '10K-100K', '100K-1M', '1M+']:
        bucket_data = metrics_df[metrics_df['Volume_Bucket'] == bucket]
        if len(bucket_data) > 0:
            win_rate = (bucket_data['Winner'] == True).mean() * 100
            avg_return = bucket_data['Future_Return'].mean()
            print(f"  {bucket:<10} Win Rate: {win_rate:5.1f}%  Avg Return: {avg_return:+8.2f}%  Count: {len(bucket_data):,}")
    
    print("\n" + "="*80)
    print("✅ ANALYSIS COMPLETE")
    print("="*80)
    
    return metrics_df

if __name__ == '__main__':
    metrics_df = analyze_winners_vs_losers()
