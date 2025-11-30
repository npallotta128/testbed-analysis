"""
CORRECT: 5% Volume Constraint with 110.83% Annualized Returns
Based on Executive Summary which clearly states these are ANNUAL returns
"""

import numpy as np

def calculate_correct_5_year_projections():
    """
    Calculate 5-year projections using the correct 110.83% ANNUAL return
    from the Executive Summary (5% volume constraint, $1M scale)
    """
    
    print("=" * 80)
    print("CORRECT: 5% VOLUME CONSTRAINT - 5 YEAR PROJECTIONS")
    print("=" * 80)
    print("Based on Executive Summary: 110.83% ANNUAL returns")
    print("Investment Scale: $1M (5% volume constraint)")
    print("Initial Capital: $100,000")
    print("=" * 80)
    
    # Executive Summary data (these are ANNUAL returns)
    annual_return_no_leverage = 1.1083  # 110.83% annual return
    initial_capital = 100000
    
    # With leverage analysis (based on our leverage strategy results)
    # Our leverage analysis showed we can enhance returns significantly with 30% equity requirement
    
    # Leverage parameters
    leverage_ratio = 2.5  # Average 2.5x leverage
    annual_interest_rate = 0.12  # 12% annual interest
    
    # Calculate leverage enhancement
    # With 2.5x leverage, we can invest 2.5x our equity
    # But we pay interest on borrowed portion (60% of total position)
    borrowed_pct = (leverage_ratio - 1) / leverage_ratio  # 60% borrowed
    
    # Gross leveraged return
    gross_leveraged_return = annual_return_no_leverage * leverage_ratio
    
    # Interest cost (on borrowed portion)
    annual_interest_cost = annual_interest_rate * borrowed_pct * leverage_ratio
    
    # Net leveraged return
    net_leveraged_return = gross_leveraged_return - annual_interest_cost
    
    print(f"ANNUAL RETURN CALCULATIONS:")
    print(f"• Base Strategy (No Leverage): {annual_return_no_leverage*100:.2f}%")
    print(f"• Gross Leveraged Return: {gross_leveraged_return*100:.2f}%")
    print(f"• Annual Interest Cost: {annual_interest_cost*100:.2f}%")
    print(f"• Net Leveraged Return: {net_leveraged_return*100:.2f}%")
    
    # 5-year projections
    print(f"\n5-YEAR PROJECTIONS:")
    print("=" * 80)
    
    # Calculate final values
    final_no_leverage = initial_capital * (1 + annual_return_no_leverage) ** 5
    final_with_leverage = initial_capital * (1 + net_leveraged_return) ** 5
    
    print(f"NO LEVERAGE SCENARIO:")
    print(f"• Annual Return: {annual_return_no_leverage*100:.2f}%")
    print(f"• 5-Year Final Value: ${final_no_leverage:,.0f}")
    print(f"• Total Gain: ${final_no_leverage - initial_capital:,.0f}")
    print(f"• Total Return: {((final_no_leverage/initial_capital) - 1)*100:.1f}%")
    
    print(f"\nWITH LEVERAGE SCENARIO:")
    print(f"• Annual Return (Net): {net_leveraged_return*100:.2f}%")
    print(f"• 5-Year Final Value: ${final_with_leverage:,.0f}")
    print(f"• Total Gain: ${final_with_leverage - initial_capital:,.0f}")
    print(f"• Total Return: {((final_with_leverage/initial_capital) - 1)*100:.1f}%")
    
    # Year-by-year breakdown
    print(f"\nYEAR-BY-YEAR BREAKDOWN:")
    print("-" * 70)
    print(f"{'Year':<6} {'No Leverage':<15} {'With Leverage':<15} {'Advantage':<15}")
    print("-" * 70)
    
    no_lev_value = initial_capital
    with_lev_value = initial_capital
    
    print(f"{'0':<6} ${no_lev_value:<14,} ${with_lev_value:<14,} ${0:<14,}")
    
    for year in range(1, 6):
        no_lev_value *= (1 + annual_return_no_leverage)
        with_lev_value *= (1 + net_leveraged_return)
        advantage = with_lev_value - no_lev_value
        
        print(f"{year:<6} ${no_lev_value:<14,.0f} ${with_lev_value:<14,.0f} ${advantage:<14,.0f}")
    
    # Key insights
    leverage_advantage = final_with_leverage - final_no_leverage
    
    print(f"\nKEY INSIGHTS:")
    print("=" * 80)
    print(f"• Starting Capital: ${initial_capital:,}")
    print(f"• No Leverage (5 years): ${final_no_leverage:,.0f}")
    print(f"• With Leverage (5 years): ${final_with_leverage:,.0f}")
    print(f"• Leverage Advantage: ${leverage_advantage:,.0f}")
    print(f"• Leverage Multiplier: {final_with_leverage/final_no_leverage:.2f}x")
    
    # Wealth milestones
    print(f"\nWEALTH MILESTONES:")
    print("-" * 40)
    print(f"• Millionaire Status:")
    
    # Calculate when you become a millionaire
    years_to_million_no_lev = np.log(1000000/initial_capital) / np.log(1 + annual_return_no_leverage)
    years_to_million_with_lev = np.log(1000000/initial_capital) / np.log(1 + net_leveraged_return)
    
    print(f"  - No Leverage: {years_to_million_no_lev:.2f} years")
    print(f"  - With Leverage: {years_to_million_with_lev:.2f} years")
    print(f"  - Time Saved: {years_to_million_no_lev - years_to_million_with_lev:.2f} years")
    
    # Monthly growth
    monthly_return_no_lev = (1 + annual_return_no_leverage) ** (1/12) - 1
    monthly_return_with_lev = (1 + net_leveraged_return) ** (1/12) - 1
    
    print(f"\nMONTHLY GROWTH (Year 5):")
    print(f"• No Leverage: ${no_lev_value * monthly_return_no_lev:,.0f}/month")
    print(f"• With Leverage: ${with_lev_value * monthly_return_with_lev:,.0f}/month")
    
    return {
        'no_leverage_final': final_no_leverage,
        'with_leverage_final': final_with_leverage,
        'leverage_advantage': leverage_advantage,
        'annual_return_no_leverage': annual_return_no_leverage,
        'annual_return_with_leverage': net_leveraged_return
    }

if __name__ == "__main__":
    results = calculate_correct_5_year_projections()
    
    print(f"\n" + "=" * 80)
    print("FINAL SUMMARY - 5% VOLUME CONSTRAINT")
    print("=" * 80)
    print(f"With $100,000 initial capital using 110.83% annual returns:")
    print(f"• NO LEVERAGE: ${results['no_leverage_final']:,.0f} after 5 years")
    print(f"• WITH LEVERAGE: ${results['with_leverage_final']:,.0f} after 5 years")
    print(f"• ADVANTAGE: ${results['leverage_advantage']:,.0f} additional wealth")
    print(f"• MULTIPLIER: {results['with_leverage_final']/results['no_leverage_final']:.2f}x")
    print("=" * 80)
    print("This is based on the Executive Summary's 110.83% ANNUAL returns")
    print("for the 5% volume constraint strategy at $1M scale.")
    print("=" * 80)