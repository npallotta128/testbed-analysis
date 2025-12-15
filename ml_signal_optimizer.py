"""
ML-based signal optimizer: rank cluster jumps by predicted 250d return likelihood.
Uses XGBoost to classify high-return vs. low-return jumps.

Input: cluster_jumps_full_250d_corrected.csv
Output: cluster_jumps_full_250d_ml_filtered.csv (high-confidence signals)
        ml_model.pkl (trained classifier)
"""

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
import xgboost as xgb
import pickle
from pathlib import Path

# Configuration
INPUT_FILE = 'cluster_jumps_full_250d_corrected.csv'
OUTPUT_FILTERED = 'cluster_jumps_full_250d_ml_filtered.csv'
MODEL_FILE = 'ml_model.pkl'
CONFIDENCE_THRESHOLD = 0.65  # only keep signals with pred prob > this
TEST_SIZE = 0.2
RANDOM_STATE = 42

print("=" * 70)
print("ML SIGNAL OPTIMIZER")
print("=" * 70)

# Load signals
print(f"\nLoading signals from {INPUT_FILE}...")
signals = pd.read_csv(INPUT_FILE)
signals['Date'] = pd.to_datetime(signals['Date'])

print(f"  Loaded {len(signals):,} signals")
print(f"  Columns: {list(signals.columns)}")

# Feature engineering
print("\nEngineering features...")
features_df = signals.copy()

# Target: binary classification (high-return vs. low-return)
median_return = features_df['return_250d'].median()
features_df['target'] = (features_df['return_250d'] > median_return).astype(int)

print(f"  Median return: {median_return:.2f}%")
print(f"  Target distribution: {features_df['target'].value_counts().to_dict()}")

# Feature set
feature_cols = []

# Numeric features
if 'Quality_Delta' in features_df.columns:
    feature_cols.append('Quality_Delta')
if 'From_Quality' in features_df.columns:
    feature_cols.append('From_Quality')
if 'To_Quality' in features_df.columns:
    feature_cols.append('To_Quality')

# Jump_Type encoding
if 'Jump_Type' in features_df.columns:
    jump_le = LabelEncoder()
    features_df['Jump_Type_encoded'] = jump_le.fit_transform(features_df['Jump_Type'])
    feature_cols.append('Jump_Type_encoded')
    print(f"  Jump_Type classes: {dict(zip(jump_le.classes_, jump_le.transform(jump_le.classes_)))}")

# Temporal features
features_df['month'] = features_df['Date'].dt.month
features_df['dayofweek'] = features_df['Date'].dt.dayofweek
feature_cols.extend(['month', 'dayofweek'])

# Handle missing values
print(f"\nHandling missing values...")
for col in feature_cols:
    missing = features_df[col].isna().sum()
    if missing > 0:
        print(f"  {col}: {missing} missing values → filling with median")
        features_df[col].fillna(features_df[col].median(), inplace=True)

print(f"\nFinal feature set: {feature_cols}")
print(f"  {len(feature_cols)} features")

# Train/test split
X = features_df[feature_cols].copy()
y = features_df['target'].copy()

X_train, X_test, y_train, y_test, idx_train, idx_test = train_test_split(
    X, y, features_df.index, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=y
)

print(f"\nTrain/test split:")
print(f"  Train: {len(X_train):,} ({y_train.mean():.1%} positive)")
print(f"  Test:  {len(X_test):,} ({y_test.mean():.1%} positive)")

# Train XGBoost
print("\nTraining XGBoost classifier...")
model = xgb.XGBClassifier(
    n_estimators=100,
    max_depth=5,
    learning_rate=0.1,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=RANDOM_STATE,
    verbosity=0
)

model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

# Evaluate
train_score = model.score(X_train, y_train)
test_score = model.score(X_test, y_test)

print(f"  Train accuracy: {train_score:.3f}")
print(f"  Test accuracy:  {test_score:.3f}")

# Feature importance
print(f"\nFeature importance:")
importances = dict(zip(feature_cols, model.feature_importances_))
for feat, imp in sorted(importances.items(), key=lambda x: x[1], reverse=True):
    print(f"  {feat:20s}: {imp:.4f}")

# Score all signals
print(f"\nScoring all {len(features_df):,} signals...")
features_df['ml_score'] = model.predict_proba(X)[:, 1]  # prob of high-return class

print(f"  ML score distribution:")
print(f"    Mean: {features_df['ml_score'].mean():.3f}")
print(f"    Median: {features_df['ml_score'].median():.3f}")
print(f"    Std: {features_df['ml_score'].std():.3f}")

# Filter by confidence threshold
filtered = features_df[features_df['ml_score'] >= CONFIDENCE_THRESHOLD].copy()
print(f"\nFiltering by confidence threshold ({CONFIDENCE_THRESHOLD}):")
print(f"  Original: {len(features_df):,} signals")
print(f"  Filtered: {len(filtered):,} signals ({len(filtered)/len(features_df)*100:.1f}%)")

if len(filtered) > 0:
    print(f"  Filtered return stats (250d):")
    print(f"    Mean: {filtered['return_250d'].mean():.2f}%")
    print(f"    Median: {filtered['return_250d'].median():.2f}%")
    print(f"    Std: {filtered['return_250d'].std():.2f}%")

# Save filtered signals
output_cols = ['Symbol', 'Date', 'From_Cluster', 'To_Cluster', 'From_Quality', 'To_Quality', 
               'Quality_Delta', 'Jump_Type', 'return_250d', 'ml_score']
output_df = filtered[output_cols].copy()
output_df = output_df.sort_values('Date').reset_index(drop=True)
output_df.to_csv(OUTPUT_FILTERED, index=False)

print(f"\n✓ Saved {len(output_df):,} filtered signals to {OUTPUT_FILTERED}")

# Save model
with open(MODEL_FILE, 'wb') as f:
    pickle.dump({'model': model, 'feature_cols': feature_cols}, f)
print(f"✓ Saved model to {MODEL_FILE}")

print(f"\n{'='*70}")
print("SUMMARY")
print(f"{'='*70}")
print(f"Original signals: {len(signals):,}")
print(f"Filtered signals: {len(output_df):,}")
print(f"Retention rate: {len(output_df)/len(signals)*100:.1f}%")
print(f"Model accuracy (test): {test_score:.3f}")
print(f"Confidence threshold: {CONFIDENCE_THRESHOLD}")

if len(filtered) > 0:
    all_avg_ret = signals['return_250d'].mean()
    filt_avg_ret = filtered['return_250d'].mean()
    print(f"\nReturn improvement:")
    print(f"  All signals avg: {all_avg_ret:.2f}%")
    print(f"  Filtered avg: {filt_avg_ret:.2f}%")
    if all_avg_ret != 0:
        print(f"  Delta: {(filt_avg_ret - all_avg_ret):.2f}% ({(filt_avg_ret/all_avg_ret - 1)*100:+.1f}%)")
