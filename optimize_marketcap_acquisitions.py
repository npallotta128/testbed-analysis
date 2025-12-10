import pandas as pd
import numpy as np
from optimize_dropout_strategy_safe import test_dropout_parameters
import time

def test_marketcap_acquisition_tiers():
    """
    Optimize acquisition events by testing different market cap tiers
    instead of quality percentiles.
    
    Tests combinations of:
    - distance_thresholds: [30, 35, 40, 45, 50]
    - market_cap_tiers: Various ranges from $100M to $500B+
    """
    
    # Parameters to test
    distance_thresholds = [30, 35, 40, 45, 50]
    
    # Market cap tiers to test (in billions)
    marketcap_tiers = [
        (0.1, 1, "Small Cap: $100M-$1B"),
        (1, 2, "Mid Cap Low: $1B-$2B"),
        (2, 10, "Large Cap Low: $2B-$10B"),
        (10, 50, "Large Cap Mid: $10B-$50B"),
        (50, 100, "Large Cap High: $50B-$100B"),
        (100, 500, "Mega Cap: $100B-$500B"),
        (500, 10000, "Ultra Mega: $500B+"),
        (2, 100, "All Large Cap: $2B-$100B"),
        (10, 100, "Mega Range: $10B-$100B"),
    ]
    
    # Fixed parameters
    block_size = 200
    stride = 50
    num_blocks = 50
    quality_metric = 'avg_return'
    quality_percentile = 80  # Fixed at 80th percentile
    forward_window = 250  # Use 250-day window (proven superior)
    
    results = []
    total_tests = len(distance_thresholds) * len(marketcap_tiers)
    test_num = 0
    
    print("=" * 80)
    print("OPTIMIZING ACQUISITION EVENTS BY MARKET CAP TIERS")
    print("=" * 80)
    print(f"Fixed Parameters:")
    print(f"  - Quality Percentile: {quality_percentile}th")
    print(f"  - Forward Window: {forward_window} days")
    print(f"  - Block Size: {block_size}, Stride: {stride}, Num Blocks: {num_blocks}")
    print(f"\nTesting {total_tests} configurations...")
    print("=" * 80)
    print()
    
    for distance_threshold in distance_thresholds:
        for min_cap, max_cap, tier_name in marketcap_tiers:
            test_num += 1
            print(f"[{test_num}/{total_tests}] Testing: distance={distance_threshold}, {tier_name}")
            
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
                    event_types=['ACQ'],  # Only acquisition events
                    min_marketcap=min_cap * 1e9,  # Convert billions to actual value
                    max_marketcap=max_cap * 1e9
                )
                
                runtime = time.time() - start_time
                
                if events_df is not None and len(events_df) > 0:
                    # Calculate metrics
                    acq_events = events_df[events_df['Event_Type'] == 'ACQ'].copy()
                    num_events = len(acq_events)
                    
                    if num_events > 0:
                        win_rate = (acq_events['Forward_Return_Pct'] > 0).sum() / num_events * 100
                        mean_return = acq_events['Forward_Return_Pct'].mean()
                        median_return = acq_events['Forward_Return_Pct'].median()
                        std_return = acq_events['Forward_Return_Pct'].std()
                        
                        # Sharpe ratio (assuming 0% risk-free rate)
                        sharpe = mean_return / std_return if std_return > 0 else 0
                        
                        # Top and bottom 10% returns
                        top_10pct = acq_events['Forward_Return_Pct'].quantile(0.9)
                        bottom_10pct = acq_events['Forward_Return_Pct'].quantile(0.1)
                        
                        results.append({
                            'Distance_Threshold': distance_threshold,
                            'Market_Cap_Tier': tier_name,
                            'Min_Cap_B': min_cap,
                            'Max_Cap_B': max_cap,
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
                        
                        print(f"  ✓ {num_events} events, Win Rate: {win_rate:.1f}%, Mean Return: {mean_return:+.1f}%")
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
        
        output_file = 'marketcap_tier_optimization.csv'
        results_df.to_csv(output_file, index=False)
        
        print()
        print("=" * 80)
        print("TOP 10 CONFIGURATIONS BY SHARPE RATIO")
        print("=" * 80)
        print(results_df[['Distance_Threshold', 'Market_Cap_Tier', 'Num_Events', 
                         'Win_Rate_%', 'Mean_Return_%', 'Sharpe_Ratio']].head(10).to_string(index=False))
        print()
        print(f"✓ Full results saved to: {output_file}")
        
        # Find best configuration and generate events
        best_config = results_df.iloc[0]
        print()
        print("=" * 80)
        print("GENERATING EVENTS WITH BEST CONFIGURATION")
        print("=" * 80)
        print(f"Distance Threshold: {best_config['Distance_Threshold']}")
        print(f"Market Cap Tier: {best_config['Market_Cap_Tier']}")
        print(f"Expected Events: {best_config['Num_Events']}")
        print()
        
        # Generate final event set
        best_events = test_dropout_parameters(
            block_size=block_size,
            stride=stride,
            num_blocks=num_blocks,
            distance_threshold=best_config['Distance_Threshold'],
            quality_metric=quality_metric,
            quality_percentile=quality_percentile,
            forward_window=forward_window,
            event_types=['ACQ'],
            min_marketcap=best_config['Min_Cap_B'] * 1e9,
            max_marketcap=best_config['Max_Cap_B'] * 1e9
        )
        
        if best_events is not None:
            acq_events = best_events[best_events['Event_Type'] == 'ACQ']
            win_rate = (acq_events['Forward_Return_Pct'] > 0).sum() / len(acq_events) * 100
            mean_return = acq_events['Forward_Return_Pct'].mean()
            
            events_file = 'marketcap_acq_events_optimized.csv'
            acq_events.to_csv(events_file, index=False)
            
            print(f"✓ Generated {len(acq_events)} acquisition events")
            print(f"  Win Rate: {win_rate:.1f}%")
            print(f"  Mean Return: {mean_return:+.2f}%")
            print(f"  Saved to: {events_file}")
    
    print()
    print("=" * 80)
    print("✅ OPTIMIZATION COMPLETE")
    print("=" * 80)

if __name__ == '__main__':
    test_marketcap_acquisition_tiers()
