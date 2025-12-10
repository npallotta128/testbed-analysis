"""
Integrate MarketCap and MarketValues data from D drive and apply Sliding Window Clustering + Dropout Protocol

This script:
1. Loads MarketCAPValues (outstanding shares) and MarketValues (OHLCV data) from D drive
2. Calculates market capitalization (shares * closing price)
3. Creates a consolidated dataset with market cap information
4. Applies sliding window clustering and dropout detection protocol
5. Generates dropout/acquisition events with market cap metrics

Outstanding Shares Dates: Quarterly (Mar 31, Jun 30, Sep 30, Dec 31)
Price Data Dates: Daily (2015-08-10 to 2025-11-28)
Strategy: Forward-fill shares data to approximate market cap on non-reporting dates
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import sys
from pathlib import Path

# Add testbed path
sys.path.insert(0, '/home/npallotta128/projects/testbed-analysis')

from optimize_dropout_strategy_safe import (
    load_data_once, perform_zscore_normalization, perform_hierarchical_clustering,
    calculate_cluster_quality_scores, test_dropout_parameters
)

class MarketCapIntegrator:
    """Integrate market cap data with price data and prepare for clustering"""
    
    def __init__(self, market_cap_file, market_values_file):
        """
        Args:
            market_cap_file: Path to MarketCAPValues.csv (outstanding shares)
            market_values_file: Path to MarketValues.csv (OHLCV data)
        """
        self.market_cap_file = market_cap_file
        self.market_values_file = market_values_file
        self.market_cap_df = None
        self.market_values_df = None
        self.consolidated_df = None
        
    def load_market_cap_data(self):
        """Load outstanding shares data with date approximation"""
        print("Loading MarketCAPValues.csv (outstanding shares)...")
        df = pd.read_csv(self.market_cap_file)
        
        # Parse dates
        df['Date'] = pd.to_datetime(df['Date'])
        df['OutstandingShares'] = pd.to_numeric(df['OutstandingShares'], errors='coerce')
        
        # Remove rows with zero or null shares
        df = df[(df['OutstandingShares'] > 0) & (df['OutstandingShares'].notna())].copy()
        
        print(f"  Loaded {len(df)} outstanding share records")
        print(f"  Date range: {df['Date'].min()} to {df['Date'].max()}")
        print(f"  Unique symbols: {df['Symbol'].nunique()}")
        
        self.market_cap_df = df.sort_values(['Symbol', 'Date'])
        return self.market_cap_df
    
    def load_market_values_data(self, sample_frac=None, nrows=None):
        """Load price data"""
        print("\nLoading MarketValues.csv (daily prices)...")
        
        if nrows is not None:
            # For testing, load only first N rows
            df = pd.read_csv(self.market_values_file, nrows=nrows)
            print(f"  Loaded FIRST {len(df)} price records (nrows={nrows})")
        elif sample_frac is not None:
            # For testing, sample a fraction
            df = pd.read_csv(self.market_values_file)
            df = df.sample(frac=sample_frac, random_state=42)
            print(f"  Loaded SAMPLE of {len(df)} price records ({sample_frac*100:.1f}%)")
        else:
            df = pd.read_csv(self.market_values_file)
            print(f"  Loaded {len(df)} price records")
        
        # Parse dates and filter out dummy data
        df['Date'] = pd.to_datetime(df['Date'])
        df = df[df['Symbol'] != 'Lenny'].copy()  # Remove dummy record
        
        # Parse numeric columns
        df['Closing'] = pd.to_numeric(df['Closing'], errors='coerce')
        df['Volume'] = pd.to_numeric(df['Volume'], errors='coerce')
        
        # Filter valid price data
        df = df[(df['Closing'] > 0) & (df['Closing'].notna())].copy()
        
        print(f"  After cleaning: {len(df)} records")
        print(f"  Date range: {df['Date'].min()} to {df['Date'].max()}")
        print(f"  Unique symbols: {df['Symbol'].nunique()}")
        
        self.market_values_df = df.sort_values(['Symbol', 'Date'])
        return self.market_values_df
    
    def approximate_shares_on_price_dates(self):
        """
        Efficiently forward-fill outstanding shares to daily price dates using merge_asof.
        For each daily price date, find the most recent shares date <= that date.
        """
        print("\nApproximating outstanding shares on daily price dates...")
        
        # Sort both datasets by Symbol and Date
        market_cap_sorted = self.market_cap_df[['Symbol', 'Date', 'OutstandingShares']].copy()
        market_cap_sorted = market_cap_sorted.sort_values(['Symbol', 'Date']).drop_duplicates(['Symbol', 'Date'], keep='last')
        
        market_values_sorted = self.market_values_df[['Symbol', 'Date', 'Closing']].copy()
        market_values_sorted = market_values_sorted.sort_values(['Symbol', 'Date'])
        
        # Use merge_asof for fast forward-fill by Symbol
        # merge_asof requires both dataframes to be sorted on the by column
        try:
            merged = pd.merge_asof(
                market_values_sorted,
                market_cap_sorted,
                on='Date',
                by='Symbol',
                direction='backward'  # Find most recent date <= price date
            )
        except ValueError as e:
            print(f"  merge_asof encountered sorting issue: {e}")
            print(f"  Falling back to simpler merge strategy...")
            
            # Fallback: use regular merge with groupby to find most recent
            merged = market_values_sorted.merge(
                market_cap_sorted,
                on=['Symbol', 'Date'],
                how='left'
            )
            
            # For missing shares, use group by forward-fill
            for symbol in merged['Symbol'].unique():
                mask = merged['Symbol'] == symbol
                merged.loc[mask, 'OutstandingShares'] = \
                    merged.loc[mask, 'OutstandingShares'].fillna(method='ffill').fillna(method='bfill')
        
        # Merge back to original with all columns
        merge_cols = ['Symbol', 'Date', 'OutstandingShares']
        if 'Closing' not in merged.columns:
            merged = merged.merge(market_values_sorted, on=['Symbol', 'Date'], how='left')
        
        # Get all original columns except those we're replacing
        keep_cols = [c for c in self.market_values_df.columns if c not in ['OutstandingShares']]
        self.market_values_df = self.market_values_df[keep_cols].merge(
            merged[['Symbol', 'Date', 'OutstandingShares']],
            on=['Symbol', 'Date'],
            how='left'
        )
        
        # Forward-fill within each symbol for any remaining missing values
        self.market_values_df['OutstandingShares'] = \
            self.market_values_df.groupby('Symbol')['OutstandingShares'].fillna(method='ffill')
        
        # Calculate market cap (shares * closing price)
        self.market_values_df['MarketCap'] = \
            self.market_values_df['OutstandingShares'] * self.market_values_df['Closing']
        
        # Filter rows with valid market cap
        self.market_values_df = self.market_values_df[self.market_values_df['MarketCap'].notna()].copy()
        
        print(f"  Approximated market cap for {len(self.market_values_df)} price records")
        print(f"  Symbols with market cap: {self.market_values_df['Symbol'].nunique()}")
        
        return self.market_values_df
    
    def create_consolidated_dataset(self, output_file='data_with_marketcap.csv'):
        """Create consolidated dataset with market cap for clustering"""
        print(f"\nCreating consolidated dataset: {output_file}")
        
        self.consolidated_df = self.market_values_df[[
            'Symbol', 'Date', 'Closing', 'Volume', 'Opening', 'High', 'Low',
            'OutstandingShares', 'MarketCap'
        ]].copy()
        
        self.consolidated_df = self.consolidated_df.sort_values(['Date', 'Symbol'])
        self.consolidated_df.to_csv(output_file, index=False)
        
        print(f"  Saved {len(self.consolidated_df)} records to {output_file}")
        print(f"  Date range: {self.consolidated_df['Date'].min()} to {self.consolidated_df['Date'].max()}")
        print(f"  Unique symbols: {self.consolidated_df['Symbol'].nunique()}")
        
        return output_file

def convert_to_compatible_format(consolidated_file, output_file='data.csv'):
    """
    Convert consolidated file to the exact format expected by optimize_dropout_strategy_safe.py
    Format: Date, Symbol, Closing, Volume (and other OHLCV)
    """
    print(f"\nConverting to compatible format: {output_file}")
    
    df = pd.read_csv(consolidated_file)
    
    # Ensure columns match expected format
    output_df = df[[
        'Symbol', 'Date', 'Closing', 'Volume', 'Opening', 'High', 'Low'
    ]].copy()
    
    # Rename for compatibility
    output_df.columns = ['Symbol', 'Date', 'Closing', 'Volume', 'Opening', 'High', 'Low']
    
    output_df.to_csv(output_file, index=False)
    print(f"  Saved {len(output_df)} records to {output_file}")
    
    return output_file

def apply_sliding_window_clustering(data_file, output_prefix='marketcap_sliding'):
    """Apply sliding window clustering protocol"""
    print(f"\nApplying sliding window clustering protocol...")
    
    # Parameters matching existing sliding window approach
    result, loss_df, acq_df = test_dropout_parameters(
        data_file,
        block_size=200,
        num_blocks=50,
        distance_threshold=40,
        quality_metric='avg_return',
        quality_threshold_percentile=80,
        stride=50,
        forward_window=500
    )
    
    # Add event type
    loss_df['Event_Type'] = 'DROP'
    acq_df['Event_Type'] = 'ACQ'
    
    # Combine
    events = pd.concat([loss_df, acq_df], ignore_index=True)
    
    # Save
    events_file = f'{output_prefix}_events.csv'
    events.to_csv(events_file, index=False)
    
    print(f"\nSliding Window Clustering Results:")
    print(f"  Dropout events: {len(loss_df)}")
    print(f"  Acquisition events: {len(acq_df)}")
    print(f"  Total events: {len(events)}")
    print(f"  Saved to: {events_file}")
    
    print(f"\nDropout Event Statistics:")
    print(f"  Mean return: {loss_df['Future_Return'].mean():.2f}%")
    print(f"  Median return: {loss_df['Future_Return'].median():.2f}%")
    print(f"  Std dev: {loss_df['Future_Return'].std():.2f}%")
    print(f"  Positive %: {(loss_df['Future_Return'] > 0).mean() * 100:.1f}%")
    
    print(f"\nAcquisition Event Statistics:")
    print(f"  Mean return: {acq_df['Future_Return'].mean():.2f}%")
    print(f"  Median return: {acq_df['Future_Return'].median():.2f}%")
    print(f"  Std dev: {acq_df['Future_Return'].std():.2f}%")
    print(f"  Positive %: {(acq_df['Future_Return'] > 0).mean() * 100:.1f}%")
    
    return events, loss_df, acq_df, events_file

def main(use_sample=False, nrows=None):
    """Main pipeline
    
    Args:
        use_sample: If True, use 10% sample
        nrows: If specified, load only first N rows (supersedes use_sample)
    """
    print("="*80)
    print("MARKETCAP + SLIDING WINDOW CLUSTERING + DROPOUT PROTOCOL")
    print("="*80)
    
    market_cap_file = '/mnt/d/MarketCAPValues.csv'
    market_values_file = '/mnt/d/MarketValues.csv'
    
    # Check files exist
    if not os.path.exists(market_cap_file):
        print(f"ERROR: {market_cap_file} not found")
        return
    if not os.path.exists(market_values_file):
        print(f"ERROR: {market_values_file} not found")
        return
    
    # Initialize integrator
    integrator = MarketCapIntegrator(market_cap_file, market_values_file)
    
    # Step 1: Load data
    integrator.load_market_cap_data()
    if nrows:
        integrator.load_market_values_data(nrows=nrows)
    else:
        integrator.load_market_values_data(sample_frac=0.1 if use_sample else None)
    
    # Step 2: Approximate shares on price dates
    integrator.approximate_shares_on_price_dates()
    
    # Step 3: Create consolidated dataset
    consolidated_file = integrator.create_consolidated_dataset(
        output_file='data_with_marketcap.csv'
    )
    
    # Step 4: Convert to compatible format
    compatible_file = convert_to_compatible_format(
        consolidated_file,
        output_file='data_marketcap_prepared.csv'
    )
    
    # Step 5: Apply sliding window clustering
    events, loss_df, acq_df, events_file = apply_sliding_window_clustering(
        compatible_file,
        output_prefix='marketcap_sliding'
    )
    
    print("\n" + "="*80)
    print("PIPELINE COMPLETE")
    print("="*80)
    print(f"Output files:")
    print(f"  - data_with_marketcap.csv (consolidated with market cap)")
    print(f"  - data_marketcap_prepared.csv (compatible format for clustering)")
    print(f"  - marketcap_sliding_events.csv (dropout & acquisition events)")
    print("="*80)

if __name__ == '__main__':
    import sys
    use_sample = '--sample' in sys.argv
    nrows = None
    
    # Check for --nrows argument
    for i, arg in enumerate(sys.argv):
        if arg == '--nrows' and i + 1 < len(sys.argv):
            try:
                nrows = int(sys.argv[i + 1])
            except ValueError:
                pass
    
    if nrows:
        print(f"\n[NOTE] Running with first {nrows:,} rows. Use --nrows N for different size.\n")
    elif use_sample:
        print("\n[NOTE] Running with 10% sample for testing. Remove --sample for full data.\n")
    
    main(use_sample=use_sample, nrows=nrows)
