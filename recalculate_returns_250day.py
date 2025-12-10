"""
Recalculate Forward Returns for Existing Events with 250-Day Window
====================================================================

This script:
1. Loads the existing events from the 500-day window analysis
2. Keeps the SAME events (same clustering, same dropout detection)
3. Only recalculates the forward returns using a 250-day window instead of 500

This ensures an apples-to-apples comparison where ONLY the holding period changes.
"""

import pandas as pd
import numpy as np
from optimize_dropout_strategy_safe import load_data_once

def recalculate_forward_returns(events_file='events_sliding_window.csv', 
                                 data_file='data.csv',
                                 forward_window=250,
                                 output_file='events_sliding_window_250day_recalc.csv'):
    """
    Recalculate forward returns for existing events using a different window
    
    Args:
        events_file: Path to existing events CSV (with 500-day returns)
        data_file: Path to price data CSV
        forward_window: New forward window size (e.g., 250 days)
        output_file: Where to save recalculated events
    """
    
    print("="*80)
    print(f"RECALCULATING FORWARD RETURNS WITH {forward_window}-DAY WINDOW")
    print("="*80)
    
    # Load existing events
    print(f"\nLoading existing events from {events_file}...")
    events = pd.read_csv(events_file)
    original_count = len(events)
    print(f"  Loaded {original_count:,} events")
    
    # Load price data
    print(f"\nLoading price data from {data_file}...")
    _, closing_table = load_data_once(data_file)
    print(f"  Loaded {len(closing_table)} timepoints, {len(closing_table.columns)} securities")
    
    # Recalculate forward returns
    print(f"\nRecalculating forward returns with {forward_window}-day window...")
    new_returns = []
    events_kept = []
    
    total_timepoints = len(closing_table)
    
    for idx, event in events.iterrows():
        if idx % 10000 == 0:
            print(f"  Progress: {idx:,}/{original_count:,} ({idx/original_count*100:.1f}%)")
        
        security = event['Security']
        block = event['Block']
        
        # Find the block end timepoint (need to reconstruct from block number and stride)
        # Original parameters: block_size=200, stride=50
        block_size = 200
        stride = 50
        block_start = block * stride
        block_end = block_start + block_size
        
        # Check if we have enough data for the new forward window
        if block_end + forward_window > total_timepoints:
            # Skip this event - not enough data
            continue
        
        # Get security's price series
        if security not in closing_table.columns:
            continue
            
        price_series = closing_table[security]
        
        # Calculate forward return
        start_price = price_series.iloc[block_end]
        end_idx = min(block_end + forward_window, total_timepoints - 1)
        end_price = price_series.iloc[end_idx]
        
        if pd.isna(start_price) or pd.isna(end_price) or start_price <= 0:
            forward_return = 0.0
        else:
            forward_return = ((end_price - start_price) / start_price) * 100
        
        new_returns.append(forward_return)
        events_kept.append(idx)
    
    print(f"  Complete!")
    
    # Update events with new returns
    events_recalc = events.loc[events_kept].copy()
    events_recalc['Future_Return'] = new_returns
    events_recalc['Forward_Window'] = forward_window
    
    # Save
    events_recalc.to_csv(output_file, index=False)
    
    print(f"\n" + "="*80)
    print("RECALCULATION RESULTS")
    print("="*80)
    print(f"  Original events (500-day window): {original_count:,}")
    print(f"  Events kept (enough data for {forward_window}-day): {len(events_recalc):,}")
    print(f"  Events dropped (insufficient data): {original_count - len(events_recalc):,}")
    print(f"  Saved to: {output_file}")
    
    # Statistics
    print(f"\n" + "="*80)
    print(f"STATISTICS WITH {forward_window}-DAY WINDOW")
    print("="*80)
    
    dropout_df = events_recalc[events_recalc['Event_Type'] == 'DROP']
    acq_df = events_recalc[events_recalc['Event_Type'] == 'ACQ']
    
    print(f"\nAll Events:")
    print(f"  Count: {len(events_recalc):,}")
    print(f"  Mean Return: {events_recalc['Future_Return'].mean():+.2f}%")
    print(f"  Median Return: {events_recalc['Future_Return'].median():+.2f}%")
    print(f"  Std Dev: {events_recalc['Future_Return'].std():.2f}%")
    print(f"  Win Rate: {(events_recalc['Future_Return'] > 0).mean() * 100:.1f}%")
    
    print(f"\nDropout Events:")
    print(f"  Count: {len(dropout_df):,}")
    print(f"  Mean Return: {dropout_df['Future_Return'].mean():+.2f}%")
    print(f"  Median Return: {dropout_df['Future_Return'].median():+.2f}%")
    print(f"  Win Rate: {(dropout_df['Future_Return'] > 0).mean() * 100:.1f}%")
    
    print(f"\nAcquisition Events:")
    print(f"  Count: {len(acq_df):,}")
    print(f"  Mean Return: {acq_df['Future_Return'].mean():+.2f}%")
    print(f"  Median Return: {acq_df['Future_Return'].median():+.2f}%")
    print(f"  Win Rate: {(acq_df['Future_Return'] > 0).mean() * 100:.1f}%")
    
    return events_recalc

def compare_250_vs_500():
    """Compare results between 250-day and 500-day windows"""
    
    print("\n" + "="*80)
    print("COMPARISON: 250-DAY vs 500-DAY FORWARD WINDOWS")
    print("="*80)
    
    # Load original 500-day events
    events_500 = pd.read_csv('events_sliding_window.csv')
    
    # Load recalculated 250-day events
    events_250 = pd.read_csv('events_sliding_window_250day_recalc.csv')
    
    # Note: events_250 may have fewer events due to data availability
    # Only compare the events that exist in both
    
    print(f"\n500-Day Window (Original):")
    print(f"  Events: {len(events_500):,}")
    print(f"  Mean Return: {events_500['Future_Return'].mean():+.2f}%")
    print(f"  Median Return: {events_500['Future_Return'].median():+.2f}%")
    print(f"  Win Rate: {(events_500['Future_Return'] > 0).mean() * 100:.1f}%")
    
    print(f"\n250-Day Window (Recalculated):")
    print(f"  Events: {len(events_250):,}")
    print(f"  Mean Return: {events_250['Future_Return'].mean():+.2f}%")
    print(f"  Median Return: {events_250['Future_Return'].median():+.2f}%")
    print(f"  Win Rate: {(events_250['Future_Return'] > 0).mean() * 100:.1f}%")
    
    print(f"\nKey Insight:")
    print(f"  Same events, different holding periods.")
    print(f"  250-day window has {len(events_500) - len(events_250):,} fewer events")
    print(f"  (those events occurred too late in the data to calculate 250-day returns)")

if __name__ == '__main__':
    # Recalculate returns with 250-day window
    events_250 = recalculate_forward_returns(
        events_file='events_sliding_window.csv',
        data_file='data.csv',
        forward_window=250,
        output_file='events_sliding_window_250day_recalc.csv'
    )
    
    # Compare results
    compare_250_vs_500()
    
    print("\n" + "="*80)
    print("✅ RECALCULATION COMPLETE")
    print("="*80)
