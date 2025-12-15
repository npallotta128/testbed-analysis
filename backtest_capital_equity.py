"""
Generate equity curves over time for multiple capital tiers.
Assumptions:
- Uses cluster_jumps_fast.csv signals with Date and return_500d (and optional return_250d).
- 250 trading-day hold; positions accrue PnL linearly over hold period (proxy MTM since daily prices unavailable).
- Trading-day calendar derived from signal dates.
- Blue-chip prioritization order retained; small-cap concurrency is unlimited (per current backtest).
Outputs:
- equity_curves.csv : rows=dates, cols=capital tiers
- equity_curves.png : plot of equity over time
"""

import pandas as pd
import numpy as np
from pathlib import Path
import matplotlib.pyplot as plt

INPUT_JUMPS_FILE = 'cluster_jumps_full_250d_winsorized.csv'
MARKET_CAPS_FILE = 'market_caps.csv'

CAPITAL_TIERS = [100_000, 1_000_000, 10_000_000, 100_000_000]
PER_TRADE_BASE = 100_000
MAX_CONCURRENT_TRADES = 20
HOLD_DAYS = 250
MIN_YEAR_COUNT = 20  # include years with at least this many signals


def load_data():
    df = pd.read_csv(INPUT_JUMPS_FILE)
    if 'Date' not in df.columns:
        raise ValueError("cluster_jumps_fast.csv must have a Date column")
    df['Date'] = pd.to_datetime(df['Date'])
    year_counts = df['Date'].dt.year.value_counts()
    valid_years = year_counts[year_counts >= MIN_YEAR_COUNT].index
    if len(valid_years) > 0:
        df = df[df['Date'].dt.year.isin(valid_years)]
    return df


def classify_signal(row):
    delta = row.get('Quality_Delta', 0)
    continuity = row.get('Cluster_Continuity', 0)
    if pd.isna(delta):
        delta = 0
    if pd.isna(continuity):
        continuity = 0
    return 'BLUE_CHIP' if (delta > 0 and continuity >= 0.6) else 'SMALL_CAP_STORY'


def build_calendar(df):
    # Build a dense business-day calendar covering signals plus hold horizon
    start = df['Date'].min()
    end = df['Date'].max() + pd.Timedelta(days=HOLD_DAYS)
    dates = pd.bdate_range(start=start, end=end, freq='C').to_pydatetime().tolist()
    date_to_idx = {d: i for i, d in enumerate(dates)}
    return dates, date_to_idx


def add_trading_days(start_date, n_days, trading_dates, date_to_idx):
    idx = date_to_idx.get(start_date, None)
    if idx is None:
        idx = next((i for i, d in enumerate(trading_dates) if d >= start_date), None)
    if idx is None:
        return start_date
    target_idx = min(idx + n_days, len(trading_dates) - 1)
    return trading_dates[target_idx]


def position_size(cash, signal_type, symbol_cap):
    base = PER_TRADE_BASE if signal_type == 'BLUE_CHIP' else PER_TRADE_BASE * 0.2
    cap_limited = min(base, cash * 0.05)
    if symbol_cap and symbol_cap > 0:
        liquidity_cap = symbol_cap * 0.005
        return min(cap_limited, liquidity_cap)
    return cap_limited


def load_caps():
    if Path(MARKET_CAPS_FILE).exists():
        caps = pd.read_csv(MARKET_CAPS_FILE)
        return caps.set_index('Symbol')['MarketCap'].to_dict()
    return {}


def simulate_equity(capital, df, trading_dates, date_to_idx, caps_dict):
    # Sort with blue-chip priority then date
    df = df.copy()
    df['SignalType'] = df.apply(classify_signal, axis=1)
    df['Priority'] = (df['SignalType'] == 'BLUE_CHIP').astype(int)
    df = df.sort_values(['Priority', 'Date'], ascending=[False, True])

    equity = pd.Series(index=trading_dates, dtype=float)
    cash = capital
    active = []

    for current_date in trading_dates:
        # Close positions ending today or earlier, add full proceeds
        still_active = []
        for pos in active:
            if pos['EndDate'] <= current_date:
                cash += pos['Proceeds']
            else:
                still_active.append(pos)
        active = still_active

        # Add MTM for active positions (linear accrual)
        mtm = 0.0
        for pos in active:
            elapsed = (current_date - pos['StartDate']).days
            elapsed = max(0, min(elapsed, HOLD_DAYS))
            accrued = pos['Alloc'] + pos['DailyPnL'] * elapsed
            mtm += accrued

        # Record equity
        equity[current_date] = cash + mtm

        # Open any signals that occur on this date
        todays = df[df['Date'] == current_date]
        # Enforce max concurrent
        slots = max(0, MAX_CONCURRENT_TRADES - len(active))
        if slots > 0 and not todays.empty:
            # Respect ordering already in df
            for _, row in todays.head(slots).iterrows():
                symbol = row['Symbol']
                symbol_cap = caps_dict.get(symbol, None)
                signal_type = row['SignalType']

                # Determine return
                if 'return_250d_winsorized' in row.index and not pd.isna(row['return_250d_winsorized']):
                    ret_target = row['return_250d_winsorized']
                elif 'return_250d' in row.index and not pd.isna(row['return_250d']):
                    ret_target = row['return_250d']
                else:
                    ret500 = row.get('return_500d', np.nan)
                    if pd.isna(ret500):
                        continue
                    ret_target = ret500 * (HOLD_DAYS / 500.0)

                size = position_size(cash, signal_type, symbol_cap)
                if size <= 0 or size > cash:
                    continue

                cash -= size
                proceeds = size * (1 + ret_target / 100.0)
                daily_pnl = (proceeds - size) / HOLD_DAYS
                end_date = add_trading_days(current_date, HOLD_DAYS, trading_dates, date_to_idx)

                active.append({
                    'Symbol': symbol,
                    'SignalType': signal_type,
                    'Alloc': size,
                    'Proceeds': proceeds,
                    'DailyPnL': daily_pnl,
                    'StartDate': current_date,
                    'EndDate': end_date
                })

    return equity


def main():
    df = load_data()
    trading_dates, date_to_idx = build_calendar(df)
    caps = load_caps()

    curves = {}
    for cap in CAPITAL_TIERS:
        eq = simulate_equity(cap, df, trading_dates, date_to_idx, caps)
        curves[f'capital_{cap}'] = eq
        print(f"Finished equity curve for capital {cap:,.0f}")

    equity_df = pd.DataFrame(curves)
    equity_df.to_csv('equity_curves.csv')

    # Plot only 100k and 1m as requested
    plt.figure(figsize=(10,6))
    for col in ['capital_100000', 'capital_1000000']:
        if col in equity_df.columns:
            plt.plot(equity_df.index, equity_df[col], label=col)
    plt.title('Equity Curves (250 trading-day hold) - 100k vs 1m')
    plt.xlabel('Date')
    plt.ylabel('Equity')
    plt.legend()
    plt.tight_layout()
    plt.savefig('equity_curves_100k_1m.png', dpi=150)
    print('Saved equity_curves.csv and equity_curves_100k_1m.png')


if __name__ == '__main__':
    main()
