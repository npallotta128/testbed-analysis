import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing as mp

# Configuration
D_DRIVE_PATH = '/mnt/d/testbed_analysis'
RETURNS_DIR = os.path.join(D_DRIVE_PATH, 'returns')
MONTECARLO_DIR = os.path.join(D_DRIVE_PATH, 'montecarlo')
INITIAL_INVESTMENT = 10000  # $10,000 initial investment
NUM_SIMULATIONS = 1000  # 1000 Monte Carlo simulations
NUM_PROCESSES = min(8, mp.cpu_count())  # Use multiple cores

def create_montecarlo_directory():
    """Create Monte Carlo directory on D drive"""
    if not os.path.exists(MONTECARLO_DIR):
        os.makedirs(MONTECARLO_DIR)
        print(f"Created directory: {MONTECARLO_DIR}")

def calculate_time_weighted_return(portfolio_trades, initial_investment):
    """
    Calculate time-weighted return accounting for holding periods.
    
    This method:
    1. Sorts trades by entry timepoint
    2. Calculates the sequence of investments over time
    3. Accounts for capital being tied up during holding periods
    4. Returns the final portfolio value and time-weighted return
    """
    
    if len(portfolio_trades) == 0:
        return initial_investment, 0.0, []
    
    # Sort trades by entry timepoint
    trades_sorted = portfolio_trades.sort_values('Entry_Timepoint').copy()
    
    # Track portfolio over time
    portfolio_value = initial_investment
    cash_available = initial_investment
    active_positions = []
    portfolio_history = []
    
    for idx, trade in trades_sorted.iterrows():
        entry_time = trade['Entry_Timepoint']
        exit_time = trade['Exit_Timepoint']
        holding_period = trade['Holding_Period']
        trade_return = trade['Final_Return']
        
        # Check if we have enough cash to make this trade
        # Allocate equal amounts to each trade (position sizing)
        position_size = cash_available * 0.1  # Use 10% of available cash per trade
        
        if position_size > 0:
            # Enter position
            active_positions.append({
                'entry_time': entry_time,
                'exit_time': exit_time,
                'position_size': position_size,
                'return': trade_return,
                'symbol': trade['Variable Name']
            })
            
            cash_available -= position_size
            
            # Check for positions that should close at this timepoint
            positions_to_close = []
            for pos_idx, position in enumerate(active_positions):
                if position['exit_time'] <= entry_time:
                    positions_to_close.append(pos_idx)
            
            # Close positions and return cash
            for pos_idx in reversed(positions_to_close):  # Reverse to maintain indices
                position = active_positions.pop(pos_idx)
                returned_cash = position['position_size'] * (1 + position['return'])
                cash_available += returned_cash
            
            # Record portfolio state
            active_value = sum(pos['position_size'] for pos in active_positions)
            total_value = cash_available + active_value
            
            portfolio_history.append({
                'timepoint': entry_time,
                'cash': cash_available,
                'active_positions_value': active_value,
                'total_value': total_value,
                'num_active_positions': len(active_positions)
            })
    
    # Close all remaining positions at the end
    final_cash = cash_available
    for position in active_positions:
        returned_cash = position['position_size'] * (1 + position['return'])
        final_cash += returned_cash
    
    final_return = (final_cash - initial_investment) / initial_investment
    
    return final_cash, final_return, portfolio_history

def run_single_simulation(args):
    """Run a single Monte Carlo simulation"""
    sim_id, returns_data, initial_investment, strategy = args
    
    if strategy == 'random_sample':
        # Randomly sample a subset of trades
        sample_size = min(len(returns_data), np.random.poisson(50))  # Average 50 trades per simulation
        if sample_size > 0:
            sampled_trades = returns_data.sample(n=sample_size, replace=False)
        else:
            sampled_trades = pd.DataFrame()
    
    elif strategy == 'sequential_chunks':
        # Take sequential chunks of trades (simulating following the strategy over time)
        chunk_size = np.random.randint(20, 100)  # Random chunk size
        start_idx = np.random.randint(0, max(1, len(returns_data) - chunk_size))
        sampled_trades = returns_data.iloc[start_idx:start_idx + chunk_size]
    
    elif strategy == 'timepoint_windows':
        # Sample trades from random timepoint windows
        window_size = np.random.randint(10, 50)  # Random window of timepoints
        timepoints = returns_data['Timepoint Index'].unique()
        if len(timepoints) > window_size:
            start_tp = np.random.choice(timepoints[:-window_size])
            end_tp = start_tp + window_size
            sampled_trades = returns_data[
                (returns_data['Timepoint Index'] >= start_tp) & 
                (returns_data['Timepoint Index'] <= end_tp)
            ]
        else:
            sampled_trades = returns_data
    
    else:  # 'all_trades'
        sampled_trades = returns_data
    
    # Calculate returns
    if len(sampled_trades) > 0:
        final_value, final_return, portfolio_history = calculate_time_weighted_return(
            sampled_trades, initial_investment
        )
    else:
        final_value = initial_investment
        final_return = 0.0
        portfolio_history = []
    
    return {
        'simulation_id': sim_id,
        'final_value': final_value,
        'final_return': final_return,
        'num_trades': len(sampled_trades),
        'portfolio_history': portfolio_history
    }

def run_monte_carlo_simulations(returns_file, num_simulations=1000, initial_investment=10000):
    """Run Monte Carlo simulations on trading strategy"""
    
    print("="*80)
    print("MONTE CARLO SIMULATIONS - TRADING STRATEGY ANALYSIS")
    print("="*80)
    
    # Load returns data
    print("Loading returns data...")
    returns_data = pd.read_csv(returns_file)
    print(f"Loaded {len(returns_data)} trades with returns")
    
    # Display data summary
    print(f"\nDATA SUMMARY:")
    print(f"Timepoint range: {returns_data['Timepoint Index'].min()} to {returns_data['Timepoint Index'].max()}")
    print(f"Date range: {returns_data['Start Timepoint'].min()} to {returns_data['End Timepoint'].max()}")
    print(f"Mean return per trade: {returns_data['Final_Return'].mean():.4f} ({returns_data['Final_Return'].mean()*100:.2f}%)")
    print(f"Win rate: {(returns_data['Final_Return'] > 0).mean():.2%}")
    print(f"Mean holding period: {returns_data['Holding_Period'].mean():.1f} days")
    
    # Define simulation strategies
    strategies = {
        'random_sample': 'Random sampling of trades',
        'sequential_chunks': 'Sequential chunks of trades over time',
        'timepoint_windows': 'Random timepoint windows',
        'all_trades': 'Use all available trades'
    }
    
    all_simulation_results = {}
    
    for strategy_name, strategy_desc in strategies.items():
        print(f"\n" + "="*60)
        print(f"RUNNING STRATEGY: {strategy_name.upper()}")
        print(f"Description: {strategy_desc}")
        print("="*60)
        
        start_time = time.time()
        
        # Prepare arguments for parallel processing
        args_list = [
            (i, returns_data, initial_investment, strategy_name) 
            for i in range(num_simulations)
        ]
        
        simulation_results = []
        
        # Run simulations in parallel
        with ProcessPoolExecutor(max_workers=NUM_PROCESSES) as executor:
            future_to_sim = {
                executor.submit(run_single_simulation, args): args[0] 
                for args in args_list
            }
            
            completed = 0
            for future in as_completed(future_to_sim):
                sim_id = future_to_sim[future]
                try:
                    result = future.result()
                    simulation_results.append(result)
                    completed += 1
                    
                    if completed % 100 == 0:
                        print(f"Completed {completed}/{num_simulations} simulations...")
                        
                except Exception as e:
                    print(f"Simulation {sim_id} failed: {e}")
        
        # Analyze results
        simulation_df = pd.DataFrame(simulation_results)
        
        final_values = simulation_df['final_value']
        final_returns = simulation_df['final_return']
        
        print(f"\nSTRATEGY RESULTS: {strategy_name}")
        print(f"Simulations completed: {len(simulation_results)}")
        print(f"Execution time: {time.time() - start_time:.2f} seconds")
        
        print(f"\nPORTFOLIO VALUE STATISTICS:")
        print(f"Mean final value: ${final_values.mean():.2f}")
        print(f"Median final value: ${final_values.median():.2f}")
        print(f"Standard deviation: ${final_values.std():.2f}")
        print(f"Min final value: ${final_values.min():.2f}")
        print(f"Max final value: ${final_values.max():.2f}")
        
        print(f"\nRETURN STATISTICS:")
        print(f"Mean return: {final_returns.mean():.4f} ({final_returns.mean()*100:.2f}%)")
        print(f"Median return: {final_returns.median():.4f} ({final_returns.median()*100:.2f}%)")
        print(f"Standard deviation: {final_returns.std():.4f} ({final_returns.std()*100:.2f}%)")
        print(f"Min return: {final_returns.min():.4f} ({final_returns.min()*100:.2f}%)")
        print(f"Max return: {final_returns.max():.4f} ({final_returns.max()*100:.2f}%)")
        
        print(f"\nRISK METRICS:")
        print(f"Probability of profit: {(final_returns > 0).mean():.2%}")
        print(f"Probability of loss > 10%: {(final_returns < -0.1).mean():.2%}")
        print(f"Probability of gain > 20%: {(final_returns > 0.2).mean():.2%}")
        
        # Percentile analysis
        percentiles = [5, 10, 25, 50, 75, 90, 95]
        print(f"\nPERCENTILE ANALYSIS (Returns):")
        for p in percentiles:
            value = np.percentile(final_returns, p)
            print(f"  {p}th percentile: {value:.4f} ({value*100:.2f}%)")
        
        # Store results for comparison
        all_simulation_results[strategy_name] = {
            'results_df': simulation_df,
            'final_values': final_values,
            'final_returns': final_returns,
            'description': strategy_desc
        }
        
        # Save individual strategy results
        strategy_filename = os.path.join(MONTECARLO_DIR, f'montecarlo_{strategy_name}_{num_simulations}_sims.csv')
        simulation_df.to_csv(strategy_filename, index=False)
        print(f"Results saved to: {strategy_filename}")
    
    # Create comprehensive summary
    print(f"\n" + "="*80)
    print("MONTE CARLO SIMULATION SUMMARY")
    print("="*80)
    
    summary_data = []
    for strategy_name, results in all_simulation_results.items():
        returns = results['final_returns']
        summary_data.append({
            'Strategy': strategy_name,
            'Description': results['description'],
            'Mean_Return': returns.mean(),
            'Median_Return': returns.median(),
            'Std_Return': returns.std(),
            'Min_Return': returns.min(),
            'Max_Return': returns.max(),
            'Prob_Profit': (returns > 0).mean(),
            'Prob_Loss_10pct': (returns < -0.1).mean(),
            'Prob_Gain_20pct': (returns > 0.2).mean(),
            'VaR_5pct': np.percentile(returns, 5),
            'VaR_1pct': np.percentile(returns, 1)
        })
    
    summary_df = pd.DataFrame(summary_data)
    
    print("\nSTRATEGY COMPARISON:")
    print(summary_df.round(4).to_string(index=False))
    
    # Save comprehensive results
    summary_filename = os.path.join(MONTECARLO_DIR, f'montecarlo_summary_{num_simulations}_simulations.csv')
    summary_df.to_csv(summary_filename, index=False)
    
    print(f"\nAll results saved to: {MONTECARLO_DIR}")
    print(f"Summary file: {summary_filename}")
    
    return all_simulation_results, summary_df

def create_visualizations(simulation_results, summary_df):
    """Create visualizations of Monte Carlo results"""
    
    print("\nCreating visualizations...")
    
    # Set up the plotting style
    plt.style.use('default')
    sns.set_palette("husl")
    
    # Create figure with subplots
    fig, axes = plt.subplots(2, 2, figsize=(15, 12))
    fig.suptitle('Monte Carlo Simulation Results - Trading Strategy Analysis', fontsize=16)
    
    # Plot 1: Return distributions
    ax1 = axes[0, 0]
    for strategy_name, results in simulation_results.items():
        returns_pct = results['final_returns'] * 100
        ax1.hist(returns_pct, bins=50, alpha=0.6, label=strategy_name, density=True)
    
    ax1.set_xlabel('Portfolio Return (%)')
    ax1.set_ylabel('Density')
    ax1.set_title('Distribution of Portfolio Returns')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: Value distributions
    ax2 = axes[0, 1]
    for strategy_name, results in simulation_results.items():
        values = results['final_values']
        ax2.hist(values, bins=50, alpha=0.6, label=strategy_name, density=True)
    
    ax2.set_xlabel('Final Portfolio Value ($)')
    ax2.set_ylabel('Density')
    ax2.set_title('Distribution of Final Portfolio Values')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # Plot 3: Risk-Return scatter
    ax3 = axes[1, 0]
    for strategy_name, results in simulation_results.items():
        mean_return = results['final_returns'].mean()
        std_return = results['final_returns'].std()
        ax3.scatter(std_return * 100, mean_return * 100, s=100, label=strategy_name, alpha=0.7)
    
    ax3.set_xlabel('Return Standard Deviation (%)')
    ax3.set_ylabel('Mean Return (%)')
    ax3.set_title('Risk-Return Profile')
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    
    # Plot 4: Summary statistics comparison
    ax4 = axes[1, 1]
    metrics = ['Mean_Return', 'Prob_Profit', 'VaR_5pct']
    x_pos = np.arange(len(summary_df))
    width = 0.2
    
    for i, metric in enumerate(metrics):
        values = summary_df[metric] * 100 if 'Return' in metric or 'VaR' in metric else summary_df[metric]
        ax4.bar(x_pos + i * width, values, width, label=metric, alpha=0.7)
    
    ax4.set_xlabel('Strategy')
    ax4.set_ylabel('Value (%)')
    ax4.set_title('Key Metrics Comparison')
    ax4.set_xticks(x_pos + width)
    ax4.set_xticklabels(summary_df['Strategy'], rotation=45)
    ax4.legend()
    ax4.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # Save the plot
    plot_filename = os.path.join(MONTECARLO_DIR, 'montecarlo_analysis_plots.png')
    plt.savefig(plot_filename, dpi=300, bbox_inches='tight')
    print(f"Plots saved to: {plot_filename}")
    
    plt.show()

def main():
    """Main function for Monte Carlo simulations"""
    
    create_montecarlo_directory()
    
    # File paths
    returns_file = os.path.join(RETURNS_DIR, 'trading_signals_with_returns_250_timepoints_start75.csv')
    
    print(f"Monte Carlo Analysis Configuration:")
    print(f"Returns file: {returns_file}")
    print(f"Initial investment: ${INITIAL_INVESTMENT:,}")
    print(f"Number of simulations: {NUM_SIMULATIONS:,}")
    print(f"Parallel processes: {NUM_PROCESSES}")
    
    if not os.path.exists(returns_file):
        print(f"\nError: Returns file not found: {returns_file}")
        print("Please run the return calculation first.")
        return
    
    # Run Monte Carlo simulations
    start_time = time.time()
    simulation_results, summary_df = run_monte_carlo_simulations(
        returns_file, NUM_SIMULATIONS, INITIAL_INVESTMENT
    )
    
    # Create visualizations
    create_visualizations(simulation_results, summary_df)
    
    total_time = time.time() - start_time
    print(f"\n" + "="*80)
    print("MONTE CARLO ANALYSIS COMPLETE!")
    print("="*80)
    print(f"Total execution time: {total_time:.2f} seconds")
    print(f"Results directory: {MONTECARLO_DIR}")

if __name__ == "__main__":
    main()