import pandas as pd
import numpy as np
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing as mp

def calculate_signal_returns(data_file, signals_file, output_file):
    """
    Calculate returns for trading signals.
    
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
    
    # Calculate returns for each signal
    results = []
    
    for idx, row in signals_df.iterrows():
        if idx % 100 == 0:
            print(f"Processing signal {idx + 1}/{len(signals_df)}")
        
        symbol = row['Variable Name']
        signal_type = row['Type']  # 'Long' or 'Short'
        end_timepoint = row['End Timepoint']  # This is where the signal was generated
        
        # Position opens at the timepoint after signal calculation
        position_open_timepoint = end_timepoint + 1
        
        # Check if we have enough data
        if position_open_timepoint >= len(dates):
            print(f"Warning: Not enough data for signal {symbol} at timepoint {position_open_timepoint}")
            continue
        
        if symbol not in price_pivot.columns:
            print(f"Warning: Symbol {symbol} not found in price data")
            continue
        
        # Get entry price
        entry_price = price_pivot.iloc[position_open_timepoint][symbol]
        if pd.isna(entry_price) or entry_price <= 0:
            print(f"Warning: Invalid entry price for {symbol} at timepoint {position_open_timepoint}")
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
        
        # Save results
        results_df.to_csv(output_file, index=False)
        print(f"\nResults saved to: {output_file}")
    else:
        print("No valid returns calculated")
    
    return results_df

def calculate_position_return(price_pivot, symbol, open_timepoint, signal_type, entry_price):
    """
    Calculate return for a single position.
    
    Args:
        price_pivot: DataFrame with prices (dates x symbols)
        symbol: Symbol name
        open_timepoint: Timepoint when position opens
        signal_type: 'Long' or 'Short'
        entry_price: Price at which position opens
    
    Returns:
        Dictionary with return information
    """
    
    max_hold_period = 20
    positive_returns_needed = 5
    
    # Track positive return timepoints
    positive_return_count = 0
    final_timepoint = None
    final_return = None
    
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
            continue
        
        # Calculate return based on position type
        if signal_type == 'Long':
            current_return = (current_price - entry_price) / entry_price
        else:  # Short
            current_return = (entry_price - current_price) / entry_price
        
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
        'Position_Closed': positive_return_count >= positive_returns_needed
    }

def main():
    """Main function to calculate returns for trading signals"""
    
    data_file = 'data.csv'
    signals_file = 'trading_signals_results.csv'
    output_file = 'trading_signals_with_returns.csv'
    
    print("Starting return calculation for trading signals...")
    print(f"Data file: {data_file}")
    print(f"Signals file: {signals_file}")
    print(f"Output file: {output_file}")
    print("="*60)
    
    results_df = calculate_signal_returns(data_file, signals_file, output_file)
    
    print("\n" + "="*60)
    print("RETURN CALCULATION COMPLETE!")
    print("="*60)

if __name__ == "__main__":
    main()