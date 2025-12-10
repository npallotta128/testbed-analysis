"""
Position Capacity Bucket Analysis

Shows how much capital each position could take and what constraint binds
"""

import pandas as pd
import numpy as np

def bucket_positions(positions_df, capital_label):
    """Analyze position sizes and constraints"""
    
    size_buckets = [
        (0, 25000, '<$25k'),
        (25000, 100000, '$25-100k'),
        (100000, 500000, '$100-500k'),
        (500000, 1000000, '$500k-$1M'),
        (1000000, float('inf'), '>$1M'),
    ]
    
    results = []
    
    for min_size, max_size, label in size_buckets:
        subset = positions_df[
            (positions_df['position_size'] >= min_size) & 
            (positions_df['position_size'] < max_size)
        ]
        
        if len(subset) == 0:
            continue
        
        total_capital = subset['position_size'].sum()
        n_positions = len(subset)
        avg_size = subset['position_size'].mean()
        
        vol_constrained = (subset['binding_constraint'] == 'volume').sum()
        cap_constrained = (subset['binding_constraint'] == 'capital').sum()
        sec_constrained = (subset['binding_constraint'] == 'security_limit').sum()
        
        winners = (subset['pnl'] > 0).sum()
        losers = (subset['pnl'] < 0).sum()
        win_rate = (winners / n_positions) * 100 if n_positions > 0 else 0
        
        avg_return = subset['return_pct'].mean()
        total_pnl = subset['pnl'].sum()
        
        results.append({
            'capital_level': capital_label,
            'size_bucket': label,
            'n_positions': n_positions,
            'total_capital_deployed': total_capital,
            'avg_position_size': avg_size,
            'volume_constrained_%': (vol_constrained / n_positions) * 100,
            'capital_constrained_%': (cap_constrained / n_positions) * 100,
            'security_constrained_%': (sec_constrained / n_positions) * 100,
            'win_rate_%': win_rate,
            'avg_return_%': avg_return,
            'total_pnl': total_pnl,
        })
    
    return results

print("="*100)
print("POSITION CAPACITY BUCKET ANALYSIS")
print("="*100)

# Analyze $1M (successful scenario)
print("\n" + "="*100)
print("$1M CAPITAL - DETAILED BREAKDOWN")
print("="*100)

pos_1m = pd.read_csv('no_staging_positions_1B.csv')
# Filter to first 326 positions to match $1M scenario
pos_1m_subset = pos_1m.head(326).copy()

buckets_1m = bucket_positions(pos_1m_subset, '$1M')
df_1m = pd.DataFrame(buckets_1m)

print("\n" + df_1m.to_string(index=False))

print(f"\n\nSUMMARY FOR $1M:")
print(f"  Total positions: {len(pos_1m_subset)}")
print(f"  Total deployed: ${pos_1m_subset['position_size'].sum()/1e6:.2f}M")
print(f"  Avg position: ${pos_1m_subset['position_size'].mean():,.0f}")
print(f"  Win rate: {(pos_1m_subset['pnl'] > 0).mean()*100:.1f}%")

# Analyze $1B (capacity-limited scenario)
print("\n\n" + "="*100)
print("$1B CAPITAL - DETAILED BREAKDOWN")
print("="*100)

pos_1b = pd.read_csv('no_staging_positions_1B.csv')

buckets_1b = bucket_positions(pos_1b, '$1B')
df_1b = pd.DataFrame(buckets_1b)

print("\n" + df_1b.to_string(index=False))

print(f"\n\nSUMMARY FOR $1B:")
print(f"  Total positions: {len(pos_1b)}")
print(f"  Total deployed: ${pos_1b['position_size'].sum()/1e6:.2f}M")
print(f"  Avg position: ${pos_1b['position_size'].mean():,.0f}")
print(f"  Win rate: {(pos_1b['pnl'] > 0).mean()*100:.1f}%")

# Combined analysis
print("\n\n" + "="*100)
print("CAPACITY INSIGHTS")
print("="*100)

print("\nPOSITION SIZE DISTRIBUTION:")
for _, row in df_1b.iterrows():
    pct = (row['n_positions'] / len(pos_1b)) * 100
    print(f"  {row['size_bucket']}: {row['n_positions']} positions ({pct:.1f}%)")

print("\n\nCONSTRAINT BINDING RATES:")
vol_pct = (pos_1b['binding_constraint'] == 'volume').mean() * 100
cap_pct = (pos_1b['binding_constraint'] == 'capital').mean() * 100
sec_pct = (pos_1b['binding_constraint'] == 'security_limit').mean() * 100

print(f"  Volume constraint: {vol_pct:.1f}% of positions")
print(f"  Capital constraint: {cap_pct:.1f}% of positions")
print(f"  Security limit: {sec_pct:.1f}% of positions")

print("\n\nCAPACITY BY CONSTRAINT:")
for constraint in ['volume', 'capital', 'security_limit']:
    subset = pos_1b[pos_1b['binding_constraint'] == constraint]
    if len(subset) > 0:
        avg_cap = subset['capital_cap'].mean()
        avg_vol = subset['volume_cap'].mean()
        avg_size = subset['position_size'].mean()
        
        print(f"\n  {constraint.upper()}:")
        print(f"    Avg capital cap: ${avg_cap:,.0f}")
        print(f"    Avg volume cap: ${avg_vol:,.0f}")
        print(f"    Avg actual size: ${avg_size:,.0f}")
        
        if constraint == 'volume':
            headroom = ((avg_cap - avg_vol) / avg_vol) * 100
            print(f"    Capital headroom: {headroom:.0f}% above volume cap")

print("\n\n" + "="*100)
print("KEY FINDINGS")
print("="*100)

print("\n1. POSITION SIZE CONCENTRATION:")
small = len(pos_1b[pos_1b['position_size'] < 500000])
medium = len(pos_1b[(pos_1b['position_size'] >= 500000) & (pos_1b['position_size'] < 1000000)])
large = len(pos_1b[pos_1b['position_size'] >= 1000000])
print(f"   • <$500k: {small} positions ({small/len(pos_1b)*100:.1f}%)")
print(f"   • $500k-$1M: {medium} positions ({medium/len(pos_1b)*100:.1f}%)")
print(f"   • >$1M: {large} positions ({large/len(pos_1b)*100:.1f}%)")

print("\n2. VOLUME CONSTRAINT DOMINANCE:")
print(f"   • {vol_pct:.1f}% of positions hit volume limit (5% ADV)")
print(f"   • Average volume cap: ${pos_1b[pos_1b['binding_constraint']=='volume']['volume_cap'].mean()/1e6:.2f}M")
print(f"   • Increasing to 10% ADV would ~double position sizes")

print("\n3. CAPITAL EFFICIENCY:")
total_deployed = pos_1b['position_size'].sum()
total_potential_capital = pos_1b['capital_cap'].sum()
efficiency = (total_deployed / total_potential_capital) * 100
print(f"   • Deployed: ${total_deployed/1e6:.0f}M of ${total_potential_capital/1e6:.0f}M potential")
print(f"   • Capital utilization: {efficiency:.1f}% (volume-limited)")

print("\n4. PERFORMANCE QUALITY:")
winners = pos_1b[pos_1b['pnl'] > 0]
losers = pos_1b[pos_1b['pnl'] < 0]
print(f"   • Winners: {len(winners)} positions, avg return: {winners['return_pct'].mean():.1f}%")
print(f"   • Losers: {len(losers)} positions, avg return: {losers['return_pct'].mean():.1f}%")
print(f"   • Median return: {pos_1b['return_pct'].median():.1f}%")

print("\n" + "="*100)

# Save detailed analysis
df_combined = pd.concat([df_1m, df_1b], ignore_index=True)
df_combined.to_csv('position_capacity_buckets.csv', index=False)
print("\n✓ Saved detailed analysis to position_capacity_buckets.csv")
