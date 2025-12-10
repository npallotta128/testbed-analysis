"""
HIGH MARKET CAP CLUSTER TRANSITION STRATEGY

Strategy Overview:
- Use sliding window clustering on price data
- Focus ONLY on high market cap stocks (e.g., top 20-30% by market cap)
- Detect cluster transitions as signals:
  * SELL: High cap stock drops to lower cluster quality
  * BUY: High cap stock moves to higher cluster quality
  
Rationale:
- High cap stocks are more liquid and predictable
- Their cluster transitions may indicate broader market moves
- Reduced noise from micro-cap volatility
"""

import pandas as pd
import numpy as np
from pathlib import Path
from collections import defaultdict
import sys
import json

sys.path.insert(0, '/home/npallotta128/projects/testbed-analysis')

from optimize_dropout_strategy_safe import (
    load_data_once, perform_zscore_normalization, perform_hierarchical_clustering,
    calculate_cluster_quality_scores
)


class HighMarketCapClusterStrategy:
    """Strategy focused on high market cap stock cluster transitions"""
    
    def __init__(self, data_file='data_with_marketcap.csv'):
        """
        Args:
            data_file: CSV with columns: Symbol, Date, Closing, Volume, MarketCap
        """
        self.data_file = data_file
        self.df = None
        self.market_cap_percentiles = None
        self.high_cap_stocks = None
        self.events = []
        
    def load_data_with_marketcap(self):
        """Load consolidated data with market cap"""
        print("Loading data with market cap...")
        self.df = pd.read_csv(self.data_file)
        self.df['Date'] = pd.to_datetime(self.df['Date'])
        self.df['Closing'] = pd.to_numeric(self.df['Closing'], errors='coerce')
        self.df['MarketCap'] = pd.to_numeric(self.df['MarketCap'], errors='coerce')
        
        # Remove invalid rows
        self.df = self.df.dropna(subset=['Closing', 'MarketCap'])
        self.df = self.df[self.df['MarketCap'] > 0]
        
        print(f"  Loaded {len(self.df)} records")
        print(f"  Date range: {self.df['Date'].min()} to {self.df['Date'].max()}")
        print(f"  Unique symbols: {self.df['Symbol'].nunique()}")
        
        return self.df
    
    def select_high_cap_stocks(self, cap_percentile=70):
        """
        Select stocks in top market cap percentile
        
        Args:
            cap_percentile: Use stocks above this percentile (70 = top 30%)
        
        Returns:
            DataFrame filtered to high cap stocks only
        """
        print(f"\nSelecting high market cap stocks (>{cap_percentile}th percentile)...")
        
        # Calculate median market cap per symbol across all dates
        symbol_median_cap = self.df.groupby('Symbol')['MarketCap'].median()
        
        # Get percentile threshold
        cap_threshold = symbol_median_cap.quantile(cap_percentile / 100)
        
        # Filter
        self.high_cap_stocks = symbol_median_cap[symbol_median_cap >= cap_threshold].index.tolist()
        self.market_cap_percentiles = symbol_median_cap
        
        print(f"  Market cap threshold: ${cap_threshold:,.0f}")
        print(f"  High cap stocks: {len(self.high_cap_stocks)}")
        print(f"  Top 10 by cap: {symbol_median_cap.nlargest(10).to_dict()}")
        
        # Filter data
        df_high_cap = self.df[self.df['Symbol'].isin(self.high_cap_stocks)].copy()
        print(f"  Records: {len(self.df)} → {len(df_high_cap)}")
        
        return df_high_cap
    
    def perform_clustering(self, data=None, block_size=150, num_blocks=10, 
                          distance_threshold=40):
        """
        Perform sliding window clustering on high cap stocks
        
        Args:
            data: DataFrame to cluster (uses filtered high-cap data if None)
            block_size: Timepoints per block
            num_blocks: Number of blocks
            distance_threshold: Clustering distance threshold
            
        Returns:
            List of block results with cluster assignments
        """
        if data is None:
            if self.high_cap_stocks is None:
                raise ValueError("Call select_high_cap_stocks() first")
            data = self.df[self.df['Symbol'].isin(self.high_cap_stocks)].copy()
        
        print(f"\nPerforming clustering (block_size={block_size}, num_blocks={num_blocks})...")
        
        # Sort by date
        data = data.sort_values('Date')
        
        # Get unique dates and limit to num_blocks worth
        unique_dates = data['Date'].unique()
        timepoints_needed = block_size * num_blocks
        
        if len(unique_dates) < timepoints_needed:
            print(f"  ⚠️  Only {len(unique_dates)} dates available, need {timepoints_needed}")
            num_blocks = len(unique_dates) // block_size
            if num_blocks < 1:
                raise ValueError("Not enough data for clustering")
        
        # Select date range
        end_date = unique_dates[timepoints_needed - 1]
        data = data[data['Date'] <= end_date].copy()
        
        all_results = []
        
        for block_id in range(num_blocks):
            start_idx = block_id * block_size
            end_idx = start_idx + block_size
            
            block_dates = unique_dates[start_idx:end_idx]
            block_data = data[data['Date'].isin(block_dates)].copy()
            
            if len(block_data) == 0:
                continue
            
            print(f"  Block {block_id}: {block_dates[0].date()} to {block_dates[-1].date()}")
            
            # Prepare for clustering: Symbol x Features
            pivot_data = block_data.pivot_table(
                index='Symbol', 
                columns='Date',
                values='Closing',
                aggfunc='last'
            )
            
            if pivot_data.shape[0] < 3 or pivot_data.shape[1] < 3:
                continue
            
            securities = pivot_data.index.values
            
            # Z-score normalize
            pivot_normalized, clean_securities = perform_zscore_normalization(
                pivot_data.values, 
                securities
            )
            
            # Hierarchical clustering
            clusters, cluster_labels = perform_hierarchical_clustering(
                pivot_normalized,
                clean_securities,
                distance_threshold=distance_threshold
            )
            
            # Calculate quality scores
            # Need to pass a price DataFrame with securities as columns
            price_df_block = block_data.pivot_table(
                index='Date',
                columns='Symbol',
                values='Closing',
                aggfunc='last'
            )
            # Filter to only clean securities
            price_df_block = price_df_block[[s for s in clean_securities if s in price_df_block.columns]]
            
            cluster_quality, cluster_returns = calculate_cluster_quality_scores(
                clusters, 
                price_df_block,
                clean_securities,
                quality_metric='avg_return'
            )
            
            # Build reverse mapping: symbol -> cluster_id
            symbol_to_cluster = {}
            for cluster_id, security_list in clusters.items():
                for security in security_list:
                    symbol_to_cluster[security] = cluster_id
            
            result = {
                'block_id': block_id,
                'date_start': block_dates[0],
                'date_end': block_dates[-1],
                'clusters': symbol_to_cluster,
                'cluster_quality': cluster_quality,
                'symbols_in_block': list(symbol_to_cluster.keys())
            }
            all_results.append(result)
        
        print(f"  Completed {len(all_results)} blocks")
        return all_results
    
    def detect_transitions(self, block_results, quality_threshold_percentile=75, 
                           min_quality_change=5):
        """
        Detect high cap stock cluster transitions
        
        Args:
            block_results: List of block clustering results
            quality_threshold_percentile: What counts as "high quality" cluster
            min_quality_change: Minimum change to trigger event
            
        Returns:
            DataFrame of detected transitions
        """
        print(f"\nDetecting cluster transitions...")
        
        transitions = []
        
        # Track each stock's cluster history
        security_history = defaultdict(list)
        
        for result in block_results:
            for symbol, cluster_id in result['clusters'].items():
                quality = result['cluster_quality'].get(cluster_id, 0)
                security_history[symbol].append({
                    'block': result['block_id'],
                    'date': result['date_end'],
                    'cluster_id': cluster_id,
                    'quality': quality
                })
        
        # Determine quality threshold
        all_qualities = []
        for result in block_results:
            all_qualities.extend(result['cluster_quality'].values())
        
        if len(all_qualities) == 0:
            print("  No quality scores available")
            return pd.DataFrame()
        
        quality_threshold = np.percentile(all_qualities, quality_threshold_percentile)
        print(f"  Quality threshold ({quality_threshold_percentile}th %ile): {quality_threshold:.2f}")
        
        # Detect transitions for high cap stocks only
        for symbol in security_history:
            if symbol not in self.high_cap_stocks:
                continue
            
            history = security_history[symbol]
            if len(history) < 2:
                continue
            
            symbol_market_cap = self.market_cap_percentiles.get(symbol, 0)
            
            for i in range(1, len(history)):
                prev = history[i - 1]
                curr = history[i]
                
                prev_quality = prev['quality']
                curr_quality = curr['quality']
                quality_change = curr_quality - prev_quality
                
                # Loss event: was in high quality, moved to lower
                if (prev_quality >= quality_threshold and 
                    curr_quality < prev_quality and 
                    abs(quality_change) >= min_quality_change):
                    
                    transitions.append({
                        'Security': symbol,
                        'Market_Cap': symbol_market_cap,
                        'Block': curr['block'],
                        'Date': curr['date'],
                        'Prev_Cluster_Quality': prev_quality,
                        'New_Cluster_Quality': curr_quality,
                        'Quality_Change': quality_change,
                        'Event_Type': 'LOSS',  # Stock leaving high quality cluster
                        'Signal': 'SELL'
                    })
                
                # Gain event: moved to higher quality
                elif (curr_quality > prev_quality and 
                      curr_quality >= quality_threshold and
                      quality_change >= min_quality_change):
                    
                    transitions.append({
                        'Security': symbol,
                        'Market_Cap': symbol_market_cap,
                        'Block': curr['block'],
                        'Date': curr['date'],
                        'Prev_Cluster_Quality': prev_quality,
                        'New_Cluster_Quality': curr_quality,
                        'Quality_Change': quality_change,
                        'Event_Type': 'GAIN',  # Stock joining high quality cluster
                        'Signal': 'BUY'
                    })
        
        events_df = pd.DataFrame(transitions)
        print(f"  Detected {len(events_df)} transitions")
        
        if len(events_df) > 0:
            print(f"    SELL (Loss): {len(events_df[events_df['Signal'] == 'SELL'])}")
            print(f"    BUY (Gain): {len(events_df[events_df['Signal'] == 'BUY'])}")
        
        self.events = events_df
        return events_df
    
    def calculate_post_event_returns(self, events_df, forward_periods=500):
        """
        Calculate future returns after each event
        
        Args:
            events_df: DataFrame of detected events
            forward_periods: Number of days to look ahead
            
        Returns:
            events_df with Future_Return column
        """
        if len(events_df) == 0:
            return events_df
        
        print(f"\nCalculating post-event returns ({forward_periods} periods ahead)...")
        
        # Get pivot of price data
        data = self.df[self.df['Symbol'].isin(self.high_cap_stocks)].copy()
        data = data.sort_values(['Symbol', 'Date'])
        
        # Create price lookup
        price_lookup = {}
        for symbol in data['Symbol'].unique():
            symbol_data = data[data['Symbol'] == symbol].sort_values('Date')
            price_lookup[symbol] = dict(zip(
                symbol_data['Date'],
                symbol_data['Closing']
            ))
        
        returns = []
        for idx, row in events_df.iterrows():
            symbol = row['Security']
            event_date = row['Date']
            
            if symbol not in price_lookup:
                returns.append(np.nan)
                continue
            
            prices = price_lookup[symbol]
            dates = sorted(prices.keys())
            
            try:
                event_date_idx = dates.index(event_date)
            except ValueError:
                returns.append(np.nan)
                continue
            
            # Calculate return over forward window
            forward_idx = event_date_idx + forward_periods
            
            if forward_idx < len(dates):
                start_price = prices[dates[event_date_idx]]
                end_price = prices[dates[forward_idx]]
                ret = ((end_price - start_price) / start_price) * 100
            else:
                # Use whatever data is available
                if forward_idx >= len(dates):
                    end_price = prices[dates[-1]]
                    start_price = prices[dates[event_date_idx]]
                    ret = ((end_price - start_price) / start_price) * 100
                else:
                    ret = np.nan
            
            returns.append(ret)
        
        events_df['Future_Return'] = returns
        
        print(f"  Calculated returns for {len([r for r in returns if not np.isnan(r)])}/{len(returns)} events")
        
        return events_df
    
    def analyze_results(self, events_df):
        """Print analysis of detected events and their returns"""
        if len(events_df) == 0:
            print("No events to analyze")
            return
        
        print("\n" + "="*80)
        print("HIGH MARKET CAP CLUSTER TRANSITION STRATEGY - ANALYSIS")
        print("="*80)
        
        events_with_returns = events_df[events_df['Future_Return'].notna()].copy()
        
        if len(events_with_returns) == 0:
            print("No events with return data")
            return
        
        print(f"\n📊 OVERALL STATISTICS ({len(events_with_returns)} events)")
        print(f"  Average return: {events_with_returns['Future_Return'].mean():+.2f}%")
        print(f"  Median return: {events_with_returns['Future_Return'].median():+.2f}%")
        print(f"  Std dev: {events_with_returns['Future_Return'].std():.2f}%")
        print(f"  Win rate: {(events_with_returns['Future_Return'] > 0).mean()*100:.1f}%")
        print(f"  Sharpe ratio: {events_with_returns['Future_Return'].mean() / (events_with_returns['Future_Return'].std() + 1e-6):.3f}")
        
        # By signal type
        print(f"\n📈 BY SIGNAL TYPE")
        for signal in ['BUY', 'SELL']:
            subset = events_with_returns[events_with_returns['Signal'] == signal]
            if len(subset) > 0:
                print(f"\n  {signal} Signals ({len(subset)} events):")
                print(f"    Avg return: {subset['Future_Return'].mean():+.2f}%")
                print(f"    Win rate: {(subset['Future_Return'] > 0).mean()*100:.1f}%")
                
                # Expected value for trading
                if signal == 'SELL':
                    # For shorts, we want negative returns
                    short_return = -subset['Future_Return'].mean()
                    print(f"    Expected short return: {short_return:+.2f}%")
                else:
                    print(f"    Expected long return: {subset['Future_Return'].mean():+.2f}%")
        
        # Top performers by quality change
        print(f"\n⭐ TOP 10 EVENTS (by quality change)")
        top_events = events_with_returns.nlargest(10, 'Quality_Change')[
            ['Security', 'Signal', 'Quality_Change', 'Future_Return', 'Market_Cap']
        ]
        for idx, row in top_events.iterrows():
            print(f"  {row['Security']:8} {row['Signal']:6} ΔQ={row['Quality_Change']:+6.2f}  Return={row['Future_Return']:+7.2f}%  Cap=${row['Market_Cap']:,.0f}")
        
        return events_with_returns
    
    def save_results(self, events_df, output_file='high_cap_cluster_events.csv'):
        """Save detected events to CSV"""
        if len(events_df) > 0:
            events_df.to_csv(output_file, index=False)
            print(f"\n✅ Saved {len(events_df)} events to {output_file}")
        return output_file


def main():
    """Run the high market cap cluster strategy"""
    
    print("="*80)
    print("HIGH MARKET CAP CLUSTER TRANSITION STRATEGY")
    print("="*80)
    
    # Initialize
    strategy = HighMarketCapClusterStrategy(data_file='data_with_marketcap.csv')
    
    # Load data
    strategy.load_data_with_marketcap()
    
    # Select high market cap stocks (top 30%)
    df_high_cap = strategy.select_high_cap_stocks(cap_percentile=70)
    
    # Clustering parameters
    block_size = 150
    num_blocks = 10
    distance_threshold = 40
    
    # Perform clustering
    block_results = strategy.perform_clustering(
        data=df_high_cap,
        block_size=block_size,
        num_blocks=num_blocks,
        distance_threshold=distance_threshold
    )
    
    # Detect transitions
    events_df = strategy.detect_transitions(
        block_results,
        quality_threshold_percentile=75,
        min_quality_change=5
    )
    
    if len(events_df) > 0:
        # Calculate post-event returns
        events_df = strategy.calculate_post_event_returns(events_df, forward_periods=500)
        
        # Analyze
        strategy.analyze_results(events_df)
        
        # Save
        strategy.save_results(events_df)
    
    print("\n" + "="*80)
    print("✅ Complete")
    print("="*80)
    
    return strategy, events_df


if __name__ == '__main__':
    strategy, events = main()
