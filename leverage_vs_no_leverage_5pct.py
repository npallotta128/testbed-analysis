"""
5% Volume Constraint Strategy: Leverage vs No Leverage Comparison
Compare 5-year performance with $100,000 initial capital
"""

import numpy as np
import pandas as pd
from datetime import datetime

def calculate_leverage_vs_no_leverage_comparison():
    """
    Compare 5% volume constraint strategy with and without leverage
    Based on Executive Summary analysis results
    """
    
    print("=" * 80)
    print("5% VOLUME CONSTRAINT STRATEGY - LEVERAGE COMPARISON")
    print("=" * 80)
    print("Initial Capital: $100,000")
    print("Volume Constraint: 5% of (volume × price)")
    print("Time Horizon: 5 years")
    print("Based on Executive Summary analysis results")
    print("=" * 80)
    
    # Strategy parameters from Executive Summary analysis
    initial_capital = 100000
    
    # Performance metrics from volume constraint analysis (5% constraint, $1M scale)
    # From volume_constraint_results.csv: 5% constraint shows 110.83% return for $1M
    # This is the TOTAL return, not annual - need to convert properly
    total_return_5_years = 1.1083  # 110.83% total return over the analysis period
    base_annual_return_no_leverage = (1 + total_return_5_years) ** (1/5) - 1  # Convert to annual
    
    # With leverage enhancement - use actual results from our leverage analysis
    # Our leverage analysis showed 64.87% annualized with 2% constraint
    # Scale up for 5% constraint based on volume constraint analysis ratios
    # 5% constraint: 110.83% vs 2% constraint: 88.50% = 1.25x multiplier
    constraint_multiplier = 1.1083 / 0.8850  # 1.25x
    
    # Base leveraged return (from our 64.87% result scaled up)
    base_leveraged_annual = 0.6487 * constraint_multiplier  # Scale up for 5% constraint
    
    # Interest costs with leverage (12% annual on borrowed funds)
    annual_interest_rate = 0.12
    avg_leverage_ratio = 2.36  # From our actual leverage analysis results
    avg_borrowed_pct = (avg_leverage_ratio - 1) / avg_leverage_ratio  # ~58% borrowed
    annual_interest_cost_rate = annual_interest_rate * avg_borrowed_pct  # ~7.0% of portfolio
    
    # Adjust interest cost relative to equity (not total portfolio)
    annual_interest_cost = annual_interest_cost_rate * avg_leverage_ratio  # Cost relative to equity
    
    # Net leveraged return after interest
    net_leveraged_return = base_leveraged_annual - annual_interest_cost
    
    print(f"\nCALCULATED ANNUAL RETURNS:")
    print("-" * 50)
    print(f"Base Strategy (No Leverage):     {base_annual_return_no_leverage*100:.2f}%")
    print(f"Leveraged Strategy (Gross):      {base_leveraged_annual*100:.2f}%")
    print(f"Interest Cost on Leverage:       {annual_interest_cost*100:.2f}%")
    print(f"Leveraged Strategy (Net):        {net_leveraged_return*100:.2f}%")
    
    # Calculate 5-year projections
    scenarios = {
        'No Leverage': {
            'annual_return': base_annual_return_no_leverage,
            'interest_cost': 0,
            'leverage_ratio': 1.0,
            'risk_level': 'Moderate'
        },
        'With Leverage': {
            'annual_return': net_leveraged_return,
            'interest_cost': annual_interest_cost,
            'leverage_ratio': avg_leverage_ratio,
            'risk_level': 'Higher'
        }
    }
    
    print(f"\n5-YEAR PROJECTIONS:")
    print("=" * 80)
    
    results = {}
    
    for scenario_name, params in scenarios.items():
        print(f"\n{scenario_name.upper()} SCENARIO:")
        print("-" * 50)
        
        current_value = initial_capital
        yearly_values = [current_value]
        total_interest_paid = 0
        
        # Year-by-year calculation
        for year in range(1, 6):
            # Apply return
            current_value = current_value * (1 + params['annual_return'])
            
            # Track interest payments for leveraged scenario
            if 'Leverage' in scenario_name:
                annual_interest = current_value * params['interest_cost'] / params['leverage_ratio']
                total_interest_paid += annual_interest
            
            yearly_values.append(current_value)
            print(f"Year {year}: ${current_value:,.0f}")
        
        final_value = current_value
        total_gain = final_value - initial_capital
        total_return_pct = (final_value - initial_capital) / initial_capital * 100
        
        results[scenario_name] = {
            'final_value': final_value,
            'total_gain': total_gain,
            'total_return_pct': total_return_pct,
            'total_interest_paid': total_interest_paid,
            'yearly_values': yearly_values,
            'annual_return': params['annual_return'],
            'leverage_ratio': params['leverage_ratio'],
            'risk_level': params['risk_level']
        }
        
        print(f"Final Value: ${final_value:,.0f}")
        print(f"Total Gain: ${total_gain:,.0f}")
        print(f"Total Return: {total_return_pct:.1f}%")
        if total_interest_paid > 0:
            print(f"Total Interest Paid: ${total_interest_paid:,.0f}")
    
    # Comparative analysis
    print(f"\nCOMPARATIVE ANALYSIS:")
    print("=" * 80)
    
    no_leverage = results['No Leverage']
    with_leverage = results['With Leverage']
    
    leverage_advantage = with_leverage['final_value'] - no_leverage['final_value']
    leverage_advantage_pct = (leverage_advantage / no_leverage['final_value']) * 100
    leverage_multiplier_actual = with_leverage['final_value'] / no_leverage['final_value']
    
    comparison_table = pd.DataFrame({
        'Metric': [
            'Final Portfolio Value',
            'Total Gain',
            'Total Return %',
            'Average Annual Return',
            'Risk Level',
            'Leverage Ratio',
            'Interest Paid (5 years)'
        ],
        'No Leverage': [
            f"${no_leverage['final_value']:,.0f}",
            f"${no_leverage['total_gain']:,.0f}",
            f"{no_leverage['total_return_pct']:.1f}%",
            f"{no_leverage['annual_return']*100:.2f}%",
            no_leverage['risk_level'],
            f"{no_leverage['leverage_ratio']:.1f}x",
            "$0"
        ],
        'With Leverage': [
            f"${with_leverage['final_value']:,.0f}",
            f"${with_leverage['total_gain']:,.0f}",
            f"{with_leverage['total_return_pct']:.1f}%",
            f"{with_leverage['annual_return']*100:.2f}%",
            with_leverage['risk_level'],
            f"{with_leverage['leverage_ratio']:.1f}x",
            f"${with_leverage['total_interest_paid']:,.0f}"
        ],
        'Leverage Advantage': [
            f"${leverage_advantage:,.0f}",
            f"${leverage_advantage:,.0f}",
            f"+{leverage_advantage_pct:.1f}%",
            f"+{(with_leverage['annual_return'] - no_leverage['annual_return'])*100:.2f}%",
            "Higher Risk",
            f"+{with_leverage['leverage_ratio'] - no_leverage['leverage_ratio']:.1f}x",
            f"-${with_leverage['total_interest_paid']:,.0f}"
        ]
    })
    
    print(comparison_table.to_string(index=False))
    
    # Key insights
    print(f"\nKEY INSIGHTS:")
    print("=" * 80)
    print(f"• Leverage increases final value by ${leverage_advantage:,.0f} ({leverage_advantage_pct:.1f}%)")
    print(f"• Leverage multiplies returns by {leverage_multiplier_actual:.2f}x")
    print(f"• Every $1,000 becomes ${no_leverage['final_value']/initial_capital*1000:.0f} (no leverage) vs ${with_leverage['final_value']/initial_capital*1000:.0f} (with leverage)")
    print(f"• Interest cost over 5 years: ${with_leverage['total_interest_paid']:,.0f}")
    print(f"• Net benefit of leverage: ${leverage_advantage - with_leverage['total_interest_paid']:,.0f}")
    
    # Risk considerations
    print(f"\nRISK CONSIDERATIONS:")
    print("=" * 80)
    print("NO LEVERAGE:")
    print("• Lower volatility and risk")
    print("• No interest payments")
    print("• No margin call risk")
    print("• Simpler implementation")
    print(f"• Final value: ${no_leverage['final_value']:,.0f}")
    
    print("\nWITH LEVERAGE:")
    print("• Higher potential returns")
    print("• 12% annual interest cost")
    print("• Margin call risk with 30% equity requirement")
    print("• More complex risk management")
    print(f"• Final value: ${with_leverage['final_value']:,.0f}")
    
    # Breakeven analysis
    breakeven_years = np.log(with_leverage['final_value'] / no_leverage['final_value']) / np.log((1 + with_leverage['annual_return']) / (1 + no_leverage['annual_return']))
    
    print(f"\nBREAKEVEN ANALYSIS:")
    print("=" * 80)
    print(f"• Leverage breaks even after: {breakeven_years:.1f} years")
    print(f"• At year 3, leverage advantage: ${(initial_capital * (1 + with_leverage['annual_return'])**3) - (initial_capital * (1 + no_leverage['annual_return'])**3):,.0f}")
    print(f"• Leverage becomes significantly advantageous after year 2")
    
    # Monthly cash flow comparison
    print(f"\nMONTHLY CASH FLOW COMPARISON (Year 5):")
    print("=" * 80)
    monthly_return_no_leverage = (no_leverage['final_value'] / initial_capital) ** (1/60) - 1
    monthly_return_with_leverage = (with_leverage['final_value'] / initial_capital) ** (1/60) - 1
    monthly_interest_payment = with_leverage['final_value'] * (annual_interest_rate/12) * (avg_borrowed_pct)
    
    print(f"No Leverage - Monthly Growth: ${initial_capital * monthly_return_no_leverage:,.0f}")
    print(f"With Leverage - Monthly Growth: ${initial_capital * monthly_return_with_leverage:,.0f}")
    print(f"With Leverage - Monthly Interest: ${monthly_interest_payment:,.0f}")
    print(f"Net Monthly Advantage: ${(initial_capital * monthly_return_with_leverage) - (initial_capital * monthly_return_no_leverage) - monthly_interest_payment:,.0f}")
    
    return results

def create_visual_comparison_data(results):
    """Create data for visualization"""
    
    print(f"\nYEAR-BY-YEAR COMPARISON TABLE:")
    print("=" * 60)
    print(f"{'Year':<6} {'No Leverage':<15} {'With Leverage':<15} {'Advantage':<12}")
    print("-" * 60)
    
    no_leverage_values = results['No Leverage']['yearly_values']
    with_leverage_values = results['With Leverage']['yearly_values']
    
    for year in range(6):
        no_lev_val = no_leverage_values[year]
        with_lev_val = with_leverage_values[year]
        advantage = with_lev_val - no_lev_val
        
        print(f"{year:<6} ${no_lev_val:<14,.0f} ${with_lev_val:<14,.0f} ${advantage:<11,.0f}")
    
    print("-" * 60)

if __name__ == "__main__":
    print("STARTING 5% VOLUME CONSTRAINT LEVERAGE COMPARISON...")
    
    # Run the comparison
    results = calculate_leverage_vs_no_leverage_comparison()
    
    # Create visual data
    create_visual_comparison_data(results)
    
    print(f"\n" + "=" * 80)
    print("FINAL RECOMMENDATION:")
    print("=" * 80)
    
    no_leverage_final = results['No Leverage']['final_value']
    with_leverage_final = results['With Leverage']['final_value']
    advantage = with_leverage_final - no_leverage_final
    
    print(f"Starting with $100,000 using 5% volume constraint strategy:")
    print(f"• NO LEVERAGE: ${no_leverage_final:,.0f} after 5 years")
    print(f"• WITH LEVERAGE: ${with_leverage_final:,.0f} after 5 years")
    print(f"• LEVERAGE ADVANTAGE: ${advantage:,.0f} additional wealth")
    print(f"• LEVERAGE MULTIPLIER: {with_leverage_final/no_leverage_final:.2f}x better returns")
    
    if advantage > 200000:  # If advantage is substantial
        print(f"\n✅ RECOMMENDATION: USE LEVERAGE")
        print(f"The leverage advantage of ${advantage:,.0f} significantly outweighs the risks")
    else:
        print(f"\n⚠️  RECOMMENDATION: CONSIDER RISK TOLERANCE")
        print(f"Leverage provides ${advantage:,.0f} advantage but adds complexity")
    
    print("=" * 80)