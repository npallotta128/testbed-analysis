import pandas as pd
from optimize_dropout_strategy_safe import test_dropout_parameters

def summarize(result, label):
    keys = [
        'Block_Size','Stride','Num_Blocks','Num_Dropout_Events','Dropout_Avg_Return',
        'Dropout_Median_Return','Dropout_Positive_Pct','Dropout_Std_Return',
        'Num_Acquisition_Events','Acq_Avg_Return','Acq_Median_Return','Acq_Positive_Pct'
    ]
    safe = {k: result.get(k) for k in keys}
    safe['Label'] = label
    return safe

def main():
    data_file = 'data.csv'
    # Baseline: non-overlapping
    base_res, base_loss, base_acq = test_dropout_parameters(
        data_file,
        block_size=200,
        num_blocks=8,
        distance_threshold=40,
        quality_metric='avg_return',
        quality_threshold_percentile=80,
        stride=None,
        forward_window=500
    )
    # Sliding: overlap with stride 50, more starts (cap for runtime)
    slide_res, slide_loss, slide_acq = test_dropout_parameters(
        data_file,
        block_size=200,
        num_blocks=50,
        distance_threshold=40,
        quality_metric='avg_return',
        quality_threshold_percentile=80,
        stride=50,
        forward_window=500
    )
    rows = [summarize(base_res,'baseline'), summarize(slide_res,'sliding')]
    df = pd.DataFrame(rows)
    df.to_csv('sliding_vs_baseline_summary.csv', index=False)
    print(df.to_string(index=False))
    print("Saved summary to sliding_vs_baseline_summary.csv")

if __name__ == '__main__':
    main()
