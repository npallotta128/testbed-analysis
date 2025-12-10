"""
Monte Carlo Simulation for 250-Day Sliding Window Strategy
===========================================================

Simulates portfolio growth with capital allocation and compounding.

Strategy:
- Start with initial capital
- Invest in events based on 250-day window signals
- Use ML model scoring or simple random selection from events
- Reinvest profits, compound over time
- Model multiple scenarios (Monte Carlo)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def load_events_with_metrics():
    """Load events with all available metrics"""
    
    print("Loading event data...")
    events = pd.read_csv('events_sliding_window_250day_recalc.csv')
    
    # Try to merge with price/volume/marketcap metrics
    try:
        price_vol_metrics = pd.read_csv('winners_losers_metrics_250d.csv')
        events = events.merge(
            price_vol_metrics[['Security', 'Block', 'Avg_Price', 'Avg_Volume', 'Price_Volatility']],
            on=['Security', 'Block'],
            how='left'
        )
        print("  ✓ Merged with price/volume metrics")
    except:
        print("  ⚠ Price/volume metrics not available")
    
    try:
        mc_metrics = pd.read_csv('marketcap_winners_losers.csv')
        events = events.merge(
            mc_metrics[['Security', 'Block', 'Avg_MarketCap']],
            on=['Security', 'Block'],
            how='left'
        )
        print("  ✓ Merged with market cap metrics")
    except:
        print("  ⚠ Market cap metrics not available")
    
    print(f"  Total events loaded: {len(events):,}")
    
    return events

def filter_events(events, filters=None):
    """
    Filter events based on criteria
    
    filters = {
        'price_min': 5,
        'price_max': 10,
        'volume_max': 1000000,
        'marketcap_min': 10e9,
        'marketcap_max': 100e9,
        'event_type': 'DROP'  # or 'ACQ'
    }
    """
    
    if filters is None:
        return events
    
    filtered = events.copy()
    
    if 'price_min' in filters and 'Avg_Price' in filtered.columns:
        filtered = filtered[filtered['Avg_Price'] >= filters['price_min']]
    
    if 'price_max' in filters and 'Avg_Price' in filtered.columns:
        filtered = filtered[filtered['Avg_Price'] <= filters['price_max']]
    
    if 'volume_max' in filters and 'Avg_Volume' in filtered.columns:
        filtered = filtered[filtered['Avg_Volume'] <= filters['volume_max']]
    
    if 'marketcap_min' in filters and 'Avg_MarketCap' in filtered.columns:
        filtered = filtered[filtered['Avg_MarketCap'] >= filters['marketcap_min']]
    
    if 'marketcap_max' in filters and 'Avg_MarketCap' in filtered.columns:
        filtered = filtered[filtered['Avg_MarketCap'] <= filters['marketcap_max']]
    
    if 'event_type' in filters:
        filtered = filtered[filtered['Event_Type'] == filters['event_type']]
    
    return filtered

def run_monte_carlo_simulation(
    events,
    initial_capital=100000,
    positions_per_period=10,
    position_size_pct=0.10,  # 10% of capital per position
    holding_days=250,
    num_simulations=1000,
    num_periods=10,  # How many 250-day periods to simulate
    filters=None,
    random_seed=42
):
    """
    Run Monte Carlo simulation
    
    Args:
        events: DataFrame of events with returns
        initial_capital: Starting capital
        positions_per_period: Number of positions to take each period
        position_size_pct: % of capital per position
        holding_days: Holding period (250 days)
        num_simulations: Number of Monte Carlo runs
        num_periods: Number of sequential periods
        filters: Event filters
        random_seed: Random seed for reproducibility
    """
    
    np.random.seed(random_seed)
    
    print("="*80)
    print("MONTE CARLO SIMULATION - 250-DAY STRATEGY")
    print("="*80)
    print(f"\nParameters:")
    print(f"  Initial Capital: ${initial_capital:,.0f}")
    print(f"  Positions Per Period: {positions_per_period}")
    print(f"  Position Size: {position_size_pct*100:.1f}% of capital")
    print(f"  Holding Period: {holding_days} days")
    print(f"  Number of Periods: {num_periods}")
    print(f"  Simulations: {num_simulations:,}")
    
    # Filter events
    if filters:
        events = filter_events(events, filters)
        print(f"\nFiltered Events: {len(events):,}")
        print(f"  Filters applied: {filters}")
    
    # Remove invalid returns
    events = events[events['Future_Return'].notna()]
    events = events[events['Future_Return'] > -100]  # Remove complete losses > 100%
    
    print(f"\nValid Events: {len(events):,}")
    print(f"  Mean Return: {events['Future_Return'].mean():.2f}%")
    print(f"  Median Return: {events['Future_Return'].median():.2f}%")
    print(f"  Win Rate: {(events['Future_Return'] > 0).mean()*100:.1f}%")
    
    # Run simulations
    print(f"\nRunning {num_simulations:,} simulations...")
    
    all_results = []
    
    for sim in range(num_simulations):
        if sim % 100 == 0:
            print(f"  Simulation {sim}/{num_simulations}")
        
        capital = initial_capital
        capital_history = [capital]
        
        for period in range(num_periods):
            # Sample events for this period
            if len(events) < positions_per_period:
                sampled_events = events.sample(n=len(events), replace=True)
            else:
                sampled_events = events.sample(n=positions_per_period, replace=True)
            
            # Calculate returns for each position
            period_returns = []
            
            for _, event in sampled_events.iterrows():
                position_return = event['Future_Return'] / 100  # Convert to decimal
                period_returns.append(position_return)
            
            # Calculate weighted portfolio return
            # Each position is position_size_pct of capital
            portfolio_return = np.mean(period_returns) * position_size_pct * positions_per_period
            
            # Update capital (can't go below 0)
            capital = max(0, capital * (1 + portfolio_return))
            capital_history.append(capital)
        
        all_results.append({
            'simulation': sim,
            'final_capital': capital,
            'total_return_pct': (capital - initial_capital) / initial_capital * 100,
            'capital_history': capital_history
        })
    
    results_df = pd.DataFrame(all_results)
    
    # Statistics
    print("\n" + "="*80)
    print("SIMULATION RESULTS")
    print("="*80)
    
    print(f"\nFinal Capital Distribution:")
    print(f"  Mean: ${results_df['final_capital'].mean():,.0f}")
    print(f"  Median: ${results_df['final_capital'].median():,.0f}")
    print(f"  10th percentile: ${results_df['final_capital'].quantile(0.10):,.0f}")
    print(f"  90th percentile: ${results_df['final_capital'].quantile(0.90):,.0f}")
    print(f"  Best case: ${results_df['final_capital'].max():,.0f}")
    print(f"  Worst case: ${results_df['final_capital'].min():,.0f}")
    
    print(f"\nTotal Return Distribution:")
    print(f"  Mean: {results_df['total_return_pct'].mean():+.2f}%")
    print(f"  Median: {results_df['total_return_pct'].median():+.2f}%")
    print(f"  10th percentile: {results_df['total_return_pct'].quantile(0.10):+.2f}%")
    print(f"  90th percentile: {results_df['total_return_pct'].quantile(0.90):+.2f}%")
    print(f"  Best: {results_df['total_return_pct'].max():+.2f}%")
    print(f"  Worst: {results_df['total_return_pct'].min():+.2f}%")
    
    print(f"\nProbability of Profit:")
    prob_profit = (results_df['total_return_pct'] > 0).mean() * 100
    print(f"  {prob_profit:.1f}% ({(results_df['total_return_pct'] > 0).sum():,} / {num_simulations:,})")
    
    print(f"\nProbability of Doubling Capital:")
    prob_double = (results_df['total_return_pct'] > 100).mean() * 100
    print(f"  {prob_double:.1f}% ({(results_df['total_return_pct'] > 100).sum():,} / {num_simulations:,})")
    
    print(f"\nProbability of 10x Return:")
    prob_10x = (results_df['total_return_pct'] > 900).mean() * 100
    print(f"  {prob_10x:.1f}% ({(results_df['total_return_pct'] > 900).sum():,} / {num_simulations:,})")
    
    # Time to target analysis
    print(f"\nTime Horizon:")
    total_days = num_periods * holding_days
    total_years = total_days / 252
    print(f"  Total Days: {total_days}")
    print(f"  Total Years: {total_years:.1f}")
    
    annualized_return = (results_df['final_capital'].median() / initial_capital) ** (1 / total_years) - 1
    print(f"  Median Annualized Return: {annualized_return * 100:+.2f}%")
    
    # Save results
    results_df.to_csv('monte_carlo_results.csv', index=False)
    print(f"\n✓ Saved detailed results to: monte_carlo_results.csv")
    
    # Plot
    plot_monte_carlo_results(results_df, initial_capital, num_periods)
    
    return results_df

def plot_monte_carlo_results(results_df, initial_capital, num_periods):
    """Plot Monte Carlo simulation results"""
    
    print("\nGenerating plots...")
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    # Plot 1: Capital evolution paths (sample of 100)
    ax = axes[0, 0]
    sample_size = min(100, len(results_df))
    for i in range(sample_size):
        history = results_df.iloc[i]['capital_history']
        ax.plot(range(len(history)), history, alpha=0.1, color='blue')
    
    # Add median and percentiles
    all_histories = np.array([r['capital_history'] for _, r in results_df.iterrows()])
    median_history = np.median(all_histories, axis=0)
    p10_history = np.percentile(all_histories, 10, axis=0)
    p90_history = np.percentile(all_histories, 90, axis=0)
    
    ax.plot(range(num_periods + 1), median_history, color='red', linewidth=2, label='Median')
    ax.plot(range(num_periods + 1), p10_history, color='orange', linewidth=1.5, linestyle='--', label='10th %ile')
    ax.plot(range(num_periods + 1), p90_history, color='green', linewidth=1.5, linestyle='--', label='90th %ile')
    
    ax.axhline(y=initial_capital, color='black', linestyle=':', alpha=0.5, label='Initial')
    ax.set_xlabel('Period')
    ax.set_ylabel('Capital ($)')
    ax.set_title('Capital Evolution (Sample Paths)')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # Plot 2: Final capital distribution
    ax = axes[0, 1]
    ax.hist(results_df['final_capital'], bins=50, edgecolor='black', alpha=0.7)
    ax.axvline(x=initial_capital, color='red', linestyle='--', label='Initial Capital')
    ax.axvline(x=results_df['final_capital'].median(), color='green', linestyle='--', label='Median Final')
    ax.set_xlabel('Final Capital ($)')
    ax.set_ylabel('Frequency')
    ax.set_title('Final Capital Distribution')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # Plot 3: Return distribution
    ax = axes[1, 0]
    ax.hist(results_df['total_return_pct'], bins=50, edgecolor='black', alpha=0.7)
    ax.axvline(x=0, color='red', linestyle='--', label='Break-even')
    ax.axvline(x=results_df['total_return_pct'].median(), color='green', linestyle='--', label='Median Return')
    ax.set_xlabel('Total Return (%)')
    ax.set_ylabel('Frequency')
    ax.set_title('Return Distribution')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # Plot 4: Cumulative probability
    ax = axes[1, 1]
    sorted_returns = np.sort(results_df['total_return_pct'])
    cumulative_prob = np.arange(1, len(sorted_returns) + 1) / len(sorted_returns)
    ax.plot(sorted_returns, cumulative_prob, linewidth=2)
    ax.axvline(x=0, color='red', linestyle='--', alpha=0.5, label='Break-even')
    ax.axhline(y=0.5, color='green', linestyle='--', alpha=0.5, label='50% Probability')
    ax.set_xlabel('Total Return (%)')
    ax.set_ylabel('Cumulative Probability')
    ax.set_title('Cumulative Distribution of Returns')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('monte_carlo_simulation.png', dpi=150)
    print("  ✓ Saved plot to: monte_carlo_simulation.png")

def compare_strategies():
    """Compare different strategy configurations"""
    
    print("\n" + "="*80)
    print("COMPARING DIFFERENT STRATEGIES")
    print("="*80)
    
    events = load_events_with_metrics()
    
    strategies = [
        {
            'name': 'Baseline (No Filters)',
            'filters': None,
            'position_size_pct': 0.10
        },
        {
            'name': 'Mega Cap Focus',
            'filters': {'marketcap_min': 10e9, 'marketcap_max': 100e9},
            'position_size_pct': 0.10
        },
        {
            'name': 'Low Volume (Illiquid)',
            'filters': {'volume_max': 100000},
            'position_size_pct': 0.05  # Smaller positions for illiquid
        },
        {
            'name': 'Aggressive (Large Positions)',
            'filters': None,
            'position_size_pct': 0.20
        }
    ]
    
    comparison = []
    
    for strategy in strategies:
        print(f"\n{'='*80}")
        print(f"Strategy: {strategy['name']}")
        print(f"{'='*80}")
        
        results = run_monte_carlo_simulation(
            events,
            initial_capital=100000,
            positions_per_period=10,
            position_size_pct=strategy['position_size_pct'],
            holding_days=250,
            num_simulations=500,  # Fewer for comparison
            num_periods=10,
            filters=strategy['filters']
        )
        
        comparison.append({
            'Strategy': strategy['name'],
            'Median_Return_%': results['total_return_pct'].median(),
            'Mean_Return_%': results['total_return_pct'].mean(),
            'Prob_Profit_%': (results['total_return_pct'] > 0).mean() * 100,
            'Prob_Double_%': (results['total_return_pct'] > 100).mean() * 100,
            '10th_Pctile_%': results['total_return_pct'].quantile(0.10),
            '90th_Pctile_%': results['total_return_pct'].quantile(0.90)
        })
    
    comparison_df = pd.DataFrame(comparison)
    comparison_df.to_csv('strategy_comparison.csv', index=False)
    
    print("\n" + "="*80)
    print("STRATEGY COMPARISON SUMMARY")
    print("="*80)
    print(comparison_df.to_string(index=False))
    print("\n✓ Saved to: strategy_comparison.csv")

if __name__ == '__main__':
    # Load events
    events = load_events_with_metrics()
    
    # Run single simulation with detailed output
    results = run_monte_carlo_simulation(
        events,
        initial_capital=100000,
        positions_per_period=10,
        position_size_pct=0.10,
        holding_days=250,
        num_simulations=1000,
        num_periods=10,
        filters=None  # No filters for baseline
    )
    
    print("\n" + "="*80)
    print("✅ MONTE CARLO SIMULATION COMPLETE")
    print("="*80)
