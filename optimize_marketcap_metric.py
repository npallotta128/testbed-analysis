import pandas as pd
import numpy as np
from optimize_dropout_strategy_safe import test_dropout_parameters
import time

def test_marketcap_as_quality_metric():
    """
    Optimize acquisition events using market cap as the quality metric.
    
    Tests combinations of:
    - distance_thresholds: [30, 35, 40, 45, 50]
    - quality_metrics: Different market cap weighted metrics
    - quality_percentiles: [75, 80, 85, 90]
    """
    
    # Parameters to test
    distance_thresholds = [30, 35, 40, 45, 50]
    
    # Market cap based quality metrics
    quality_metrics = [
        ('cap_weighted_return', 'Market Cap Weighted Return'),
        ('cap_weighted_positive_pct', 'Market Cap Weighted Win Rate'),
        ('cap_weighted_sharpe', 'Market Cap Weighted Sharpe'),
        ('avg_return', 'Simple Avg Return (baseline)')
    ]
    
    quality_percentiles = [75, 80, 85, 90]
    
    # Fixed parameters
    block_size = 200
    stride = 50
    num_blocks = 50
    forward_window = 250  # Use 250-day window
    min_marketcap = 2e9    # $2B minimum
    max_marketcap = 100e9  # $100B maximum (large caps)
    
    results = []
    total_tests = len(distance_thresholds) * len(quality_metrics) * len(quality_percentiles)
    test_num = 0
    
    print("=" * 80)
    print("OPTIMIZING ACQUISITION EVENTS WITH MARKET CAP AS QUALITY METRIC")
    print("=" * 80)
    print(f"Fixed Parameters:")
    print(f"  - Market Cap Range: $2B - $100B (Large Caps)")
    print(f"  - Forward Window: {forward_window} days")
    print(f"  - Block Size: {block_size}, Stride: {stride}, Num Blocks: {num_blocks}")
    print(f"\nTesting {total_tests} configurations...")
    print("=" * 80)
    print()
    
    for distance_threshold in distance_thresholds:
        for quality_metric, metric_name in quality_metrics:
            for quality_percentile in quality_percentiles:
                test_num += 1
                print(f"[{test_num}/{total_tests}] distance={distance_threshold}, {metric_name}, {quality_percentile}th pct")
                
                start_time = time.time()
                
                try:
                    # Load market cap data
                    marketcap_df = pd.read_csv('data_with_marketcap.csv')
                    
                    result, loss_df, acquisition_df = test_dropout_parameters(
                        data_file='data.csv',
                        block_size=block_size,
                        stride=stride,
                        num_blocks=num_blocks,
                        distance_threshold=distance_threshold,
                        quality_metric=quality_metric,
                        quality_threshold_percentile=quality_percentile,
                        forward_window=forward_window,
                        market_caps_df=marketcap_df
                    )
                    
                    runtime = time.time() - start_time
                    
                    # Filter acquisition events by market cap range
                    if acquisition_df is not None and len(acquisition_df) > 0:
                        # Merge with market cap data
                        acq_with_cap = acquisition_df.merge(
                            marketcap_df.groupby('Symbol')['MarketCap'].mean().reset_index(),
                            left_on='Security',
                            right_on='Symbol',
                            how='left'
                        )
                        # Filter by market cap range
                        acq_events = acq_with_cap[
                            (acq_with_cap['MarketCap'] >= min_marketcap) & 
                            (acq_with_cap['MarketCap'] <= max_marketcap)
                        ].copy()
                        num_events = len(acq_events)
                        
                        if num_events > 0:
                            win_rate = (acq_events['Future_Return'] > 0).sum() / num_events * 100
                            mean_return = acq_events['Future_Return'].mean()
                            median_return = acq_events['Future_Return'].median()
                            std_return = acq_events['Future_Return'].std()
                            
                            # Sharpe ratio (assuming 0% risk-free rate)
                            sharpe = mean_return / std_return if std_return > 0 else 0
                            
                            # Top and bottom 10% returns
                            top_10pct = acq_events['Future_Return'].quantile(0.9)
                            bottom_10pct = acq_events['Future_Return'].quantile(0.1)
                            
                            results.append({
                                'Distance_Threshold': distance_threshold,
                                'Quality_Metric': metric_name,
                                'Quality_Percentile': quality_percentile,
                                'Num_Events': num_events,
                                'Win_Rate_%': win_rate,
                                'Mean_Return_%': mean_return,
                                'Median_Return_%': median_return,
                                'Std_Return_%': std_return,
                                'Sharpe_Ratio': sharpe,
                                'Top_10pct_%': top_10pct,
                                'Bottom_10pct_%': bottom_10pct,
                                'Runtime_Sec': runtime
                            })
                            
                            print(f"  ✓ {num_events} events, Win Rate: {win_rate:.1f}%, Mean: {mean_return:+.1f}%, Sharpe: {sharpe:.2f}")
                        else:
                            print(f"  ✗ No events generated")
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
        
        output_file = 'marketcap_metric_optimization.csv'
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
        print("BEST CONFIGURATION SUMMARY")
        print("=" * 80)
        print(f"Distance Threshold: {best_config['Distance_Threshold']}")
        print(f"Quality Metric: {best_config['Quality_Metric']}")
        print(f"Quality Percentile: {best_config['Quality_Percentile']}th")
        print(f"Events: {best_config['Num_Events']}")
        print(f"Win Rate: {best_config['Win_Rate_%']:.1f}%")
        print(f"Mean Return: {best_config['Mean_Return_%']:+.2f}%")
        print(f"Sharpe Ratio: {best_config['Sharpe_Ratio']:.3f}")
        
        # Also show comparison by metric type
        print()
        print("=" * 80)
        print("BEST SHARPE BY QUALITY METRIC TYPE")
        print("=" * 80)
        metric_summary = results_df.groupby('Quality_Metric').apply(
            lambda x: x.nlargest(1, 'Sharpe_Ratio')
        ).reset_index(drop=True)
        print(metric_summary[['Quality_Metric', 'Distance_Threshold', 'Quality_Percentile',
                              'Num_Events', 'Win_Rate_%', 'Mean_Return_%', 'Sharpe_Ratio']].to_string(index=False))
    
    print()
    print("=" * 80)
    print("✅ OPTIMIZATION COMPLETE")
    print("=" * 80)

if __name__ == '__main__':
    test_marketcap_as_quality_metric()
