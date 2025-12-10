"""
ML Event Model for Sliding Window Events
Feature engineering and model training matching baseline approach but applied to sliding window events.
"""
import pandas as pd
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import average_precision_score, precision_score, recall_score, roc_auc_score
import joblib
import json

def load_events(csv_path):
    """Load event dataset"""
    df = pd.read_csv(csv_path)
    print(f"Loaded {len(df)} events from {csv_path}")
    return df

def compute_prior_returns_volatility(df, data_file='data.csv'):
    """Compute prior returns and volatilities - VECTORIZED"""
    print("Loading price data for return/vol calculation...")
    from optimize_dropout_strategy_safe import load_data_once
    _, closing = load_data_once(data_file)
    
    print(f"Pre-computing rolling returns/vol matrices for {len(closing.columns)} securities...")
    # Precompute pct_change once
    pct_changes = closing.pct_change() * 100
    
    # Precompute rolling windows
    windows = [20, 60, 120]
    returns_cache = {}
    vol_cache = {}
    
    for window in windows:
        print(f"  Window {window}...")
        # Rolling return: (close[t] - close[t-window]) / close[t-window] * 100
        shifted = closing.shift(window)
        returns_cache[window] = ((closing - shifted) / shifted * 100).values
        # Rolling vol: std of daily returns over window
        vol_cache[window] = pct_changes.rolling(window).std().values
    
    print(f"Computing features for {len(df)} events...")
    results = {'ret_20': [], 'vol_20': [], 'ret_60': [], 'vol_60': [], 'ret_120': [], 'vol_120': []}
    
    # Vectorized lookup
    for idx, row in df.iterrows():
        if idx % 25000 == 0:
            print(f"  {idx}/{len(df)}")
        
        security = row['Security']
        block = row['Block']
        event_timepoint = (block + 1) * 200
        
        if security not in closing.columns or event_timepoint >= len(closing):
            for k in results:
                results[k].append(np.nan)
            continue
        
        col_idx = closing.columns.get_loc(security)
        
        for window in windows:
            ret_val = returns_cache[window][event_timepoint, col_idx]
            vol_val = vol_cache[window][event_timepoint, col_idx]
            results[f'ret_{window}'].append(ret_val)
            results[f'vol_{window}'].append(vol_val)
    
    for k, v in results.items():
        df[k] = v
    
    print("Return/vol computation complete.")
    return df

def build_features(df):
    """Feature engineering matching baseline approach"""
    # Unify quality change column
    if 'Quality_Loss' in df.columns:
        df['Quality_Change'] = df['Quality_Loss'].fillna(0)
    if 'Quality_Jump' in df.columns:
        df['Quality_Change'] = df['Quality_Change'].fillna(df['Quality_Jump'])
    
    # Temporal features
    df = df.sort_values(['Security', 'Block']).reset_index(drop=True)
    df['time_since_last_dropout'] = df.groupby('Security').cumcount()
    df['time_since_last_acquisition'] = df.groupby('Security').cumcount()
    df['dropout_to_acquisition_gap'] = np.nan
    df['acquisition_to_dropout_gap'] = np.nan
    df['cumulative_dropout_count'] = (df['Event_Type'] == 'DROP').groupby(df['Security']).cumsum()
    df['cumulative_acquisition_count'] = (df['Event_Type'] == 'ACQ').groupby(df['Security']).cumsum()
    df['cumulative_dropout_acq_ratio'] = df['cumulative_dropout_count'] / (df['cumulative_acquisition_count'] + 1)
    
    # Block-level aggregates
    block_mean_qc = df.groupby('Block')['Quality_Change'].transform('mean')
    df['quality_change_relative_block_mean'] = df['Quality_Change'] - block_mean_qc
    df['block_acquisition_count'] = df.groupby('Block')['Event_Type'].transform(lambda x: (x == 'ACQ').sum())
    df['block_dropout_count'] = df.groupby('Block')['Event_Type'].transform(lambda x: (x == 'DROP').sum())
    df['block_ratio_dropout_acq'] = df['block_dropout_count'] / (df['block_acquisition_count'] + 1)
    
    # Block percentile ranks
    num_cols = ['Quality_Change', 'quality_change_relative_block_mean', 'ret_20', 'ret_60', 'ret_120',
                'vol_20', 'vol_60', 'vol_120', 'cumulative_dropout_count', 'cumulative_acquisition_count']
    for col in num_cols:
        if col in df.columns:
            df[f'{col}_blk_pct'] = df.groupby('Block')[col].rank(pct=True)
    
    return df

def create_labels(df, percentile=90):
    """Create binary labels for top decile forward returns"""
    train_blocks = df['Block'].unique()[:int(len(df['Block'].unique()) * 0.7)]
    train_data = df[df['Block'].isin(train_blocks)]
    threshold = np.percentile(train_data['Future_Return'].dropna(), percentile)
    df['label_high'] = (df['Future_Return'] >= threshold).astype(int)
    print(f"Label threshold (top {100-percentile}%): {threshold:.2f}")
    print(f"Positive class: {df['label_high'].sum()} / {len(df)} = {df['label_high'].mean()*100:.2f}%")
    return df

def train_eval_model(df, event_type, model_name='HGB'):
    """Train and evaluate model per event type"""
    subset = df[df['Event_Type'] == event_type].copy()
    subset = subset.dropna(subset=['Future_Return', 'label_high'])
    
    if len(subset) < 100:
        print(f"Insufficient {event_type} events ({len(subset)}); skipping.")
        return None
    
    feature_cols = [c for c in subset.columns if c.endswith('_blk_pct') or c in 
                    ['ret_20', 'ret_60', 'ret_120', 'vol_20', 'vol_60', 'vol_120',
                     'Prev_Quality', 'New_Quality', 'Quality_Change', 'quality_change_relative_block_mean',
                     'cumulative_dropout_count', 'cumulative_acquisition_count', 'cumulative_dropout_acq_ratio']]
    feature_cols = [c for c in feature_cols if c in subset.columns]
    
    X = subset[feature_cols].fillna(0)
    y = subset['label_high']
    
    # Train/test split by block
    blocks = subset['Block'].unique()
    train_blocks = blocks[:int(len(blocks) * 0.7)]
    train_mask = subset['Block'].isin(train_blocks)
    
    X_train, X_test = X[train_mask], X[~train_mask]
    y_train, y_test = y[train_mask], y[~train_mask]
    
    if model_name == 'HGB':
        model = HistGradientBoostingClassifier(max_iter=100, random_state=42, class_weight='balanced')
    else:
        model = Pipeline([
            ('scaler', StandardScaler()),
            ('lr', LogisticRegression(max_iter=1000, random_state=42, class_weight='balanced'))
        ])
    
    model.fit(X_train, y_train)
    
    y_pred_proba = model.predict_proba(X_test)[:, 1] if hasattr(model, 'predict_proba') else model.decision_function(X_test)
    
    ap = average_precision_score(y_test, y_pred_proba)
    auc = roc_auc_score(y_test, y_pred_proba) if len(np.unique(y_test)) > 1 else np.nan
    
    # Precision at top k%
    k_vals = [0.01, 0.05, 0.10]
    prec_at_k = {}
    for k in k_vals:
        top_k = int(len(y_pred_proba) * k)
        if top_k == 0:
            top_k = 1
        top_indices = np.argsort(y_pred_proba)[-top_k:]
        prec_at_k[f'precision@{int(k*100)}pct'] = y_test.iloc[top_indices].mean()
    
    metrics = {
        'event_type': event_type,
        'model': model_name,
        'train_size': len(X_train),
        'test_size': len(X_test),
        'avg_precision': ap,
        'auc_roc': auc,
        **prec_at_k
    }
    
    print(f"\n{event_type} - {model_name}:")
    print(f"  Train: {len(X_train)}, Test: {len(X_test)}")
    print(f"  AP: {ap:.4f}, AUC: {auc:.4f}")
    for k, v in prec_at_k.items():
        print(f"  {k}: {v:.4f}")
    
    return model, metrics

def main():
    # Load sliding window events
    df = load_events('events_sliding_window.csv')
    
    # Compute returns/vol
    df = compute_prior_returns_volatility(df)
    
    # Feature engineering
    df = build_features(df)
    
    # Create labels
    df = create_labels(df, percentile=90)
    
    # Save enriched dataset
    df.to_csv('events_sliding_window_features.csv', index=False)
    print(f"\nSaved enriched events to events_sliding_window_features.csv")
    
    # Train models per event type
    all_metrics = []
    for event_type in ['DROP', 'ACQ']:
        for model_name in ['HGB', 'LR']:
            model, metrics = train_eval_model(df, event_type, model_name)
            if metrics:
                all_metrics.append(metrics)
                joblib.dump(model, f'ml_event_model_sliding_{event_type.lower()}_{model_name.lower()}.pkl')
    
    # Save metrics
    with open('ml_event_metrics_sliding.json', 'w') as f:
        json.dump(all_metrics, f, indent=2)
    
    print("\nMetrics saved to ml_event_metrics_sliding.json")
    
    # Compare to baseline
    try:
        baseline_metrics = json.load(open('ml_event_metrics.json'))
        print("\n" + "="*60)
        print("BASELINE vs SLIDING WINDOW COMPARISON")
        print("="*60)
        baseline_df = pd.DataFrame(baseline_metrics)
        sliding_df = pd.DataFrame(all_metrics)
        
        for event_type in ['DROP', 'ACQ']:
            print(f"\n{event_type} Events:")
            base_row = baseline_df[(baseline_df['event_type'] == event_type) & (baseline_df['model'] == 'LR')]
            slide_row = sliding_df[(sliding_df['event_type'] == event_type) & (sliding_df['model'] == 'LR')]
            if not base_row.empty and not slide_row.empty:
                print(f"  Baseline AP: {base_row['avg_precision'].values[0]:.4f}, Sliding AP: {slide_row['avg_precision'].values[0]:.4f}")
                print(f"  Baseline P@5%: {base_row['precision@5pct'].values[0]:.4f}, Sliding P@5%: {slide_row['precision@5pct'].values[0]:.4f}")
                print(f"  Baseline P@10%: {base_row['precision@10pct'].values[0]:.4f}, Sliding P@10%: {slide_row['precision@10pct'].values[0]:.4f}")
    except:
        print("\nBaseline metrics not found for comparison.")

if __name__ == '__main__':
    main()
