"""
Capital Allocation Backtest for Sliding Window Events
Uses LR model probabilities to rank dropout events and simulate equal-weight allocation.
"""
import pandas as pd
import numpy as np
import joblib
from scipy.stats import trim_mean

def load_model_and_events():
    """Load trained LR model and sliding window events with features"""
    model = joblib.load('ml_event_model_sliding_drop_lr.pkl')
    events = pd.read_csv('events_sliding_window_features.csv')
    
    # Filter dropout events only
    dropout = events[events['Event_Type'] == 'DROP'].copy()
    dropout = dropout.dropna(subset=['Future_Return'])
    
    print(f"Loaded {len(dropout)} dropout events")
    return model, dropout

def get_features(df):
    """Extract feature columns matching training"""
    feature_cols = [c for c in df.columns if c.endswith('_blk_pct') or c in 
                    ['ret_20', 'ret_60', 'ret_120', 'vol_20', 'vol_60', 'vol_120',
                     'Prev_Quality', 'New_Quality', 'Quality_Change', 'quality_change_relative_block_mean',
                     'cumulative_dropout_count', 'cumulative_acquisition_count', 'cumulative_dropout_acq_ratio']]
    feature_cols = [c for c in feature_cols if c in df.columns]
    return df[feature_cols].fillna(0)

def compute_summary_stats(returns, label):
    """Compute summary statistics with winsorization"""
    returns_clean = returns.dropna()
    if len(returns_clean) == 0:
        return {f'{label}_mean': np.nan, f'{label}_median': np.nan, 
                f'{label}_trimmed_mean': np.nan, f'{label}_std': np.nan, f'{label}_positive_pct': np.nan}
    
    # Winsorize at 1% and 99% for trimmed mean
    trimmed = trim_mean(returns_clean, proportiontocut=0.01)
    
    return {
        f'{label}_mean': returns_clean.mean(),
        f'{label}_median': returns_clean.median(),
        f'{label}_trimmed_mean': trimmed,
        f'{label}_std': returns_clean.std(),
        f'{label}_positive_pct': (returns_clean > 0).mean() * 100,
        f'{label}_count': len(returns_clean)
    }

def run_allocation_backtest(model, dropout_df):
    """
    Backtest capital allocation using model probabilities.
    Split into train/test by blocks, use test events only.
    """
    # Train/test split by block
    blocks = dropout_df['Block'].unique()
    train_blocks = blocks[:int(len(blocks) * 0.7)]
    test_df = dropout_df[~dropout_df['Block'].isin(train_blocks)].copy()
    
    print(f"Test set: {len(test_df)} events")
    
    # Get model predictions
    X_test = get_features(test_df)
    test_df['model_proba'] = model.predict_proba(X_test)[:, 1]
    
    # Rank by Quality_Change for baseline heuristic
    test_df['quality_rank'] = test_df['Quality_Change'].rank(ascending=False, pct=True)
    
    # Define selection tiers
    tiers = {
        'top_1pct': 0.01,
        'top_5pct': 0.05,
        'top_10pct': 0.10
    }
    
    results = []
    
    for tier_name, threshold in tiers.items():
        n_select = int(len(test_df) * threshold)
        if n_select == 0:
            n_select = 1
        
        # Model selection
        model_top = test_df.nlargest(n_select, 'model_proba')
        model_stats = compute_summary_stats(model_top['Future_Return'], 'model')
        
        # Quality_Change heuristic selection
        quality_top = test_df.nlargest(n_select, 'Quality_Change')
        quality_stats = compute_summary_stats(quality_top['Future_Return'], 'quality_change')
        
        # Random baseline (average of 10 random samples)
        random_means = []
        random_medians = []
        for _ in range(10):
            random_sample = test_df.sample(n=n_select, random_state=np.random.randint(0, 10000))
            random_means.append(random_sample['Future_Return'].mean())
            random_medians.append(random_sample['Future_Return'].median())
        
        random_stats = {
            'random_mean': np.mean(random_means),
            'random_median': np.median(random_medians),
            'random_std': np.std(random_means),
            'random_positive_pct': np.nan,  # Not computed per sample
            'random_count': n_select
        }
        
        # Combine stats
        tier_result = {'tier': tier_name, 'n_events': n_select}
        tier_result.update(model_stats)
        tier_result.update(quality_stats)
        tier_result.update(random_stats)
        
        # Improvement ratios
        tier_result['improvement_vs_quality'] = model_stats['model_mean'] / quality_stats['quality_change_mean'] if quality_stats['quality_change_mean'] != 0 else np.nan
        tier_result['improvement_vs_random'] = model_stats['model_mean'] / random_stats['random_mean'] if random_stats['random_mean'] != 0 else np.nan
        
        results.append(tier_result)
        
        print(f"\n{tier_name.upper()} ({n_select} events):")
        print(f"  Model:          mean={model_stats['model_mean']:.2f}%, median={model_stats['model_median']:.2f}%, positive={model_stats['model_positive_pct']:.1f}%")
        print(f"  Quality_Change: mean={quality_stats['quality_change_mean']:.2f}%, median={quality_stats['quality_change_median']:.2f}%, positive={quality_stats['quality_change_positive_pct']:.1f}%")
        print(f"  Random:         mean={random_stats['random_mean']:.2f}%, median={random_stats['random_median']:.2f}%")
        print(f"  Improvement:    vs quality={tier_result['improvement_vs_quality']:.2f}x, vs random={tier_result['improvement_vs_random']:.2f}x")
    
    return pd.DataFrame(results)

def main():
    print("="*80)
    print("SLIDING WINDOW CAPITAL ALLOCATION BACKTEST")
    print("="*80)
    
    model, dropout_df = load_model_and_events()
    results_df = run_allocation_backtest(model, dropout_df)
    
    # Save results
    results_df.to_csv('backtest_sliding_allocation.csv', index=False)
    print(f"\nResults saved to backtest_sliding_allocation.csv")
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(results_df[['tier', 'n_events', 'model_mean', 'quality_change_mean', 'random_mean', 
                       'improvement_vs_quality', 'improvement_vs_random']].to_string(index=False))

if __name__ == '__main__':
    main()
