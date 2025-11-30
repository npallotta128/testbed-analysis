"""
REALISTIC: 5% Volume Constraint with Scaling Returns
Accounts for decreasing returns as capital grows (per Executive Summary)
"""

import numpy as np

def calculate_scaling_returns_projection():
    """
    Calculate 5-year projections with scaling returns as capital grows
    Based on Executive Summary scaling characteristics
    """
    
    print("=" * 80)
    print("REALISTIC: 5% VOLUME CONSTRAINT WITH SCALING RETURNS")
    print("=" * 80)
    print("Accounts for return degradation as capital scales up")
    print("Based on Executive Summary scaling data")
    print("=" * 80)
    
    # Executive Summary scaling data (5% volume constraint)
    scale_returns = {
        1_000_000: 1.1083,      # 110.83% at $1M
        10_000_000: 0.4137,     # 41.37% at $10M  
        100_000_000: 0.1418     # 14.18% at $100M
    }
    
    def get_annual_return(portfolio_value):
        """
        Calculate annual return based on portfolio size using interpolation
        """
        if portfolio_value <= 1_000_000:
            return scale_returns[1_000_000]
        elif portfolio_value <= 10_000_000:
            # Interpolate between $1M and $10M
            ratio = (portfolio_value - 1_000_000) / (10_000_000 - 1_000_000)
            return scale_returns[1_000_000] * (1 - ratio) + scale_returns[10_000_000] * ratio
        elif portfolio_value <= 100_000_000:
            # Interpolate between $10M and $100M
            ratio = (portfolio_value - 10_000_000) / (100_000_000 - 10_000_000)
            return scale_returns[10_000_000] * (1 - ratio) + scale_returns[100_000_000] * ratio
        else:
            # Beyond $100M, assume continued degradation
            return max(0.05, scale_returns[100_000_000] * 0.8)  # Minimum 5% return
    
    def calculate_leverage_effects(base_return, portfolio_value, leverage_ratio=2.5):
        """
        Calculate leverage effects with scaling interest costs
        """
        annual_interest_rate = 0.12
        borrowed_pct = (leverage_ratio - 1) / leverage_ratio
        
        # Interest cost increases with scale due to higher borrowing costs
        if portfolio_value > 10_000_000:
            # Higher interest rates for larger borrowing
            scale_multiplier = min(1.5, 1 + (portfolio_value - 10_000_000) / 100_000_000 * 0.5)
            effective_interest_rate = annual_interest_rate * scale_multiplier
        else:
            effective_interest_rate = annual_interest_rate
        
        # Gross leveraged return
        gross_leveraged_return = base_return * leverage_ratio
        
        # Interest cost
        interest_cost = effective_interest_rate * borrowed_pct * leverage_ratio
        
        # Net leveraged return
        net_leveraged_return = gross_leveraged_return - interest_cost
        
        return max(0.01, net_leveraged_return), interest_cost  # Minimum 1% return
    
    # Initial conditions
    initial_capital = 100000
    years = 5
    
    # Track year-by-year with scaling returns
    print(f"YEAR-BY-YEAR SCALING ANALYSIS:")
    print("-" * 80)
    print(f"{'Year':<6} {'Portfolio':<12} {'Return%':<8} {'No Lev':<12} {'Lev Return%':<11} {'With Lev':<12} {'Advantage':<12}")
    print("-" * 80)
    
    # No leverage scenario
    no_lev_value = initial_capital
    no_lev_values = [no_lev_value]
    
    # With leverage scenario  
    with_lev_value = initial_capital
    with_lev_values = [with_lev_value]
    
    print(f"{'0':<6} ${no_lev_value:<11,} {'--':<8} ${no_lev_value:<11,} {'--':<11} ${with_lev_value:<11,} ${0:<11,}")
    
    for year in range(1, years + 1):
        # No leverage: calculate return based on current portfolio size
        base_return_no_lev = get_annual_return(no_lev_value)
        no_lev_value *= (1 + base_return_no_lev)
        no_lev_values.append(no_lev_value)
        
        # With leverage: calculate return based on current portfolio size
        base_return_with_lev = get_annual_return(with_lev_value)
        net_lev_return, interest_cost = calculate_leverage_effects(base_return_with_lev, with_lev_value)
        with_lev_value *= (1 + net_lev_return)
        with_lev_values.append(with_lev_value)
        
        advantage = with_lev_value - no_lev_value
        
        print(f"{year:<6} ${no_lev_values[year-1]:<11,.0f} {base_return_no_lev*100:<7.1f}% ${no_lev_value:<11,.0f} {net_lev_return*100:<10.1f}% ${with_lev_value:<11,.0f} ${advantage:<11,.0f}")
    
    # Final results
    final_no_leverage = no_lev_values[-1]
    final_with_leverage = with_lev_values[-1]
    leverage_advantage = final_with_leverage - final_no_leverage
    
    print(f"\nFINAL RESULTS AFTER {years} YEARS:")
    print("=" * 80)
    print(f"• Initial Capital: ${initial_capital:,}")
    print(f"• No Leverage Final: ${final_no_leverage:,.0f}")
    print(f"• With Leverage Final: ${final_with_leverage:,.0f}")
    print(f"• Leverage Advantage: ${leverage_advantage:,.0f}")
    print(f"• Leverage Multiplier: {final_with_leverage/final_no_leverage:.2f}x")
    
    # Total returns
    total_return_no_lev = (final_no_leverage - initial_capital) / initial_capital * 100
    total_return_with_lev = (final_with_leverage - initial_capital) / initial_capital * 100
    
    print(f"\nTOTAL RETURNS:")
    print(f"• No Leverage: {total_return_no_lev:.1f}%")
    print(f"• With Leverage: {total_return_with_lev:.1f}%")
    
    # Comparison with unrealistic constant return assumption
    constant_return_final = initial_capital * (1 + scale_returns[1_000_000]) ** years
    
    print(f"\nCOMPARISON:")
    print("=" * 80)
    print(f"Unrealistic (constant 110.83%): ${constant_return_final:,.0f}")
    print(f"Realistic (scaling returns): ${final_no_leverage:,.0f}")
    print(f"Difference: ${constant_return_final - final_no_leverage:,.0f}")
    print(f"Overestimate factor: {constant_return_final/final_no_leverage:.2f}x")
    
    # Key insights about scaling
    print(f"\nSCALING INSIGHTS:")
    print("=" * 80)
    print(f"• Returns degrade significantly as capital grows")
    print(f"• At $1M: {scale_returns[1_000_000]*100:.1f}% annual return")
    print(f"• At $10M: {scale_returns[10_000_000]*100:.1f}% annual return") 
    print(f"• At $100M: {scale_returns[100_000_000]*100:.1f}% annual return")
    print(f"• This is due to market capacity constraints")
    print(f"• Leverage advantage diminishes at higher scales")
    
    return {
        'final_no_leverage': final_no_leverage,
        'final_with_leverage': final_with_leverage,
        'leverage_advantage': leverage_advantage,
        'yearly_values_no_lev': no_lev_values,
        'yearly_values_with_lev': with_lev_values
    }

if __name__ == "__main__":
    results = calculate_scaling_returns_projection()
    
    print(f"\n" + "=" * 80)
    print("CONCLUSION: REALISTIC SCALING ANALYSIS")
    print("=" * 80)
    print(f"The previous calculation assuming constant 110.83% returns was unrealistic.")
    print(f"With proper scaling, $100,000 grows to:")
    print(f"• NO LEVERAGE: ${results['final_no_leverage']:,.0f}")
    print(f"• WITH LEVERAGE: ${results['final_with_leverage']:,.0f}")
    print(f"• ADVANTAGE: ${results['leverage_advantage']:,.0f}")
    print(f"\nThis is much more realistic than the $4.17M/$59.69M projections")
    print(f"that ignored return degradation as capital scales up.")
    print("=" * 80)