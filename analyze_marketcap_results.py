"""
Detailed Analysis of MarketCap Sliding Window Clustering Results

Analyzes the detected dropout and acquisition events with market cap context.
"""

import pandas as pd
import numpy as np
from pathlib import Path

def analyze_events_detailed():
    """Comprehensive analysis of generated events"""
    
    results_dir = Path('marketcap_pipeline_results')
    events_file = results_dir / 'marketcap_sliding_events.csv'
    data_file = results_dir / 'data_with_marketcap.csv'
    
    if not events_file.exists():
        print(f"❌ Events file not found: {events_file}")
        return
    
    print("\n" + "="*80)
    print("MARKETCAP SLIDING WINDOW CLUSTERING - DETAILED ANALYSIS")
    print("="*80)
    
    # Load events
    events = pd.read_csv(events_file)
    data = pd.read_csv(data_file)
    
    print(f"\n📊 DATASET OVERVIEW")
    print(f"  Total events detected: {len(events):,}")
    print(f"  Dropout events: {len(events[events['Event_Type']=='DROP']):,}")
    print(f"  Acquisition events: {len(events[events['Event_Type']=='ACQ']):,}")
    print(f"  Date range: {data['Date'].min()} to {data['Date'].max()}")
    print(f"  Unique symbols: {data['Symbol'].nunique()}")
    
    # Return analysis
    dropout = events[events['Event_Type'] == 'DROP'].copy()
    acq = events[events['Event_Type'] == 'ACQ'].copy()
    
    print(f"\n📈 DROPOUT EVENT ANALYSIS (n={len(dropout)})")
    print(f"  Returns (with data):")
    dropout_with_returns = dropout[dropout['Future_Return'].notna()]
    print(f"    Count: {len(dropout_with_returns):,}")
    print(f"    Mean: {dropout_with_returns['Future_Return'].mean():+.2f}%")
    print(f"    Median: {dropout_with_returns['Future_Return'].median():+.2f}%")
    print(f"    Std dev: {dropout_with_returns['Future_Return'].std():.2f}%")
    print(f"    Min: {dropout_with_returns['Future_Return'].min():.2f}%")
    print(f"    Max: {dropout_with_returns['Future_Return'].max():.2f}%")
    print(f"    Win rate: {(dropout_with_returns['Future_Return'] > 0).mean()*100:.1f}%")
    
    # Quartile analysis
    q1 = dropout_with_returns['Future_Return'].quantile(0.25)
    q3 = dropout_with_returns['Future_Return'].quantile(0.75)
    print(f"  Return distribution:")
    print(f"    Q1 (25%): {q1:+.2f}%")
    print(f"    Q3 (75%): {q3:+.2f}%")
    print(f"    IQR: {q3-q1:.2f}%")
    
    print(f"\n📊 ACQUISITION EVENT ANALYSIS (n={len(acq)})")
    print(f"  Returns (with data):")
    acq_with_returns = acq[acq['Future_Return'].notna()]
    print(f"    Count: {len(acq_with_returns):,}")
    print(f"    Mean: {acq_with_returns['Future_Return'].mean():+.2f}%")
    print(f"    Median: {acq_with_returns['Future_Return'].median():+.2f}%")
    print(f"    Std dev: {acq_with_returns['Future_Return'].std():.2f}%")
    print(f"    Min: {acq_with_returns['Future_Return'].min():.2f}%")
    print(f"    Max: {acq_with_returns['Future_Return'].max():.2f}%")
    print(f"    Win rate: {(acq_with_returns['Future_Return'] > 0).mean()*100:.1f}%")
    
    # Quartile analysis
    q1 = acq_with_returns['Future_Return'].quantile(0.25)
    q3 = acq_with_returns['Future_Return'].quantile(0.75)
    print(f"  Return distribution:")
    print(f"    Q1 (25%): {q1:+.2f}%")
    print(f"    Q3 (75%): {q3:+.2f}%")
    print(f"    IQR: {q3-q1:.2f}%")
    
    # Top performers
    print(f"\n⭐ TOP 10 DROPOUT PERFORMERS")
    top_dropout = dropout_with_returns.nlargest(10, 'Future_Return')[['Security', 'Future_Return', 'Quality_Loss']]
    for idx, row in top_dropout.iterrows():
        print(f"  {row['Security']:6s} - Return: {row['Future_Return']:+7.2f}%  Quality_Loss: {row['Quality_Loss']:7.1f}")
    
    print(f"\n⭐ TOP 10 ACQUISITION PERFORMERS")
    top_acq = acq_with_returns.nlargest(10, 'Future_Return')[['Security', 'Future_Return', 'Quality_Loss']]
    for idx, row in top_acq.iterrows():
        print(f"  {row['Security']:6s} - Return: {row['Future_Return']:+7.2f}%  Quality_Loss: {row['Quality_Loss']:7.1f}")
    
    # Worst performers
    print(f"\n💥 WORST 10 DROPOUT PERFORMERS")
    worst_dropout = dropout_with_returns.nsmallest(10, 'Future_Return')[['Security', 'Future_Return', 'Quality_Loss']]
    for idx, row in worst_dropout.iterrows():
        print(f"  {row['Security']:6s} - Return: {row['Future_Return']:+7.2f}%  Quality_Loss: {row['Quality_Loss']:7.1f}")
    
    print(f"\n💥 WORST 10 ACQUISITION PERFORMERS")
    worst_acq = acq_with_returns.nsmallest(10, 'Future_Return')[['Security', 'Future_Return', 'Quality_Loss']]
    for idx, row in worst_acq.iterrows():
        print(f"  {row['Security']:6s} - Return: {row['Future_Return']:+7.2f}%  Quality_Loss: {row['Quality_Loss']:7.1f}")
    
    # Quality Loss Analysis
    print(f"\n🔍 QUALITY LOSS ANALYSIS")
    print(f"  Dropout events:")
    print(f"    Mean Quality Loss: {dropout['Quality_Loss'].mean():7.2f}")
    print(f"    Median Quality Loss: {dropout['Quality_Loss'].median():7.2f}")
    print(f"    Min Quality Loss: {dropout['Quality_Loss'].min():7.2f}")
    print(f"    Max Quality Loss: {dropout['Quality_Loss'].max():7.2f}")
    
    print(f"  Acquisition events:")
    print(f"    Mean Quality Loss: {acq['Quality_Loss'].mean():7.2f}")
    print(f"    Median Quality Loss: {acq['Quality_Loss'].median():7.2f}")
    print(f"    Min Quality Loss: {acq['Quality_Loss'].min():7.2f}")
    print(f"    Max Quality Loss: {acq['Quality_Loss'].max():7.2f}")
    
    # Stock analysis
    print(f"\n📌 TOP 10 STOCKS BY EVENT COUNT")
    security_counts = events['Security'].value_counts().head(10)
    for stock, count in security_counts.items():
        avg_return = events[events['Security']==stock]['Future_Return'].mean()
        print(f"  {stock:8s} - Events: {count:4d}  Avg Return: {avg_return:+7.2f}%")
    
    # Market cap integration summary
    print(f"\n💰 MARKET CAP DATA INTEGRATION")
    mc_stats = data.groupby('Symbol')['MarketCap'].agg(['count', 'min', 'max', 'mean'])
    mc_stats.columns = ['records', 'min_cap', 'max_cap', 'mean_cap']
    mc_stats = mc_stats.sort_values('mean_cap', ascending=False).head(10)
    print(f"  Top 10 stocks by mean market cap:")
    for stock, row in mc_stats.iterrows():
        print(f"    {stock:8s} - Min: ${row['min_cap']/1e9:6.2f}B  Max: ${row['max_cap']/1e9:6.2f}B  Mean: ${row['mean_cap']/1e9:6.2f}B")
    
    print(f"\n" + "="*80)
    print("✅ ANALYSIS COMPLETE")
    print("="*80)

if __name__ == '__main__':
    analyze_events_detailed()
