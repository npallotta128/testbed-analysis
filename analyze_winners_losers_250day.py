"""
Analyze Winners vs Losers - 250-Day Events
===========================================

Compare characteristics of winning vs losing events during the clustering timeframe:
- Price levels
- Volume (ADV)
- Market cap
- Price volatility
- Volume consistency

Goal: Identify obvious differences that could improve event filtering
"""

import pandas as pd
import numpy as np
from optimize_dropout_strategy_safe import load_data_once

def load_event_data():
    """Load 250-day recalculated events"""
    print("Loading 250-day event data...")
    events = pd.read_csv('events_sliding_window_250day_recalc.csv')
    
    # Classify winners vs losers
    events['Winner'] = events['Future_Return'] > 0
    
    print(f"  Total events: {len(events):,}")
    print(f"  Winners: {events['Winner'].sum():,} ({events['Winner'].mean()*100:.1f}%)")
    print(f"  Losers: {(~events['Winner']).sum():,} ({(~events['Winner']).mean()*100:.1f}%)")
    
    return events

def calculate_clustering_period_metrics(events, data_file='data.csv'):
    """
    Calculate price, volume, and market cap metrics during the clustering period
    
    For each event, we look at the block period (200 days) where clustering occurred
    """
    print("\nCalculating clustering period metrics...")
    
    # Load price data
    price_df = pd.read_csv(data_file)
    price_df['Date'] = pd.to_datetime(price_df['Date'])
    
    # Parameters from sliding window
    block_size = 200
    stride = 50
    
    results = []
    
    for idx, event in events.iterrows():
        if idx % 10000 == 0:
            print(f"  Progress: {idx:,}/{len(events):,} ({idx/len(events)*100:.1f}%)")
        
        security = event['Security']
        block = event['Block']
        
        # Calculate block timepoint range
        block_start = block * stride
        block_end = block_start + block_size
        
        # Get security's data during clustering period
        sec_data = price_df[price_df['Symbol'] == security].sort_values('Date')
        
        if len(sec_data) == 0:
            continue
        
        # Get data for the block period
        block_data = sec_data.iloc[block_start:block_end]
        
        if len(block_data) < 50:  # Need minimum data
            continue
        
        # Calculate metrics
        avg_price = block_data['Closing'].mean()
        median_price = block_data['Closing'].median()
        price_std = block_data['Closing'].std()
        price_volatility = (price_std / avg_price * 100) if avg_price > 0 else 0
        
        avg_volume = block_data['Volume'].mean()
        median_volume = block_data['Volume'].median()
        volume_std = block_data['Volume'].std()
        volume_cv = (volume_std / avg_volume) if avg_volume > 0 else 0  # Coefficient of variation
        
        # Calculate market cap if we have the data
        market_cap = np.nan
        if 'MarketCap' in block_data.columns:
            market_cap = block_data['MarketCap'].mean()
        elif avg_price > 0 and avg_volume > 0:
            # Rough estimate: assume shares outstanding ~ volume * some factor
            # This is very rough but gives relative sizing
            market_cap = avg_price * avg_volume * 50  # Rough multiplier
        
        results.append({
            'Security': security,
            'Block': block,
            'Event_Type': event['Event_Type'],
            'Future_Return': event['Future_Return'],
            'Winner': event['Winner'],
            'Avg_Price': avg_price,
            'Median_Price': median_price,
            'Price_Std': price_std,
            'Price_Volatility_%': price_volatility,
            'Avg_Volume': avg_volume,
            'Median_Volume': median_volume,
            'Volume_Std': volume_std,
            'Volume_CV': volume_cv,
            'Est_MarketCap': market_cap,
            'Block_Days': len(block_data)
        })
    
    return pd.DataFrame(results)

def compare_winners_vs_losers(metrics_df):
    """Compare characteristics of winners vs losers"""
    
    print("\n" + "="*80)
    print("WINNERS vs LOSERS COMPARISON")
    print("="*80)
    
    winners = metrics_df[metrics_df['Winner'] == True]
    losers = metrics_df[metrics_df['Winner'] == False]
    
    print(f"\nSample sizes:")
    print(f"  Winners: {len(winners):,}")
    print(f"  Losers: {len(losers):,}")
    
    # Price comparison
    print(f"\n" + "-"*80)
    print("PRICE DURING CLUSTERING PERIOD")
    print("-"*80)
    print(f"Average Price:")
    print(f"  Winners: ${winners['Avg_Price'].mean():.2f} (median: ${winners['Avg_Price'].median():.2f})")
    print(f"  Losers:  ${losers['Avg_Price'].mean():.2f} (median: ${losers['Avg_Price'].median():.2f})")
    print(f"  Difference: ${winners['Avg_Price'].mean() - losers['Avg_Price'].mean():.2f}")
    
    print(f"\nPrice Volatility (%):")
    print(f"  Winners: {winners['Price_Volatility_%'].mean():.2f}% (median: {winners['Price_Volatility_%'].median():.2f}%)")
    print(f"  Losers:  {losers['Price_Volatility_%'].mean():.2f}% (median: {losers['Price_Volatility_%'].median():.2f}%)")
    print(f"  Difference: {winners['Price_Volatility_%'].mean() - losers['Price_Volatility_%'].mean():.2f}%")
    
    # Volume comparison
    print(f"\n" + "-"*80)
    print("VOLUME (ADV) DURING CLUSTERING PERIOD")
    print("-"*80)
    print(f"Average Daily Volume:")
    print(f"  Winners: {winners['Avg_Volume'].mean():,.0f} (median: {winners['Avg_Volume'].median():,.0f})")
    print(f"  Losers:  {losers['Avg_Volume'].mean():,.0f} (median: {losers['Avg_Volume'].median():,.0f})")
    print(f"  Difference: {winners['Avg_Volume'].mean() - losers['Avg_Volume'].mean():,.0f}")
    
    print(f"\nVolume Consistency (lower CV = more consistent):")
    print(f"  Winners: {winners['Volume_CV'].mean():.2f} (median: {winners['Volume_CV'].median():.2f})")
    print(f"  Losers:  {losers['Volume_CV'].mean():.2f} (median: {losers['Volume_CV'].median():.2f})")
    print(f"  Difference: {winners['Volume_CV'].mean() - losers['Volume_CV'].mean():.2f}")
    
    # Market cap comparison
    print(f"\n" + "-"*80)
    print("ESTIMATED MARKET CAP DURING CLUSTERING PERIOD")
    print("-"*80)
    winners_mc = winners['Est_MarketCap'].dropna()
    losers_mc = losers['Est_MarketCap'].dropna()
    
    print(f"Estimated Market Cap:")
    print(f"  Winners: ${winners_mc.mean()/1e9:.2f}B (median: ${winners_mc.median()/1e9:.2f}B)")
    print(f"  Losers:  ${losers_mc.mean()/1e9:.2f}B (median: ${losers_mc.median()/1e9:.2f}B)")
    print(f"  Difference: ${(winners_mc.mean() - losers_mc.mean())/1e9:.2f}B")
    
    # Statistical significance tests (t-test)
    from scipy import stats
    
    print(f"\n" + "-"*80)
    print("STATISTICAL SIGNIFICANCE (t-tests)")
    print("-"*80)
    
    # Price t-test
    t_price, p_price = stats.ttest_ind(winners['Avg_Price'].dropna(), losers['Avg_Price'].dropna())
    print(f"Price: t={t_price:.2f}, p={p_price:.4f} {'***' if p_price < 0.001 else '**' if p_price < 0.01 else '*' if p_price < 0.05 else 'ns'}")
    
    # Volatility t-test
    t_vol, p_vol = stats.ttest_ind(winners['Price_Volatility_%'].dropna(), losers['Price_Volatility_%'].dropna())
    print(f"Volatility: t={t_vol:.2f}, p={p_vol:.4f} {'***' if p_vol < 0.001 else '**' if p_vol < 0.01 else '*' if p_vol < 0.05 else 'ns'}")
    
    # Volume t-test
    t_volume, p_volume = stats.ttest_ind(winners['Avg_Volume'].dropna(), losers['Avg_Volume'].dropna())
    print(f"Volume: t={t_volume:.2f}, p={p_volume:.4f} {'***' if p_volume < 0.001 else '**' if p_volume < 0.01 else '*' if p_volume < 0.05 else 'ns'}")
    
    # Volume CV t-test
    t_volcv, p_volcv = stats.ttest_ind(winners['Volume_CV'].dropna(), losers['Volume_CV'].dropna())
    print(f"Volume Consistency: t={t_volcv:.2f}, p={p_volcv:.4f} {'***' if p_volcv < 0.001 else '**' if p_volcv < 0.01 else '*' if p_volcv < 0.05 else 'ns'}")
    
    # Market cap t-test
    t_mc, p_mc = stats.ttest_ind(winners_mc, losers_mc)
    print(f"Market Cap: t={t_mc:.2f}, p={p_mc:.4f} {'***' if p_mc < 0.001 else '**' if p_mc < 0.01 else '*' if p_mc < 0.05 else 'ns'}")
    
    print(f"\n*** p<0.001, ** p<0.01, * p<0.05, ns = not significant")

def analyze_by_quartiles(metrics_df):
    """Analyze win rates by quartiles of price, volume, market cap"""
    
    print("\n" + "="*80)
    print("WIN RATE BY QUARTILES")
    print("="*80)
    
    # Price quartiles
    metrics_df['Price_Quartile'] = pd.qcut(metrics_df['Avg_Price'], q=4, labels=['Q1 (Low)', 'Q2', 'Q3', 'Q4 (High)'], duplicates='drop')
    price_qr = metrics_df.groupby('Price_Quartile').agg({
        'Winner': ['count', 'sum', 'mean'],
        'Future_Return': 'mean'
    }).round(3)
    
    print(f"\nBy Average Price Quartile:")
    print(price_qr)
    
    # Volume quartiles
    metrics_df['Volume_Quartile'] = pd.qcut(metrics_df['Avg_Volume'], q=4, labels=['Q1 (Low)', 'Q2', 'Q3', 'Q4 (High)'], duplicates='drop')
    volume_qr = metrics_df.groupby('Volume_Quartile').agg({
        'Winner': ['count', 'sum', 'mean'],
        'Future_Return': 'mean'
    }).round(3)
    
    print(f"\nBy Average Volume Quartile:")
    print(volume_qr)
    
    # Volatility quartiles
    metrics_df['Volatility_Quartile'] = pd.qcut(metrics_df['Price_Volatility_%'], q=4, labels=['Q1 (Low)', 'Q2', 'Q3', 'Q4 (High)'], duplicates='drop')
    vol_qr = metrics_df.groupby('Volatility_Quartile').agg({
        'Winner': ['count', 'sum', 'mean'],
        'Future_Return': 'mean'
    }).round(3)
    
    print(f"\nBy Price Volatility Quartile:")
    print(vol_qr)

def main():
    print("="*80)
    print("WINNERS vs LOSERS ANALYSIS - 250-DAY EVENTS")
    print("="*80)
    
    # Load events
    events = load_event_data()
    
    # Calculate metrics during clustering period
    metrics_df = calculate_clustering_period_metrics(events)
    
    # Save detailed metrics
    metrics_df.to_csv('winners_losers_metrics_250day.csv', index=False)
    print(f"\n✓ Saved detailed metrics to: winners_losers_metrics_250day.csv")
    
    # Compare winners vs losers
    compare_winners_vs_losers(metrics_df)
    
    # Analyze by quartiles
    analyze_by_quartiles(metrics_df)
    
    # Summary statistics
    print("\n" + "="*80)
    print("SUMMARY FINDINGS")
    print("="*80)
    
    winners = metrics_df[metrics_df['Winner'] == True]
    losers = metrics_df[metrics_df['Winner'] == False]
    
    print(f"\nKey Differences (Winners vs Losers):")
    
    price_diff_pct = (winners['Avg_Price'].median() - losers['Avg_Price'].median()) / losers['Avg_Price'].median() * 100
    print(f"  Price: {price_diff_pct:+.1f}% {'higher' if price_diff_pct > 0 else 'lower'} (median)")
    
    vol_diff_pct = (winners['Avg_Volume'].median() - losers['Avg_Volume'].median()) / losers['Avg_Volume'].median() * 100
    print(f"  Volume: {vol_diff_pct:+.1f}% {'higher' if vol_diff_pct > 0 else 'lower'} (median)")
    
    volat_diff = winners['Price_Volatility_%'].median() - losers['Price_Volatility_%'].median()
    print(f"  Volatility: {volat_diff:+.1f}% {'higher' if volat_diff > 0 else 'lower'} (median)")
    
    print("\n" + "="*80)
    print("✅ ANALYSIS COMPLETE")
    print("="*80)

if __name__ == '__main__':
    main()
