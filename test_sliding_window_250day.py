"""
Test Sliding Window Strategy with 250-Day Forward Window
========================================================

Combines:
1. Sliding window clustering with market cap integration
2. 250-day forward return window (instead of 500)
3. Comprehensive event detection and analysis

This addresses the missing clusters issue by:
- Running fresh clustering with proper data handling
- Using all available blocks and events
- Ensuring complete coverage of the analysis period
"""

import pandas as pd
import numpy as np
import os
import sys
from datetime import datetime

# Add testbed path
sys.path.insert(0, '/home/npallotta128/projects/testbed-analysis')

from optimize_dropout_strategy_safe import test_dropout_parameters

def run_sliding_window_250day(data_file='data.csv', output_prefix='sliding_window_250day'):
    """
    Run sliding window clustering with 250-day forward window
    
    Parameters:
    - block_size: 200 timepoints
    - num_blocks: 50 (more coverage than baseline 8)
    - stride: 50 (75% overlap between windows)
    - forward_window: 250 (new shorter window)
    - distance_threshold: 40 (hierarchical clustering threshold)
    - quality_metric: avg_return (cluster quality metric)
    - quality_threshold_percentile: 80 (top 20% clusters for signals)
    """
    
    print("="*80)
    print("SLIDING WINDOW STRATEGY WITH 250-DAY FORWARD WINDOW")
    print("="*80)
    print(f"\nParameters:")
    print(f"  Block Size: 200 timepoints")
    print(f"  Number of Blocks: 50 (enabling overlapping windows)")
    print(f"  Stride: 50 timepoints (75% overlap)")
    print(f"  Forward Window: 250 days ⭐ NEW")
    print(f"  Distance Threshold: 40 (hierarchical clustering)")
    print(f"  Quality Metric: Average Return")
    print(f"  Quality Threshold: 80th percentile")
    
    print(f"\nRunning clustering protocol...")
    
    # Run sliding window clustering with 250-day forward window
    result, loss_df, acq_df = test_dropout_parameters(
        data_file,
        block_size=200,
        num_blocks=50,
        distance_threshold=40,
        quality_metric='avg_return',
        quality_threshold_percentile=80,
        stride=50,
        forward_window=250  # ⭐ KEY CHANGE: Use 250-day window
    )
    
    # Add event type
    loss_df['Event_Type'] = 'DROP'
    acq_df['Event_Type'] = 'ACQ'
    
    # Combine
    events = pd.concat([loss_df, acq_df], ignore_index=True)
    
    # Sort by block for better analysis
    events = events.sort_values('Block')
    
    # Save events
    events_file = f'{output_prefix}_events.csv'
    events.to_csv(events_file, index=False)
    
    print(f"\n" + "="*80)
    print("EVENT DETECTION RESULTS")
    print("="*80)
    print(f"✓ Dropout events detected: {len(loss_df):,}")
    print(f"✓ Acquisition events detected: {len(acq_df):,}")
    print(f"✓ Total events: {len(events):,}")
    print(f"✓ Saved to: {events_file}")
    
    # Detailed statistics
    print(f"\n" + "="*80)
    print("DROPOUT EVENT STATISTICS (250-day window)")
    print("="*80)
    print(f"  Mean Return: {loss_df['Future_Return'].mean():+.2f}%")
    print(f"  Median Return: {loss_df['Future_Return'].median():+.2f}%")
    print(f"  Std Dev: {loss_df['Future_Return'].std():.2f}%")
    print(f"  Min Return: {loss_df['Future_Return'].min():+.2f}%")
    print(f"  Max Return: {loss_df['Future_Return'].max():+.2f}%")
    print(f"  Win Rate: {(loss_df['Future_Return'] > 0).mean() * 100:.1f}% ({(loss_df['Future_Return'] > 0).sum()}/{len(loss_df)})")
    
    print(f"\n" + "="*80)
    print("ACQUISITION EVENT STATISTICS (250-day window)")
    print("="*80)
    print(f"  Mean Return: {acq_df['Future_Return'].mean():+.2f}%")
    print(f"  Median Return: {acq_df['Future_Return'].median():+.2f}%")
    print(f"  Std Dev: {acq_df['Future_Return'].std():.2f}%")
    print(f"  Min Return: {acq_df['Future_Return'].min():+.2f}%")
    print(f"  Max Return: {acq_df['Future_Return'].max():+.2f}%")
    print(f"  Win Rate: {(acq_df['Future_Return'] > 0).mean() * 100:.1f}% ({(acq_df['Future_Return'] > 0).sum()}/{len(acq_df)})")
    
    # Combined statistics
    print(f"\n" + "="*80)
    print("COMBINED STATISTICS (All Events)")
    print("="*80)
    print(f"  Mean Return: {events['Future_Return'].mean():+.2f}%")
    print(f"  Median Return: {events['Future_Return'].median():+.2f}%")
    print(f"  Std Dev: {events['Future_Return'].std():.2f}%")
    print(f"  Overall Win Rate: {(events['Future_Return'] > 0).mean() * 100:.1f}%")
    
    # Distribution by block
    print(f"\n" + "="*80)
    print("EVENTS BY BLOCK (First 10 blocks)")
    print("="*80)
    block_summary = events.groupby('Block').agg({
        'Future_Return': ['count', 'mean', 'median', lambda x: (x > 0).mean() * 100]
    }).round(2)
    block_summary.columns = ['Count', 'Avg_Return', 'Median_Return', 'Win_Rate_%']
    print(block_summary.head(10))
    
    # Quality change statistics
    print(f"\n" + "="*80)
    print("QUALITY CHANGE ANALYSIS")
    print("="*80)
    # Check what columns are available
    quality_col = 'Quality_Loss' if 'Quality_Loss' in loss_df.columns else 'Prev_Quality'
    if quality_col in loss_df.columns:
        print(f"Dropout Events:")
        print(f"  Mean Quality Loss: {loss_df[quality_col].mean():.2f}")
        print(f"  Median Quality Loss: {loss_df[quality_col].median():.2f}")
    if quality_col in acq_df.columns:
        print(f"Acquisition Events:")
        print(f"  Mean Quality Gain: {acq_df[quality_col].mean():.2f}")
        print(f"  Median Quality Gain: {acq_df[quality_col].median():.2f}")
    
    # Save summary report
    summary_report = {
        'Metric': [
            'Total Events',
            'Dropout Events',
            'Acquisition Events',
            'Forward Window (days)',
            'Avg Return (All)',
            'Win Rate (All)',
            'Avg Return (Dropout)',
            'Win Rate (Dropout)',
            'Avg Return (Acq)',
            'Win Rate (Acq)',
            'Timestamp'
        ],
        'Value': [
            len(events),
            len(loss_df),
            len(acq_df),
            250,
            f"{events['Future_Return'].mean():.2f}%",
            f"{(events['Future_Return'] > 0).mean() * 100:.1f}%",
            f"{loss_df['Future_Return'].mean():.2f}%",
            f"{(loss_df['Future_Return'] > 0).mean() * 100:.1f}%",
            f"{acq_df['Future_Return'].mean():.2f}%",
            f"{(acq_df['Future_Return'] > 0).mean() * 100:.1f}%",
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ]
    }
    
    summary_df = pd.DataFrame(summary_report)
    summary_file = f'{output_prefix}_summary.csv'
    summary_df.to_csv(summary_file, index=False)
    print(f"\n✓ Summary saved to: {summary_file}")
    
    print(f"\n" + "="*80)
    print("✅ ANALYSIS COMPLETE")
    print("="*80)
    print(f"\nOutput Files:")
    print(f"  1. {events_file} - All detected events with returns")
    print(f"  2. {summary_file} - Summary statistics")
    
    return events, loss_df, acq_df

def compare_windows_250_vs_500():
    """Compare 250-day vs 500-day window results"""
    print("\n" + "="*80)
    print("COMPARING 250-DAY vs 500-DAY FORWARD WINDOWS")
    print("="*80)
    
    # Load existing 500-day results if available
    if os.path.exists('events_sliding_window.csv'):
        events_500 = pd.read_csv('events_sliding_window.csv')
        print(f"\n500-day window (existing data):")
        print(f"  Events: {len(events_500)}")
        print(f"  Mean Return: {events_500['Future_Return'].mean():.2f}%")
        print(f"  Win Rate: {(events_500['Future_Return'] > 0).mean() * 100:.1f}%")
    
    # Load new 250-day results
    if os.path.exists('sliding_window_250day_events.csv'):
        events_250 = pd.read_csv('sliding_window_250day_events.csv')
        print(f"\n250-day window (new analysis):")
        print(f"  Events: {len(events_250)}")
        print(f"  Mean Return: {events_250['Future_Return'].mean():.2f}%")
        print(f"  Win Rate: {(events_250['Future_Return'] > 0).mean() * 100:.1f}%")
        
        if os.path.exists('events_sliding_window.csv'):
            print(f"\nComparison:")
            delta_events = len(events_250) - len(events_500)
            delta_return = events_250['Future_Return'].mean() - events_500['Future_Return'].mean()
            delta_winrate = ((events_250['Future_Return'] > 0).mean() - (events_500['Future_Return'] > 0).mean()) * 100
            print(f"  Event count delta: {delta_events:+,} ({delta_events/len(events_500)*100:+.1f}%)")
            print(f"  Mean return delta: {delta_return:+.2f}%")
            print(f"  Win rate delta: {delta_winrate:+.1f}%")

if __name__ == '__main__':
    # Run sliding window strategy with 250-day forward window
    events, loss_df, acq_df = run_sliding_window_250day()
    
    # Compare with 500-day results
    compare_windows_250_vs_500()
    
    print("\n" + "="*80)
    print("✅ SLIDING WINDOW 250-DAY ANALYSIS COMPLETE")
    print("="*80)
