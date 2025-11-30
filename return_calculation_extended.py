import pandas as pd
import numpy as np
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing as mp
import time

def calculate_signal_returns_extended(data_file, signals_file, output_file):
    """
    Calculate returns for trading signals - extended version for Monte Carlo preparation.
    
    Args:
        data_file: Path to the main data CSV file
        signals_file: Path to the trading signals CSV file
        output_file: Path to save the results with returns
    """
    
    print("Loading data and signals...")
    
    # Load signals
    signals_df = pd.read_csv(signals_file)
    print(f"Loaded {len(signals_df)} signals")
    
    # Load price data
    print("Loading price data...")
    data = pd.read_csv(data_file)
    
    # Create pivot table for faster lookups
    print("Creating price pivot table...")
    price_pivot = data.pivot_table(index='Date', columns='Symbol', values='Closing', aggfunc='first')
    dates = price_pivot.index.tolist()
    
    print(f"Price data shape: {price_pivot.shape}")
    print(f"Date range: {dates[0]} to {dates[-1]}")
    
    # Add timepoint information to signals
    signals_df['Signal_Timepoint'] = signals_df['End Timepoint'] - 2000  # Convert back to original timepoint numbering
    
    # Calculate returns for each signal
    results = []
    
    for idx, row in signals_df.iterrows():
        if idx % 500 == 0:
            print(f"Processing signal {idx + 1}/{len(signals_df)}")
        
        symbol = row['Variable Name']
        signal_type = row['Type']  # 'Long' or 'Short'
        end_timepoint = row['End Timepoint']  # This is where the signal was generated
        signal_timepoint = row['Signal_Timepoint']
        
        # Position opens at the timepoint after signal calculation
        position_open_timepoint = end_timepoint + 1
        
        # Check if we have enough data
        if position_open_timepoint >= len(dates):
            continue
        
        if symbol not in price_pivot.columns:
            continue
        
        # Get entry price
        entry_price = price_pivot.iloc[position_open_timepoint][symbol]
        if pd.isna(entry_price) or entry_price <= 0:
            continue
        
        # Calculate returns for next 20 timepoints
        returns_data = calculate_position_return(
            price_pivot, symbol, position_open_timepoint, signal_type, entry_price
        )
        
        if returns_data is not None:
            result = row.to_dict()
            result.update(returns_data)
            results.append(result)
    
    # Create results DataFrame
    results_df = pd.DataFrame(results)
    
    if not results_df.empty:
        print(f"\nCalculated returns for {len(results_df)} signals")
        print(f"Successfully closed positions: {len(results_df[results_df['Position_Closed'] == True])}")
        print(f"Positions stopped at 20 timepoints: {len(results_df[results_df['Position_Closed'] == False])}")
        
        # Add additional metrics for Monte Carlo
        results_df['Daily_Returns'] = results_df.apply(lambda row: calculate_daily_returns(price_pivot, row), axis=1)
        results_df['Volatility'] = results_df['Daily_Returns'].apply(lambda x: np.std(x) if len(x) > 1 else 0)
        results_df['Max_Drawdown'] = results_df['Daily_Returns'].apply(lambda x: calculate_max_drawdown(x))
        
        # Summary statistics
        print(f"\nReturn Statistics:")
        print(f"Mean return: {results_df['Final_Return'].mean():.4f}")
        print(f"Median return: {results_df['Final_Return'].median():.4f}")
        print(f"Std return: {results_df['Final_Return'].std():.4f}")
        print(f"Min return: {results_df['Final_Return'].min():.4f}")
        print(f"Max return: {results_df['Final_Return'].max():.4f}")
        
        # Long vs Short performance
        long_returns = results_df[results_df['Type'] == 'Long']['Final_Return']
        short_returns = results_df[results_df['Type'] == 'Short']['Final_Return']
        
        if len(long_returns) > 0:
            print(f"\nLong positions ({len(long_returns)}):")
            print(f"  Mean return: {long_returns.mean():.4f}")
            print(f"  Win rate: {(long_returns > 0).mean():.2%}")
        
        if len(short_returns) > 0:
            print(f"\nShort positions ({len(short_returns)}):")
            print(f"  Mean return: {short_returns.mean():.4f}")
            print(f"  Win rate: {(short_returns > 0).mean():.2%}")
        
        # Performance by timepoint (for Monte Carlo analysis)
        timepoint_performance = results_df.groupby('Signal_Timepoint')['Final_Return'].agg(['count', 'mean', 'std']).reset_index()
        timepoint_performance.columns = ['Timepoint', 'Count', 'Mean_Return', 'Std_Return']
        print(f"\nSignals per timepoint: {timepoint_performance['Count'].mean():.1f} average")
        print(f"Timepoint range: {timepoint_performance['Timepoint'].min()} to {timepoint_performance['Timepoint'].max()}")
        
        # Save results
        results_df.to_csv(output_file, index=False)
        timepoint_performance.to_csv(output_file.replace('.csv', '_by_timepoint.csv'), index=False)
        print(f"\nResults saved to: {output_file}")
        print(f"Timepoint summary saved to: {output_file.replace('.csv', '_by_timepoint.csv')}")
    else:
        print("No valid returns calculated")
    
    return results_df

def calculate_position_return(price_pivot, symbol, open_timepoint, signal_type, entry_price):
    """Calculate return for a single position with detailed tracking"""
    
    max_hold_period = 20
    positive_returns_needed = 5
    
    # Track positive return timepoints
    positive_return_count = 0
    final_timepoint = None
    final_return = None
    daily_returns = [0]  # Start with 0 return on day 0
    
    # Check up to 20 timepoints after opening
    for i in range(1, max_hold_period + 1):
        check_timepoint = open_timepoint + i
        
        # Check if we have data for this timepoint
        if check_timepoint >= len(price_pivot):
            # Not enough data, close at last available timepoint
            final_timepoint = len(price_pivot) - 1
            final_price = price_pivot.iloc[final_timepoint][symbol]
            break
        
        current_price = price_pivot.iloc[check_timepoint][symbol]
        
        # Skip if price is NaN
        if pd.isna(current_price):
            daily_returns.append(daily_returns[-1])  # Carry forward last return
            continue
        
        # Calculate return based on position type
        if signal_type == 'Long':
            current_return = (current_price - entry_price) / entry_price
        else:  # Short
            current_return = (entry_price - current_price) / entry_price
        
        daily_returns.append(current_return)
        
        # Check if this is a positive return
        if current_return > 0:
            positive_return_count += 1
            
            # Close position if we hit 5 positive returns
            if positive_return_count >= positive_returns_needed:
                final_timepoint = check_timepoint
                final_return = current_return
                final_price = current_price
                break
        
        # If this is the last timepoint we're checking
        if i == max_hold_period:
            final_timepoint = check_timepoint
            final_return = current_return
            final_price = current_price
    
    # If we never found a final timepoint (all prices were NaN), use the last valid one
    if final_timepoint is None:
        final_timepoint = open_timepoint + max_hold_period
        if final_timepoint >= len(price_pivot):
            final_timepoint = len(price_pivot) - 1
        final_price = price_pivot.iloc[final_timepoint][symbol]
        
        if pd.isna(final_price):
            return None  # Can't calculate return
        
        if signal_type == 'Long':
            final_return = (final_price - entry_price) / entry_price
        else:  # Short
            final_return = (entry_price - final_price) / entry_price
    
    return {
        'Entry_Price': entry_price,
        'Exit_Price': final_price,
        'Entry_Timepoint': open_timepoint,
        'Exit_Timepoint': final_timepoint,
        'Holding_Period': final_timepoint - open_timepoint,
        'Final_Return': final_return,
        'Positive_Return_Count': positive_return_count,
        'Position_Closed': positive_return_count >= positive_returns_needed,
        'Daily_Returns_Raw': daily_returns
    }

def calculate_daily_returns(price_pivot, row):
    """Extract daily returns for a position"""
    if 'Daily_Returns_Raw' in row and row['Daily_Returns_Raw'] is not None:
        return row['Daily_Returns_Raw']
    else:
        return [0]

def calculate_max_drawdown(returns_series):
    """Calculate maximum drawdown from a series of returns"""
    if len(returns_series) <= 1:
        return 0
    
    cumulative = np.cumprod(1 + np.array(returns_series))
    running_max = np.maximum.accumulate(cumulative)
    drawdown = (cumulative - running_max) / running_max
    return drawdown.min()

def main():
    """Main function to calculate returns for extended trading signals"""
    
    # Wait for the signal generation to complete
    signals_file = 'trading_signals_results_extended.csv'
    
    print("Waiting for signal generation to complete...")
    while True:
        try:
            signals_df = pd.read_csv(signals_file)
            print(f"Found {len(signals_df)} signals in {signals_file}")
            break
        except FileNotFoundError:
            print("Signals file not found yet, waiting...")
            time.sleep(30)
        except pd.errors.EmptyDataError:
            print("Signals file is empty, waiting...")
            time.sleep(30)
    
    data_file = 'data.csv'
    output_file = 'trading_signals_with_returns_extended.csv'
    
    print("Starting return calculation for extended trading signals...")
    print(f"Data file: {data_file}")
    print(f"Signals file: {signals_file}")
    print(f"Output file: {output_file}")
    print("="*60)
    
    results_df = calculate_signal_returns_extended(data_file, signals_file, output_file)
    
    print("\n" + "="*60)
    print("EXTENDED RETURN CALCULATION COMPLETE!")
    print("="*60)
    
    if not results_df.empty:
        # Create Monte Carlo preparation data
        print("Preparing Monte Carlo simulation data...")
        
        # Save return distribution parameters
        mc_params = {
            'mean_return': results_df['Final_Return'].mean(),
            'std_return': results_df['Final_Return'].std(),
            'win_rate': (results_df['Final_Return'] > 0).mean(),
            'avg_holding_period': results_df['Holding_Period'].mean(),
            'early_close_rate': results_df['Position_Closed'].mean(),
            'total_signals': len(results_df),
            'long_signals': len(results_df[results_df['Type'] == 'Long']),
            'short_signals': len(results_df[results_df['Type'] == 'Short'])
        }
        
        # Save parameters for Monte Carlo
        import json
        with open('monte_carlo_parameters.json', 'w') as f:
            json.dump(mc_params, f, indent=2)
        
        print(f"Monte Carlo parameters saved to: monte_carlo_parameters.json")
        print("Ready for Monte Carlo simulations!")

if __name__ == "__main__":
    main()