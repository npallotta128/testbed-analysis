"""
Integration Module: Enhanced Quality + Dynamic Exits for Monte Carlo

This module orchestrates both Layer 1 and Layer 2 enhancements:
- Layer 1: Uses enhanced cluster quality (with dropout/acquisition weighting)
- Layer 2: Applies dynamic exit signals instead of fixed 250d holds

Can run three modes:
1. Baseline: Current implementation (fixed 250d hold, base quality)
2. Layer1: Enhanced quality + fixed 250d hold
3. Layer1+2: Enhanced quality + dynamic exits
4. Layer2: Base quality + dynamic exits (for comparison)

Usage:
    python monte_carlo_enhanced_integration.py --mode layer1_and_2 --capital 100000
"""

import sys
import argparse
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple
import json
from datetime import datetime

# Import enhancement modules
try:
    from cluster_quality_enhanced import (
        calculate_cluster_transitions,
        calculate_cluster_stability,
        adjust_cluster_quality,
        analyze_quality_impact
    )
    from monte_carlo_dynamic_exits import (
        PositionExitMonitor,
        compare_exit_strategies,
        generate_exit_summary_report
    )
except ImportError as e:
    print(f"Warning: Could not import enhancement modules: {e}")
    print("Make sure cluster_quality_enhanced.py and monte_carlo_dynamic_exits.py are in the same directory")


class EnhancedMonteCarloRunner:
    """
    Runs Monte Carlo simulations with configurable enhancements:
    - Quality metric adjustment (Layer 1)
    - Dynamic exit signals (Layer 2)
    """
    
    def __init__(
        self,
        mode: str = "baseline",
        capital: float = 100000,
        num_simulations: int = 1000,
        quality_adjustment_weights: Dict = None,
        exit_signal_params: Dict = None
    ):
        """
        Parameters:
            mode: "baseline", "layer1", "layer2", or "layer1_and_2"
            capital: Capital per simulation in dollars
            num_simulations: Number of Monte Carlo resamples
            quality_adjustment_weights: Dict with stability_weight, dropout_weight, acquisition_weight
            exit_signal_params: Dict with stop_loss_pct, take_profit_pct, max_hold_days
        """
        self.mode = mode
        self.capital = capital
        self.num_simulations = num_simulations
        
        # Default quality adjustment weights
        self.quality_weights = quality_adjustment_weights or {
            'stability_weight': 0.15,
            'dropout_weight': 0.20,
            'acquisition_weight': 0.10
        }
        
        # Default exit signal parameters
        self.exit_params = exit_signal_params or {
            'quality_threshold': 0.0,
            'stop_loss_pct': 0.15,
            'take_profit_pct': 0.50,
            'max_hold_days': 250
        }
        
        print(f"Initialized Enhanced Monte Carlo Runner:")
        print(f"  Mode: {self.mode}")
        print(f"  Capital: ${capital:,.0f}")
        print(f"  Simulations: {num_simulations}")
        print(f"  Quality Weights: {self.quality_weights}")
        print(f"  Exit Params: {self.exit_params}")
    
    def prepare_quality_metrics(self, block_results: List[Dict]) -> Tuple[Dict, Dict, Dict]:
        """
        Prepare quality metrics based on mode:
        - baseline/layer2: Return original quality scores
        - layer1/layer1_and_2: Return adjusted quality scores
        
        Returns:
            (base_quality, adjusted_quality, transition_analysis)
        """
        
        # Extract base quality scores
        base_quality = {}
        for result in block_results:
            base_quality.update(result['cluster_quality'])
        
        if self.mode in ['baseline', 'layer2']:
            # Return base quality unchanged
            return base_quality, base_quality, {}
        
        # For layer1 modes: calculate adjustments
        try:
            loss_df, acquisition_df, quality_threshold = calculate_cluster_transitions(block_results)
            stability_metrics = calculate_cluster_stability(block_results)
            
            adjusted_quality = adjust_cluster_quality(
                base_quality=base_quality,
                stability_metrics=stability_metrics,
                dropout_df=loss_df,
                acquisition_df=acquisition_df,
                **self.quality_weights
            )
            
            transition_analysis = analyze_quality_impact(
                dropout_df=loss_df,
                acquisition_df=acquisition_df,
                quality_threshold=quality_threshold
            )
            
            print(f"\nQuality Metrics Preparation:")
            print(f"  Base quality clusters: {len(base_quality)}")
            print(f"  Adjusted quality clusters: {len(adjusted_quality)}")
            print(f"  Transition analysis: {transition_analysis}")
            
            return base_quality, adjusted_quality, transition_analysis
        
        except Exception as e:
            print(f"Warning: Quality adjustment failed: {e}")
            print(f"Falling back to base quality")
            return base_quality, base_quality, {}
    
    def prepare_exit_monitor(self) -> PositionExitMonitor:
        """
        Create exit monitor configured for dynamic exit detection.
        Used in layer2 and layer1_and_2 modes.
        """
        if self.mode in ['baseline', 'layer1']:
            return None
        
        return PositionExitMonitor(
            quality_threshold=self.exit_params['quality_threshold'],
            stop_loss_pct=self.exit_params['stop_loss_pct'],
            take_profit_pct=self.exit_params['take_profit_pct'],
            max_hold_days=self.exit_params['max_hold_days']
        )
    
    def compare_modes(
        self,
        results_baseline: List[float],
        results_enhanced: List[float],
        enhancement_description: str,
        output_dir: str = "."
    ) -> Dict:
        """
        Compare results between baseline and enhanced mode.
        
        Returns:
            Comparison statistics dictionary
        """
        
        if len(results_baseline) != len(results_enhanced):
            print(f"Warning: Sample size mismatch - baseline: {len(results_baseline)}, enhanced: {len(results_enhanced)}")
        
        baseline_array = np.array(results_baseline)
        enhanced_array = np.array(results_enhanced[:len(results_baseline)])  # Align sizes
        
        comparison = {
            'Enhancement': enhancement_description,
            'Baseline_Mean_%': float(np.mean(baseline_array)),
            'Enhanced_Mean_%': float(np.mean(enhanced_array)),
            'Mean_Delta_%': float(np.mean(enhanced_array) - np.mean(baseline_array)),
            'Mean_Delta_Pct': float((np.mean(enhanced_array) - np.mean(baseline_array)) / abs(np.mean(baseline_array)) * 100),
            
            'Baseline_Sharpe': float(np.mean(baseline_array) / np.std(baseline_array)) if np.std(baseline_array) > 0 else 0,
            'Enhanced_Sharpe': float(np.mean(enhanced_array) / np.std(enhanced_array)) if np.std(enhanced_array) > 0 else 0,
            'Sharpe_Delta': float((np.mean(enhanced_array) / np.std(enhanced_array)) - (np.mean(baseline_array) / np.std(baseline_array))) if np.std(baseline_array) > 0 and np.std(enhanced_array) > 0 else 0,
            
            'Baseline_Win_%': float((baseline_array > 0).sum() / len(baseline_array) * 100),
            'Enhanced_Win_%': float((enhanced_array > 0).sum() / len(enhanced_array) * 100),
            
            'Baseline_Median_%': float(np.median(baseline_array)),
            'Enhanced_Median_%': float(np.median(enhanced_array)),
            
            'Sample_Size': len(enhanced_array),
            'Timestamp': datetime.now().isoformat()
        }
        
        # Save comparison
        output_file = Path(output_dir) / f"mode_comparison_{enhancement_description.lower().replace(' ', '_')}.csv"
        pd.DataFrame([comparison]).to_csv(output_file, index=False)
        print(f"\nComparison saved to {output_file}")
        
        return comparison
    
    def generate_mode_report(self, comparisons: List[Dict], output_dir: str = ".") -> str:
        """
        Generate comprehensive report comparing different modes.
        """
        
        report = []
        report.append("=" * 100)
        report.append("MONTE CARLO ENHANCEMENT COMPARISON REPORT")
        report.append("=" * 100)
        report.append(f"Generated: {datetime.now().isoformat()}")
        report.append(f"Capital: ${self.capital:,.0f}")
        report.append(f"Simulations per Mode: {self.num_simulations}")
        report.append("")
        
        report.append("QUALITY ADJUSTMENT WEIGHTS (Layer 1):")
        for key, val in self.quality_weights.items():
            report.append(f"  {key}: {val}")
        report.append("")
        
        report.append("EXIT SIGNAL PARAMETERS (Layer 2):")
        for key, val in self.exit_params.items():
            report.append(f"  {key}: {val}")
        report.append("")
        
        report.append("=" * 100)
        report.append("MODE COMPARISON RESULTS")
        report.append("=" * 100)
        report.append("")
        
        for i, comp in enumerate(comparisons, 1):
            report.append(f"Comparison {i}: {comp['Enhancement']}")
            report.append("-" * 100)
            report.append(f"  Baseline Mean Return:    {comp['Baseline_Mean_%']:>7.2f}%")
            report.append(f"  Enhanced Mean Return:    {comp['Enhanced_Mean_%']:>7.2f}%")
            report.append(f"  Improvement:             {comp['Mean_Delta_%']:+7.2f}% ({comp['Mean_Delta_Pct']:+6.2f}%)")
            report.append("")
            report.append(f"  Baseline Sharpe Ratio:   {comp['Baseline_Sharpe']:>7.3f}")
            report.append(f"  Enhanced Sharpe Ratio:   {comp['Enhanced_Sharpe']:>7.3f}")
            report.append(f"  Sharpe Delta:            {comp['Sharpe_Delta']:+7.3f}")
            report.append("")
            report.append(f"  Baseline Win Rate:       {comp['Baseline_Win_%']:>7.1f}%")
            report.append(f"  Enhanced Win Rate:       {comp['Enhanced_Win_%']:>7.1f}%")
            report.append("")
        
        report_str = "\n".join(report)
        
        output_file = Path(output_dir) / "enhancement_comparison_report.txt"
        with open(output_file, 'w') as f:
            f.write(report_str)
        
        print(f"\nReport saved to {output_file}")
        
        return report_str


def main():
    parser = argparse.ArgumentParser(description="Enhanced Monte Carlo with Layer 1 & Layer 2")
    parser.add_argument('--mode', choices=['baseline', 'layer1', 'layer2', 'layer1_and_2'], 
                       default='layer1_and_2',
                       help='Enhancement mode to run')
    parser.add_argument('--capital', type=float, default=100000, 
                       help='Capital amount in dollars')
    parser.add_argument('--sims', type=int, default=1000, 
                       help='Number of Monte Carlo simulations')
    parser.add_argument('--compare', action='store_true', 
                       help='Run all modes and generate comparison')
    parser.add_argument('--output', type=str, default='.',
                       help='Output directory for results')
    
    args = parser.parse_args()
    
    runner = EnhancedMonteCarloRunner(
        mode=args.mode,
        capital=args.capital,
        num_simulations=args.sims
    )
    
    print(f"\nStarting Enhanced Monte Carlo Runner in {args.mode} mode...")
    print(f"Output directory: {args.output}")
    
    if args.compare:
        print("\n" + "=" * 80)
        print("COMPARISON MODE: Running all modes and generating comparative analysis")
        print("=" * 80)
        
        # TODO: Implement full comparison across all modes
        # This would:
        # 1. Run baseline simulations
        # 2. Run layer1 simulations
        # 3. Run layer2 simulations  
        # 4. Run layer1_and_2 simulations
        # 5. Generate comparison report with statistics
        
        print("\nComparison mode not yet implemented - use individual modes for now")
    else:
        print(f"\nRunning {args.mode} mode with ${args.capital:,.0f} capital")


if __name__ == "__main__":
    main()
