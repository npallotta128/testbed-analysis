"""
Optimize Sliding Window for Large Cap Acquisitions with Cluster Distance
=========================================================================

Focus on:
1. Large cap stocks (market cap filters)
2. Acquisition events (ACQ) only
3. Cluster distance as a signal quality metric
4. Optimize parameters for maximum win rate

Tests different:
- Distance thresholds (tighter clusters = more similar stocks)
- Market cap tiers
- Quality thresholds
- Block sizes
"""

import pandas as pd
import numpy as np
from optimize_dropout_strategy_safe import test_dropout_parameters
import time

def test_large_cap_acquisitions(
    data_file='data.csv',
    market_cap_file='data_with_marketcap.csv',
    distance_thresholds=[30, 35, 40, 45, 50],
    quality_percentiles=[75, 80, 85, 90],
    marketcap_min=2e9,  # $2B minimum
    marketcap_max=100e9,  # $100B maximum
    block_size=200,
    stride=50,
    num_blocks=50,
    forward_window=250
):
    """
    Test different configurations for large cap acquisition events
    
    Args:
        distance_thresholds: Clustering distance thresholds to test
        quality_percentiles: Quality threshold percentiles
        marketcap_min: Minimum market cap for filtering
        marketcap_max: Maximum market cap for filtering
    """
    
    print("="*80)
    print("LARGE CAP ACQUISITION OPTIMIZATION")
    print("="*80)
    print(f"\nConfiguration:")
    print(f"  Market Cap Range: ${marketcap_min/1e9:.1f}B - ${marketcap_max/1e9:.1f}B")
    print(f"  Block Size: {block_size}")
    print(f"  Stride: {stride}")
    print(f"  Forward Window: {forward_window} days")
    print(f"  Distance Thresholds: {distance_thresholds}")
    print(f"  Quality Percentiles: {quality_percentiles}")
    
    # Load market cap data for filtering
    print(f"\nLoading market cap data...")
    try:
        mc_data = pd.read_csv(market_cap_file)
        mc_data['Date'] = pd.to_datetime(mc_data['Date'])
        
        # Calculate average market cap per symbol
        symbol_avg_mc = mc_data.groupby('Symbol')['MarketCap'].mean()
        
        # Filter to large caps only
        large_cap_symbols = symbol_avg_mc[
            (symbol_avg_mc >= marketcap_min) & 
            (symbol_avg_mc <= marketcap_max)
        ].index.tolist()
        
        print(f"  Found {len(large_cap_symbols)} large cap symbols")
        print(f"  Sample symbols: {large_cap_symbols[:10]}")
        
        # Create market cap DataFrame for the optimizer
        mc_df = mc_data[['Symbol', 'Date', 'MarketCap']].copy()
        mc_df.columns = ['Symbol', 'Date', 'MarketCap']
        
    except Exception as e:
        print(f"  ⚠ Could not load market cap data: {e}")
        print(f"  Will run without market cap filtering")
        mc_df = None
        large_cap_symbols = None
    
    # Test all parameter combinations
    total_tests = len(distance_thresholds) * len(quality_percentiles)
    test_num = 0
    
    print(f"\nRunning {total_tests} parameter combinations...")
    print("="*80)
    
    results = []
    
    for dist_thresh in distance_thresholds:
        for qual_pct in quality_percentiles:
            test_num += 1
            
            print(f"\n[{test_num}/{total_tests}] Testing: distance={dist_thresh}, quality={qual_pct}%")
            print("-" * 80)
            
            start_time = time.time()
            
            # Run clustering with these parameters
            try:
                result, loss_df, acq_df = test_dropout_parameters(
                    data_file,
                    block_size=block_size,
                    num_blocks=num_blocks,
                    distance_threshold=dist_thresh,
                    quality_metric='avg_return',
                    quality_threshold_percentile=qual_pct,
                    stride=stride,
                    forward_window=forward_window,
                    market_caps_df=mc_df
                )
                
                # Filter to large caps if we have that data
                if large_cap_symbols is not None:
                    acq_df_filtered = acq_df[acq_df['Security'].isin(large_cap_symbols)]
                else:
                    acq_df_filtered = acq_df
                
                # Calculate metrics
                n_events = len(acq_df_filtered)
                
                if n_events > 0:
                    mean_return = acq_df_filtered['Future_Return'].mean()
                    median_return = acq_df_filtered['Future_Return'].median()
                    win_rate = (acq_df_filtered['Future_Return'] > 0).mean() * 100
                    std_return = acq_df_filtered['Future_Return'].std()
                    
                    # Additional quality metrics
                    top_10pct = acq_df_filtered['Future_Return'].quantile(0.90)
                    bottom_10pct = acq_df_filtered['Future_Return'].quantile(0.10)
                    
                    # Sharpe-like ratio
                    sharpe = mean_return / std_return if std_return > 0 else 0
                else:
                    mean_return = median_return = win_rate = std_return = 0
                    top_10pct = bottom_10pct = sharpe = 0
                
                elapsed = time.time() - start_time
                
                print(f"  ✓ Complete in {elapsed:.1f}s")
                print(f"  Events: {n_events:,}")
                print(f"  Win Rate: {win_rate:.1f}%")
                print(f"  Mean Return: {mean_return:+.2f}%")
                print(f"  Median Return: {median_return:+.2f}%")
                
                results.append({
                    'Distance_Threshold': dist_thresh,
                    'Quality_Percentile': qual_pct,
                    'Num_Events': n_events,
                    'Win_Rate_%': win_rate,
                    'Mean_Return_%': mean_return,
                    'Median_Return_%': median_return,
                    'Std_Return_%': std_return,
                    'Sharpe_Ratio': sharpe,
                    'Top_10pct_%': top_10pct,
                    'Bottom_10pct_%': bottom_10pct,
                    'Runtime_Sec': elapsed
                })
                
            except Exception as e:
                print(f"  ✗ Error: {e}")
                elapsed = time.time() - start_time
                results.append({
                    'Distance_Threshold': dist_thresh,
                    'Quality_Percentile': qual_pct,
                    'Num_Events': 0,
                    'Win_Rate_%': 0,
                    'Mean_Return_%': 0,
                    'Median_Return_%': 0,
                    'Std_Return_%': 0,
                    'Sharpe_Ratio': 0,
                    'Top_10pct_%': 0,
                    'Bottom_10pct_%': 0,
                    'Runtime_Sec': elapsed
                })
    
    # Convert to DataFrame
    results_df = pd.DataFrame(results)
    
    # Save results
    results_df.to_csv('large_cap_acq_optimization.csv', index=False)
    
    print("\n" + "="*80)
    print("OPTIMIZATION RESULTS")
    print("="*80)
    
    # Sort by win rate
    results_df = results_df.sort_values('Win_Rate_%', ascending=False)
    
    print("\nTop 10 Configurations by Win Rate:")
    print(results_df.head(10)[['Distance_Threshold', 'Quality_Percentile', 
                                 'Num_Events', 'Win_Rate_%', 'Mean_Return_%', 
                                 'Median_Return_%']].to_string(index=False))
    
    print("\n" + "="*80)
    print("Best Configuration:")
    print("="*80)
    best = results_df.iloc[0]
    print(f"  Distance Threshold: {best['Distance_Threshold']}")
    print(f"  Quality Percentile: {best['Quality_Percentile']}%")
    print(f"  Number of Events: {best['Num_Events']:,.0f}")
    print(f"  Win Rate: {best['Win_Rate_%']:.1f}% ⭐")
    print(f"  Mean Return: {best['Mean_Return_%']:+.2f}%")
    print(f"  Median Return: {best['Median_Return_%']:+.2f}%")
    print(f"  Sharpe Ratio: {best['Sharpe_Ratio']:.4f}")
    print(f"  Top 10% Returns: {best['Top_10pct_%']:+.2f}%")
    print(f"  Bottom 10% Returns: {best['Bottom_10pct_%']:+.2f}%")
    
    # Analysis by parameter
    print("\n" + "="*80)
    print("PARAMETER SENSITIVITY")
    print("="*80)
    
    print("\nBy Distance Threshold:")
    dist_summary = results_df.groupby('Distance_Threshold').agg({
        'Win_Rate_%': 'mean',
        'Mean_Return_%': 'mean',
        'Num_Events': 'mean'
    }).round(2)
    print(dist_summary)
    
    print("\nBy Quality Percentile:")
    qual_summary = results_df.groupby('Quality_Percentile').agg({
        'Win_Rate_%': 'mean',
        'Mean_Return_%': 'mean',
        'Num_Events': 'mean'
    }).round(2)
    print(qual_summary)
    
    # Save best configuration for use
    best_config = {
        'distance_threshold': best['Distance_Threshold'],
        'quality_percentile': best['Quality_Percentile'],
        'win_rate': best['Win_Rate_%'],
        'mean_return': best['Mean_Return_%']
    }
    
    print(f"\n✓ Results saved to: large_cap_acq_optimization.csv")
    
    return results_df, best_config

def generate_events_with_best_config(best_config, data_file='data.csv'):
    """Generate events using the best configuration"""
    
    print("\n" + "="*80)
    print("GENERATING EVENTS WITH BEST CONFIGURATION")
    print("="*80)
    
    print(f"\nUsing optimal parameters:")
    print(f"  Distance Threshold: {best_config['distance_threshold']}")
    print(f"  Quality Percentile: {best_config['quality_percentile']}%")
    
    # Load market cap data
    try:
        mc_data = pd.read_csv('data_with_marketcap.csv')
        mc_data['Date'] = pd.to_datetime(mc_data['Date'])
        mc_df = mc_data[['Symbol', 'Date', 'MarketCap']].copy()
        mc_df.columns = ['Symbol', 'Date', 'MarketCap']
    except:
        mc_df = None
    
    # Generate events
    result, loss_df, acq_df = test_dropout_parameters(
        data_file,
        block_size=200,
        num_blocks=50,
        distance_threshold=best_config['distance_threshold'],
        quality_metric='avg_return',
        quality_threshold_percentile=best_config['quality_percentile'],
        stride=50,
        forward_window=250,
        market_caps_df=mc_df
    )
    
    # Add event type
    loss_df['Event_Type'] = 'DROP'
    acq_df['Event_Type'] = 'ACQ'
    
    # Filter to large caps
    if mc_df is not None:
        symbol_avg_mc = mc_data.groupby('Symbol')['MarketCap'].mean()
        large_cap_symbols = symbol_avg_mc[
            (symbol_avg_mc >= 2e9) & 
            (symbol_avg_mc <= 100e9)
        ].index.tolist()
        
        acq_df_large_cap = acq_df[acq_df['Security'].isin(large_cap_symbols)]
    else:
        acq_df_large_cap = acq_df
    
    # Save
    acq_df_large_cap.to_csv('large_cap_acq_events_optimized.csv', index=False)
    
    print(f"\n✓ Generated {len(acq_df_large_cap):,} large cap acquisition events")
    print(f"  Win Rate: {(acq_df_large_cap['Future_Return'] > 0).mean() * 100:.1f}%")
    print(f"  Mean Return: {acq_df_large_cap['Future_Return'].mean():+.2f}%")
    print(f"  Saved to: large_cap_acq_events_optimized.csv")
    
    return acq_df_large_cap

if __name__ == '__main__':
    print("Starting optimization...")
    print("This will test multiple parameter combinations")
    print("Progress will be shown for each test\n")
    
    # Run optimization
    results_df, best_config = test_large_cap_acquisitions(
        distance_thresholds=[30, 35, 40, 45, 50],
        quality_percentiles=[75, 80, 85, 90],
        marketcap_min=2e9,
        marketcap_max=100e9,
        forward_window=250
    )
    
    # Generate events with best config
    events = generate_events_with_best_config(best_config)
    
    print("\n" + "="*80)
    print("✅ OPTIMIZATION COMPLETE")
    print("="*80)
