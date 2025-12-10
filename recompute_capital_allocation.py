"""
Recompute Capital Allocation and Returns using data.csv

Assumptions:
- Position sizing rule: min(5% of current equity, 2% of price*ADV) * signal_strength
- If ADV (average daily volume) is not present, falls back to 5% capital cap only.
- Uses dropout events by default if Event_Type column exists; otherwise processes all rows.

Outputs:
- capital_allocation_positions.csv: Per-position sizing with constraint flags
- capital_allocation_results.csv: Portfolio-level summary metrics
"""

import os
import pandas as pd
import numpy as np

DATA_FILE = 'data.csv'
POSITIONS_OUT = 'capital_allocation_positions.csv'
SUMMARY_OUT = 'capital_allocation_results.csv'

# Configurable parameters
MAX_POSITION_PCT = 0.05  # 5% of equity
VOLUME_CONSTRAINT_PCT = 0.02  # 2% of price*ADV
INITIAL_EQUITY = float(os.environ.get('INITIAL_EQUITY', '100000'))
SIGNAL_STRENGTH_DEFAULT = float(os.environ.get('SIGNAL_STRENGTH', '1.0'))

def infer_columns(df: pd.DataFrame):
    """Infer key columns for pricing, volume, returns, and event type."""
    cols = df.columns.str.lower().tolist()
    # Price
    price_col = next((c for c in df.columns if c.lower() in ['price','close','adj_close']), None)
    # ADV / Volume
    adv_col = next((c for c in df.columns if c.lower() in ['adv','average_daily_volume','avg_volume','volume']), None)
    # Return
    ret_col = next((c for c in df.columns if c.lower() in ['future_return','ret_20','ret_60','ret_120','return','pct_change']), None)
    # Event type
    evt_col = next((c for c in df.columns if c.lower() in ['event_type','event','type']), None)
    # Security identifier
    sym_col = next((c for c in df.columns if c.lower() in ['security','symbol','ticker']), None)
    return price_col, adv_col, ret_col, evt_col, sym_col

def load_data():
    df = pd.read_csv(DATA_FILE)
    price_col, adv_col, ret_col, evt_col, sym_col = infer_columns(df)
    missing = []
    if price_col is None:
        missing.append('price')
    if ret_col is None:
        missing.append('return')
    if sym_col is None:
        missing.append('symbol')
    if missing:
        print(f"Warning: Missing columns {missing}. Proceeding with available data.")
    return df, price_col, adv_col, ret_col, evt_col, sym_col

def filter_events(df: pd.DataFrame, evt_col: str | None):
    if evt_col and 'DROP' in df[evt_col].unique().tolist():
        return df[df[evt_col] == 'DROP'].copy()
    return df.copy()

def compute_positions(df: pd.DataFrame, price_col: str | None, adv_col: str | None, ret_col: str | None, sym_col: str | None):
    equity = INITIAL_EQUITY
    positions = []
    for idx, row in df.iterrows():
        price = float(row[price_col]) if price_col and not pd.isna(row.get(price_col)) else np.nan
        adv = float(row[adv_col]) if adv_col and not pd.isna(row.get(adv_col)) else np.nan
        expected_ret = float(row[ret_col]) if ret_col and not pd.isna(row.get(ret_col)) else 0.0
        signal_strength = SIGNAL_STRENGTH_DEFAULT

        capital_cap = equity * MAX_POSITION_PCT
        if not np.isnan(price) and not np.isnan(adv):
            volume_cap = price * adv * VOLUME_CONSTRAINT_PCT
        else:
            volume_cap = np.inf

        base_size = min(capital_cap, volume_cap)
        position_size = base_size * signal_strength
        binding = 'capital' if capital_cap <= volume_cap else ('volume' if volume_cap < np.inf else 'capital')

        # Execute pseudo-trade: deploy and immediately realize expected return
        invested = min(position_size, equity)  # no leverage in recompute
        pnl = invested * expected_ret
        equity = equity - invested + (invested + pnl)

        positions.append({
            'symbol': row[sym_col] if sym_col else f'row_{idx}',
            'price': price,
            'adv': adv,
            'expected_return_pct': expected_ret * 100,
            'position_size': invested,
            'binding_constraint': binding,
            'capital_cap': capital_cap,
            'volume_cap': volume_cap if volume_cap < np.inf else None,
            'pnl': pnl,
            'post_trade_equity': equity
        })

    return pd.DataFrame(positions), equity

def summarize(positions_df: pd.DataFrame, final_equity: float):
    initial = INITIAL_EQUITY
    total_deployed = positions_df['position_size'].sum()
    win_rate = (positions_df['pnl'] > 0).mean() * 100 if len(positions_df) else 0.0
    cap_bind_pct = (positions_df['binding_constraint'] == 'capital').mean() * 100 if len(positions_df) else 0.0
    vol_bind_pct = (positions_df['binding_constraint'] == 'volume').mean() * 100 if len(positions_df) else 0.0

    summary = {
        'initial_equity': initial,
        'final_equity': final_equity,
        'total_deployed': total_deployed,
        'n_positions': len(positions_df),
        'avg_position_size': positions_df['position_size'].mean() if len(positions_df) else 0.0,
        'total_pnl': positions_df['pnl'].sum(),
        'total_return_pct': ((final_equity/initial) - 1) * 100 if initial > 0 else 0.0,
        'win_rate_pct': win_rate,
        'capital_binding_pct': cap_bind_pct,
        'volume_binding_pct': vol_bind_pct,
    }
    return pd.DataFrame([summary])

def main():
    df, price_col, adv_col, ret_col, evt_col, sym_col = load_data()
    df = filter_events(df, evt_col)
    positions_df, final_equity = compute_positions(df, price_col, adv_col, ret_col, sym_col)
    positions_df.to_csv(POSITIONS_OUT, index=False)
    summary_df = summarize(positions_df, final_equity)
    summary_df.to_csv(SUMMARY_OUT, index=False)
    print(f"Saved positions to {POSITIONS_OUT} and summary to {SUMMARY_OUT}")

if __name__ == '__main__':
    main()
