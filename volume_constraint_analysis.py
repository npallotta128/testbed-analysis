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
NUM_SIMULATIONS = 1000  # 1000 Monte Carlo simulations
NUM_PROCESSES = min(8, mp.cpu_count())  # Use multiple cores
MAX_POSITION_PCT = 0.05  # Maximum 5% of capital per position

# Volume constraint levels to test
VOLUME_CONSTRAINT_LEVELS = [0.01, 0.02, 0.05]  # 1%, 2%, 5% of (volume * price)

# Investment amounts to test scalability
INVESTMENT_AMOUNTS = [1_000_000, 10_000_000, 100_000_000]  # $1M, $10M, $100M

def create_montecarlo_directory():
    """Create Monte Carlo directory on D drive"""
    if not os.path.exists(MONTECARLO_DIR):
        os.makedirs(MONTECARLO_DIR)
        print(f"Created directory: {MONTECARLO_DIR}")

def calculate_scalable_capital_allocation_return(returns_data, initial_investment, start_timepoint, volume_constraint_pct):
    """
    Calculate returns using enhanced capital allocation strategy with variable volume constraints:
    - Deploy capital in allotments no bigger than 5% of total capital
    - Deploy capital in allotments no bigger than volume_constraint_pct of (volume * price)
    - Capital may grow over 5% when invested
    - Randomly choose available signals when capital is available
    - Start randomly at any of the first 5 timepoints
    - Invest until the last timepoint
    """
    
    # Filter data to start from the chosen timepoint
    available_trades = returns_data[returns_data['Timepoint Index'] >= start_timepoint].copy()
    
    if len(available_trades) == 0:
        return initial_investment, 0.0, [], {}
    
    # Sort trades by entry timepoint for chronological processing
    available_trades = available_trades.sort_values('Entry_Timepoint').copy()
    
    # Track portfolio state
    current_capital = initial_investment
    active_positions = []
    portfolio_history = []
    volume_limited_count = 0
    capital_limited_count = 0
    
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
        
        # Try to invest in signals while capital and both constraints allow
        for idx, signal in timepoint_signals.iterrows():
            # Calculate maximum position size based on capital (5% of current total capital)
            total_portfolio_value = current_capital + sum(pos['invested_amount'] for pos in active_positions)
            max_capital_position = total_portfolio_value * MAX_POSITION_PCT
            
            # Calculate maximum position size based on volume constraint
            volume = signal['Volume']
            price = signal['Price']
            market_capacity = volume * price * volume_constraint_pct
            
            # Take the minimum of the two constraints
            max_position_size = min(max_capital_position, market_capacity)
            
            # Check if we have available cash for this position
            if current_capital >= max_position_size and max_position_size > 0:
                # Invest in this signal
                invested_amount = max_position_size
                current_capital -= invested_amount
                
                # Track which constraint was binding
                if market_capacity < max_capital_position:
                    volume_limited_count += 1
                else:
                    capital_limited_count += 1
                
                active_positions.append({
                    'entry_timepoint': signal['Entry_Timepoint'],
                    'exit_timepoint': signal['Exit_Timepoint'],
                    'invested_amount': invested_amount,
                    'return': signal['Final_Return'],
                    'symbol': signal['Variable Name'],
                    'signal_type': signal['Type'],
                    'volume_constraint': market_capacity,
                    'capital_constraint': max_capital_position,
                    'binding_constraint': 'volume' if market_capacity < max_capital_position else 'capital'
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
            'max_position_size_capital': total_value * MAX_POSITION_PCT,
            'volume_limited_positions': volume_limited_count,
            'capital_limited_positions': capital_limited_count
        })
    
    # Close all remaining positions at the end
    final_capital = current_capital
    for position in active_positions:
        returned_amount = position['invested_amount'] * (1 + position['return'])
        final_capital += returned_amount
    
    final_return = (final_capital - initial_investment) / initial_investment
    
    # Calculate constraint statistics
    total_positions = volume_limited_count + capital_limited_count
    volume_constraint_pct_actual = volume_limited_count / total_positions if total_positions > 0 else 0
    capital_constraint_pct_actual = capital_limited_count / total_positions if total_positions > 0 else 0
    
    return final_capital, final_return, portfolio_history, {
        'volume_limited_count': volume_limited_count,
        'capital_limited_count': capital_limited_count,
        'volume_constraint_pct': volume_constraint_pct_actual,
        'capital_constraint_pct': capital_constraint_pct_actual,
        'total_positions': total_positions
    }

def run_scalable_capital_allocation_simulation(args):
    """Run a single scalable capital allocation simulation"""
    sim_id, returns_data, initial_investment, volume_constraint_pct = args
    
    # Randomly choose starting timepoint from first 5
    start_timepoint = np.random.choice(range(1, 6))  # Timepoints 1, 2, 3, 4, or 5
    
    # Calculate returns using enhanced capital allocation strategy
    final_value, final_return, portfolio_history, constraint_stats = calculate_scalable_capital_allocation_return(
        returns_data, initial_investment, start_timepoint, volume_constraint_pct
    )
    
    # Calculate simulation statistics
    num_trades = len([h for h in portfolio_history if h['num_active_positions'] > 0])
    max_positions = max([h['num_active_positions'] for h in portfolio_history] + [0])
    avg_utilization = np.mean([h['active_positions_value'] / h['total_value'] 
                              for h in portfolio_history if h['total_value'] > 0])
    
    return {
        'simulation_id': sim_id,
        'start_timepoint': start_timepoint,
        'initial_investment': initial_investment,
        'volume_constraint_pct': volume_constraint_pct,
        'final_value': final_value,
        'final_return': final_return,
        'num_timepoints_active': num_trades,
        'max_concurrent_positions': max_positions,
        'avg_capital_utilization': avg_utilization,
        'volume_limited_count': constraint_stats['volume_limited_count'],
        'capital_limited_count': constraint_stats['capital_limited_count'],
        'volume_constraint_pct_actual': constraint_stats['volume_constraint_pct'],
        'capital_constraint_pct_actual': constraint_stats['capital_constraint_pct'],
        'total_positions': constraint_stats['total_positions'],
        'portfolio_history': portfolio_history
    }

def run_volume_constraint_monte_carlo(returns_file, investment_amounts, volume_constraints, num_simulations=1000):
    """Run Monte Carlo simulations for different volume constraints and investment amounts"""
    
    print("="*80)
    print("VOLUME CONSTRAINT SCALABILITY MONTE CARLO SIMULATIONS")
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
    print(f"Mean volume: ${returns_data['Volume'].mean():,.0f}")
    print(f"Mean price: ${returns_data['Price'].mean():.2f}")
    
    print(f"\nSTRATEGY PARAMETERS:")
    print(f"- Maximum position size: {MAX_POSITION_PCT*100:.1f}% of total capital")
    print(f"- Volume constraints tested: {[f'{vc*100:.1f}%' for vc in volume_constraints]}")
    print(f"- Investment amounts: {[f'${amt:,}' for amt in investment_amounts]}")
    
    all_results = {}
    
    for volume_constraint in volume_constraints:
        print(f"\n" + "="*60)
        print(f"TESTING VOLUME CONSTRAINT: {volume_constraint*100:.1f}% of (volume × price)")
        print("="*60)
        
        volume_results = {}
        
        for investment_amount in investment_amounts:
            print(f"\n--- Investment Amount: ${investment_amount:,} ---")
            
            start_time = time.time()
            
            # Prepare arguments for parallel processing
            args_list = [
                (i, returns_data, investment_amount, volume_constraint) 
                for i in range(num_simulations)
            ]
            
            simulation_results = []
            
            # Run simulations in parallel
            print(f"Running {num_simulations} simulations...")
            
            with ProcessPoolExecutor(max_workers=NUM_PROCESSES) as executor:
                future_to_sim = {
                    executor.submit(run_scalable_capital_allocation_simulation, args): args[0] 
                    for args in args_list
                }
                
                completed = 0
                for future in as_completed(future_to_sim):
                    sim_id = future_to_sim[future]
                    try:
                        result = future.result()
                        simulation_results.append(result)
                        completed += 1
                        
                        if completed % 200 == 0:
                            print(f"  Completed {completed}/{num_simulations} simulations...")
                            
                    except Exception as e:
                        print(f"Simulation {sim_id} failed: {e}")
            
            # Analyze results
            simulation_df = pd.DataFrame([
                {
                    'simulation_id': r['simulation_id'],
                    'start_timepoint': r['start_timepoint'],
                    'initial_investment': r['initial_investment'],
                    'volume_constraint_pct': r['volume_constraint_pct'],
                    'final_value': r['final_value'],
                    'final_return': r['final_return'],
                    'num_timepoints_active': r['num_timepoints_active'],
                    'max_concurrent_positions': r['max_concurrent_positions'],
                    'avg_capital_utilization': r['avg_capital_utilization'],
                    'volume_limited_count': r['volume_limited_count'],
                    'capital_limited_count': r['capital_limited_count'],
                    'volume_constraint_pct_actual': r['volume_constraint_pct_actual'],
                    'capital_constraint_pct_actual': r['capital_constraint_pct_actual'],
                    'total_positions': r['total_positions']
                }
                for r in simulation_results
            ])
            
            execution_time = time.time() - start_time
            
            # Performance Statistics
            final_returns = simulation_df['final_return']
            
            print(f"Volume: {volume_constraint*100:.1f}%, Investment: ${investment_amount:,}")
            print(f"Mean return: {final_returns.mean():.2%}")
            print(f"Volume-limited: {simulation_df['volume_constraint_pct_actual'].mean():.1%}")
            print(f"Positions: {simulation_df['total_positions'].mean():.0f}")
            print(f"Capital util: {simulation_df['avg_capital_utilization'].mean():.1%}")
            print(f"Time: {execution_time:.1f}s")
            
            # Save results
            vol_label = f"{volume_constraint*100:.0f}pct"
            inv_label = f"${investment_amount//1_000_000}M"
            results_filename = os.path.join(MONTECARLO_DIR, f'volume_constraint_{vol_label}_{inv_label}_sims.csv')
            simulation_df.to_csv(results_filename, index=False)
            
            # Store for comparison
            volume_results[investment_amount] = {
                'simulation_df': simulation_df,
                'final_returns': final_returns,
                'execution_time': execution_time
            }
        
        all_results[volume_constraint] = volume_results
    
    return all_results

def create_comprehensive_volume_comparison(all_results):
    """Create comprehensive comparison across volume constraints and investment amounts"""
    
    print(f"\n" + "="*80)
    print("COMPREHENSIVE VOLUME CONSTRAINT COMPARISON")
    print("="*80)
    
    comparison_data = []
    
    for volume_constraint, volume_results in all_results.items():
        for investment_amount, results in volume_results.items():
            simulation_df = results['simulation_df']
            final_returns = results['final_returns']
            
            comparison_data.append({
                'Volume_Constraint_Pct': volume_constraint,
                'Volume_Constraint_Label': f"{volume_constraint*100:.1f}%",
                'Investment_Amount': investment_amount,
                'Investment_Label': f"${investment_amount//1_000_000}M",
                'Mean_Return': final_returns.mean(),
                'Median_Return': final_returns.median(),
                'Std_Return': final_returns.std(),
                'Min_Return': final_returns.min(),
                'Max_Return': final_returns.max(),
                'Prob_Profit': (final_returns > 0).mean(),
                'Prob_Loss_10pct': (final_returns < -0.1).mean(),
                'Prob_Gain_20pct': (final_returns > 0.2).mean(),
                'Prob_Gain_50pct': (final_returns > 0.5).mean(),
                'Mean_Positions': simulation_df['total_positions'].mean(),
                'Volume_Limited_Pct': simulation_df['volume_constraint_pct_actual'].mean(),
                'Capital_Limited_Pct': simulation_df['capital_constraint_pct_actual'].mean(),
                'Mean_Max_Positions': simulation_df['max_concurrent_positions'].mean(),
                'Mean_Capital_Utilization': simulation_df['avg_capital_utilization'].mean(),
                'VaR_5pct': np.percentile(final_returns, 5),
                'VaR_1pct': np.percentile(final_returns, 1)
            })
    
    comparison_df = pd.DataFrame(comparison_data)
    
    # Display key comparisons
    print("\nVOLUME CONSTRAINT IMPACT BY INVESTMENT SIZE:")
    print("=" * 70)
    
    for investment_amount in INVESTMENT_AMOUNTS:
        inv_label = f"${investment_amount//1_000_000}M"
        inv_data = comparison_df[comparison_df['Investment_Amount'] == investment_amount]
        
        print(f"\n{inv_label} Investment:")
        print("Vol Constraint | Mean Return | Volume Limited | Positions | Capital Util")
        print("-" * 70)
        for _, row in inv_data.iterrows():
            print(f"    {row['Volume_Constraint_Label']:>6} | "
                  f"   {row['Mean_Return']:>7.1%} | "
                  f"      {row['Volume_Limited_Pct']:>7.1%} | "
                  f"  {row['Mean_Positions']:>7.0f} | "
                  f"    {row['Mean_Capital_Utilization']:>7.1%}")
    
    print(f"\nINVESTMENT SIZE IMPACT BY VOLUME CONSTRAINT:")
    print("=" * 70)
    
    for volume_constraint in VOLUME_CONSTRAINT_LEVELS:
        vol_label = f"{volume_constraint*100:.1f}%"
        vol_data = comparison_df[comparison_df['Volume_Constraint_Pct'] == volume_constraint]
        
        print(f"\n{vol_label} Volume Constraint:")
        print("Investment | Mean Return | Volume Limited | Positions | Capital Util")
        print("-" * 70)
        for _, row in vol_data.iterrows():
            print(f"     {row['Investment_Label']:>4} | "
                  f"   {row['Mean_Return']:>7.1%} | "
                  f"      {row['Volume_Limited_Pct']:>7.1%} | "
                  f"  {row['Mean_Positions']:>7.0f} | "
                  f"    {row['Mean_Capital_Utilization']:>7.1%}")
    
    # Key insights
    print(f"\n" + "="*60)
    print("KEY INSIGHTS:")
    print("="*60)
    
    # Volume constraint effectiveness
    for investment_amount in INVESTMENT_AMOUNTS:
        inv_label = f"${investment_amount//1_000_000}M"
        inv_data = comparison_df[comparison_df['Investment_Amount'] == investment_amount]
        returns_by_constraint = inv_data['Mean_Return'].values
        constraints_by_level = inv_data['Volume_Limited_Pct'].values
        
        print(f"\n{inv_label} Analysis:")
        print(f"  Returns: {returns_by_constraint[0]:.1%} → {returns_by_constraint[1]:.1%} → {returns_by_constraint[2]:.1%}")
        print(f"  Volume-limited: {constraints_by_level[0]:.1%} → {constraints_by_level[1]:.1%} → {constraints_by_level[2]:.1%}")
    
    # Save comprehensive comparison
    comparison_filename = os.path.join(MONTECARLO_DIR, 'volume_constraint_comprehensive_comparison.csv')
    comparison_df.to_csv(comparison_filename, index=False)
    print(f"\nComprehensive comparison saved to: {comparison_filename}")
    
    return comparison_df

def main():
    """Main function for volume constraint scalability Monte Carlo simulations"""
    
    create_montecarlo_directory()
    
    # File paths
    returns_file = os.path.join(RETURNS_DIR, 'trading_signals_with_returns_250_timepoints_start75.csv')
    
    print(f"Volume Constraint Scalability Monte Carlo Configuration:")
    print(f"Returns file: {returns_file}")
    print(f"Investment amounts: {[f'${amt:,}' for amt in INVESTMENT_AMOUNTS]}")
    print(f"Volume constraints: {[f'{vc*100:.1f}%' for vc in VOLUME_CONSTRAINT_LEVELS]}")
    print(f"Number of simulations per combination: {NUM_SIMULATIONS:,}")
    print(f"Max position size (capital): {MAX_POSITION_PCT*100:.1f}%")
    print(f"Parallel processes: {NUM_PROCESSES}")
    
    if not os.path.exists(returns_file):
        print(f"\nError: Returns file not found: {returns_file}")
        print("Please run the return calculation first.")
        return
    
    # Run volume constraint scalability Monte Carlo simulations
    start_time = time.time()
    all_results = run_volume_constraint_monte_carlo(
        returns_file, INVESTMENT_AMOUNTS, VOLUME_CONSTRAINT_LEVELS, NUM_SIMULATIONS
    )
    
    # Create comprehensive comparison
    comparison_df = create_comprehensive_volume_comparison(all_results)
    
    total_time = time.time() - start_time
    total_simulations = len(INVESTMENT_AMOUNTS) * len(VOLUME_CONSTRAINT_LEVELS) * NUM_SIMULATIONS
    
    print(f"\n" + "="*80)
    print("VOLUME CONSTRAINT SCALABILITY MONTE CARLO COMPLETE!")
    print("="*80)
    print(f"Total execution time: {total_time:.2f} seconds")
    print(f"Total simulations: {total_simulations:,}")
    print(f"Average time per simulation: {total_time/total_simulations:.3f} seconds")
    print(f"Results directory: {MONTECARLO_DIR}")

if __name__ == "__main__":
    main()