"""
Analyze Winners vs Losers from 250-Day Events
==============================================

Compare characteristics during the clustering timeframe:
- Volume (ADV)
- Price level
- Market cap
- Volatility
"""

import pandas as pd
import numpy as np
from optimize_dropout_strategy_safe import load_data_once

def analyze_winners_vs_losers():
    """
    Load 250-day events and compare winners vs losers
    """
    
    print("="*80)
    print("WINNERS vs LOSERS ANALYSIS (250-DAY EVENTS)")
    print("="*80)
    
    # Load events
    print("\nLoading 250-day events...")
    events = pd.read_csv('events_sliding_window_250day_recalc.csv')
    
    # Separate winners and losers
    winners = events[events['Future_Return'] > 0]
    losers = events[events['Future_Return'] <= 0]
    
    print(f"Total events: {len(events):,}")
    print(f"Winners: {len(winners):,} ({len(winners)/len(events)*100:.1f}%)")
    print(f"Losers: {len(losers):,} ({len(losers)/len(events)*100:.1f}%)")
    
    # Load price data
    print("\nLoading price data...")
    _, closing_table = load_data_once('data.csv')
    volume_data = pd.read_csv('data.csv')
    
    print(f"Data loaded: {len(closing_table)} timepoints, {len(closing_table.columns)} securities")
    
    # Get volume info
    print("\nExtracting volume data...")
    volume_pivot = volume_data.pivot_table(
        index='Date', 
        columns='Symbol', 
        values='Volume', 
        aggfunc='first'
    )
    print(f"Volume pivot: {len(volume_pivot)} dates, {len(volume_pivot.columns)} securities")
    
    # Analyze characteristics at block time
    print("\n" + "="*80)
    print("EXTRACTING CHARACTERISTICS AT BLOCK TIME")
    print("="*80)
    
    characteristics = []
    
    for idx, event in events.iterrows():
        if idx % 20000 == 0:
            print(f"Progress: {idx:,}/{len(events):,}")
        
        security = event['Security']
        block = event['Block']
        future_return = event['Future_Return']
        
        # Reconstruct block end timepoint
        block_size = 200
        stride = 50
        block_start = block * stride
        block_end = min(block_start + block_size, len(closing_table) - 1)
        
        # Get security data at block end
        if security not in closing_table.columns:
            continue
        
        price_series = closing_table[security]
        
        # Get price at block end
        if pd.isna(price_series.iloc[block_end]):
            continue
        price_at_block = price_series.iloc[block_end]
        
        # Calculate volatility in the block (std of returns)
        block_prices = price_series.iloc[max(0, block_start):block_end+1]
        if len(block_prices) > 1:
            block_returns = block_prices.pct_change().dropna()
            volatility = block_returns.std() * 100 if len(block_returns) > 0 else np.nan
        else:
            volatility = np.nan
        
        # Get average volume in block (approximate)
        try:
            block_volume = volume_data[volume_data['Symbol'] == security]['Volume'].mean()
        except:
            block_volume = np.nan
        
        characteristics.append({
            'Security': security,
            'Block': block,
            'Future_Return': future_return,
            'Price_At_Block': price_at_block,
            'Volatility_%': volatility,
            'Avg_Volume': block_volume,
            'Event_Type': event['Event_Type'],
            'Winner': future_return > 0
        })
    
    char_df = pd.DataFrame(characteristics)
    char_df = char_df.dropna()
    
    print(f"\n✓ Extracted characteristics for {len(char_df):,} events")
    
    # Split into winners and losers
    winners_char = char_df[char_df['Winner'] == True]
    losers_char = char_df[char_df['Winner'] == False]
    
    print("\n" + "="*80)
    print("PRICE CHARACTERISTICS")
    print("="*80)
    
    print(f"\nWinners (Price at Block Time):")
    print(f"  Mean: ${winners_char['Price_At_Block'].mean():.2f}")
    print(f"  Median: ${winners_char['Price_At_Block'].median():.2f}")
    print(f"  Std Dev: ${winners_char['Price_At_Block'].std():.2f}")
    print(f"  Min: ${winners_char['Price_At_Block'].min():.2f}")
    print(f"  Max: ${winners_char['Price_At_Block'].max():.2f}")
    
    print(f"\nLosers (Price at Block Time):")
    print(f"  Mean: ${losers_char['Price_At_Block'].mean():.2f}")
    print(f"  Median: ${losers_char['Price_At_Block'].median():.2f}")
    print(f"  Std Dev: ${losers_char['Price_At_Block'].std():.2f}")
    print(f"  Min: ${losers_char['Price_At_Block'].min():.2f}")
    print(f"  Max: ${losers_char['Price_At_Block'].max():.2f}")
    
    print(f"\nDifference:")
    price_diff = winners_char['Price_At_Block'].mean() - losers_char['Price_At_Block'].mean()
    print(f"  Mean Price: {price_diff:+.2f} ({price_diff/losers_char['Price_At_Block'].mean()*100:+.1f}%)")
    
    print("\n" + "="*80)
    print("VOLUME CHARACTERISTICS")
    print("="*80)
    
    print(f"\nWinners (Average Volume):")
    print(f"  Mean: {winners_char['Avg_Volume'].mean():,.0f}")
    print(f"  Median: {winners_char['Avg_Volume'].median():,.0f}")
    print(f"  Std Dev: {winners_char['Avg_Volume'].std():,.0f}")
    print(f"  Min: {winners_char['Avg_Volume'].min():,.0f}")
    print(f"  Max: {winners_char['Avg_Volume'].max():,.0f}")
    
    print(f"\nLosers (Average Volume):")
    print(f"  Mean: {losers_char['Avg_Volume'].mean():,.0f}")
    print(f"  Median: {losers_char['Avg_Volume'].median():,.0f}")
    print(f"  Std Dev: {losers_char['Avg_Volume'].std():,.0f}")
    print(f"  Min: {losers_char['Avg_Volume'].min():,.0f}")
    print(f"  Max: {losers_char['Avg_Volume'].max():,.0f}")
    
    print(f"\nDifference:")
    volume_diff = winners_char['Avg_Volume'].mean() - losers_char['Avg_Volume'].mean()
    volume_pct = volume_diff / losers_char['Avg_Volume'].mean() * 100
    print(f"  Mean Volume: {volume_diff:+,.0f} ({volume_pct:+.1f}%)")
    
    print("\n" + "="*80)
    print("VOLATILITY CHARACTERISTICS")
    print("="*80)
    
    print(f"\nWinners (Volatility during Block):")
    print(f"  Mean: {winners_char['Volatility_%'].mean():.3f}%")
    print(f"  Median: {winners_char['Volatility_%'].median():.3f}%")
    print(f"  Std Dev: {winners_char['Volatility_%'].std():.3f}%")
    
    print(f"\nLosers (Volatility during Block):")
    print(f"  Mean: {losers_char['Volatility_%'].mean():.3f}%")
    print(f"  Median: {losers_char['Volatility_%'].median():.3f}%")
    print(f"  Std Dev: {losers_char['Volatility_%'].std():.3f}%")
    
    print(f"\nDifference:")
    vol_diff = winners_char['Volatility_%'].mean() - losers_char['Volatility_%'].mean()
    print(f"  Mean Volatility: {vol_diff:+.3f}%")
    
    # By event type
    print("\n" + "="*80)
    print("ANALYSIS BY EVENT TYPE")
    print("="*80)
    
    for event_type in ['DROP', 'ACQ']:
        winners_type = winners_char[winners_char['Event_Type'] == event_type]
        losers_type = losers_char[losers_char['Event_Type'] == event_type]
        
        if len(winners_type) == 0 or len(losers_type) == 0:
            continue
        
        print(f"\n{event_type} Events:")
        print(f"  Winners: {len(winners_type):,}")
        print(f"  Losers: {len(losers_type):,}")
        print(f"  Winner Avg Price: ${winners_type['Price_At_Block'].mean():.2f}")
        print(f"  Loser Avg Price: ${losers_type['Price_At_Block'].mean():.2f}")
        print(f"  Winner Avg Volume: {winners_type['Avg_Volume'].mean():,.0f}")
        print(f"  Loser Avg Volume: {losers_type['Avg_Volume'].mean():,.0f}")
        print(f"  Winner Avg Volatility: {winners_type['Volatility_%'].mean():.3f}%")
        print(f"  Loser Avg Volatility: {losers_type['Volatility_%'].mean():.3f}%")
    
    # Save detailed comparison
    char_df.to_csv('winners_vs_losers_250day.csv', index=False)
    print(f"\n✓ Saved detailed data to: winners_vs_losers_250day.csv")
    
    # Statistical test
    print("\n" + "="*80)
    print("STATISTICAL SIGNIFICANCE")
    print("="*80)
    
    from scipy import stats
    
    # Price comparison
    t_stat, p_value = stats.ttest_ind(
        winners_char['Price_At_Block'].dropna(),
        losers_char['Price_At_Block'].dropna()
    )
    print(f"\nPrice (t-test):")
    print(f"  t-statistic: {t_stat:.4f}")
    print(f"  p-value: {p_value:.6f}")
    print(f"  Significant: {'YES ✓' if p_value < 0.05 else 'NO'}")
    
    # Volume comparison
    t_stat_vol, p_value_vol = stats.ttest_ind(
        winners_char['Avg_Volume'].dropna(),
        losers_char['Avg_Volume'].dropna()
    )
    print(f"\nVolume (t-test):")
    print(f"  t-statistic: {t_stat_vol:.4f}")
    print(f"  p-value: {p_value_vol:.6f}")
    print(f"  Significant: {'YES ✓' if p_value_vol < 0.05 else 'NO'}")
    
    # Volatility comparison
    t_stat_vol_pct, p_value_vol_pct = stats.ttest_ind(
        winners_char['Volatility_%'].dropna(),
        losers_char['Volatility_%'].dropna()
    )
    print(f"\nVolatility (t-test):")
    print(f"  t-statistic: {t_stat_vol_pct:.4f}")
    print(f"  p-value: {p_value_vol_pct:.6f}")
    print(f"  Significant: {'YES ✓' if p_value_vol_pct < 0.05 else 'NO'}")
    
    print("\n" + "="*80)
    print("✅ ANALYSIS COMPLETE")
    print("="*80)

if __name__ == '__main__':
    analyze_winners_vs_losers()
