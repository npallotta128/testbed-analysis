import pandas as pd
import numpy as np
import os
import time
import gc
import psutil
from concurrent.futures import ProcessPoolExecutor, as_completed

# Configuration for large-scale return calculation
D_DRIVE_PATH = '/mnt/d/testbed_analysis'
RESULTS_DIR = os.path.join(D_DRIVE_PATH, 'results')
RETURNS_DIR = os.path.join(D_DRIVE_PATH, 'returns')
CHUNK_SIZE = 1000  # Process signals in chunks
NUM_PROCESSES = 4  # Conservative for memory

def create_returns_directory():
    """Create returns directory on D drive"""
    if not os.path.exists(RETURNS_DIR):
        os.makedirs(RETURNS_DIR)
        print(f"Created directory: {RETURNS_DIR}")

def get_memory_usage():
    """Get current memory usage"""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024  # MB

def log_memory_usage(stage):
    """Log memory usage at different stages"""
    memory_mb = get_memory_usage()
    print(f"Memory usage at {stage}: {memory_mb:.1f} MB")

def calculate_position_return(price_data, symbol, open_timepoint, signal_type, entry_price):
    """
    Calculate return for a single position using ORIGINAL position management rules.
    
    Position Management Rules (ORIGINAL):
    - Entry: Position opens at timepoint AFTER signal calculation
    - Exit: Close after 5 positive return timepoints OR at 20 timepoints maximum
    - Long: Profit when price goes up
    - Short: Profit when price goes down
    """
    max_hold_period = 20  # ORIGINAL: 20 timepoints maximum
    positive_returns_needed = 5  # ORIGINAL: 5 positive returns to close
    
    # Get symbol column for faster lookup
    if symbol not in price_data.columns:
        return None
    
    symbol_prices = price_data[symbol]
    
    # Track positive return timepoints
    positive_return_count = 0
    final_timepoint = None
    final_return = None
    final_price = None
    
    # Check up to 20 timepoints after opening
    for i in range(1, max_hold_period + 1):
        check_timepoint = open_timepoint + i
        
        # Check if we have data for this timepoint
        if check_timepoint >= len(symbol_prices):
            final_timepoint = len(symbol_prices) - 1
            final_price = symbol_prices.iloc[final_timepoint]
            break
        
        current_price = symbol_prices.iloc[check_timepoint]
        
        # Skip if price is NaN
        if pd.isna(current_price) or current_price <= 0:
            continue
        
        # Calculate return based on position type (ORIGINAL LOGIC)
        if signal_type == 'Long':
            current_return = (current_price - entry_price) / entry_price
        else:  # Short
            current_return = (entry_price - current_price) / entry_price
        
        # Check if this is a positive return
        if current_return > 0:
            positive_return_count += 1
            
            # Close position if we hit 5 positive returns (ORIGINAL RULE)
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
    
    # Handle case where no valid final timepoint found
    if final_timepoint is None:
        final_timepoint = min(open_timepoint + max_hold_period, len(symbol_prices) - 1)
        final_price = symbol_prices.iloc[final_timepoint]
        
        if pd.isna(final_price) or final_price <= 0:
            return None
        
        if signal_type == 'Long':
            final_return = (final_price - entry_price) / entry_price
        else:
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

def process_signal_chunk(args):
    """Process a chunk of signals for return calculation"""
    chunk_signals, price_pivot, chunk_id = args
    
    print(f"Processing return chunk {chunk_id + 1} with {len(chunk_signals)} signals...")
    
    results = []
    
    for idx, row in chunk_signals.iterrows():
        symbol = row['Variable Name']
        signal_type = row['Type']
        end_timepoint = row['End Timepoint']
        
        # Position opens at timepoint after signal calculation (ORIGINAL RULE)
        position_open_timepoint = end_timepoint + 1
        
        # Check bounds
        if position_open_timepoint >= len(price_pivot):
            continue
        
        if symbol not in price_pivot.columns:
            continue
        
        # Get entry price
        entry_price = price_pivot.iloc[position_open_timepoint][symbol]
        if pd.isna(entry_price) or entry_price <= 0:
            continue
        
        # Calculate returns using ORIGINAL rules
        returns_data = calculate_position_return(
            price_pivot, symbol, position_open_timepoint, signal_type, entry_price
        )
        
        if returns_data is not None:
            result = row.to_dict()
            result.update(returns_data)
            results.append(result)
    
    print(f"Processed chunk {chunk_id + 1}: {len(results)} valid returns")
    return results

def calculate_returns_for_large_dataset(signals_file, data_file, output_file):
    """Calculate returns for large-scale signals dataset using ORIGINAL rules"""
    
    print("="*80)
    print("LARGE-SCALE RETURN CALCULATION FOR MONTE CARLO")
    print("="*80)
    
    start_time = time.time()
    
    # Load signals
    print("Loading signals...")
    signals_df = pd.read_csv(signals_file)
    print(f"Loaded {len(signals_df)} signals")
    
    # Load price data efficiently
    print("Loading price data (this may take a while)...")
    log_memory_usage("before loading price data")
    
    # Read price data in chunks and create pivot table
    chunk_size = 100000
    chunks = []
    
    for chunk in pd.read_csv(data_file, chunksize=chunk_size):
        chunks.append(chunk)
    
    print(f"Loaded {len(chunks)} chunks of price data")
    
    # Combine chunks
    data = pd.concat(chunks, ignore_index=True)
    del chunks
    gc.collect()
    
    print("Creating price pivot table...")
    price_pivot = data.pivot_table(index='Date', columns='Symbol', values='Closing', aggfunc='first')
    dates = price_pivot.index.tolist()
    
    # Clean up
    del data
    gc.collect()
    
    log_memory_usage("after loading price data")
    print(f"Price data shape: {price_pivot.shape}")
    print(f"Date range: {dates[0]} to {dates[-1]}")
    
    # Split signals into chunks for processing
    signal_chunks = []
    for i in range(0, len(signals_df), CHUNK_SIZE):
        chunk = signals_df.iloc[i:i + CHUNK_SIZE]
        signal_chunks.append(chunk)
    
    print(f"Split signals into {len(signal_chunks)} chunks")
    
    # Process chunks in parallel
    all_results = []
    
    # Prepare arguments for parallel processing
    args_list = [(chunk, price_pivot, i) for i, chunk in enumerate(signal_chunks)]
    
    with ProcessPoolExecutor(max_workers=NUM_PROCESSES) as executor:
        future_to_chunk = {
            executor.submit(process_signal_chunk, args): args[2] 
            for args in args_list
        }
        
        for future in as_completed(future_to_chunk):
            chunk_id = future_to_chunk[future]
            try:
                chunk_results = future.result()
                all_results.extend(chunk_results)
                
                elapsed = time.time() - start_time
                completed_chunks = chunk_id + 1
                progress = completed_chunks / len(signal_chunks)
                
                print(f"Completed chunk {chunk_id + 1}/{len(signal_chunks)} ({progress:.1%}) in {elapsed:.2f}s total")
                
            except Exception as e:
                print(f"Chunk {chunk_id} failed: {e}")
    
    # Create final results DataFrame
    if all_results:
        results_df = pd.DataFrame(all_results)
        
        print(f"\n" + "="*60)
        print("RETURN CALCULATION RESULTS")
        print("="*60)
        print(f"Calculated returns for {len(results_df)} signals")
        print(f"Successfully closed positions (5+ positive): {len(results_df[results_df['Position_Closed'] == True])}")
        print(f"Positions held to 20-day limit: {len(results_df[results_df['Position_Closed'] == False])}")
        
        # Summary statistics
        print(f"\nRETURN STATISTICS:")
        print(f"Mean return: {results_df['Final_Return'].mean():.4f} ({results_df['Final_Return'].mean()*100:.2f}%)")
        print(f"Median return: {results_df['Final_Return'].median():.4f}")
        print(f"Std return: {results_df['Final_Return'].std():.4f}")
        print(f"Min return: {results_df['Final_Return'].min():.4f}")
        print(f"Max return: {results_df['Final_Return'].max():.4f}")
        print(f"Win rate: {(results_df['Final_Return'] > 0).mean():.2%}")
        
        # Performance by signal type
        long_returns = results_df[results_df['Type'] == 'Long']['Final_Return']
        short_returns = results_df[results_df['Type'] == 'Short']['Final_Return']
        
        if len(long_returns) > 0:
            print(f"\nLong positions ({len(long_returns)}):")
            print(f"  Mean return: {long_returns.mean():.4f} ({long_returns.mean()*100:.2f}%)")
            print(f"  Win rate: {(long_returns > 0).mean():.2%}")
        
        if len(short_returns) > 0:
            print(f"\nShort positions ({len(short_returns)}):")
            print(f"  Mean return: {short_returns.mean():.4f} ({short_returns.mean()*100:.2f}%)")
            print(f"  Win rate: {(short_returns > 0).mean():.2%}")
        
        # Save results
        results_df.to_csv(output_file, index=False)
        print(f"\nResults saved to: {output_file}")
        print(f"Ready for Monte Carlo simulations!")
        
        return results_df
    else:
        print("No valid returns calculated")
        return pd.DataFrame()

def main():
    """Main function for large-scale return calculation"""
    
    create_returns_directory()
    
    # File paths
    signals_file = os.path.join(RESULTS_DIR, 'trading_signals_250_timepoints_start75_original_criteria.csv')
    data_file = '/home/npallotta128/projects/testbed-analysis/data.csv'  # Original data file
    output_file = os.path.join(RETURNS_DIR, 'trading_signals_with_returns_250_timepoints_start75.csv')
    
    print(f"Input signals file: {signals_file}")
    print(f"Price data file: {data_file}")
    print(f"Output file: {output_file}")
    
    if not os.path.exists(signals_file):
        print(f"Error: Signals file not found: {signals_file}")
        return
    
    log_memory_usage("startup")
    
    start_time = time.time()
    results_df = calculate_returns_for_large_dataset(signals_file, data_file, output_file)
    total_duration = time.time() - start_time
    
    print("\n" + "="*80)
    print("RETURN CALCULATION COMPLETE!")
    print("="*80)
    print(f"Total computation time: {total_duration:.2f} seconds ({total_duration/3600:.2f} hours)")
    
    if not results_df.empty:
        print(f"\nDataset ready for Monte Carlo simulations:")
        print(f"  File: {output_file}")
        print(f"  Records: {len(results_df)}")
        print(f"  Timepoints: {results_df['Timepoint Index'].min()}-{results_df['Timepoint Index'].max()}")
    
    log_memory_usage("completion")

if __name__ == "__main__":
    main()