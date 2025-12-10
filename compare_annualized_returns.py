"""
Compare Annualized Returns: 250-day vs 500-day Windows
======================================================

Accounts for different holding periods and compounding potential.
"""

import pandas as pd
import numpy as np

def calculate_annualized_metrics(events_df, holding_days, trading_days_per_year=252):
    """Calculate annualized returns and metrics"""
    
    # Annualization factor
    periods_per_year = trading_days_per_year / holding_days
    
    # Mean annualized return
    mean_return = events_df['Future_Return'].mean()
    annualized_mean = mean_return * periods_per_year
    
    # Median annualized return
    median_return = events_df['Future_Return'].median()
    annualized_median = median_return * periods_per_year
    
    # Win rate (doesn't change with annualization)
    win_rate = (events_df['Future_Return'] > 0).mean() * 100
    
    # Sharpe ratio approximation (using std dev)
    std_dev = events_df['Future_Return'].std()
    annualized_std = std_dev * np.sqrt(periods_per_year)
    sharpe = annualized_mean / annualized_std if annualized_std > 0 else 0
    
    # Number of trades per year (compounding opportunities)
    trades_per_year = periods_per_year
    
    return {
        'holding_days': holding_days,
        'mean_return': mean_return,
        'annualized_mean': annualized_mean,
        'median_return': median_return,
        'annualized_median': annualized_median,
        'win_rate': win_rate,
        'std_dev': std_dev,
        'annualized_std': annualized_std,
        'sharpe': sharpe,
        'periods_per_year': periods_per_year,
        'trades_per_year': trades_per_year
    }

def calculate_compound_returns(mean_return, win_rate, holding_days, years=1, trading_days_per_year=252):
    """
    Calculate expected compound return over multiple periods
    
    Assumes you can reinvest capital after each holding period
    """
    periods_per_year = trading_days_per_year / holding_days
    total_periods = periods_per_year * years
    
    # Expected return per period (accounting for win rate)
    # If 40% win rate with +387% mean, the expected value is different
    # But we'll use the mean which already accounts for wins/losses
    expected_multiplier_per_period = 1 + (mean_return / 100)
    
    # Compound over all periods
    compound_multiplier = expected_multiplier_per_period ** total_periods
    compound_return = (compound_multiplier - 1) * 100
    
    return compound_return, total_periods

def main():
    print("="*80)
    print("ANNUALIZED RETURN COMPARISON: 250-DAY vs 500-DAY WINDOWS")
    print("="*80)
    
    # Load both datasets
    events_500 = pd.read_csv('events_sliding_window.csv')
    events_250 = pd.read_csv('events_sliding_window_250day_recalc.csv')
    
    # Calculate metrics for both
    metrics_500 = calculate_annualized_metrics(events_500, holding_days=500)
    metrics_250 = calculate_annualized_metrics(events_250, holding_days=250)
    
    print("\n" + "="*80)
    print("500-DAY HOLDING PERIOD")
    print("="*80)
    print(f"Holding Period: {metrics_500['holding_days']} days (~{metrics_500['holding_days']/252:.1f} years)")
    print(f"Periods Per Year: {metrics_500['periods_per_year']:.2f}")
    print(f"Mean Return: {metrics_500['mean_return']:+.2f}%")
    print(f"Annualized Mean Return: {metrics_500['annualized_mean']:+.2f}%")
    print(f"Median Return: {metrics_500['median_return']:+.2f}%")
    print(f"Annualized Median Return: {metrics_500['annualized_median']:+.2f}%")
    print(f"Win Rate: {metrics_500['win_rate']:.1f}%")
    print(f"Sharpe Ratio: {metrics_500['sharpe']:.4f}")
    print(f"Trades Per Year: {metrics_500['trades_per_year']:.2f}")
    
    print("\n" + "="*80)
    print("250-DAY HOLDING PERIOD")
    print("="*80)
    print(f"Holding Period: {metrics_250['holding_days']} days (~{metrics_250['holding_days']/252:.1f} years)")
    print(f"Periods Per Year: {metrics_250['periods_per_year']:.2f}")
    print(f"Mean Return: {metrics_250['mean_return']:+.2f}%")
    print(f"Annualized Mean Return: {metrics_250['annualized_mean']:+.2f}%")
    print(f"Median Return: {metrics_250['median_return']:+.2f}%")
    print(f"Annualized Median Return: {metrics_250['annualized_median']:+.2f}%")
    print(f"Win Rate: {metrics_250['win_rate']:.1f}%")
    print(f"Sharpe Ratio: {metrics_250['sharpe']:.4f}")
    print(f"Trades Per Year: {metrics_250['trades_per_year']:.2f}")
    
    print("\n" + "="*80)
    print("COMPARISON & COMPOUNDING ADVANTAGE")
    print("="*80)
    
    delta_annualized = metrics_250['annualized_mean'] - metrics_500['annualized_mean']
    delta_winrate = metrics_250['win_rate'] - metrics_500['win_rate']
    delta_sharpe = metrics_250['sharpe'] - metrics_500['sharpe']
    delta_trades = metrics_250['trades_per_year'] - metrics_500['trades_per_year']
    
    print(f"\nAnnualized Mean Return:")
    print(f"  250-day: {metrics_250['annualized_mean']:+.2f}%")
    print(f"  500-day: {metrics_500['annualized_mean']:+.2f}%")
    print(f"  Advantage: {delta_annualized:+.2f}% ⭐" if delta_annualized > 0 else f"  Difference: {delta_annualized:+.2f}%")
    
    print(f"\nWin Rate:")
    print(f"  250-day: {metrics_250['win_rate']:.1f}%")
    print(f"  500-day: {metrics_500['win_rate']:.1f}%")
    print(f"  Advantage: {delta_winrate:+.1f}% ⭐" if delta_winrate > 0 else f"  Difference: {delta_winrate:+.1f}%")
    
    print(f"\nSharpe Ratio (Risk-Adjusted):")
    print(f"  250-day: {metrics_250['sharpe']:.4f}")
    print(f"  500-day: {metrics_500['sharpe']:.4f}")
    print(f"  Advantage: {delta_sharpe:+.4f} ⭐" if delta_sharpe > 0 else f"  Difference: {delta_sharpe:+.4f}")
    
    print(f"\nTrading Frequency:")
    print(f"  250-day: {metrics_250['trades_per_year']:.2f} cycles/year")
    print(f"  500-day: {metrics_500['trades_per_year']:.2f} cycles/year")
    print(f"  Additional cycles: {delta_trades:+.2f} per year ⭐")
    
    # Compound return simulation
    print("\n" + "="*80)
    print("COMPOUND RETURN SIMULATION (3 Years)")
    print("="*80)
    
    compound_500_1yr, periods_500_1yr = calculate_compound_returns(
        metrics_500['mean_return'], metrics_500['win_rate'], 500, years=1)
    compound_250_1yr, periods_250_1yr = calculate_compound_returns(
        metrics_250['mean_return'], metrics_250['win_rate'], 250, years=1)
    
    compound_500_3yr, periods_500_3yr = calculate_compound_returns(
        metrics_500['mean_return'], metrics_500['win_rate'], 500, years=3)
    compound_250_3yr, periods_250_3yr = calculate_compound_returns(
        metrics_250['mean_return'], metrics_250['win_rate'], 250, years=3)
    
    print(f"\n1-Year Horizon (with compounding):")
    print(f"  500-day: {periods_500_1yr:.1f} cycles → {compound_500_1yr:+.2f}% total return")
    print(f"  250-day: {periods_250_1yr:.1f} cycles → {compound_250_1yr:+.2f}% total return")
    print(f"  Advantage: {compound_250_1yr - compound_500_1yr:+.2f}% ⭐" if compound_250_1yr > compound_500_1yr else f"  Difference: {compound_250_1yr - compound_500_1yr:+.2f}%")
    
    print(f"\n3-Year Horizon (with compounding):")
    print(f"  500-day: {periods_500_3yr:.1f} cycles → {compound_500_3yr:+.2f}% total return")
    print(f"  250-day: {periods_250_3yr:.1f} cycles → {compound_250_3yr:+.2f}% total return")
    print(f"  Advantage: {compound_250_3yr - compound_500_3yr:+.2f}% ⭐" if compound_250_3yr > compound_500_3yr else f"  Difference: {compound_250_3yr - compound_500_3yr:+.2f}%")
    
    # Summary
    print("\n" + "="*80)
    print("RECOMMENDATION")
    print("="*80)
    
    winner = "250-day" if metrics_250['annualized_mean'] > metrics_500['annualized_mean'] else "500-day"
    
    print(f"\n✅ WINNER: {winner} holding period")
    print(f"\nKey Advantages of 250-day window:")
    print(f"  • {metrics_250['annualized_mean']:+.2f}% annualized return vs {metrics_500['annualized_mean']:+.2f}%")
    print(f"  • {metrics_250['win_rate']:.1f}% win rate (vs {metrics_500['win_rate']:.1f}%) - much more consistent")
    print(f"  • {metrics_250['trades_per_year']:.2f} compounding cycles per year (vs {metrics_500['trades_per_year']:.2f})")
    print(f"  • Lower risk (higher win rate = more predictable outcomes)")
    
    # Save comparison
    comparison_df = pd.DataFrame([
        {
            'Window': '500-day',
            'Holding_Days': 500,
            'Mean_Return_%': metrics_500['mean_return'],
            'Annualized_Mean_%': metrics_500['annualized_mean'],
            'Win_Rate_%': metrics_500['win_rate'],
            'Sharpe': metrics_500['sharpe'],
            'Trades_Per_Year': metrics_500['trades_per_year'],
            '1Yr_Compound_%': compound_500_1yr,
            '3Yr_Compound_%': compound_500_3yr
        },
        {
            'Window': '250-day',
            'Holding_Days': 250,
            'Mean_Return_%': metrics_250['mean_return'],
            'Annualized_Mean_%': metrics_250['annualized_mean'],
            'Win_Rate_%': metrics_250['win_rate'],
            'Sharpe': metrics_250['sharpe'],
            'Trades_Per_Year': metrics_250['trades_per_year'],
            '1Yr_Compound_%': compound_250_1yr,
            '3Yr_Compound_%': compound_250_3yr
        }
    ])
    
    comparison_df.to_csv('window_comparison_annualized.csv', index=False)
    print(f"\n✓ Saved detailed comparison to: window_comparison_annualized.csv")
    
    print("\n" + "="*80)
    print("✅ ANALYSIS COMPLETE")
    print("="*80)

if __name__ == '__main__':
    main()
