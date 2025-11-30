import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

def analyze_trading_results(results_file):
    """Analyze the trading results with detailed statistics"""
    
    # Load results
    df = pd.read_csv(results_file)
    
    print("="*80)
    print("DETAILED TRADING SIGNAL ANALYSIS")
    print("="*80)
    
    print(f"\nTotal signals analyzed: {len(df)}")
    print(f"Successfully closed positions (5+ positive returns): {len(df[df['Position_Closed'] == True])}")
    print(f"Positions held to 20-day limit: {len(df[df['Position_Closed'] == False])}")
    
    # Overall performance
    print(f"\nOVERALL PERFORMANCE:")
    print(f"Mean return: {df['Final_Return'].mean():.4f} ({df['Final_Return'].mean()*100:.2f}%)")
    print(f"Median return: {df['Final_Return'].median():.4f} ({df['Final_Return'].median()*100:.2f}%)")
    print(f"Standard deviation: {df['Final_Return'].std():.4f} ({df['Final_Return'].std()*100:.2f}%)")
    print(f"Min return: {df['Final_Return'].min():.4f} ({df['Final_Return'].min()*100:.2f}%)")
    print(f"Max return: {df['Final_Return'].max():.4f} ({df['Final_Return'].max()*100:.2f}%)")
    print(f"Total win rate: {(df['Final_Return'] > 0).mean():.2%}")
    
    # Performance by signal type
    print(f"\nPERFORMANCE BY SIGNAL TYPE:")
    
    long_signals = df[df['Type'] == 'Long']
    short_signals = df[df['Type'] == 'Short']
    
    if len(long_signals) > 0:
        print(f"\nLong Positions ({len(long_signals)} signals):")
        print(f"  Mean return: {long_signals['Final_Return'].mean():.4f} ({long_signals['Final_Return'].mean()*100:.2f}%)")
        print(f"  Median return: {long_signals['Final_Return'].median():.4f} ({long_signals['Final_Return'].median()*100:.2f}%)")
        print(f"  Win rate: {(long_signals['Final_Return'] > 0).mean():.2%}")
        print(f"  Early closes (5+ positive): {(long_signals['Position_Closed']).sum()}/{len(long_signals)}")
        print(f"  Average holding period: {long_signals['Holding_Period'].mean():.1f} days")
    
    if len(short_signals) > 0:
        print(f"\nShort Positions ({len(short_signals)} signals):")
        print(f"  Mean return: {short_signals['Final_Return'].mean():.4f} ({short_signals['Final_Return'].mean()*100:.2f}%)")
        print(f"  Median return: {short_signals['Final_Return'].median():.4f} ({short_signals['Final_Return'].median()*100:.2f}%)")
        print(f"  Win rate: {(short_signals['Final_Return'] > 0).mean():.2%}")
        print(f"  Early closes (5+ positive): {(short_signals['Position_Closed']).sum()}/{len(short_signals)}")
        print(f"  Average holding period: {short_signals['Holding_Period'].mean():.1f} days")
    
    # Performance by closure reason
    print(f"\nPERFORMANCE BY CLOSURE REASON:")
    
    early_close = df[df['Position_Closed'] == True]
    late_close = df[df['Position_Closed'] == False]
    
    print(f"\nEarly Closure (5+ positive returns, {len(early_close)} positions):")
    print(f"  Mean return: {early_close['Final_Return'].mean():.4f} ({early_close['Final_Return'].mean()*100:.2f}%)")
    print(f"  Average holding period: {early_close['Holding_Period'].mean():.1f} days")
    print(f"  Average positive return count: {early_close['Positive_Return_Count'].mean():.1f}")
    
    print(f"\nHeld to Limit (20 days, {len(late_close)} positions):")
    print(f"  Mean return: {late_close['Final_Return'].mean():.4f} ({late_close['Final_Return'].mean()*100:.2f}%)")
    print(f"  Win rate: {(late_close['Final_Return'] > 0).mean():.2%}")
    print(f"  Average positive return count: {late_close['Positive_Return_Count'].mean():.1f}")
    
    # Top and bottom performers
    print(f"\nTOP 10 PERFORMING SIGNALS:")
    top_performers = df.nlargest(10, 'Final_Return')[['Variable Name', 'Type', 'Final_Return', 'Holding_Period', 'Position_Closed']]
    print(top_performers.to_string(index=False))
    
    print(f"\nBOTTOM 10 PERFORMING SIGNALS:")
    bottom_performers = df.nsmallest(10, 'Final_Return')[['Variable Name', 'Type', 'Final_Return', 'Holding_Period', 'Position_Closed']]
    print(bottom_performers.to_string(index=False))
    
    # Holding period analysis
    print(f"\nHOLDING PERIOD ANALYSIS:")
    print(f"Average holding period: {df['Holding_Period'].mean():.1f} days")
    print(f"Median holding period: {df['Holding_Period'].median():.1f} days")
    
    holding_period_stats = df.groupby('Holding_Period')['Final_Return'].agg(['count', 'mean']).reset_index()
    holding_period_stats.columns = ['Days_Held', 'Count', 'Avg_Return']
    print(f"\nReturn by holding period:")
    print(holding_period_stats.to_string(index=False))
    
    # Risk metrics
    print(f"\nRISK METRICS:")
    returns = df['Final_Return']
    negative_returns = returns[returns < 0]
    positive_returns = returns[returns > 0]
    
    print(f"Sharpe ratio estimate: {returns.mean() / returns.std():.4f}")
    print(f"Maximum drawdown: {negative_returns.min():.4f} ({negative_returns.min()*100:.2f}%)")
    print(f"Average winning trade: {positive_returns.mean():.4f} ({positive_returns.mean()*100:.2f}%)")
    print(f"Average losing trade: {negative_returns.mean():.4f} ({negative_returns.mean()*100:.2f}%)")
    print(f"Profit factor: {positive_returns.sum() / abs(negative_returns.sum()):.4f}")
    
    # Signal state analysis
    print(f"\nSIGNAL STRENGTH ANALYSIS:")
    print("Performance by signal state ranges:")
    
    # For short signals (state > 3.4)
    short_signals = df[df['Type'] == 'Short']
    if len(short_signals) > 0:
        state_bins = pd.cut(short_signals['State'], bins=5)
        state_performance = short_signals.groupby(state_bins)['Final_Return'].agg(['count', 'mean']).reset_index()
        print("\nShort signals by state ranges:")
        print(state_performance.to_string(index=False))
    
    # For long signals (state < -3)
    long_signals = df[df['Type'] == 'Long']
    if len(long_signals) > 0:
        state_bins = pd.cut(long_signals['State'], bins=3)
        state_performance = long_signals.groupby(state_bins)['Final_Return'].agg(['count', 'mean']).reset_index()
        print("\nLong signals by state ranges:")
        print(state_performance.to_string(index=False))
    
    print("\n" + "="*80)
    print("ANALYSIS COMPLETE")
    print("="*80)

if __name__ == "__main__":
    analyze_trading_results('trading_signals_with_returns.csv')