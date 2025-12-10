"""
High Market Cap Strategy - Parameter Optimization

Tests different parameter combinations to find optimal configuration
"""

import pandas as pd
import numpy as np
from itertools import product
import time
import sys

sys.path.insert(0, '/home/npallotta128/projects/testbed-analysis')

from high_marketcap_cluster_strategy import HighMarketCapClusterStrategy


def test_parameter_combination(params):
    """Test a single parameter combination"""
    
    cap_percentile = params['cap_percentile']
    block_size = params['block_size']
    num_blocks = params['num_blocks']
    distance_threshold = params['distance_threshold']
    quality_threshold_pct = params['quality_threshold_pct']
    min_quality_change = params['min_quality_change']
    
    try:
        # Initialize strategy
        strategy = HighMarketCapClusterStrategy(data_file='data_with_marketcap.csv')
        strategy.load_data_with_marketcap()
        
        # Select high cap stocks
        df_high_cap = strategy.select_high_cap_stocks(cap_percentile=cap_percentile)
        
        # Perform clustering
        block_results = strategy.perform_clustering(
            data=df_high_cap,
            block_size=block_size,
            num_blocks=num_blocks,
            distance_threshold=distance_threshold
        )
        
        if len(block_results) == 0:
            return None
        
        # Detect transitions
        events_df = strategy.detect_transitions(
            block_results,
            quality_threshold_percentile=quality_threshold_pct,
            min_quality_change=min_quality_change
        )
        
        if len(events_df) == 0:
            return None
        
        # Calculate returns
        events_df = strategy.calculate_post_event_returns(events_df, forward_periods=500)
        events_with_returns = events_df[events_df['Future_Return'].notna()]
        
        if len(events_with_returns) == 0:
            return None
        
        # Calculate metrics
        result = {
            'cap_percentile': cap_percentile,
            'block_size': block_size,
            'num_blocks': num_blocks,
            'distance_threshold': distance_threshold,
            'quality_threshold_pct': quality_threshold_pct,
            'min_quality_change': min_quality_change,
            'num_events': len(events_with_returns),
            'num_buy': len(events_with_returns[events_with_returns['Signal'] == 'BUY']),
            'num_sell': len(events_with_returns[events_with_returns['Signal'] == 'SELL']),
            'avg_return': events_with_returns['Future_Return'].mean(),
            'median_return': events_with_returns['Future_Return'].median(),
            'std_return': events_with_returns['Future_Return'].std(),
            'win_rate': (events_with_returns['Future_Return'] > 0).mean() * 100,
            'sharpe': events_with_returns['Future_Return'].mean() / (events_with_returns['Future_Return'].std() + 1e-6),
            'buy_avg_return': events_with_returns[events_with_returns['Signal'] == 'BUY']['Future_Return'].mean() if len(events_with_returns[events_with_returns['Signal'] == 'BUY']) > 0 else np.nan,
            'sell_avg_return': events_with_returns[events_with_returns['Signal'] == 'SELL']['Future_Return'].mean() if len(events_with_returns[events_with_returns['Signal'] == 'SELL']) > 0 else np.nan,
        }
        
        return result
    
    except Exception as e:
        print(f"  Error: {e}")
        return None


def optimize_parameters(quick_test=True):
    """Test parameter combinations"""
    
    print("="*80)
    print("HIGH MARKET CAP STRATEGY - PARAMETER OPTIMIZATION")
    print("="*80)
    
    if quick_test:
        print("\n🏃 QUICK TEST (Limited combinations)")
        
        param_ranges = {
            'cap_percentile': [60, 70, 80],
            'block_size': [125, 150],
            'num_blocks': [10],
            'distance_threshold': [35, 40, 50],
            'quality_threshold_pct': [70, 75],
            'min_quality_change': [5]
        }
    else:
        print("\n🔬 FULL OPTIMIZATION (All combinations)")
        
        param_ranges = {
            'cap_percentile': [50, 60, 70, 80, 90],
            'block_size': [100, 125, 150, 175, 200],
            'num_blocks': [8, 10, 12],
            'distance_threshold': [30, 40, 50, 60],
            'quality_threshold_pct': [70, 75, 80],
            'min_quality_change': [3, 5, 10]
        }
    
    # Generate all combinations
    param_keys = param_ranges.keys()
    param_values = param_ranges.values()
    total_combinations = np.prod([len(v) for v in param_values])
    
    print(f"\nTotal combinations to test: {total_combinations}")
    
    results = []
    start_time = time.time()
    
    current = 0
    for param_tuple in product(*param_values):
        current += 1
        
        params = dict(zip(param_keys, param_tuple))
        
        print(f"\n[{current}/{total_combinations}] Testing: "
              f"cap={params['cap_percentile']} bs={params['block_size']} "
              f"nb={params['num_blocks']} dt={params['distance_threshold']} "
              f"qt={params['quality_threshold_pct']} mc={params['min_quality_change']}")
        
        result = test_parameter_combination(params)
        
        if result is not None:
            results.append(result)
            print(f"  ✓ Events={result['num_events']} Avg={result['avg_return']:+.2f}% "
                  f"WinRate={result['win_rate']:.1f}%")
        else:
            print(f"  ✗ No valid results")
    
    elapsed = time.time() - start_time
    
    # Convert to DataFrame
    results_df = pd.DataFrame(results)
    
    print("\n" + "="*80)
    print("OPTIMIZATION COMPLETE")
    print("="*80)
    
    print(f"\nTime elapsed: {elapsed:.1f} seconds")
    print(f"Valid combinations: {len(results_df)}/{total_combinations}")
    
    if len(results_df) > 0:
        # Save results
        results_df = results_df.sort_values('avg_return', ascending=False)
        results_df.to_csv('highcap_optimization_results.csv', index=False)
        print(f"\nSaved results to: highcap_optimization_results.csv")
        
        # Print top configurations
        print("\n📊 TOP 10 CONFIGURATIONS (by avg return)")
        print("-" * 80)
        
        top_10 = results_df.head(10)
        for idx, row in top_10.iterrows():
            print(f"{idx+1:2}. cap={int(row['cap_percentile']):2}% bs={int(row['block_size']):3} "
                  f"nb={int(row['num_blocks']):2} dt={int(row['distance_threshold']):2} "
                  f"qt={int(row['quality_threshold_pct']):2} mc={int(row['min_quality_change']):2} | "
                  f"Events={int(row['num_events']):3} Return={row['avg_return']:+6.2f}% "
                  f"WinRate={row['win_rate']:5.1f}%")
        
        # Print best by win rate
        print("\n🏆 TOP 5 BY WIN RATE")
        print("-" * 80)
        
        top_winrate = results_df.nlargest(5, 'win_rate')
        for idx, row in top_winrate.iterrows():
            print(f"  cap={int(row['cap_percentile']):2}% bs={int(row['block_size']):3} "
                  f"nb={int(row['num_blocks']):2} dt={int(row['distance_threshold']):2} | "
                  f"WinRate={row['win_rate']:5.1f}% Return={row['avg_return']:+6.2f}%")
        
        # Statistics
        print("\n📈 STATISTICS")
        print("-" * 80)
        print(f"  Avg return (mean): {results_df['avg_return'].mean():+.2f}%")
        print(f"  Avg return (median): {results_df['avg_return'].median():+.2f}%")
        print(f"  Std dev: {results_df['avg_return'].std():.2f}%")
        print(f"  Best return: {results_df['avg_return'].max():+.2f}%")
        print(f"  Worst return: {results_df['avg_return'].min():+.2f}%")
        print(f"  Avg win rate: {results_df['win_rate'].mean():.1f}%")
        print(f"  Positive return configs: {len(results_df[results_df['avg_return'] > 0])} / {len(results_df)}")
    
    return results_df


def main():
    """Run optimization"""
    
    import argparse
    
    parser = argparse.ArgumentParser(description='Optimize high market cap strategy parameters')
    parser.add_argument('--full', action='store_true', help='Run full optimization (slower)')
    parser.add_argument('--quick', action='store_true', default=True, help='Run quick test (default)')
    
    args = parser.parse_args()
    
    quick_test = not args.full
    
    results_df = optimize_parameters(quick_test=quick_test)
    
    print("\n" + "="*80)
    print("✅ OPTIMIZATION COMPLETE")
    print("="*80)
    
    return results_df


if __name__ == '__main__':
    results = main()
