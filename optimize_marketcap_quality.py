import pandas as pd
import numpy as np
from optimize_dropout_strategy_safe import test_dropout_parameters
import time

def optimize_with_marketcap_quality():
    """
    Optimize acquisition events using market cap as the quality metric.
    
    Tests:
    - distance_thresholds: [30, 35, 40, 45, 50]
    - quality_metrics: cap_weighted_return, cap_weighted_positive_pct, cap_weighted_sharpe
    - quality_percentiles: [75, 80, 85, 90]
    
    This treats market cap as a QUALITY signal - giving more weight to
    larger cap stocks when calculating cluster quality scores.
    """
    
    # Parameters to test
    distance_thresholds = [30, 35, 40, 45, 50]
    quality_metrics = [
        'cap_weighted_return',      # Average return weighted by market cap
        'cap_weighted_positive_pct', # % positive weighted by market cap
        'cap_weighted_sharpe'        # Sharpe ratio weighted by market cap
    ]
    quality_percentiles = [75, 80, 85, 90]
    
    # Fixed parameters
    block_size = 200
    stride = 50
    num_blocks = 50
    forward_window = 250  # Use 250-day window (proven superior)
    
    results = []
    total_tests = len(distance_thresholds) * len(quality_metrics) * len(quality_percentiles)
    test_num = 0
    
    print("=" * 80)
    print("OPTIMIZING WITH MARKET CAP AS QUALITY METRIC")
    print("=" * 80)
    print(f"Strategy: Market cap weights cluster quality scores")
    print(f"  - Larger cap stocks have more influence on cluster quality")
    print(f"  - Only 'quality' clusters (by market cap weighting) trigger events")
    print(f"\nFixed Parameters:")
    print(f"  - Forward Window: {forward_window} days")
    print(f"  - Block Size: {block_size}, Stride: {stride}, Num Blocks: {num_blocks}")
    print(f"\nTesting {total_tests} configurations...")
    print("=" * 80)
    print()
    
    for distance_threshold in distance_thresholds:
        for quality_metric in quality_metrics:
            for quality_percentile in quality_percentiles:
                test_num += 1
                print(f"[{test_num}/{total_tests}] distance={distance_threshold}, "
                      f"metric={quality_metric}, percentile={quality_percentile}th")
                
                start_time = time.time()
                
                try:
                    events_df = test_dropout_parameters(
                        block_size=block_size,
                        stride=stride,
                        num_blocks=num_blocks,
                        distance_threshold=distance_threshold,
                        quality_metric=quality_metric,
                        quality_percentile=quality_percentile,
                        forward_window=forward_window,
                        event_types=['ACQ']  # Only acquisition events
                    )
                    
                    runtime = time.time() - start_time
                    
                    if events_df is not None and len(events_df) > 0:
                        acq_events = events_df[events_df['Event_Type'] == 'ACQ'].copy()
                        num_events = len(acq_events)
                        
                        if num_events > 0:
                            win_rate = (acq_events['Forward_Return_Pct'] > 0).sum() / num_events * 100
                            mean_return = acq_events['Forward_Return_Pct'].mean()
                            median_return = acq_events['Forward_Return_Pct'].median()
                            std_return = acq_events['Forward_Return_Pct'].std()
                            
                            # Sharpe ratio
                            sharpe = mean_return / std_return if std_return > 0 else 0
                            
                            # Top and bottom 10%
                            top_10pct = acq_events['Forward_Return_Pct'].quantile(0.9)
                            bottom_10pct = acq_events['Forward_Return_Pct'].quantile(0.1)
                            
                            # Average market cap of events (if available)
                            avg_marketcap = acq_events['Avg_MarketCap'].mean() if 'Avg_MarketCap' in acq_events.columns else None
                            
                            results.append({
                                'Distance_Threshold': distance_threshold,
                                'Quality_Metric': quality_metric,
                                'Quality_Percentile': quality_percentile,
                                'Num_Events': num_events,
                                'Win_Rate_%': win_rate,
                                'Mean_Return_%': mean_return,
                                'Median_Return_%': median_return,
                                'Std_Return_%': std_return,
                                'Sharpe_Ratio': sharpe,
                                'Top_10pct_%': top_10pct,
                                'Bottom_10pct_%': bottom_10pct,
                                'Avg_MarketCap_B': avg_marketcap / 1e9 if avg_marketcap else None,
                                'Runtime_Sec': runtime
                            })
                            
                            print(f"  ✓ {num_events} events, Win: {win_rate:.1f}%, "
                                  f"Return: {mean_return:+.1f}%, Sharpe: {sharpe:.3f}")
                        else:
                            print(f"  ✗ No ACQ events")
                    else:
                        print(f"  ✗ No events generated")
                        
                except Exception as e:
                    print(f"  ✗ Error: {str(e)}")
                    runtime = time.time() - start_time
    
    # Convert to DataFrame and save
    results_df = pd.DataFrame(results)
    
    if len(results_df) > 0:
        # Sort by Sharpe ratio descending
        results_df = results_df.sort_values('Sharpe_Ratio', ascending=False)
        
        output_file = 'marketcap_quality_optimization.csv'
        results_df.to_csv(output_file, index=False)
        
        print()
        print("=" * 80)
        print("TOP 10 CONFIGURATIONS BY SHARPE RATIO")
        print("=" * 80)
        print(results_df[['Distance_Threshold', 'Quality_Metric', 'Quality_Percentile',
                         'Num_Events', 'Win_Rate_%', 'Mean_Return_%', 'Sharpe_Ratio']].head(10).to_string(index=False))
        print()
        print(f"✓ Full results saved to: {output_file}")
        
        # Find best configuration and generate events
        best_config = results_df.iloc[0]
        print()
        print("=" * 80)
        print("GENERATING EVENTS WITH BEST CONFIGURATION")
        print("=" * 80)
        print(f"Distance Threshold: {best_config['Distance_Threshold']}")
        print(f"Quality Metric: {best_config['Quality_Metric']}")
        print(f"Quality Percentile: {best_config['Quality_Percentile']}th")
        print(f"Expected Events: {best_config['Num_Events']}")
        print()
        
        # Generate final event set
        best_events = test_dropout_parameters(
            block_size=block_size,
            stride=stride,
            num_blocks=num_blocks,
            distance_threshold=best_config['Distance_Threshold'],
            quality_metric=best_config['Quality_Metric'],
            quality_percentile=best_config['Quality_Percentile'],
            forward_window=forward_window,
            event_types=['ACQ']
        )
        
        if best_events is not None:
            acq_events = best_events[best_events['Event_Type'] == 'ACQ']
            win_rate = (acq_events['Forward_Return_Pct'] > 0).sum() / len(acq_events) * 100
            mean_return = acq_events['Forward_Return_Pct'].mean()
            
            events_file = 'marketcap_quality_acq_events.csv'
            acq_events.to_csv(events_file, index=False)
            
            print(f"✓ Generated {len(acq_events)} acquisition events")
            print(f"  Win Rate: {win_rate:.1f}%")
            print(f"  Mean Return: {mean_return:+.2f}%")
            print(f"  Saved to: {events_file}")
            
            # Show market cap distribution
            if 'Avg_MarketCap' in acq_events.columns:
                print()
                print("Market Cap Distribution of Events:")
                acq_events['Cap_Tier'] = pd.cut(
                    acq_events['Avg_MarketCap'] / 1e9,
                    bins=[0, 1, 2, 10, 50, 100, 500, 10000],
                    labels=['<$1B', '$1B-$2B', '$2B-$10B', '$10B-$50B', '$50B-$100B', '$100B-$500B', '>$500B']
                )
                print(acq_events['Cap_Tier'].value_counts().sort_index())
    
    print()
    print("=" * 80)
    print("✅ OPTIMIZATION COMPLETE")
    print("=" * 80)

if __name__ == '__main__':
    optimize_with_marketcap_quality()
