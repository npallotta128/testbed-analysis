import pandas as pd
import numpy as np

ACQ_FILE = 'cluster_acquisition_events.csv'
LOSS_FILE = 'cluster_loss_events.csv'
ASSIGN_FILE = 'detailed_cluster_assignments.csv'

# Multiple decay strategies
STRATEGIES = {
    'Short_Term': {'lambda': 0.15, 'description': 'Heavy recency bias, recent blocks dominate'},
    'Medium_Term': {'lambda': 0.05, 'description': 'Moderate recency, balanced horizon'},
    'Long_Term': {'lambda': 0.02, 'description': 'Low decay, long-term accumulation emphasis'},
    'Equal_Weight': {'lambda': 0.0, 'description': 'No decay, all blocks weighted equally'},
}

WINSOR_LOWER = 0.01
WINSOR_UPPER = 0.99

def winsor(series: pd.Series, lower=WINSOR_LOWER, upper=WINSOR_UPPER):
    series = series.dropna()
    if series.empty:
        return series
    lo = series.quantile(lower)
    hi = series.quantile(upper)
    return series.clip(lo, hi)

def compute_recency_weights(df: pd.DataFrame, decay_lambda):
    if 'Block_ID' not in df.columns or decay_lambda == 0.0:
        return np.ones(len(df))
    max_block = df['Block_ID'].max()
    return np.exp(-decay_lambda * (max_block - df['Block_ID']))

def load_events():
    acq = pd.read_csv(ACQ_FILE).rename(columns={'Block':'Block_ID'})
    loss = pd.read_csv(LOSS_FILE).rename(columns={'Block':'Block_ID'})
    assign = pd.read_csv(ASSIGN_FILE)[['Block_ID','Cluster_ID','Security']]
    for df in [acq, loss]:
        for col in ['Prev_Quality','New_Quality','Quality_Jump','Quality_Loss','Final_Return']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
    return acq, loss, assign

def aggregate_security_metrics(acq, loss, assign, decay_lambda):
    # Base aggregates
    acq_grp = acq.groupby('Security')
    acq_df = acq_grp.agg(
        Acquisition_Event_Count=('Security','count'),
        Acquisition_Quality_Jump_Sum=('Quality_Jump','sum'),
        Acquisition_Quality_Jump_Avg=('Quality_Jump','mean'),
        Acquisition_Final_Return_Mean=('Final_Return','mean'),
        Acquisition_Final_Return_Median=('Final_Return','median')
    )
    loss_grp = loss.groupby('Security')
    loss_df = loss_grp.agg(
        Loss_Event_Count=('Security','count'),
        Loss_Quality_Loss_Sum=('Quality_Loss','sum'),
        Loss_Quality_Loss_Avg=('Quality_Loss','mean'),
        Loss_Final_Return_Mean=('Final_Return','mean'),
        Loss_Final_Return_Median=('Final_Return','median')
    )
    combined = acq_df.join(loss_df, how='outer').fillna(0)
    combined['Total_Event_Count'] = combined['Acquisition_Event_Count'] + combined['Loss_Event_Count']
    combined['Net_Quality_Delta'] = combined['Acquisition_Quality_Jump_Sum'] - combined['Loss_Quality_Loss_Sum']
    combined['Event_Balance_Ratio'] = np.where(combined['Total_Event_Count']>0,
                                               combined['Acquisition_Event_Count']/combined['Total_Event_Count'],0)

    # Winsorization
    acq['Winsor_Final_Return'] = winsor(acq['Final_Return'])
    loss['Winsor_Final_Return'] = winsor(loss['Final_Return'])
    
    acq_winsor_grp = acq.groupby('Security')['Winsor_Final_Return']
    loss_winsor_grp = loss.groupby('Security')['Winsor_Final_Return']
    combined['Acq_Winsor_Median_Return'] = acq_winsor_grp.median()
    combined['Loss_Winsor_Median_Return'] = loss_winsor_grp.median()
    combined[['Acq_Winsor_Median_Return','Loss_Winsor_Median_Return']] = \
        combined[['Acq_Winsor_Median_Return','Loss_Winsor_Median_Return']].fillna(0)

    # Recency weighting
    acq['Recency_Weight'] = compute_recency_weights(acq, decay_lambda)
    loss['Recency_Weight'] = compute_recency_weights(loss, decay_lambda)

    acq_rec_grp = acq.groupby('Security')
    loss_rec_grp = loss.groupby('Security')
    
    combined['Acq_Recency_Weighted_Jump_Sum'] = acq_rec_grp.apply(
        lambda g: (g['Quality_Jump'] * g['Recency_Weight']).sum() if 'Quality_Jump' in g else 0,
        include_groups=False
    )
    combined['Loss_Recency_Weighted_Loss_Sum'] = loss_rec_grp.apply(
        lambda g: (g['Quality_Loss'] * g['Recency_Weight']).sum() if 'Quality_Loss' in g else 0,
        include_groups=False
    )
    combined[['Acq_Recency_Weighted_Jump_Sum','Loss_Recency_Weighted_Loss_Sum']] = \
        combined[['Acq_Recency_Weighted_Jump_Sum','Loss_Recency_Weighted_Loss_Sum']].fillna(0)
    combined['Net_Quality_Delta_Recency'] = combined['Acq_Recency_Weighted_Jump_Sum'] - combined['Loss_Recency_Weighted_Loss_Sum']

    def weighted_mean(group, value_col, weight_col):
        vals = group[value_col]
        w = group[weight_col]
        if len(vals) == 0:
            return 0.0
        return (vals * w).sum() / w.sum() if w.sum() != 0 else 0.0

    combined['Acq_Recency_Winsor_Mean_Return'] = acq_rec_grp.apply(
        lambda g: weighted_mean(g, 'Winsor_Final_Return', 'Recency_Weight'),
        include_groups=False
    )
    combined['Loss_Recency_Winsor_Mean_Return'] = loss_rec_grp.apply(
        lambda g: weighted_mean(g, 'Winsor_Final_Return', 'Recency_Weight'),
        include_groups=False
    )
    combined[['Acq_Recency_Winsor_Mean_Return','Loss_Recency_Winsor_Mean_Return']] = \
        combined[['Acq_Recency_Winsor_Mean_Return','Loss_Recency_Winsor_Mean_Return']].fillna(0)
    
    combined['Weighted_Winsor_Final_Return_Recency'] = (
        (combined['Acq_Recency_Winsor_Mean_Return'] * combined['Acquisition_Event_Count'] +
         combined['Loss_Recency_Winsor_Mean_Return'] * combined['Loss_Event_Count']) /
        combined['Total_Event_Count'].replace({0:np.nan})
    ).fillna(0)

    combined['Quality_Momentum_Score_Adj'] = combined['Net_Quality_Delta_Recency'] * (
        combined['Acq_Winsor_Median_Return'] - combined['Loss_Winsor_Median_Return']
    )

    # Cluster diversity
    all_events = pd.concat([
        acq[['Security','Block_ID']],
        loss[['Security','Block_ID']]
    ], ignore_index=True).drop_duplicates()
    all_events = all_events.merge(assign, on=['Security','Block_ID'], how='left')
    diversity = all_events.groupby('Security').agg(
        Unique_Clusters=('Cluster_ID', lambda x: x.nunique()),
        Unique_Blocks=('Block_ID', 'nunique')
    )
    combined = combined.join(diversity, how='left').fillna({'Unique_Clusters':0,'Unique_Blocks':0})
    combined['Events_Per_Block'] = np.where(combined['Unique_Blocks']>0, 
                                            combined['Total_Event_Count']/combined['Unique_Blocks'],0)

    # Percentile ranks
    rank_cols = [
        'Net_Quality_Delta_Recency','Quality_Momentum_Score_Adj','Weighted_Winsor_Final_Return_Recency',
        'Event_Balance_Ratio','Events_Per_Block'
    ]
    for c in rank_cols:
        combined[c+'_Percentile'] = combined[c].rank(pct=True)

    # Composite rank
    combined['Composite_Quality_Event_Rank'] = (
        0.30*combined['Net_Quality_Delta_Recency_Percentile'] +
        0.30*combined['Quality_Momentum_Score_Adj_Percentile'] +
        0.20*combined['Weighted_Winsor_Final_Return_Recency_Percentile'] +
        0.10*combined['Event_Balance_Ratio_Percentile'] +
        0.10*combined['Events_Per_Block_Percentile']
    )
    
    combined = combined.sort_values('Composite_Quality_Event_Rank', ascending=False)
    combined.reset_index(inplace=True)
    return combined

def run_strategy(strategy_name, params, acq, loss, assign):
    print(f"\nRunning {strategy_name} (λ={params['lambda']}): {params['description']}")
    ranked = aggregate_security_metrics(acq, loss, assign, params['lambda'])
    output_file = f"quality_ranking_{strategy_name}.csv"
    ranked.to_csv(output_file, index=False)
    print(f"  Saved: {output_file}")
    top_50 = ranked.head(50)[['Security','Composite_Quality_Event_Rank','Net_Quality_Delta_Recency',
                              'Quality_Momentum_Score_Adj','Weighted_Winsor_Final_Return_Recency']]
    top_50.to_csv(f"quality_ranking_{strategy_name}_top50.csv", index=False)
    return ranked

def find_consensus_stocks(strategies_dict):
    # Find stocks in top N across multiple strategies
    top_ns = [20, 50, 100]
    consensus = {}
    
    for n in top_ns:
        stock_counts = {}
        for strategy_name in strategies_dict.keys():
            df = pd.read_csv(f"quality_ranking_{strategy_name}.csv")
            top_stocks = set(df.head(n)['Security'])
            for stock in top_stocks:
                stock_counts[stock] = stock_counts.get(stock, 0) + 1
        
        # Filter stocks appearing in at least 3 strategies
        consensus[n] = {stock: count for stock, count in stock_counts.items() if count >= 3}
    
    return consensus

def main():
    print("="*80)
    print("MULTI-TIMEFRAME QUALITY EVENT RANKING")
    print("="*80)
    
    acq, loss, assign = load_events()
    print(f"Loaded {len(acq)} acquisition events, {len(loss)} loss events")
    
    results = {}
    for strategy_name, params in STRATEGIES.items():
        results[strategy_name] = run_strategy(strategy_name, params, acq, loss, assign)
    
    print("\n" + "="*80)
    print("CONSENSUS ANALYSIS")
    print("="*80)
    consensus = find_consensus_stocks(STRATEGIES)
    
    consensus_summary = []
    for n, stocks in consensus.items():
        print(f"\nTop {n} Consensus (appearing in 3+ strategies):")
        sorted_stocks = sorted(stocks.items(), key=lambda x: x[1], reverse=True)[:20]
        for stock, count in sorted_stocks:
            print(f"  {stock}: {count}/4 strategies")
            consensus_summary.append({'Top_N': n, 'Security': stock, 'Strategy_Count': count})
    
    pd.DataFrame(consensus_summary).to_csv('quality_ranking_consensus.csv', index=False)
    print("\nSaved: quality_ranking_consensus.csv")
    
    # Strategy comparison table
    comparison = []
    for strategy_name in STRATEGIES.keys():
        df = pd.read_csv(f"quality_ranking_{strategy_name}.csv")
        comparison.append({
            'Strategy': strategy_name,
            'Lambda': STRATEGIES[strategy_name]['lambda'],
            'Top_50_Avg_Net_Quality_Delta': df.head(50)['Net_Quality_Delta_Recency'].mean(),
            'Top_50_Avg_Momentum_Score': df.head(50)['Quality_Momentum_Score_Adj'].mean(),
            'Top_50_Avg_Return': df.head(50)['Weighted_Winsor_Final_Return_Recency'].mean(),
        })
    
    comparison_df = pd.DataFrame(comparison)
    comparison_df.to_csv('quality_ranking_strategy_comparison.csv', index=False)
    print("\nStrategy Comparison:")
    print(comparison_df)
    print("\nSaved: quality_ranking_strategy_comparison.csv")
    
    print("\n" + "="*80)
    print("INVESTMENT STRATEGY RECOMMENDATIONS")
    print("="*80)
    print("\n1. CONSERVATIVE (Long_Term): Focus on sustained quality improvement")
    print("   → Use quality_ranking_Long_Term_top50.csv")
    print("\n2. BALANCED (Medium_Term): Moderate recency with stability")
    print("   → Use quality_ranking_Medium_Term_top50.csv")
    print("\n3. OPPORTUNISTIC (Short_Term): Recent quality momentum plays")
    print("   → Use quality_ranking_Short_Term_top50.csv")
    print("\n4. CORE HOLDINGS (Consensus): High-conviction cross-strategy picks")
    print("   → Use quality_ranking_consensus.csv (3-4 strategy appearances)")
    print("\n" + "="*80)

if __name__ == '__main__':
    main()
