"""
CLUSTER STRENGTHENING STRATEGY

Concept:
- When a high market cap stock joins a cluster → cluster is "strengthening"
- Hypothesis: Strengthened clusters outperform in forward period
- Measure: Compare cluster performance BEFORE and AFTER large-cap stock joins

Logic:
1. Each block: identify clusters
2. Between blocks: detect when large-cap stocks join/leave clusters
3. For events where large-cap joins cluster:
   - Measure cluster quality BEFORE event
   - Measure cluster quality AFTER event (next block)
   - Forward return: Calculate all stocks in cluster's returns over forward period
4. Test: Does joining large-cap predict cluster outperformance?
"""

import pandas as pd
import numpy as np
from collections import defaultdict
from pathlib import Path
import sys

sys.path.insert(0, '/home/npallotta128/projects/testbed-analysis')

from optimize_dropout_strategy_safe import (
    perform_zscore_normalization, perform_hierarchical_clustering,
    calculate_cluster_quality_scores
)


class ClusterStrengtheningStrategy:
    """Detect when clusters strengthen due to large-cap stock joining"""
    
    def __init__(self, data_file='data_with_marketcap.csv'):
        self.data_file = data_file
        self.df = None
        self.high_cap_stocks = None
        self.market_cap_percentiles = None
        
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
        """Select high market cap stocks"""
        print(f"\nSelecting high market cap stocks (>{cap_percentile}th percentile)...")
        
        # Calculate median market cap per symbol
        symbol_median_cap = self.df.groupby('Symbol')['MarketCap'].median()
        cap_threshold = symbol_median_cap.quantile(cap_percentile / 100)
        
        self.high_cap_stocks = symbol_median_cap[symbol_median_cap >= cap_threshold].index.tolist()
        self.market_cap_percentiles = symbol_median_cap
        
        print(f"  Market cap threshold: ${cap_threshold:,.0f}")
        print(f"  High cap stocks: {len(self.high_cap_stocks)}")
        print(f"  Top 5 by cap: {symbol_median_cap.nlargest(5).to_dict()}")
        
        return self.high_cap_stocks
    
    def perform_clustering_all_stocks(self, block_size=150, num_blocks=10, 
                                     distance_threshold=40):
        """
        Perform clustering on ALL stocks (not just high-cap)
        This gives us the full universe of clusters
        
        Returns:
            List of block results with cluster assignments for all stocks
        """
        print(f"\nPerforming clustering on ALL stocks (block_size={block_size}, num_blocks={num_blocks})...")
        
        data = self.df.sort_values('Date')
        unique_dates = data['Date'].unique()
        timepoints_needed = block_size * num_blocks
        
        if len(unique_dates) < timepoints_needed:
            num_blocks = len(unique_dates) // block_size
            if num_blocks < 1:
                raise ValueError("Not enough data for clustering")
        
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
            
            # Cluster on all available stocks
            pivot_data = block_data.pivot_table(
                index='Symbol',
                columns='Date',
                values='Closing',
                aggfunc='last'
            )
            
            if pivot_data.shape[0] < 3 or pivot_data.shape[1] < 3:
                continue
            
            securities = pivot_data.index.values
            
            # Normalize and cluster
            pivot_normalized, clean_securities = perform_zscore_normalization(
                pivot_data.values,
                securities
            )
            
            clusters, cluster_labels = perform_hierarchical_clustering(
                pivot_normalized,
                clean_securities,
                distance_threshold=distance_threshold
            )
            
            # Calculate cluster quality
            price_df_block = block_data.pivot_table(
                index='Date',
                columns='Symbol',
                values='Closing',
                aggfunc='last'
            )
            price_df_block = price_df_block[[s for s in clean_securities if s in price_df_block.columns]]
            
            cluster_quality, cluster_returns = calculate_cluster_quality_scores(
                clusters,
                price_df_block,
                clean_securities,
                quality_metric='avg_return'
            )
            
            # Build symbol -> cluster mapping
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
                'cluster_members': clusters,  # For getting all members per cluster
            }
            all_results.append(result)
        
        print(f"  Completed {len(all_results)} blocks")
        return all_results
    
    def detect_large_cap_cluster_entries(self, block_results):
        """
        Detect when large-cap stocks join clusters between blocks
        
        Returns:
            List of events where large-cap stock joins a cluster
        """
        print(f"\nDetecting large-cap stock cluster entries...")
        
        events = []
        
        # Track each symbol's cluster membership over time
        symbol_history = defaultdict(list)
        
        for result in block_results:
            for symbol, cluster_id in result['clusters'].items():
                quality = result['cluster_quality'].get(cluster_id, 0)
                symbol_history[symbol].append({
                    'block': result['block_id'],
                    'date': result['date_end'],
                    'cluster_id': cluster_id,
                    'quality': quality,
                    'result': result  # Keep reference to full result
                })
        
        # Look for large-cap stocks changing clusters
        for symbol in symbol_history:
            if symbol not in self.high_cap_stocks:
                continue  # Only care about large-cap movements
            
            history = symbol_history[symbol]
            if len(history) < 2:
                continue
            
            symbol_market_cap = self.market_cap_percentiles.get(symbol, 0)
            
            for i in range(1, len(history)):
                prev = history[i-1]
                curr = history[i]
                
                prev_cluster = prev['cluster_id']
                curr_cluster = curr['cluster_id']
                
                # Event: cluster changed (large-cap stock joining new cluster)
                if prev_cluster != curr_cluster:
                    prev_quality = prev['quality']
                    curr_quality = curr['quality']
                    quality_change = curr_quality - prev_quality
                    
                    # We care about JOIN events (moving to different cluster)
                    events.append({
                        'Security': symbol,
                        'Market_Cap': symbol_market_cap,
                        'Block': curr['block'],
                        'Date': curr['date'],
                        'From_Cluster': prev_cluster,
                        'To_Cluster': curr_cluster,
                        'From_Cluster_Quality': prev_quality,
                        'To_Cluster_Quality': curr_quality,
                        'Quality_Change': quality_change,
                        'Event_Type': 'CLUSTER_JOIN',
                        'Prev_Result': prev['result'],
                        'Curr_Result': curr['result']
                    })
        
        events_df = pd.DataFrame(events)
        print(f"  Detected {len(events_df)} large-cap cluster transitions")
        
        return events_df
    
    def measure_cluster_outperformance(self, events_df, block_results):
        """
        For each event where large-cap stock joins cluster:
        - Get all members of the NEW cluster (in next block)
        - EXCLUDE the triggering large-cap stock
        - Measure OTHER cluster members' collective performance in forward window
        - This tests: does the cluster strengthen beyond just the large-cap's own performance?
        
        Returns:
            events_df with cluster future returns (excluding the triggering stock)
        """
        print(f"\nMeasuring cluster outperformance (excluding triggering large-cap stock)...")
        
        cluster_future_returns = []
        cluster_future_returns_with_stock = []  # For comparison
        
        for idx, event in events_df.iterrows():
            block_id = event['Block']
            new_cluster = event['To_Cluster']
            triggering_stock = event['Security']
            
            # Get the current block result
            curr_result = event['Curr_Result']
            cluster_members = curr_result['cluster_members'].get(new_cluster, [])
            
            # Exclude the triggering large-cap stock
            other_members = [m for m in cluster_members if m != triggering_stock]
            
            if len(other_members) < 1:
                cluster_future_returns.append(np.nan)
                cluster_future_returns_with_stock.append(np.nan)
                continue
            
            # Get price data for cluster members in forward window
            # Forward window = next 500 trading days
            forward_start_date = event['Date']
            
            # Get all data after event
            future_data = self.df[self.df['Date'] > forward_start_date].copy()
            future_data = future_data.sort_values('Date')
            
            if len(future_data) == 0:
                cluster_future_returns.append(np.nan)
                cluster_future_returns_with_stock.append(np.nan)
                continue
            
            unique_dates = future_data['Date'].unique()
            if len(unique_dates) < 250:  # Need at least ~1 year
                cluster_future_returns.append(np.nan)
                cluster_future_returns_with_stock.append(np.nan)
                continue
            
            # Take first 500 timepoints (or all available)
            forward_end_idx = min(500, len(unique_dates))
            forward_end_date = unique_dates[forward_end_idx - 1]
            
            # Get returns for OTHER cluster members (excluding triggering stock)
            other_member_returns = []
            for member in other_members:
                member_data = future_data[
                    (future_data['Symbol'] == member) &
                    (future_data['Date'] <= forward_end_date)
                ].sort_values('Date')
                
                if len(member_data) < 2:
                    continue
                
                start_price = member_data.iloc[0]['Closing']
                end_price = member_data.iloc[-1]['Closing']
                
                if start_price > 0:
                    ret = ((end_price - start_price) / start_price) * 100
                    other_member_returns.append(ret)
            
            # Also calculate with the triggering stock (for comparison)
            all_member_returns = []
            for member in cluster_members:
                member_data = future_data[
                    (future_data['Symbol'] == member) &
                    (future_data['Date'] <= forward_end_date)
                ].sort_values('Date')
                
                if len(member_data) < 2:
                    continue
                
                start_price = member_data.iloc[0]['Closing']
                end_price = member_data.iloc[-1]['Closing']
                
                if start_price > 0:
                    ret = ((end_price - start_price) / start_price) * 100
                    all_member_returns.append(ret)
            
            if len(other_member_returns) > 0:
                # Cluster's average return over forward period (excluding triggering stock)
                cluster_avg_return = np.mean(other_member_returns)
                cluster_future_returns.append(cluster_avg_return)
            else:
                cluster_future_returns.append(np.nan)
            
            if len(all_member_returns) > 0:
                cluster_avg_return_with = np.mean(all_member_returns)
                cluster_future_returns_with_stock.append(cluster_avg_return_with)
            else:
                cluster_future_returns_with_stock.append(np.nan)
        
        events_df['Cluster_Future_Return'] = cluster_future_returns
        events_df['Cluster_Future_Return_With_Stock'] = cluster_future_returns_with_stock
        
        valid_without = len([r for r in cluster_future_returns if not np.isnan(r)])
        print(f"  Calculated cluster returns (excluding triggering stock): {valid_without}/{len(cluster_future_returns)} events")
        
        return events_df
    
    def analyze_results(self, events_df):
        """Analyze cluster strengthening events"""
        
        if len(events_df) == 0:
            print("No events to analyze")
            return
        
        events_with_returns = events_df[events_df['Cluster_Future_Return'].notna()].copy()
        
        if len(events_with_returns) == 0:
            print("No events with return data")
            return
        
        print("\n" + "="*80)
        print("CLUSTER STRENGTHENING ANALYSIS")
        print("="*80)
        
        print(f"\n📊 OVERALL STATISTICS ({len(events_with_returns)} events)")
        print(f"  Cluster avg future return: {events_with_returns['Cluster_Future_Return'].mean():+.2f}%")
        print(f"  Median: {events_with_returns['Cluster_Future_Return'].median():+.2f}%")
        print(f"  Std dev: {events_with_returns['Cluster_Future_Return'].std():.2f}%")
        print(f"  Win rate (positive): {(events_with_returns['Cluster_Future_Return'] > 0).mean()*100:.1f}%")
        print(f"  Sharpe ratio: {events_with_returns['Cluster_Future_Return'].mean() / (events_with_returns['Cluster_Future_Return'].std() + 1e-6):.3f}")
        
        # By stock
        print(f"\n💼 BY SECURITY (cluster performance when this large-cap joined)")
        stock_stats = events_with_returns.groupby('Security').agg({
            'Cluster_Future_Return': ['count', 'mean', 'median'],
            'Market_Cap': 'first'
        }).round(2)
        stock_stats.columns = ['Count', 'Avg_Return', 'Median_Return', 'Market_Cap']
        stock_stats = stock_stats.sort_values('Avg_Return', ascending=False)
        
        for idx, row in stock_stats.iterrows():
            cap_str = f"${row['Market_Cap']/1e9:.1f}B" if row['Market_Cap'] > 0 else "N/A"
            print(f"  {idx:10} Count={int(row['Count']):2}  Mean={row['Avg_Return']:+7.2f}%  "
                  f"Median={row['Median_Return']:+7.2f}%  Cap={cap_str}")
        
        # Quality change analysis
        print(f"\n🔄 QUALITY CHANGE ANALYSIS")
        print(f"  Avg quality change (stock movement): {events_with_returns['Quality_Change'].mean():+.2f}")
        
        # Correlation
        corr = events_with_returns['Quality_Change'].corr(events_with_returns['Cluster_Future_Return'])
        print(f"  Correlation (quality change vs cluster return): {corr:.3f}")
        
        print(f"\n✅ KEY INSIGHT")
        if events_with_returns['Cluster_Future_Return'].mean() > 0:
            print(f"  ✓ Clusters strengthened by large-cap joins OUTPERFORMED")
            print(f"    Avg cluster return: {events_with_returns['Cluster_Future_Return'].mean():+.2f}%")
        else:
            print(f"  ✗ Clusters strengthened by large-cap joins UNDERPERFORMED")
            print(f"    Avg cluster return: {events_with_returns['Cluster_Future_Return'].mean():+.2f}%")
        
        return events_with_returns
    
    def save_results(self, events_df, output_file='cluster_strengthening_events.csv'):
        """Save events to CSV"""
        if len(events_df) > 0:
            # Remove 'result' columns (not serializable)
            save_df = events_df.drop(columns=['Prev_Result', 'Curr_Result'], errors='ignore')
            save_df.to_csv(output_file, index=False)
            print(f"\n✅ Saved {len(save_df)} events to {output_file}")
        return output_file


def main():
    """Run cluster strengthening strategy"""
    
    print("="*80)
    print("CLUSTER STRENGTHENING STRATEGY")
    print("When large-cap stocks join clusters → does cluster outperform?")
    print("="*80)
    
    # Initialize
    strategy = ClusterStrengtheningStrategy(data_file='data_with_marketcap.csv')
    
    # Load data
    strategy.load_data_with_marketcap()
    
    # Select high-cap universe
    strategy.select_high_cap_stocks(cap_percentile=70)
    
    # Cluster all stocks (not just high-cap)
    block_results = strategy.perform_clustering_all_stocks(
        block_size=150,
        num_blocks=10,
        distance_threshold=40
    )
    
    # Detect when large-cap stocks join clusters
    events_df = strategy.detect_large_cap_cluster_entries(block_results)
    
    if len(events_df) > 0:
        # Measure cluster future performance
        events_df = strategy.measure_cluster_outperformance(events_df, block_results)
        
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
