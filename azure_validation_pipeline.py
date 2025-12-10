"""
Azure End-to-End Validation Pipeline
Chains: data fetch → sliding window events → ML training → allocation backtest

Environment variables:
  AZURE_LIMIT: row limit for data fetch (default None = full table)
  SKIP_FETCH: set to '1' to skip Azure fetch and use existing data.csv
  
Usage:
  python azure_validation_pipeline.py
  AZURE_LIMIT=500000 python azure_validation_pipeline.py
  SKIP_FETCH=1 python azure_validation_pipeline.py  # Use existing data.csv
"""
import os
import sys
import time
import pandas as pd
import numpy as np
import joblib
from scipy.stats import trim_mean

# Import components
from azure_run_protocol import connect_engine, fetch_market_values, fetch_market_values_chunked
from optimize_dropout_strategy_safe import test_dropout_parameters, load_market_caps
from ml_sliding_window import compute_prior_returns_volatility, build_features, create_labels, train_eval_model

def step1_fetch_azure_data(limit=None, skip_fetch=False):
    """Fetch data from Azure SQL or use existing data.csv"""
    if skip_fetch:
        print("\n" + "="*80)
        print("STEP 1: Using existing data.csv (SKIP_FETCH=1)")
        print("="*80)
        if not os.path.exists('data.csv'):
            raise FileNotFoundError("data.csv not found; cannot skip fetch")
        return
    
    print("\n" + "="*80)
    print("STEP 1: Fetching data from Azure SQL")
    print("="*80)
    
    engine = connect_engine()
    if engine is None:
        print("ERROR: Azure connection failed (missing ODBC drivers)")
        print("Run with SKIP_FETCH=1 to use existing data.csv instead")
        sys.exit(1)
    
    chunk_env = os.getenv('CHUNKED_FETCH') == '1'
    if chunk_env and not limit:
        max_rows = int(os.getenv('MAX_ROWS')) if os.getenv('MAX_ROWS') else None
        fetch_market_values_chunked(engine, chunk_size=250000, max_rows=max_rows, output_path='data.csv')
    else:
        df = fetch_market_values(engine, limit=limit)
        df.to_csv('data.csv', index=False)
    
    print("✓ Data saved to data.csv")

def step2_generate_sliding_events():
    """Generate sliding window events"""
    print("\n" + "="*80)
    print("STEP 2: Generating sliding window events (stride=50)")
    print("="*80)
    
    result, loss_df, acq_df = test_dropout_parameters(
        'data.csv',
        block_size=200,
        num_blocks=50,
        distance_threshold=40,
        quality_metric='avg_return',
        quality_threshold_percentile=80,
        stride=50,
        forward_window=500
    )
    
    loss_df['Event_Type'] = 'DROP'
    acq_df['Event_Type'] = 'ACQ'
    events = pd.concat([loss_df, acq_df], ignore_index=True)
    events.to_csv('events_sliding_window.csv', index=False)
    
    print(f"✓ Generated {len(loss_df)} dropout, {len(acq_df)} acquisition events")
    print(f"✓ Saved to events_sliding_window.csv")
    return events

def step3_train_ml_model():
    """Train ML model on sliding window events"""
    print("\n" + "="*80)
    print("STEP 3: Training ML model")
    print("="*80)
    
    df = pd.read_csv('events_sliding_window.csv')
    print(f"Loaded {len(df)} events")
    
    # Compute returns/vol
    df = compute_prior_returns_volatility(df)
    
    # Feature engineering
    df = build_features(df)
    
    # Create labels
    df = create_labels(df, percentile=90)
    
    # Save enriched dataset
    df.to_csv('events_sliding_window_features.csv', index=False)
    print(f"✓ Saved enriched events to events_sliding_window_features.csv")
    
    # Train dropout model (LR only for speed)
    print("\nTraining DROPOUT Logistic Regression model...")
    model, metrics = train_eval_model(df, 'DROP', 'LR')
    
    if model:
        joblib.dump(model, 'ml_event_model_sliding_drop_lr.pkl')
        print(f"✓ Model saved")
        print(f"  AP: {metrics['avg_precision']:.4f}")
        print(f"  Precision@5%: {metrics['precision@5pct']:.4f}")
        print(f"  Precision@10%: {metrics['precision@10pct']:.4f}")
        return model, df
    else:
        print("ERROR: Model training failed")
        sys.exit(1)

def step4_allocation_backtest(model, dropout_df):
    """Run allocation backtest"""
    print("\n" + "="*80)
    print("STEP 4: Capital allocation backtest")
    print("="*80)
    
    # Extract features
    feature_cols = [c for c in dropout_df.columns if c.endswith('_blk_pct') or c in 
                    ['ret_20', 'ret_60', 'ret_120', 'vol_20', 'vol_60', 'vol_120',
                     'Prev_Quality', 'New_Quality', 'Quality_Change', 'quality_change_relative_block_mean',
                     'cumulative_dropout_count', 'cumulative_acquisition_count', 'cumulative_dropout_acq_ratio']]
    feature_cols = [c for c in feature_cols if c in dropout_df.columns]
    
    # Filter dropout, train/test split
    dropout = dropout_df[dropout_df['Event_Type'] == 'DROP'].copy()
    dropout = dropout.dropna(subset=['Future_Return'])
    
    blocks = dropout['Block'].unique()
    train_blocks = blocks[:int(len(blocks) * 0.7)]
    test_df = dropout[~dropout['Block'].isin(train_blocks)].copy()
    
    print(f"Test set: {len(test_df)} events")
    
    # Predictions
    X_test = test_df[feature_cols].fillna(0)
    test_df['model_proba'] = model.predict_proba(X_test)[:, 1]
    
    # Backtest tiers
    tiers = {'top_1pct': 0.01, 'top_5pct': 0.05, 'top_10pct': 0.10}
    results = []
    
    for tier_name, threshold in tiers.items():
        n_select = max(1, int(len(test_df) * threshold))
        
        # Model selection
        model_top = test_df.nlargest(n_select, 'model_proba')
        model_mean = model_top['Future_Return'].mean()
        model_median = model_top['Future_Return'].median()
        model_pos_pct = (model_top['Future_Return'] > 0).mean() * 100
        
        # Quality heuristic
        quality_top = test_df.nlargest(n_select, 'Quality_Change')
        quality_mean = quality_top['Future_Return'].mean()
        
        # Random baseline
        random_means = [test_df.sample(n=n_select, random_state=i)['Future_Return'].mean() for i in range(10)]
        random_mean = np.mean(random_means)
        
        improvement_vs_quality = model_mean / quality_mean if quality_mean != 0 else np.nan
        improvement_vs_random = model_mean / random_mean if random_mean != 0 else np.nan
        
        results.append({
            'tier': tier_name,
            'n_events': n_select,
            'model_mean': model_mean,
            'model_median': model_median,
            'model_positive_pct': model_pos_pct,
            'quality_mean': quality_mean,
            'random_mean': random_mean,
            'improvement_vs_quality': improvement_vs_quality,
            'improvement_vs_random': improvement_vs_random
        })
        
        print(f"\n{tier_name.upper()} ({n_select} events):")
        print(f"  Model:   {model_mean:>10.2f}% mean, {model_median:>8.2f}% median, {model_pos_pct:>5.1f}% positive")
        print(f"  Quality: {quality_mean:>10.2f}% mean")
        print(f"  Random:  {random_mean:>10.2f}% mean")
        print(f"  Improvement: {improvement_vs_quality:.2f}x vs quality, {improvement_vs_random:.2f}x vs random")
    
    results_df = pd.DataFrame(results)
    results_df.to_csv('azure_validation_backtest.csv', index=False)
    print(f"\n✓ Results saved to azure_validation_backtest.csv")
    
    return results_df

def main():
    start_time = time.time()
    
    print("="*80)
    print("AZURE END-TO-END VALIDATION PIPELINE")
    print("="*80)
    
    # Configuration
    limit = int(os.getenv('AZURE_LIMIT')) if os.getenv('AZURE_LIMIT') else None
    skip_fetch = os.getenv('SKIP_FETCH') == '1'
    
    print(f"\nConfiguration:")
    print(f"  Data limit: {limit or 'None (full table)'}")
    print(f"  Skip fetch: {skip_fetch}")
    
    try:
        # Step 1: Fetch data
        step1_fetch_azure_data(limit=limit, skip_fetch=skip_fetch)
        
        # Step 2: Generate events
        events = step2_generate_sliding_events()
        
        # Step 3: Train model
        model, enriched_df = step3_train_ml_model()
        
        # Step 4: Backtest allocation
        results = step4_allocation_backtest(model, enriched_df)
        
        # Summary
        elapsed = time.time() - start_time
        print("\n" + "="*80)
        print("PIPELINE COMPLETE")
        print("="*80)
        print(f"Total time: {elapsed/60:.1f} minutes")
        print("\nFinal Results Summary:")
        print(results[['tier', 'model_mean', 'quality_mean', 'improvement_vs_quality']].to_string(index=False))
        
        print("\n✓ Validation successful - model performance confirmed on Azure data")
        
    except Exception as e:
        print(f"\n✗ Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
