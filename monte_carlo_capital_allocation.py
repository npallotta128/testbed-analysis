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
MAX_POSITION_PCT = 0.05  # Maximum 5% of capital per position

def create_montecarlo_directory():
    """Create Monte Carlo directory on D drive"""
    if not os.path.exists(MONTECARLO_DIR):
        os.makedirs(MONTECARLO_DIR)
        print(f"Created directory: {MONTECARLO_DIR}")

def calculate_capital_allocation_return(returns_data, initial_investment, start_timepoint):
    """
    Calculate returns using capital allocation strategy:
    - Deploy capital in allotments no bigger than 5% of total
    - Capital may grow over 5% when invested
    - Randomly choose available signals when capital is available
    - Start randomly at any of the first 5 timepoints
    - Invest until the last timepoint
    """
    
    # Filter data to start from the chosen timepoint
    available_trades = returns_data[returns_data['Timepoint Index'] >= start_timepoint].copy()
    
    if len(available_trades) == 0:
        return initial_investment, 0.0, []
    
    # Sort trades by entry timepoint for chronological processing
    available_trades = available_trades.sort_values('Entry_Timepoint').copy()
    
    # Track portfolio state
    current_capital = initial_investment
    active_positions = []
    portfolio_history = []
    
    # Get all unique timepoints for processing
    all_timepoints = sorted(available_trades['Entry_Timepoint'].unique())
    
    for current_timepoint in all_timepoints:
        # Check for positions that should close at this timepoint
        positions_to_close = []
        for pos_idx, position in enumerate(active_positions):
            if position['exit_timepoint'] <= current_timepoint:
                positions_to_close.append(pos_idx)
        
        # Close positions and update capital
        for pos_idx in reversed(positions_to_close):  # Reverse to maintain indices
            position = active_positions.pop(pos_idx)
            returned_amount = position['invested_amount'] * (1 + position['return'])
            current_capital += returned_amount
        
        # Get available signals for this timepoint
        timepoint_signals = available_trades[
            available_trades['Entry_Timepoint'] == current_timepoint
        ].copy()
        
        if len(timepoint_signals) == 0:
            continue
        
        # Randomly shuffle signals for this timepoint
        timepoint_signals = timepoint_signals.sample(frac=1.0).reset_index(drop=True)
        
        # Try to invest in signals while capital and 5% rule allows
        for idx, signal in timepoint_signals.iterrows():
            # Calculate maximum position size (5% of current total capital)
            total_portfolio_value = current_capital + sum(pos['invested_amount'] for pos in active_positions)
            max_position_size = total_portfolio_value * MAX_POSITION_PCT
            
            # Check if we have available cash for this position
            if current_capital >= max_position_size:
                # Invest in this signal
                invested_amount = max_position_size
                current_capital -= invested_amount
                
                active_positions.append({
                    'entry_timepoint': signal['Entry_Timepoint'],
                    'exit_timepoint': signal['Exit_Timepoint'],
                    'invested_amount': invested_amount,
                    'return': signal['Final_Return'],
                    'symbol': signal['Variable Name'],
                    'signal_type': signal['Type']
                })
        
        # Record portfolio state
        active_value = sum(pos['invested_amount'] for pos in active_positions)
        total_value = current_capital + active_value
        
        portfolio_history.append({
            'timepoint': current_timepoint,
            'cash': current_capital,
            'active_positions_value': active_value,
            'total_value': total_value,
            'num_active_positions': len(active_positions),
            'max_position_size': total_value * MAX_POSITION_PCT
        })
    
    # Close all remaining positions at the end
    final_capital = current_capital
    for position in active_positions:
        returned_amount = position['invested_amount'] * (1 + position['return'])
        final_capital += returned_amount
    
    final_return = (final_capital - initial_investment) / initial_investment
    
    return final_capital, final_return, portfolio_history

def run_capital_allocation_simulation(args):
    """Run a single capital allocation simulation"""
    sim_id, returns_data, initial_investment = args
    
    # Randomly choose starting timepoint from first 5
    start_timepoint = np.random.choice(range(1, 6))  # Timepoints 1, 2, 3, 4, or 5
    
    # Calculate returns using capital allocation strategy
    final_value, final_return, portfolio_history = calculate_capital_allocation_return(
        returns_data, initial_investment, start_timepoint
    )
    
    # Calculate simulation statistics
    num_trades = len([h for h in portfolio_history if h['num_active_positions'] > 0])
    max_positions = max([h['num_active_positions'] for h in portfolio_history] + [0])
    avg_utilization = np.mean([h['active_positions_value'] / h['total_value'] 
                              for h in portfolio_history if h['total_value'] > 0])
    
    return {
        'simulation_id': sim_id,
        'start_timepoint': start_timepoint,
        'final_value': final_value,
        'final_return': final_return,
        'num_timepoints_active': num_trades,
        'max_concurrent_positions': max_positions,
        'avg_capital_utilization': avg_utilization,
        'portfolio_history': portfolio_history
    }

def run_capital_allocation_monte_carlo(returns_file, num_simulations=1000, initial_investment=10000):
    """Run Monte Carlo simulations using capital allocation strategy"""
    
    print("="*80)
    print("CAPITAL ALLOCATION MONTE CARLO SIMULATIONS")
    print("="*80)
    
    # Load returns data
    print("Loading returns data...")
    returns_data = pd.read_csv(returns_file)
    print(f"Loaded {len(returns_data)} trades with returns")
    
    # Display data summary
    print(f"\nDATA SUMMARY:")
    print(f"Timepoint range: {returns_data['Timepoint Index'].min()} to {returns_data['Timepoint Index'].max()}")
    print(f"Mean return per trade: {returns_data['Final_Return'].mean():.4f} ({returns_data['Final_Return'].mean()*100:.2f}%)")
    print(f"Win rate: {(returns_data['Final_Return'] > 0).mean():.2%}")
    
    print(f"\nSTRATEGY PARAMETERS:")
    print(f"- Maximum position size: {MAX_POSITION_PCT*100:.1f}% of total capital")
    print(f"- Random start timepoint: 1-5")
    print(f"- Random signal selection when capital available")
    print(f"- Trade until last timepoint (250)")
    
    start_time = time.time()
    
    # Prepare arguments for parallel processing
    args_list = [
        (i, returns_data, initial_investment) 
        for i in range(num_simulations)
    ]
    
    simulation_results = []
    
    # Run simulations in parallel
    print(f"\nRunning {num_simulations} simulations with {NUM_PROCESSES} processes...")
    
    with ProcessPoolExecutor(max_workers=NUM_PROCESSES) as executor:
        future_to_sim = {
            executor.submit(run_capital_allocation_simulation, args): args[0] 
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
    simulation_df = pd.DataFrame([
        {
            'simulation_id': r['simulation_id'],
            'start_timepoint': r['start_timepoint'],
            'final_value': r['final_value'],
            'final_return': r['final_return'],
            'num_timepoints_active': r['num_timepoints_active'],
            'max_concurrent_positions': r['max_concurrent_positions'],
            'avg_capital_utilization': r['avg_capital_utilization']
        }
        for r in simulation_results
    ])
    
    execution_time = time.time() - start_time
    
    print(f"\n" + "="*60)
    print("CAPITAL ALLOCATION STRATEGY RESULTS")
    print("="*60)
    print(f"Simulations completed: {len(simulation_results)}")
    print(f"Execution time: {execution_time:.2f} seconds")
    
    # Performance Statistics
    final_values = simulation_df['final_value']
    final_returns = simulation_df['final_return']
    
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
    print(f"Probability of gain > 50%: {(final_returns > 0.5).mean():.2%}")
    
    # Percentile analysis
    percentiles = [1, 5, 10, 25, 50, 75, 90, 95, 99]
    print(f"\nPERCENTILE ANALYSIS (Returns):")
    for p in percentiles:
        value = np.percentile(final_returns, p)
        print(f"  {p}th percentile: {value:.4f} ({value*100:.2f}%)")
    
    # Strategy-specific statistics
    print(f"\nSTRATEGY UTILIZATION STATISTICS:")
    print(f"Mean timepoints active: {simulation_df['num_timepoints_active'].mean():.1f}")
    print(f"Mean max concurrent positions: {simulation_df['max_concurrent_positions'].mean():.1f}")
    print(f"Mean capital utilization: {simulation_df['avg_capital_utilization'].mean():.2%}")
    
    # Starting timepoint analysis
    print(f"\nSTARTING TIMEPOINT ANALYSIS:")
    for tp in range(1, 6):
        tp_results = simulation_df[simulation_df['start_timepoint'] == tp]
        if len(tp_results) > 0:
            print(f"  Timepoint {tp}: {len(tp_results)} sims, "
                  f"mean return: {tp_results['final_return'].mean():.2%}")
    
    # Save results
    results_filename = os.path.join(MONTECARLO_DIR, 'capital_allocation_strategy_1000_sims.csv')
    simulation_df.to_csv(results_filename, index=False)
    print(f"\nResults saved to: {results_filename}")
    
    return simulation_df

def create_capital_allocation_visualizations(simulation_df):
    """Create visualizations for capital allocation strategy"""
    
    print("\nCreating visualizations...")
    
    # Set up the plotting style
    plt.style.use('default')
    sns.set_palette("husl")
    
    # Create figure with subplots
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    fig.suptitle('Capital Allocation Strategy - Monte Carlo Results', fontsize=16)
    
    # Plot 1: Return distribution
    ax1 = axes[0, 0]
    returns_pct = simulation_df['final_return'] * 100
    ax1.hist(returns_pct, bins=50, alpha=0.7, color='skyblue', edgecolor='black')
    ax1.axvline(returns_pct.mean(), color='red', linestyle='--', label=f'Mean: {returns_pct.mean():.1f}%')
    ax1.axvline(returns_pct.median(), color='orange', linestyle='--', label=f'Median: {returns_pct.median():.1f}%')
    ax1.set_xlabel('Portfolio Return (%)')
    ax1.set_ylabel('Frequency')
    ax1.set_title('Distribution of Portfolio Returns')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: Final value distribution
    ax2 = axes[0, 1]
    final_values = simulation_df['final_value']
    ax2.hist(final_values, bins=50, alpha=0.7, color='lightgreen', edgecolor='black')
    ax2.axvline(final_values.mean(), color='red', linestyle='--', label=f'Mean: ${final_values.mean():.0f}')
    ax2.axvline(final_values.median(), color='orange', linestyle='--', label=f'Median: ${final_values.median():.0f}')
    ax2.set_xlabel('Final Portfolio Value ($)')
    ax2.set_ylabel('Frequency')
    ax2.set_title('Distribution of Final Portfolio Values')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # Plot 3: Starting timepoint performance
    ax3 = axes[0, 2]
    start_tp_returns = []
    start_tp_labels = []
    for tp in range(1, 6):
        tp_data = simulation_df[simulation_df['start_timepoint'] == tp]['final_return'] * 100
        if len(tp_data) > 0:
            start_tp_returns.append(tp_data)
            start_tp_labels.append(f'TP {tp}')
    
    ax3.boxplot(start_tp_returns, labels=start_tp_labels)
    ax3.set_xlabel('Starting Timepoint')
    ax3.set_ylabel('Return (%)')
    ax3.set_title('Returns by Starting Timepoint')
    ax3.grid(True, alpha=0.3)
    
    # Plot 4: Capital utilization
    ax4 = axes[1, 0]
    utilization_pct = simulation_df['avg_capital_utilization'] * 100
    ax4.hist(utilization_pct, bins=30, alpha=0.7, color='coral', edgecolor='black')
    ax4.axvline(utilization_pct.mean(), color='red', linestyle='--', 
                label=f'Mean: {utilization_pct.mean():.1f}%')
    ax4.set_xlabel('Average Capital Utilization (%)')
    ax4.set_ylabel('Frequency')
    ax4.set_title('Distribution of Capital Utilization')
    ax4.legend()
    ax4.grid(True, alpha=0.3)
    
    # Plot 5: Concurrent positions
    ax5 = axes[1, 1]
    max_positions = simulation_df['max_concurrent_positions']
    ax5.hist(max_positions, bins=range(int(max_positions.max()) + 2), 
             alpha=0.7, color='gold', edgecolor='black')
    ax5.axvline(max_positions.mean(), color='red', linestyle='--', 
                label=f'Mean: {max_positions.mean():.1f}')
    ax5.set_xlabel('Maximum Concurrent Positions')
    ax5.set_ylabel('Frequency')
    ax5.set_title('Distribution of Max Concurrent Positions')
    ax5.legend()
    ax5.grid(True, alpha=0.3)
    
    # Plot 6: Return vs Utilization scatter
    ax6 = axes[1, 2]
    scatter = ax6.scatter(simulation_df['avg_capital_utilization'] * 100, 
                         simulation_df['final_return'] * 100,
                         alpha=0.6, c=simulation_df['start_timepoint'], 
                         cmap='viridis', s=20)
    ax6.set_xlabel('Average Capital Utilization (%)')
    ax6.set_ylabel('Final Return (%)')
    ax6.set_title('Return vs Capital Utilization')
    ax6.grid(True, alpha=0.3)
    plt.colorbar(scatter, ax=ax6, label='Start Timepoint')
    
    plt.tight_layout()
    
    # Save the plot
    plot_filename = os.path.join(MONTECARLO_DIR, 'capital_allocation_strategy_plots.png')
    plt.savefig(plot_filename, dpi=300, bbox_inches='tight')
    print(f"Plots saved to: {plot_filename}")
    
    plt.show()

def main():
    """Main function for capital allocation Monte Carlo simulations"""
    
    create_montecarlo_directory()
    
    # File paths
    returns_file = os.path.join(RETURNS_DIR, 'trading_signals_with_returns_250_timepoints_start75.csv')
    
    print(f"Capital Allocation Monte Carlo Configuration:")
    print(f"Returns file: {returns_file}")
    print(f"Initial investment: ${INITIAL_INVESTMENT:,}")
    print(f"Number of simulations: {NUM_SIMULATIONS:,}")
    print(f"Max position size: {MAX_POSITION_PCT*100:.1f}% of total capital")
    print(f"Parallel processes: {NUM_PROCESSES}")
    
    if not os.path.exists(returns_file):
        print(f"\nError: Returns file not found: {returns_file}")
        print("Please run the return calculation first.")
        return
    
    # Run Monte Carlo simulations
    start_time = time.time()
    simulation_df = run_capital_allocation_monte_carlo(
        returns_file, NUM_SIMULATIONS, INITIAL_INVESTMENT
    )
    
    # Create visualizations
    create_capital_allocation_visualizations(simulation_df)
    
    total_time = time.time() - start_time
    print(f"\n" + "="*80)
    print("CAPITAL ALLOCATION MONTE CARLO COMPLETE!")
    print("="*80)
    print(f"Total execution time: {total_time:.2f} seconds")
    print(f"Results directory: {MONTECARLO_DIR}")

if __name__ == "__main__":
    main()