"""
Calculate yearly returns from cluster jump signals
"""

import pandas as pd
import numpy as np

# Load signals
df = pd.read_csv('cluster_jumps_full_250d_winsorized.csv')
df['Date'] = pd.to_datetime(df['Date'])
df['Year'] = df['Date'].dt.year

# Use winsorized returns if available, else regular
return_col = 'return_250d_winsorized' if 'return_250d_winsorized' in df.columns else 'return_250d'

print("="*80)
print("YEARLY RETURNS ANALYSIS")
print("="*80)
print(f"\nTotal signals: {len(df):,}")
print(f"Date range: {df['Date'].min()} to {df['Date'].max()}")
print(f"Using return column: {return_col}")

# Overall statistics
print("\n" + "-"*80)
print("OVERALL STATISTICS")
print("-"*80)
print(f"Total trades: {len(df):,}")
print(f"Win rate: {(df[return_col] > 0).sum() / len(df) * 100:.2f}%")
print(f"Mean return: {df[return_col].mean():.2f}%")
print(f"Median return: {df[return_col].median():.2f}%")
print(f"Std dev: {df[return_col].std():.2f}%")

# Yearly breakdown
print("\n" + "-"*80)
print("YEARLY BREAKDOWN")
print("-"*80)
print(f"{'Year':<8} {'Signals':<10} {'Win Rate':<12} {'Mean Ret %':<14} {'Median Ret %':<16} {'Std Dev %':<12}")
print("-"*80)

yearly_stats = []
for year in sorted(df['Year'].unique()):
    year_data = df[df['Year'] == year]
    n_signals = len(year_data)
    win_rate = (year_data[return_col] > 0).sum() / n_signals * 100
    mean_ret = year_data[return_col].mean()
    median_ret = year_data[return_col].median()
    std_ret = year_data[return_col].std()
    
    print(f"{year:<8} {n_signals:<10,} {win_rate:<12.1f} {mean_ret:<14.2f} {median_ret:<16.2f} {std_ret:<12.2f}")
    
    yearly_stats.append({
        'Year': year,
        'N_Signals': n_signals,
        'Win_Rate_Pct': win_rate,
        'Mean_Return_Pct': mean_ret,
        'Median_Return_Pct': median_ret,
        'Std_Dev_Pct': std_ret,
        'Min_Return_Pct': year_data[return_col].min(),
        'Max_Return_Pct': year_data[return_col].max(),
        'Total_Return_Pct': year_data[return_col].sum()
    })

# Calculate simulated portfolio returns by year
# Assume equal-weighted portfolio starting fresh each year
print("\n" + "-"*80)
print("SIMULATED PORTFOLIO RETURNS BY YEAR (Equal-Weighted)")
print("-"*80)
print("Note: Assumes each signal gets equal weight and compounds within year")
print()
print(f"{'Year':<8} {'Portfolio Return %':<20} {'Compounded from $100k':<25}")
print("-"*80)

for year in sorted(df['Year'].unique()):
    year_data = df[df['Year'] == year]
    # Simple average return as proxy (not perfect but indicative)
    avg_return = year_data[return_col].mean() / 100.0
    portfolio_return = avg_return * 100
    final_value = 100000 * (1 + avg_return)
    
    print(f"{year:<8} {portfolio_return:<20.2f} ${final_value:<24,.0f}")

# Save to CSV
yearly_df = pd.DataFrame(yearly_stats)
yearly_df.to_csv('yearly_returns_analysis.csv', index=False)
print(f"\n{'='*80}")
print(f"Yearly statistics saved to: yearly_returns_analysis.csv")
print(f"{'='*80}")

# Calculate cumulative effect
print("\n" + "-"*80)
print("CUMULATIVE PERFORMANCE (if holding across years)")
print("-"*80)
cumulative = 100000
print(f"{'Year':<8} {'Avg Return %':<15} {'Cumulative Value':<20}")
print("-"*80)
for year in sorted(df['Year'].unique()):
    year_data = df[df['Year'] == year]
    avg_return = year_data[return_col].mean() / 100.0
    cumulative *= (1 + avg_return)
    print(f"{year:<8} {avg_return*100:<15.2f} ${cumulative:<19,.0f}")

print(f"\nFinal cumulative value: ${cumulative:,.0f}")
print(f"Total return: {(cumulative/100000 - 1)*100:.2f}%")
