"""
Full Data Pipeline: MarketCap Integration + Sliding Window + Dropout Analysis

Optimized for processing the full D drive dataset with memory efficiency.
This script:
1. Loads and processes MarketCAP and MarketValues files incrementally
2. Creates consolidated dataset with market cap data
3. Applies sliding window clustering protocol
4. Generates comprehensive analysis and backtesting results

Usage:
    python run_marketcap_full_pipeline.py              # Full data run
    python run_marketcap_full_pipeline.py --test       # Quick test with 100k rows
    python run_marketcap_full_pipeline.py --nrows 500000  # Custom row limit
"""

import pandas as pd
import numpy as np
import os
import sys
from pathlib import Path
import logging
from datetime import datetime
import time

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

sys.path.insert(0, '/home/npallotta128/projects/testbed-analysis')

from integrate_marketcap_protocol import MarketCapIntegrator, convert_to_compatible_format
from optimize_dropout_strategy_safe import test_dropout_parameters

class FullPipelineRunner:
    """Orchestrates full pipeline execution with comprehensive reporting"""
    
    def __init__(self, output_dir='marketcap_pipeline_results'):
        self.output_dir = output_dir
        Path(self.output_dir).mkdir(exist_ok=True)
        logger.info(f"Output directory: {self.output_dir}")
    
    def run_integration(self, nrows=None):
        """Run market cap integration phase"""
        logger.info("="*80)
        logger.info("PHASE 1: MARKET CAP INTEGRATION")
        logger.info("="*80)
        
        market_cap_file = '/mnt/d/MarketCAPValues.csv'
        market_values_file = '/mnt/d/MarketValues.csv'
        
        integrator = MarketCapIntegrator(market_cap_file, market_values_file)
        integrator.load_market_cap_data()
        integrator.load_market_values_data(nrows=nrows)
        integrator.approximate_shares_on_price_dates()
        
        consolidated_file = os.path.join(self.output_dir, 'data_with_marketcap.csv')
        integrator.create_consolidated_dataset(output_file=consolidated_file)
        
        prepared_file = os.path.join(self.output_dir, 'data_marketcap_prepared.csv')
        convert_to_compatible_format(consolidated_file, output_file=prepared_file)
        
        logger.info(f"Integration complete. Data shape: {integrator.consolidated_df.shape}")
        return prepared_file, integrator.consolidated_df
    
    def run_clustering(self, data_file):
        """Run sliding window clustering and dropout detection"""
        logger.info("="*80)
        logger.info("PHASE 2: SLIDING WINDOW CLUSTERING + DROPOUT DETECTION")
        logger.info("="*80)
        
        result, loss_df, acq_df = test_dropout_parameters(
            data_file,
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
        
        events_file = os.path.join(self.output_dir, 'marketcap_sliding_events.csv')
        events.to_csv(events_file, index=False)
        
        logger.info(f"\nSliding Window Results:")
        logger.info(f"  Dropout events: {len(loss_df)}")
        logger.info(f"  Acquisition events: {len(acq_df)}")
        
        return events, loss_df, acq_df, events_file
    
    def analyze_events(self, events, loss_df, acq_df):
        """Comprehensive event analysis"""
        logger.info("="*80)
        logger.info("PHASE 3: EVENT ANALYSIS")
        logger.info("="*80)
        
        analysis = {}
        
        # Dropout analysis
        dropout_stats = {
            'mean_return': loss_df['Future_Return'].mean(),
            'median_return': loss_df['Future_Return'].median(),
            'std_return': loss_df['Future_Return'].std(),
            'positive_pct': (loss_df['Future_Return'] > 0).mean() * 100,
            'negative_pct': (loss_df['Future_Return'] < 0).mean() * 100,
            'extreme_negative_pct': (loss_df['Future_Return'] < -50).mean() * 100,
            'extreme_positive_pct': (loss_df['Future_Return'] > 100).mean() * 100,
            'count': len(loss_df)
        }
        
        # Acquisition analysis
        acq_stats = {
            'mean_return': acq_df['Future_Return'].mean(),
            'median_return': acq_df['Future_Return'].median(),
            'std_return': acq_df['Future_Return'].std(),
            'positive_pct': (acq_df['Future_Return'] > 0).mean() * 100,
            'negative_pct': (acq_df['Future_Return'] < 0).mean() * 100,
            'extreme_negative_pct': (acq_df['Future_Return'] < -50).mean() * 100,
            'extreme_positive_pct': (acq_df['Future_Return'] > 100).mean() * 100,
            'count': len(acq_df)
        }
        
        logger.info(f"\nDROPOUT EVENTS (n={len(loss_df)}):")
        logger.info(f"  Mean return:     {dropout_stats['mean_return']:8.2f}%")
        logger.info(f"  Median return:   {dropout_stats['median_return']:8.2f}%")
        logger.info(f"  Std dev:         {dropout_stats['std_return']:8.2f}%")
        logger.info(f"  Positive %:      {dropout_stats['positive_pct']:8.1f}%")
        logger.info(f"  Negative %:      {dropout_stats['negative_pct']:8.1f}%")
        logger.info(f"  Extreme gains (>100%):  {dropout_stats['extreme_positive_pct']:5.1f}%")
        logger.info(f"  Extreme losses (<-50%): {dropout_stats['extreme_negative_pct']:5.1f}%")
        
        logger.info(f"\nACQUISITION EVENTS (n={len(acq_df)}):")
        logger.info(f"  Mean return:     {acq_stats['mean_return']:8.2f}%")
        logger.info(f"  Median return:   {acq_stats['median_return']:8.2f}%")
        logger.info(f"  Std dev:         {acq_stats['std_return']:8.2f}%")
        logger.info(f"  Positive %:      {acq_stats['positive_pct']:8.1f}%")
        logger.info(f"  Negative %:      {acq_stats['negative_pct']:8.1f}%")
        logger.info(f"  Extreme gains (>100%):  {acq_stats['extreme_positive_pct']:5.1f}%")
        logger.info(f"  Extreme losses (<-50%): {acq_stats['extreme_negative_pct']:5.1f}%")
        
        return {
            'dropout': dropout_stats,
            'acquisition': acq_stats,
            'total_events': len(events),
            'event_ratio_drop_to_acq': len(loss_df) / len(acq_df) if len(acq_df) > 0 else 0
        }
    
    def generate_summary_report(self, consolidated_df, analysis, events_file):
        """Generate summary report"""
        logger.info("="*80)
        logger.info("SUMMARY REPORT")
        logger.info("="*80)
        
        report = f"""
MARKETCAP INTEGRATION + SLIDING WINDOW CLUSTERING PIPELINE
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

DATASET INFORMATION:
  Total records: {len(consolidated_df):,}
  Date range: {consolidated_df['Date'].min()} to {consolidated_df['Date'].max()}
  Unique symbols: {consolidated_df['Symbol'].nunique()}
  
  Market Cap Stats:
    Min:  ${consolidated_df['MarketCap'].min():,.0f}
    Max:  ${consolidated_df['MarketCap'].max():,.0f}
    Mean: ${consolidated_df['MarketCap'].mean():,.0f}
    Median: ${consolidated_df['MarketCap'].median():,.0f}

EVENT DETECTION RESULTS:
  Total events: {analysis['total_events']}
  Dropout events: {analysis['dropout']['count']}
  Acquisition events: {analysis['acquisition']['count']}
  Dropout/Acquisition ratio: {analysis['event_ratio_drop_to_acq']:.2f}

DROPOUT EVENT PERFORMANCE:
  Mean return: {analysis['dropout']['mean_return']:.2f}%
  Median return: {analysis['dropout']['median_return']:.2f}%
  Std dev: {analysis['dropout']['std_return']:.2f}%
  Win rate: {analysis['dropout']['positive_pct']:.1f}%
  
ACQUISITION EVENT PERFORMANCE:
  Mean return: {analysis['acquisition']['mean_return']:.2f}%
  Median return: {analysis['acquisition']['median_return']:.2f}%
  Std dev: {analysis['acquisition']['std_return']:.2f}%
  Win rate: {analysis['acquisition']['positive_pct']:.1f}%

OUTPUT FILES:
  - data_with_marketcap.csv (consolidated data)
  - data_marketcap_prepared.csv (clustering-ready format)
  - marketcap_sliding_events.csv (detected events)
  - pipeline_summary_report.txt (this file)

NEXT STEPS:
  1. Review event distribution in marketcap_sliding_events.csv
  2. Run backtests on dropout/acquisition events
  3. Analyze market cap impact on event returns
  4. Compare performance vs. baseline (without market cap)
"""
        
        report_file = os.path.join(self.output_dir, 'pipeline_summary_report.txt')
        with open(report_file, 'w') as f:
            f.write(report)
        
        logger.info(report)
        return report_file
    
    def run_full_pipeline(self, nrows=None):
        """Execute complete pipeline"""
        start_time = time.time()
        logger.info(f"\n{'='*80}")
        logger.info(f"STARTING FULL MARKETCAP PIPELINE")
        logger.info(f"{'='*80}\n")
        
        try:
            # Phase 1: Integration
            prepared_file, consolidated_df = self.run_integration(nrows=nrows)
            
            # Phase 2: Clustering
            events, loss_df, acq_df, events_file = self.run_clustering(prepared_file)
            
            # Phase 3: Analysis
            analysis = self.analyze_events(events, loss_df, acq_df)
            
            # Phase 4: Report
            report_file = self.generate_summary_report(consolidated_df, analysis, events_file)
            
            elapsed_time = time.time() - start_time
            logger.info(f"\n{'='*80}")
            logger.info(f"PIPELINE COMPLETE ({elapsed_time:.1f}s)")
            logger.info(f"Results saved to: {self.output_dir}/")
            logger.info(f"{'='*80}\n")
            
            return {
                'success': True,
                'output_dir': self.output_dir,
                'files': {
                    'events': events_file,
                    'report': report_file
                },
                'analysis': analysis,
                'elapsed_time': elapsed_time
            }
        
        except Exception as e:
            logger.error(f"Pipeline failed: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Full MarketCap Pipeline Runner')
    parser.add_argument('--test', action='store_true', help='Quick test with 100k rows')
    parser.add_argument('--nrows', type=int, help='Limit to N rows of price data')
    parser.add_argument('--output', default='marketcap_pipeline_results', 
                       help='Output directory (default: marketcap_pipeline_results)')
    
    args = parser.parse_args()
    
    nrows = args.nrows
    if args.test:
        nrows = 100_000
        logger.info(f"[TEST MODE] Using 100,000 rows")
    elif nrows:
        logger.info(f"[CUSTOM MODE] Using {nrows:,} rows")
    else:
        logger.info(f"[FULL MODE] Using all available data")
    
    runner = FullPipelineRunner(output_dir=args.output)
    result = runner.run_full_pipeline(nrows=nrows)
    
    if result['success']:
        logger.info(f"\n✓ Pipeline completed successfully!")
        logger.info(f"  Output: {result['output_dir']}")
        logger.info(f"  Events file: {result['files']['events']}")
        logger.info(f"  Report: {result['files']['report']}")
        sys.exit(0)
    else:
        logger.error(f"\n✗ Pipeline failed: {result.get('error', 'Unknown error')}")
        sys.exit(1)

if __name__ == '__main__':
    main()
