"""Generate sliding window event dataset for ML pipeline comparison"""
import pandas as pd
from optimize_dropout_strategy_safe import test_dropout_parameters

def main():
    print("Generating sliding window events (stride=50)...")
    result, loss_df, acq_df = test_dropout_parameters(
        'data.csv',
        block_size=200,
        num_blocks=50,  # Allow more starts
        distance_threshold=40,
        quality_metric='avg_return',
        quality_threshold_percentile=80,
        stride=50,
        forward_window=500
    )
    
    print(f"\nGenerated {len(loss_df)} dropout events, {len(acq_df)} acquisition events")
    
    # Add event type
    loss_df['Event_Type'] = 'DROP'
    acq_df['Event_Type'] = 'ACQ'
    
    # Combine
    events = pd.concat([loss_df, acq_df], ignore_index=True)
    
    # Save
    events.to_csv('events_sliding_window.csv', index=False)
    print(f"Saved {len(events)} total events to events_sliding_window.csv")
    
    print("\nSummary:")
    print(f"  Dropout avg return: {loss_df['Future_Return'].mean():.2f}%")
    print(f"  Dropout median return: {loss_df['Future_Return'].median():.2f}%")
    print(f"  Acquisition avg return: {acq_df['Future_Return'].mean():.2f}%")

if __name__ == '__main__':
    main()
