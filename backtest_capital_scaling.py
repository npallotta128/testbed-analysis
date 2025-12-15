"""
Backtest portfolio performance at different capital levels
Capital tiers: 100k, 1m, 10m, 100m
Strategy: Cluster jump signals filtered by market-cap weighted quality

Inputs:
- cluster_jumps_fast.csv: Detected jump events with 500d returns (return_500d)
- market_caps.csv: Market caps for liquidity-aware sizing

Outputs:
- backtest_capital_scaling.csv: Results per capital tier
- backtest_capital_scaling_summary.txt: Human-readable summary
"""

import pandas as pd
import numpy as np
from pathlib import Path

CAPITAL_TIERS = [100_000, 1_000_000, 10_000_000, 100_000_000]
PER_TRADE_BASE = 100_000  # base allocation per signal before scaling
MAX_CONCURRENT_TRADES = 20  # cap number of concurrent positions
HOLD_DAYS = 250  # requested hold period
MIN_YEAR_COUNT = 20  # include years with at least this many signals (keeps sparse years out)

INPUT_JUMPS_FILE = 'cluster_jumps_full_250d_winsorized.csv'
MARKET_CAPS_FILE = 'market_caps.csv'


def load_data():
    jumps = pd.read_csv(INPUT_JUMPS_FILE)
    # Expected columns: Symbol, Block, Date, From_Cluster, To_Cluster,
    # From_Quality, To_Quality, Quality_Delta, Jump_Type, Cluster_Continuity, return_500d, (optional) return_250d
    if 'Date' in jumps.columns:
        jumps['Date'] = pd.to_datetime(jumps['Date'])
        year_counts = jumps['Date'].dt.year.value_counts()
        valid_years = year_counts[year_counts >= MIN_YEAR_COUNT].index
        if len(valid_years) > 0:
            jumps = jumps[jumps['Date'].dt.year.isin(valid_years)]
    return jumps

def build_trading_calendar(jumps_df):
    """Return sorted unique trading dates and index map"""
    if 'Date' not in jumps_df.columns:
        return None, None
    dates = sorted(pd.to_datetime(jumps_df['Date'].dropna().unique()))
    date_to_idx = {d: i for i, d in enumerate(dates)}
    return dates, date_to_idx

def add_trading_days(start_date, n_days, trading_dates, date_to_idx):
    """Advance by n trading days using provided calendar"""
    idx = date_to_idx.get(start_date, None)
    if idx is None:
        # find nearest next date
        # assume start_date may not be exact; choose first date >= start_date
        idx = next((i for i, d in enumerate(trading_dates) if d >= start_date), None)
        if idx is None:
            return start_date
    target_idx = min(idx + n_days, len(trading_dates) - 1)
    return trading_dates[target_idx]


def load_market_caps():
    if Path(MARKET_CAPS_FILE).exists():
        caps = pd.read_csv(MARKET_CAPS_FILE)
        return caps.set_index('Symbol')['MarketCap'].to_dict()
    return {}


def classify_signal(row):
    # Blue-chip consensus if cap-weighted quality likely improved; proxy using Quality_Delta > 0 and continuity
    delta = row.get('Quality_Delta', 0)
    continuity = row.get('Cluster_Continuity', 0)
    jump_type = row.get('Jump_Type', '')
    if pd.isna(delta):
        delta = 0
    if pd.isna(continuity):
        continuity = 0
    is_blue_chip = (delta > 0) and (continuity >= 0.6)
    return 'BLUE_CHIP' if is_blue_chip else 'SMALL_CAP_STORY'


def position_size(capital, signal_type, symbol_cap):
    # Base sizing by signal type
    if signal_type == 'BLUE_CHIP':
        base = PER_TRADE_BASE
    else:
        base = PER_TRADE_BASE * 0.2
    # Scale by portfolio capital (keep per-trade under 5% of capital)
    cap_limited = min(base, capital * 0.05)
    # Liquidity constraint: do not exceed 0.5% of symbol market cap
    if symbol_cap and symbol_cap > 0:
        liquidity_cap = symbol_cap * 0.005
        return min(cap_limited, liquidity_cap)
    return cap_limited


def simulate_portfolio(capital, jumps_df, caps_dict):
    # Sort signals by date to simulate sequence
    df = jumps_df.copy()
    if 'Date' in df.columns:
        # prioritize BLUE_CHIP signals first, then by date
        df['SignalType'] = df.apply(classify_signal, axis=1)
        df['Priority'] = (df['SignalType'] == 'BLUE_CHIP').astype(int)
        df = df.sort_values(['Priority', 'Date'], ascending=[False, True])
    else:
        df = df.sort_values(['Block', 'Symbol'])

    # Build trading calendar
    trading_dates, date_to_idx = build_trading_calendar(df)

    cash = capital
    trades = []
    active_positions = []

    small_cap_active = 0
    for _, row in df.iterrows():
        symbol = row['Symbol']
        symbol_cap = caps_dict.get(symbol, None)
        signal_type = row['SignalType']
        # Determine 250d return: prefer winsorized, else raw, else approximate from 500d
        if 'return_250d_winsorized' in row.index and not pd.isna(row['return_250d_winsorized']):
            ret_target = row['return_250d_winsorized']
        elif 'return_250d' in row.index and not pd.isna(row['return_250d']):
            ret_target = row['return_250d']
        else:
            ret500 = row.get('return_500d', np.nan)
            if pd.isna(ret500):
                continue
            # Simple proportional approximation (note: assumption)
            ret_target = ret500 * (HOLD_DAYS / 500.0)

        # Close any positions whose end date is <= current event date
        current_date = row['Date'] if 'Date' in row.index else None
        if current_date is not None:
            still_active = []
            for pos in active_positions:
                if pos['EndDate'] <= current_date:
                    cash += pos['Proceeds']
                    trades.append(pos)
                    if pos['SignalType'] == 'SMALL_CAP_STORY':
                        small_cap_active = max(0, small_cap_active - 1)
                else:
                    still_active.append(pos)
            active_positions = still_active
        
        # Close positions if exceeding max concurrent
        if len(active_positions) >= MAX_CONCURRENT_TRADES:
            # Close the oldest
            close_pos = active_positions.pop(0)
            cash += close_pos['Proceeds']
            trades.append(close_pos)
        
        # Determine position size
        size = position_size(cash, signal_type, symbol_cap)
        if size <= 0 or size > cash:
            continue
        
        # Open position (buy at t0, sell at t+HOLD_DAYS)
        cash -= size
        proceeds = size * (1 + ret_target / 100.0)
        pnl = proceeds - size
        end_date = None
        if current_date is not None and trading_dates is not None:
            end_date = add_trading_days(current_date, HOLD_DAYS, trading_dates, date_to_idx)
        
        pos = {
            'Symbol': symbol,
            'SignalType': signal_type,
            'Alloc': size,
            'ReturnTarget_pct': ret_target,
            'Proceeds': proceeds,
            'PnL': pnl,
            'EndDate': end_date if end_date is not None else pd.NaT
        }
        active_positions.append(pos)
        if signal_type == 'SMALL_CAP_STORY':
            small_cap_active += 1
    
    # Close remaining positions
    for pos in active_positions:
        cash += pos['Proceeds']
        trades.append(pos)
    
    final_value = cash
    total_pnl = sum(t['PnL'] for t in trades)
    num_trades = len(trades)
    win_rate = (sum(1 for t in trades if t['ReturnTarget_pct'] > 0) / num_trades * 100) if num_trades else 0
    avg_return = np.mean([t['ReturnTarget_pct'] for t in trades]) if num_trades else 0
    
    return {
        'capital': capital,
        'final_value': final_value,
        'total_pnl': total_pnl,
        'num_trades': num_trades,
        'win_rate_pct': win_rate,
        'avg_trade_return_pct': avg_return
    }


def main():
    jumps = load_data()
    caps = load_market_caps()
    results = []
    for cap in CAPITAL_TIERS:
        res = simulate_portfolio(cap, jumps, caps)
        results.append(res)
        print(f"Capital {cap:>10,d} → Final {res['final_value']:>12,.0f} | PnL {res['total_pnl']:>12,.0f} | Trades {res['num_trades']} | Win {res['win_rate_pct']:.1f}% | AvgRet {res['avg_trade_return_pct']:.2f}%")
    
    out_csv = 'backtest_capital_scaling.csv'
    pd.DataFrame(results).to_csv(out_csv, index=False)
    
    # Summary
    lines = [
        'Backtest Capital Scaling Summary (Hold 250d)',
        'Capital, FinalValue, TotalPnL, NumTrades, WinRate%, AvgTradeReturn%'
    ]
    for r in results:
        lines.append(f"{r['capital']},{r['final_value']:.2f},{r['total_pnl']:.2f},{r['num_trades']},{r['win_rate_pct']:.2f},{r['avg_trade_return_pct']:.2f}")
    with open('backtest_capital_scaling_summary.txt', 'w') as f:
        f.write('\n'.join(lines))
    print(f"Saved results to {out_csv} and backtest_capital_scaling_summary.txt")


if __name__ == '__main__':
    main()
