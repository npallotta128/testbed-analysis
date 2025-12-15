"""
Build a pickle cache of price data for faster loading.
Run this once, then clustering can load from cache.
"""

import pandas as pd
import numpy as np
import pickle
import gc
from pathlib import Path

DATA_FILE = '/mnt/d/MarketValues.csv'
CACHE_FILE = 'price_data_cache.pkl'

print("Building price data cache...")
print(f"Reading from: {DATA_FILE}")

data_by_date = {}
all_symbols = set()
all_dates = set()

chunk_size = 200_000
chunk_num = 0

for chunk in pd.read_csv(DATA_FILE, chunksize=chunk_size):
    chunk_num += 1
    
    chunk = chunk[chunk['Symbol'] != 'Lenny']
    chunk = chunk.dropna(subset=['Symbol', 'Date', 'Closing'])
    chunk['Date'] = pd.to_datetime(chunk['Date'])
    
    # Vectorized approach - group by date
    for date, group in chunk.groupby('Date'):
        if date not in data_by_date:
            data_by_date[date] = {}
        for symbol, price in zip(group['Symbol'], group['Closing']):
            data_by_date[date][symbol] = price
            all_symbols.add(symbol)
        all_dates.add(date)
    
    if chunk_num % 20 == 0:
        print(f"  Chunk {chunk_num}: {chunk_num * chunk_size:,} rows processed")
    
    del chunk
    gc.collect()

print(f"\n✓ Processed {len(all_symbols):,} symbols across {len(all_dates):,} dates")

# Sort
sorted_dates = sorted(list(all_dates))
sorted_symbols = sorted(list(all_symbols))

print(f"Date range: {sorted_dates[0]} to {sorted_dates[-1]}")

# Save cache
cache_data = {
    'data_by_date': data_by_date,
    'sorted_dates': sorted_dates,
    'sorted_symbols': sorted_symbols
}

print(f"\nSaving cache to {CACHE_FILE}...")
with open(CACHE_FILE, 'wb') as f:
    pickle.dump(cache_data, f, protocol=pickle.HIGHEST_PROTOCOL)

cache_size_mb = Path(CACHE_FILE).stat().st_size / (1024 * 1024)
print(f"✓ Cache saved ({cache_size_mb:.1f} MB)")
