import pandas as pd
import numpy as np

# Parameters for enhancement
WINSOR_LOWER = 0.01
WINSOR_UPPER = 0.99
DECAY_LAMBDA = 0.05  # recency decay; larger => more weight on recent blocks

ACQ_FILE = 'cluster_acquisition_events.csv'
LOSS_FILE = 'cluster_loss_events.csv'
ASSIGN_FILE = 'detailed_cluster_assignments.csv'

def load_events():
    acq = pd.read_csv(ACQ_FILE).rename(columns={'Block':'Block_ID'})
    loss = pd.read_csv(LOSS_FILE).rename(columns={'Block':'Block_ID'})
    assign = pd.read_csv(ASSIGN_FILE)[['Block_ID','Cluster_ID','Security']]
    for df in [acq, loss]:
        for col in ['Prev_Quality','New_Quality','Quality_Jump','Quality_Loss','Final_Return']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
    return acq, loss, assign

def winsor(series: pd.Series, lower=WINSOR_LOWER, upper=WINSOR_UPPER):
    series = series.dropna()
    if series.empty:
        return series
    lo = series.quantile(lower)
    hi = series.quantile(upper)
    return series.clip(lo, hi)

def compute_recency_weights(df: pd.DataFrame):
    if 'Block_ID' not in df.columns:
        return np.ones(len(df))
    max_block = df['Block_ID'].max()
    # weight increases for more recent blocks (higher Block_ID)
    # w = exp(-lambda*(max_block - block)) => recent (difference small) => larger weight
    return np.exp(-DECAY_LAMBDA * (max_block - df['Block_ID']))

def aggregate_security_metrics(acq, loss, assign):
    # Acquisition aggregates
    acq_grp = acq.groupby('Security')
    acq_df = acq_grp.agg(
        Acquisition_Event_Count=('Security','count'),
        Acquisition_Quality_Jump_Sum=('Quality_Jump','sum'),
        Acquisition_Quality_Jump_Avg=('Quality_Jump','mean'),
        Acquisition_Quality_Jump_Max=('Quality_Jump','max'),
        Acquisition_Final_Return_Mean=('Final_Return','mean'),
        Acquisition_Final_Return_Median=('Final_Return','median')
    )
    # Loss aggregates
    loss_grp = loss.groupby('Security')
    loss_df = loss_grp.agg(
        Loss_Event_Count=('Security','count'),
        Loss_Quality_Loss_Sum=('Quality_Loss','sum'),
        Loss_Quality_Loss_Avg=('Quality_Loss','mean'),
        Loss_Quality_Loss_Max=('Quality_Loss','max'),
        Loss_Final_Return_Mean=('Final_Return','mean'),
        Loss_Final_Return_Median=('Final_Return','median')
    )
    # Merge
    combined = acq_df.join(loss_df, how='outer')
    combined = combined.fillna(0)
    # Net metrics
    combined['Total_Event_Count'] = combined['Acquisition_Event_Count'] + combined['Loss_Event_Count']
    combined['Net_Quality_Delta'] = combined['Acquisition_Quality_Jump_Sum'] - combined['Loss_Quality_Loss_Sum']
    combined['Event_Balance_Ratio'] = np.where(combined['Total_Event_Count']>0,
                                               combined['Acquisition_Event_Count']/combined['Total_Event_Count'],0)
    # Return blend (weighted by event counts)
    acq_ret = combined['Acquisition_Final_Return_Mean'] * combined['Acquisition_Event_Count']
    loss_ret = combined['Loss_Final_Return_Mean'] * combined['Loss_Event_Count']
    combined['Weighted_Avg_Final_Return'] = np.where(combined['Total_Event_Count']>0,(acq_ret+loss_ret)/combined['Total_Event_Count'],0)
    # Quality momentum style score
    combined['Quality_Momentum_Score'] = combined['Net_Quality_Delta'] * (combined['Acquisition_Final_Return_Median'] - combined['Loss_Final_Return_Median'])

    # ------------------------- Enhancements: Winsorization & Recency -------------------------
    # Prepare winsorized returns per event before aggregation
    acq['Winsor_Final_Return'] = winsor(acq['Final_Return'])
    loss['Winsor_Final_Return'] = winsor(loss['Final_Return'])

    # Map winsorized stats
    acq_winsor_grp = acq.groupby('Security')['Winsor_Final_Return']
    loss_winsor_grp = loss.groupby('Security')['Winsor_Final_Return']

    combined['Acq_Winsor_Mean_Return'] = acq_winsor_grp.mean()
    combined['Acq_Winsor_Median_Return'] = acq_winsor_grp.median()
    combined['Loss_Winsor_Mean_Return'] = loss_winsor_grp.mean()
    combined['Loss_Winsor_Median_Return'] = loss_winsor_grp.median()

    combined[['Acq_Winsor_Mean_Return','Acq_Winsor_Median_Return','Loss_Winsor_Mean_Return','Loss_Winsor_Median_Return']] = \
        combined[['Acq_Winsor_Mean_Return','Acq_Winsor_Median_Return','Loss_Winsor_Mean_Return','Loss_Winsor_Median_Return']].fillna(0)

    # Recency weights
    acq['Recency_Weight'] = compute_recency_weights(acq)
    loss['Recency_Weight'] = compute_recency_weights(loss)

    # Recency weighted sums
    acq_rec_grp = acq.groupby('Security')
    loss_rec_grp = loss.groupby('Security')
    combined['Acq_Recency_Weighted_Jump_Sum'] = acq_rec_grp.apply(lambda g: (g['Quality_Jump'] * g['Recency_Weight']).sum() if 'Quality_Jump' in g else 0)
    combined['Loss_Recency_Weighted_Loss_Sum'] = loss_rec_grp.apply(lambda g: (g['Quality_Loss'] * g['Recency_Weight']).sum() if 'Quality_Loss' in g else 0)
    combined[['Acq_Recency_Weighted_Jump_Sum','Loss_Recency_Weighted_Loss_Sum']] = combined[['Acq_Recency_Weighted_Jump_Sum','Loss_Recency_Weighted_Loss_Sum']].fillna(0)
    combined['Net_Quality_Delta_Recency'] = combined['Acq_Recency_Weighted_Jump_Sum'] - combined['Loss_Recency_Weighted_Loss_Sum']

    # Recency-weighted winsorized returns (weighted mean)
    def weighted_mean(group, value_col, weight_col):
        vals = group[value_col]
        w = group[weight_col]
        if len(vals) == 0:
            return 0.0
        return (vals * w).sum() / w.sum() if w.sum() != 0 else 0.0

    combined['Acq_Recency_Winsor_Mean_Return'] = acq_rec_grp.apply(lambda g: weighted_mean(g, 'Winsor_Final_Return', 'Recency_Weight'))
    combined['Loss_Recency_Winsor_Mean_Return'] = loss_rec_grp.apply(lambda g: weighted_mean(g, 'Winsor_Final_Return', 'Recency_Weight'))
    combined[['Acq_Recency_Winsor_Mean_Return','Loss_Recency_Winsor_Mean_Return']] = combined[['Acq_Recency_Winsor_Mean_Return','Loss_Recency_Winsor_Mean_Return']].fillna(0)
    combined['Weighted_Winsor_Final_Return_Recency'] = (
        (combined['Acq_Recency_Winsor_Mean_Return'] * combined['Acquisition_Event_Count'] +
         combined['Loss_Recency_Winsor_Mean_Return'] * combined['Loss_Event_Count']) /
        combined['Total_Event_Count'].replace({0:np.nan})
    ).fillna(0)

    # Adjusted momentum using recency-weighted net delta and winsor medians
    combined['Quality_Momentum_Score_Adj'] = combined['Net_Quality_Delta_Recency'] * (
        combined['Acq_Winsor_Median_Return'] - combined['Loss_Winsor_Median_Return']
    )
    # Cluster diversity: unique clusters touched across all events
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
    # Per-block rates
    combined['Events_Per_Block'] = np.where(combined['Unique_Blocks']>0, combined['Total_Event_Count']/combined['Unique_Blocks'],0)
    # Percentile ranks for key metrics
    rank_cols = [
        'Net_Quality_Delta','Quality_Momentum_Score','Weighted_Avg_Final_Return',
        'Net_Quality_Delta_Recency','Quality_Momentum_Score_Adj','Weighted_Winsor_Final_Return_Recency',
        'Event_Balance_Ratio','Events_Per_Block'
    ]
    for c in rank_cols:
        combined[c+'_Percentile'] = combined[c].rank(pct=True)
    # Composite ranking (can tune weights)
    # Updated composite rank emphasizing recency-adjusted quality and robust returns
    combined['Composite_Quality_Event_Rank'] = (
        0.20*combined['Net_Quality_Delta_Recency_Percentile'] +
        0.20*combined['Quality_Momentum_Score_Adj_Percentile'] +
        0.20*combined['Weighted_Winsor_Final_Return_Recency_Percentile'] +
        0.15*combined['Net_Quality_Delta_Percentile'] +
        0.15*combined['Quality_Momentum_Score_Percentile'] +
        0.10*combined['Event_Balance_Ratio_Percentile'] +
        0.10*combined['Events_Per_Block_Percentile']
    )
    combined = combined.sort_values('Composite_Quality_Event_Rank', ascending=False)
    combined.reset_index(inplace=True)
    return combined

def save_outputs(ranked):
    ranked.to_csv('quality_event_security_rankings_enhanced.csv', index=False)
    # Top subsets
    ranked.head(100).to_csv('quality_event_top100_enhanced.csv', index=False)
    ranked[['Security','Composite_Quality_Event_Rank','Net_Quality_Delta_Recency','Quality_Momentum_Score_Adj','Weighted_Winsor_Final_Return_Recency']].head(50).to_csv('quality_event_leaderboard_enhanced.csv', index=False)

def main():
    acq, loss, assign = load_events()
    ranked = aggregate_security_metrics(acq, loss, assign)
    save_outputs(ranked)
    print('Saved rankings: quality_event_security_rankings_enhanced.csv (full), top100_enhanced, leaderboard_enhanced.')
    print(ranked.head(10))

if __name__ == '__main__':
    main()
