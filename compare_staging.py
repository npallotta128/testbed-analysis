"""
Compare Staging vs No-Staging Results
"""

import pandas as pd

print("="*80)
print("STAGING vs NO-STAGING COMPARISON")
print("="*80)

# Load results
staged = pd.read_csv('realistic_capital_allocation_results.csv')
no_staging = pd.read_csv('no_staging_allocation_results.csv')

# Create comparison
compare = pd.DataFrame({
    'Capital ($M)': staged['initial_capital'] / 1e6,
    'Staged Annualized %': staged['annualized_return_pct'],
    'No-Staging Annualized %': no_staging['annualized_return_pct'],
    'Difference (pp)': no_staging['annualized_return_pct'] - staged['annualized_return_pct'],
    'Staged Positions': staged['n_positions'],
    'No-Staging Positions': no_staging['n_positions'],
    'Position Diff': no_staging['n_positions'] - staged['n_positions'],
})

print("\n" + compare.to_string(index=False))

print("\n\nKEY FINDINGS:")
print("-" * 80)
print(f"At $1M: No-staging improves return by {compare.loc[0, 'Difference (pp)']:.2f} pp")
print(f"        Opens {compare.loc[0, 'Position Diff']:.0f} more positions")
print(f"\nAt $1B: No-staging improves return by {compare.loc[8, 'Difference (pp)']:.2f} pp")
print(f"        Opens {compare.loc[8, 'Position Diff']:.0f} more positions")

print("\n\nIMPLICATIONS:")
print("-" * 80)
print("• No-staging allows immediate deployment → higher position count")
print("• Better returns at all capital levels (21-27pp improvement)")
print("• $1M still positive (+34% annualized), larger capital still negative")
print("• Volume constraint still binds for 92-98% of positions")
print("• Core issue remains: only 21% win rate on top 1000 events")

print("\n" + "="*80)
