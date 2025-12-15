"""
FULL-UNIVERSE CLUSTER JUMP DETECTION with checkpoints
Tracks stocks jumping between clusters over time (matching analyze_cluster_jumps_fast.py logic)

Key difference from previous version:
- Detects cluster TRANSITIONS (From_Cluster → To_Cluster)
- Tracks quality changes (UP/DOWN jumps)
- NOT just z-score outliers within a cluster
"""

import pandas as pd
import numpy as np
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import pdist
import gc
from pathlib import Path
import json
from datetime import datetime
import pickle

# Configuration
CACHE_FILE = 'price_data_cache.pkl'
CHECKPOINT_DIR = Path('checkpoints_cluster_jumps')
FINAL_OUTPUT = 'cluster_jumps_full_250d_corrected.csv'
METADATA_FILE = CHECKPOINT_DIR / 'metadata.json'
MARKETCAP_VALUES_FILE = '/mnt/d/MarketCAPValues.csv'  # provides OutstandingShares by Symbol/Date

HISTORY_WINDOW = 1501  # trading days for clustering
RETURN_WINDOW = 250    # trading days for returns
DISTANCE_THRESHOLD = 50
MIN_CLUSTER_SIZE = 40
BLOCK_STRIDE = 100     # days between blocks (to create temporal sequence)
CHECKPOINT_FREQUENCY = 5  # save every 5 blocks

def load_metadata():
    """Load processing metadata or create new"""
    CHECKPOINT_DIR.mkdir(exist_ok=True)
    if METADATA_FILE.exists():
        with open(METADATA_FILE, 'r') as f:
            return json.load(f)
    return {
        'last_block_idx': -1,
        'total_jumps': 0,
        'blocks_processed': 0,
        'started_at': datetime.now().isoformat(),
        'last_updated': None
    }

def save_metadata(meta):
    """Save processing metadata"""
    meta['last_updated'] = datetime.now().isoformat()
    with open(METADATA_FILE, 'w') as f:
        json.dump(meta, f, indent=2)

def load_price_cache():
    """Load price data from cache"""
    print(f"Loading price data from cache ({CACHE_FILE})...")
    with open(CACHE_FILE, 'rb') as f:
        cache_data = pickle.load(f)
    
    data_by_date = cache_data['data_by_date']
    sorted_dates = cache_data['sorted_dates']
    sorted_symbols = cache_data['sorted_symbols']
    
    print(f"✓ Loaded {len(sorted_symbols):,} symbols across {len(sorted_dates):,} dates from cache")
    return data_by_date, sorted_dates, sorted_symbols

def get_price_matrix(data_by_date, dates, symbols):
    """Build price matrix for given date range and symbols"""
    n_dates = len(dates)
    n_symbols = len(symbols)
    
    matrix = np.full((n_symbols, n_dates), np.nan)
    
    for j, date in enumerate(dates):
        date_prices = data_by_date.get(date, {})
        for i, symbol in enumerate(symbols):
            if symbol in date_prices:
                matrix[i, j] = date_prices[symbol]
    
    # Forward fill then backward fill NaNs
    df_temp = pd.DataFrame(matrix)
    df_temp = df_temp.ffill(axis=1).bfill(axis=1)
    
    return df_temp.values

def build_symbol_shares_map(marketcap_csv_path: str):
    """Build a per-symbol sorted series of outstanding shares using chunked CSV reads.
    Returns a dict: symbol -> list of (date, shares) sorted by date.
    """
    print(f"Loading outstanding shares from {marketcap_csv_path}...")
    symbol_to_shares = {}
    chunk_size = 200_000
    for chunk in pd.read_csv(marketcap_csv_path, chunksize=chunk_size):
        # Expect columns like: Symbol, Date, OutstandingShares (case-insensitive handling)
        cols = {c.lower(): c for c in chunk.columns}
        sym_col = cols.get('symbol')
        date_col = cols.get('date')
        shares_col = cols.get('outstandingshares') or cols.get('shares') or cols.get('outstanding_shares')
        if not (sym_col and date_col and shares_col):
            # skip chunk if expected columns missing
            continue
        chunk = chunk.dropna(subset=[sym_col, date_col, shares_col])
        chunk[date_col] = pd.to_datetime(chunk[date_col])
        # normalize shares to float
        chunk[shares_col] = chunk[shares_col].astype(float)
        for sym, grp in chunk.groupby(sym_col):
            entries = list(zip(grp[date_col].tolist(), grp[shares_col].tolist()))
            if sym in symbol_to_shares:
                symbol_to_shares[sym].extend(entries)
            else:
                symbol_to_shares[sym] = entries
    # sort each symbol's entries by date
    for sym in list(symbol_to_shares.keys()):
        symbol_to_shares[sym].sort(key=lambda x: x[0])
    print(f"✓ Loaded shares for {len(symbol_to_shares):,} symbols")
    return symbol_to_shares

def get_nearest_shares(symbol_to_shares, symbol, ref_date):
    """Get outstanding shares closest to ref_date (use last known before ref_date, else next)."""
    entries = symbol_to_shares.get(symbol)
    if not entries:
        return np.nan
    # binary search
    lo, hi = 0, len(entries)-1
    if ref_date <= entries[0][0]:
        return entries[0][1]
    if ref_date >= entries[-1][0]:
        return entries[-1][1]
    # find rightmost date <= ref_date
    while lo <= hi:
        mid = (lo+hi)//2
        d = entries[mid][0]
        if d <= ref_date:
            lo = mid + 1
        else:
            hi = mid - 1
    return entries[max(0, hi)][1]

def calculate_cluster_quality(price_matrix, dates, symbols, cluster_id, clusters, symbol_to_shares):
    """Calculate market-cap weighted quality for a cluster.
    - Intrablock return per symbol: (last/first - 1)*100
    - Market cap at block end: price_last * OutstandingShares (nearest by date)
    - Quality = cap-weighted mean of intrablock returns + cap-weighted mean correlation (scaled)
    """
    mask = clusters == cluster_id
    idxs = np.where(mask)[0]
    if len(idxs) < 2:
        return 0.0
    block_end_date = dates[-1]
    # collect per-symbol metrics
    rets = []
    caps = []
    cluster_prices = []
    for i in idxs:
        series = price_matrix[i]
        first = series[0]
        last = series[-1]
        if np.isnan(first) or np.isnan(last) or first <= 0:
            continue
        ret = ((last/first) - 1.0) * 100.0
        sym = symbols[i]
        shares = get_nearest_shares(symbol_to_shares, sym, block_end_date)
        if np.isnan(shares) or shares <= 0:
            continue
        cap = last * shares
        rets.append(ret)
        caps.append(cap)
        cluster_prices.append(series)
    if len(caps) < 2:
        return 0.0
    caps_arr = np.array(caps, dtype=float)
    weights = caps_arr / np.sum(caps_arr)
    rets_arr = np.array(rets, dtype=float)
    # weighted mean of returns
    w_ret = float(np.sum(weights * rets_arr))
    # approximate weighted mean pairwise correlation by weighting each member's average corr
    n = len(cluster_prices)
    # build correlation matrix in a memory-aware way
    avg_corrs = []
    for i in range(n):
        s_i = cluster_prices[i]
        corrs_i = []
        for j in range(n):
            if i == j:
                continue
            s_j = cluster_prices[j]
            try:
                c = np.corrcoef(s_i, s_j)[0,1]
                if not np.isnan(c):
                    corrs_i.append(c)
            except Exception:
                pass
        avg_corrs.append(np.mean(corrs_i) if corrs_i else 0.0)
    avg_corrs = np.array(avg_corrs, dtype=float)
    # align weights length with avg_corrs length
    if len(weights) != len(avg_corrs):
        # fallback: simple mean
        w_corr = float(np.mean(avg_corrs))
    else:
        w_corr = float(np.sum(weights * avg_corrs))
    # scale correlation component for readability
    quality = w_ret + (w_corr * 100.0)
    return quality

def perform_clustering_on_block(data_by_date, block_dates, sorted_symbols, symbol_to_shares):
    """Cluster stocks in a single temporal block"""
    
    # Build price matrix
    price_matrix = get_price_matrix(data_by_date, block_dates, sorted_symbols)
    
    # Filter symbols with sufficient data
    valid_mask = np.sum(~np.isnan(price_matrix), axis=1) >= (len(block_dates) * 0.8)
    valid_symbols = [s for i, s in enumerate(sorted_symbols) if valid_mask[i]]
    valid_prices = price_matrix[valid_mask]
    
    if len(valid_symbols) < MIN_CLUSTER_SIZE:
        return None
    
    # Z-score normalize
    price_normalized = np.zeros_like(valid_prices)
    for i in range(len(valid_symbols)):
        series = valid_prices[i]
        mean_price = np.mean(series)
        std_price = np.std(series)
        if std_price > 0:
            price_normalized[i] = (series - mean_price) / std_price
        else:
            price_normalized[i] = series
    
    # Hierarchical clustering
    try:
        distances = pdist(price_normalized, metric='euclidean')
        Z = linkage(distances, method='ward')
        clusters = fcluster(Z, t=DISTANCE_THRESHOLD, criterion='distance')
    except Exception as e:
        print(f"    Clustering failed: {e}")
        return None
    
    # Calculate cluster qualities (cap-weighted, intrablock returns + corr)
    cluster_qualities = {}
    for cluster_id in np.unique(clusters):
        quality = calculate_cluster_quality(valid_prices, block_dates, valid_symbols, cluster_id, clusters, symbol_to_shares)
        cluster_qualities[cluster_id] = quality
    
    # Build result
    symbol_to_cluster = {}
    symbol_to_quality = {}
    for i, symbol in enumerate(valid_symbols):
        cluster_id = clusters[i]
        symbol_to_cluster[symbol] = cluster_id
        symbol_to_quality[symbol] = cluster_qualities[cluster_id]
    
    return {
        'date': block_dates[-1],  # Use last date of block as reference
        'symbol_to_cluster': symbol_to_cluster,
        'symbol_to_quality': symbol_to_quality,
        'cluster_sizes': {cid: np.sum(clusters == cid) for cid in np.unique(clusters)}
    }

def detect_jumps(prev_block, curr_block):
    """Detect cluster jumps between two consecutive blocks"""
    jumps = []
    
    prev_clusters = prev_block['symbol_to_cluster']
    curr_clusters = curr_block['symbol_to_cluster']
    prev_qualities = prev_block['symbol_to_quality']
    curr_qualities = curr_block['symbol_to_quality']
    
    # Find symbols present in both blocks
    common_symbols = set(prev_clusters.keys()) & set(curr_clusters.keys())
    
    for symbol in common_symbols:
        prev_cluster = prev_clusters[symbol]
        curr_cluster = curr_clusters[symbol]
        
        # Jump = cluster membership changed
        if prev_cluster != curr_cluster:
            prev_quality = prev_qualities[symbol]
            curr_quality = curr_qualities[symbol]
            quality_delta = curr_quality - prev_quality
            
            jumps.append({
                'Symbol': symbol,
                'Date': curr_block['date'],
                'From_Cluster': prev_cluster,
                'To_Cluster': curr_cluster,
                'From_Quality': prev_quality,
                'To_Quality': curr_quality,
                'Quality_Delta': quality_delta,
                'Jump_Type': 'UP' if quality_delta > 0 else ('DOWN' if quality_delta < 0 else 'LATERAL')
            })
    
    return jumps

def calculate_250d_return(data_by_date, sorted_dates, symbol, signal_date, jump_type):
    """Calculate 250-day return for a jump"""
    try:
        signal_idx = sorted_dates.index(signal_date)
    except ValueError:
        return np.nan
    
    # Get prices for next 250 trading days
    end_idx = min(signal_idx + RETURN_WINDOW, len(sorted_dates))
    future_dates = sorted_dates[signal_idx:end_idx]
    
    prices = []
    for date in future_dates:
        date_data = data_by_date.get(date, {})
        if symbol in date_data:
            prices.append(date_data[symbol])
    
    if len(prices) < 10 or prices[0] <= 0:
        return np.nan
    
    ref_price = prices[0]
    max_price = np.max(prices)
    
    # Return = best performance over 250 days (UP jumps should go up)
    return ((max_price - ref_price) / ref_price) * 100

def save_checkpoint(block_idx, jumps):
    """Save checkpoint file"""
    if not jumps:
        return
    
    checkpoint_file = CHECKPOINT_DIR / f'checkpoint_block_{block_idx:04d}.csv'
    df = pd.DataFrame(jumps)
    df.to_csv(checkpoint_file, index=False)
    print(f"  ✓ Checkpoint saved: {len(jumps)} jumps in block {block_idx}")

def consolidate_checkpoints():
    """Consolidate all checkpoint files into final output"""
    print("\nConsolidating checkpoints...")
    
    checkpoint_files = sorted(CHECKPOINT_DIR.glob('checkpoint_block_*.csv'))
    
    if not checkpoint_files:
        print("  No checkpoint files found!")
        return None
    
    all_jumps = []
    for cp_file in checkpoint_files:
        df = pd.read_csv(cp_file)
        all_jumps.append(df)
        print(f"  Loaded {len(df)} jumps from {cp_file.name}")
    
    final_df = pd.concat(all_jumps, ignore_index=True)
    final_df = final_df.drop_duplicates()
    final_df = final_df.sort_values('Date')
    
    final_df.to_csv(FINAL_OUTPUT, index=False)
    print(f"\n✓ Final output: {len(final_df)} jumps saved to {FINAL_OUTPUT}")
    
    return final_df

def main():
    print("=" * 70)
    print("FULL-UNIVERSE CLUSTER JUMP DETECTION WITH CHECKPOINTS")
    print("=" * 70)
    
    # Load metadata
    meta = load_metadata()
    print(f"\nMetadata: Last block processed = {meta['last_block_idx']}")
    print(f"          Total jumps so far = {meta['total_jumps']}")
    
    # Load price data
    data_by_date, sorted_dates, sorted_symbols = load_price_cache()
    # Load outstanding shares map for market cap
    symbol_to_shares = build_symbol_shares_map(MARKETCAP_VALUES_FILE)
    
    print(f"\nDate range: {sorted_dates[0]} to {sorted_dates[-1]}")
    print(f"Total symbols: {len(sorted_symbols):,}")
    
    # Calculate blocks
    total_blocks = (len(sorted_dates) - HISTORY_WINDOW) // BLOCK_STRIDE
    print(f"\nProcessing {total_blocks} blocks (stride={BLOCK_STRIDE} days)")
    print(f"History window: {HISTORY_WINDOW} days")
    print(f"Return window: {RETURN_WINDOW} days")
    
    # Resume from checkpoint
    start_block = meta['last_block_idx'] + 1
    print(f"Starting from block {start_block}")
    
    # Process blocks
    prev_block_result = None
    block_jumps_buffer = []
    
    for block_idx in range(start_block, total_blocks):
        block_start = block_idx * BLOCK_STRIDE
        block_end = block_start + HISTORY_WINDOW
        
        if block_end >= len(sorted_dates):
            break
        
        block_dates = sorted_dates[block_start:block_end]
        
        print(f"\nBlock {block_idx}/{total_blocks}: {block_dates[0]} to {block_dates[-1]}")
        
        # Cluster this block
        curr_block_result = perform_clustering_on_block(data_by_date, block_dates, sorted_symbols, symbol_to_shares)
        
        if curr_block_result is None:
            print(f"  Skipping block {block_idx} (insufficient data)")
            continue
        
        print(f"  Clustered {len(curr_block_result['symbol_to_cluster'])} symbols")
        
        # Detect jumps if we have previous block
        jumps = []
        if prev_block_result is not None:
            jumps = detect_jumps(prev_block_result, curr_block_result)
            print(f"  Found {len(jumps)} cluster jumps")
            
            if jumps:
                # Calculate returns
                for jump in jumps:
                    jump['return_250d'] = calculate_250d_return(
                        data_by_date, sorted_dates, jump['Symbol'], 
                        jump['Date'], jump['Jump_Type']
                    )
                
                block_jumps_buffer.extend(jumps)
                
                up_count = sum(1 for j in jumps if j['Jump_Type'] == 'UP')
                down_count = sum(1 for j in jumps if j['Jump_Type'] == 'DOWN')
                print(f"    UP: {up_count}, DOWN: {down_count}")
        
        # Update for next iteration
        prev_block_result = curr_block_result
        
        # Update metadata
        meta['last_block_idx'] = block_idx
        meta['blocks_processed'] = block_idx + 1
        meta['total_jumps'] += len(jumps)
        
        # Checkpoint every N blocks
        if (block_idx + 1) % CHECKPOINT_FREQUENCY == 0 and block_jumps_buffer:
            save_checkpoint(block_idx, block_jumps_buffer)
            save_metadata(meta)
            block_jumps_buffer = []
            gc.collect()
    
    # Save final buffer
    if block_jumps_buffer:
        save_checkpoint(meta['last_block_idx'], block_jumps_buffer)
        save_metadata(meta)
    
    # Consolidate all checkpoints
    final_df = consolidate_checkpoints()
    
    if final_df is not None:
        # Remove NaN returns
        final_df = final_df.dropna(subset=['return_250d'])
        final_df.to_csv(FINAL_OUTPUT, index=False)
        
        print(f"\n{'='*70}")
        print(f"FINAL STATISTICS")
        print(f"{'='*70}")
        print(f"Total jumps: {len(final_df):,}")
        print(f"Unique symbols: {final_df['Symbol'].nunique():,}")
        print(f"Date range: {final_df['Date'].min()} to {final_df['Date'].max()}")
        print(f"UP jumps: {len(final_df[final_df['Jump_Type']=='UP']):,}")
        print(f"DOWN jumps: {len(final_df[final_df['Jump_Type']=='DOWN']):,}")
        print(f"\nReturn stats (250d):")
        print(f"  Mean: {final_df['return_250d'].mean():.2f}%")
        print(f"  Median: {final_df['return_250d'].median():.2f}%")
        print(f"  Std: {final_df['return_250d'].std():.2f}%")

if __name__ == '__main__':
    main()
