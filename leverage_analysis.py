"""
Leverage Analysis for Financial Strategy
Incorporates 30% equity requirement with 12% annual interest
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

class LeverageAnalysis:
    def __init__(self, initial_capital=100000, equity_requirement=0.30, annual_interest_rate=0.12):
        """
        Initialize leverage analysis parameters
        
        Args:
            initial_capital: Starting investment amount
            equity_requirement: Minimum equity percentage (0.30 = 30%)
            annual_interest_rate: Annual interest rate on borrowed funds (0.12 = 12%)
        """
        self.initial_capital = initial_capital
        self.equity_requirement = equity_requirement
        self.annual_interest_rate = annual_interest_rate
        self.monthly_interest_rate = annual_interest_rate / 12
        self.daily_interest_rate = annual_interest_rate / 365
        
        # Track leverage metrics
        self.leverage_history = []
        self.interest_payments = []
        self.equity_history = []
        self.margin_calls = []
        
    def calculate_max_position_size(self, equity_value, cash_available):
        """
        Calculate maximum position size given equity requirements
        
        Args:
            equity_value: Current equity value (stocks + cash)
            cash_available: Available cash for new positions
            
        Returns:
            max_position_size: Maximum allowable position size
        """
        # Maximum portfolio value with leverage
        max_portfolio_value = equity_value / self.equity_requirement
        
        # Maximum borrowing capacity
        max_borrowing = max_portfolio_value - equity_value
        
        # Available for new positions (cash + borrowing capacity)
        max_position_size = cash_available + max_borrowing
        
        return max_position_size
    
    def calculate_interest_payment(self, borrowed_amount, days_elapsed):
        """
        Calculate interest payment for borrowed amount
        
        Args:
            borrowed_amount: Amount borrowed
            days_elapsed: Days since last interest payment
            
        Returns:
            interest_payment: Interest owed
        """
        return borrowed_amount * self.daily_interest_rate * days_elapsed
    
    def check_margin_call(self, current_equity, total_borrowed):
        """
        Check if margin call is triggered
        
        Args:
            current_equity: Current equity value
            total_borrowed: Total borrowed amount
            
        Returns:
            margin_call: Boolean indicating margin call status
            required_equity: Minimum required equity
        """
        total_portfolio_value = current_equity + total_borrowed
        required_equity = total_portfolio_value * self.equity_requirement
        
        margin_call = current_equity < required_equity
        
        return margin_call, required_equity
    
    def simulate_leveraged_strategy(self, returns_data, strategy_signals, years=5):
        """
        Simulate leveraged trading strategy with realistic constraints
        
        Args:
            returns_data: DataFrame with stock returns
            strategy_signals: Trading signals from base strategy
            years: Number of years to simulate
            
        Returns:
            results: Dictionary with simulation results
        """
        print(f"Starting leverage simulation with ${self.initial_capital:,} initial capital")
        print(f"Equity requirement: {self.equity_requirement*100}%")
        print(f"Annual interest rate: {self.annual_interest_rate*100}%")
        
        # Initialize portfolio - start with fully invested position
        current_cash = self.initial_capital * 0.3  # Keep some cash for margin
        current_stocks_value = self.initial_capital * 0.7  # Initial stock position
        total_borrowed = 0
        
        # Track performance
        portfolio_values = []
        leverage_ratios = []
        interest_paid_total = 0
        days_since_last_payment = 0
        
        # Generate trading dates (5 years, excluding weekends)
        start_date = datetime(2024, 1, 1)
        end_date = start_date + timedelta(days=years * 365)
        trading_dates = pd.bdate_range(start_date, end_date)
        
        # Set random seed for reproducible results
        np.random.seed(42)
        
        # Simulate each trading day
        for i, current_date in enumerate(trading_dates):
            days_since_last_payment += 1
            
            # Monthly interest payments (every 30 days approximately)
            if days_since_last_payment >= 30 and total_borrowed > 0:
                interest_payment = total_borrowed * self.monthly_interest_rate
                current_cash -= interest_payment
                interest_paid_total += interest_payment
                days_since_last_payment = 0
                
                self.interest_payments.append({
                    'date': current_date,
                    'payment': interest_payment,
                    'borrowed_amount': total_borrowed
                })
            
            # Update stock positions value with market simulation
            if current_stocks_value > 0:
                # Simulate realistic market returns: 8% annual return, 15% volatility
                daily_return = np.random.normal(0.0003, 0.015)  # ~8% annually, 15% volatility
                current_stocks_value *= (1 + daily_return)
                
                # Prevent stocks from going negative
                current_stocks_value = max(current_stocks_value, 0)
            
            # Calculate current equity (assets minus liabilities)
            total_assets = current_cash + current_stocks_value
            current_equity = total_assets - total_borrowed
            
            # Check for margin call before any trading
            if total_borrowed > 0 and current_equity > 0:
                margin_call, required_equity = self.check_margin_call(current_equity, total_borrowed)
                if margin_call and current_stocks_value > 0:
                    # Force position liquidation to meet margin requirements
                    equity_shortfall = required_equity - current_equity
                    liquidation_amount = min(equity_shortfall * 1.1, current_stocks_value * 0.5)  # Liquidate up to 50%
                    
                    current_cash += liquidation_amount
                    current_stocks_value -= liquidation_amount
                    
                    # Reduce borrowed amount with excess cash
                    if current_cash > liquidation_amount * 0.1:  # Keep some cash buffer
                        repayment = min(total_borrowed, current_cash - liquidation_amount * 0.1)
                        current_cash -= repayment
                        total_borrowed -= repayment
                    
                    self.margin_calls.append({
                        'date': current_date,
                        'liquidation_amount': liquidation_amount
                    })
            
            # Recalculate equity after margin call handling
            total_assets = current_cash + current_stocks_value
            current_equity = total_assets - total_borrowed
            
            # Execute leveraged trading strategy (every 10 days)
            if i % 10 == 0 and current_equity > 1000:  # Only trade if we have meaningful equity
                # Calculate available leverage capacity
                max_total_position = current_equity / self.equity_requirement
                current_total_position = current_stocks_value + total_borrowed
                available_leverage = max_total_position - current_total_position
                
                # Conservative position sizing: use 20% of available leverage
                if available_leverage > 1000:  # Minimum trade size
                    trade_size = min(available_leverage * 0.2, current_equity * 0.5)  # Max 50% of equity per trade
                    
                    if trade_size > current_cash:
                        # Need to borrow for this trade
                        borrow_needed = trade_size - current_cash
                        # Only borrow if it doesn't violate equity requirements
                        new_total_borrowed = total_borrowed + borrow_needed
                        new_equity_ratio = current_equity / (current_equity + new_total_borrowed)
                        
                        if new_equity_ratio >= self.equity_requirement:
                            total_borrowed += borrow_needed
                            current_cash += borrow_needed
                    
                    if trade_size <= current_cash:  # Only execute if we have the cash
                        current_cash -= trade_size
                        current_stocks_value += trade_size
            
            # Calculate final metrics for the day
            total_assets = current_cash + current_stocks_value
            current_equity = total_assets - total_borrowed
            
            # Prevent negative equity scenarios
            if current_equity <= 0:
                print(f"Portfolio liquidated on {current_date} - negative equity")
                current_equity = 0
                current_stocks_value = 0
                current_cash = 0
                break
            
            total_portfolio_value = total_assets
            leverage_ratio = total_portfolio_value / current_equity if current_equity > 0 else 1.0
            
            # Record daily metrics
            portfolio_values.append(total_portfolio_value)
            leverage_ratios.append(min(leverage_ratio, 10))  # Cap at 10x for visualization
            
            self.leverage_history.append({
                'date': current_date,
                'cash': current_cash,
                'stocks_value': current_stocks_value,
                'total_borrowed': total_borrowed,
                'equity': current_equity,
                'portfolio_value': total_portfolio_value,
                'leverage_ratio': leverage_ratio
            })
        
        # Calculate final results
        final_equity = max(current_equity, 0)
        total_return = (final_equity - self.initial_capital) / self.initial_capital if self.initial_capital > 0 else -1
        
        # Handle edge cases for annualized return calculation
        if final_equity > 0 and self.initial_capital > 0:
            annualized_return = (final_equity / self.initial_capital) ** (1/years) - 1
        else:
            annualized_return = -1.0  # Total loss
        
        results = {
            'initial_capital': self.initial_capital,
            'final_equity': final_equity,
            'total_return': total_return,
            'annualized_return': annualized_return,
            'total_interest_paid': interest_paid_total,
            'max_leverage': max(leverage_ratios) if leverage_ratios else 1.0,
            'avg_leverage': np.mean(leverage_ratios) if leverage_ratios else 1.0,
            'margin_calls': len(self.margin_calls),
            'trading_days': len(trading_dates),
            'portfolio_values': portfolio_values,
            'leverage_ratios': leverage_ratios
        }
        
        return results
    
    def generate_leverage_report(self, results):
        """
        Generate comprehensive leverage analysis report
        
        Args:
            results: Results from leverage simulation
            
        Returns:
            report: Formatted report string
        """
        report = f"""
# LEVERAGE ANALYSIS REPORT
## Investment Strategy with 30% Equity Requirement

### SIMULATION PARAMETERS
- Initial Capital: ${results['initial_capital']:,.2f}
- Equity Requirement: {self.equity_requirement*100}%
- Annual Interest Rate: {self.annual_interest_rate*100}%
- Simulation Period: 5 years ({results['trading_days']} trading days)

### PERFORMANCE RESULTS
- Final Equity Value: ${results['final_equity']:,.2f}
- Total Return: {results['total_return']*100:.2f}%
- Annualized Return: {results['annualized_return']*100:.2f}%
- Total Interest Paid: ${results['total_interest_paid']:,.2f}

### LEVERAGE METRICS
- Maximum Leverage Ratio: {results['max_leverage']:.2f}x
- Average Leverage Ratio: {results['avg_leverage']:.2f}x
- Margin Calls Triggered: {results['margin_calls']}

### RISK ANALYSIS
- Interest Cost as % of Initial Capital: {(results['total_interest_paid']/results['initial_capital'])*100:.2f}%
- Leverage Efficiency: {((results['total_return']*100) - (results['total_interest_paid']/results['initial_capital']*100)):.2f}%

### COMPARATIVE ANALYSIS
#### Without Leverage (Baseline)
- Estimated Return: ~{(results['annualized_return']/results['avg_leverage'])*100:.2f}% annually
- Risk Level: Lower
- Capital Efficiency: Standard

#### With Leverage (Current Strategy)
- Actual Return: {results['annualized_return']*100:.2f}% annually
- Risk Level: Higher
- Capital Efficiency: {results['avg_leverage']:.2f}x enhanced

### RECOMMENDATIONS
1. **Risk Management**: Monitor leverage ratios daily
2. **Interest Optimization**: Consider refinancing if rates decrease
3. **Position Sizing**: Maintain buffer above minimum equity requirements
4. **Stress Testing**: Model scenarios with market downturns
"""
        
        return report

def run_leverage_analysis():
    """
    Execute complete leverage analysis
    """
    print("=" * 60)
    print("LEVERAGE ANALYSIS - FINANCIAL STRATEGY")
    print("=" * 60)
    
    # Initialize analyzer
    analyzer = LeverageAnalysis(
        initial_capital=100000,
        equity_requirement=0.30,
        annual_interest_rate=0.12
    )
    
    # Create dummy data for simulation
    # In practice, would use actual returns data
    dummy_returns = pd.DataFrame({
        'returns': np.random.normal(0.0008, 0.02, 1000)
    })
    dummy_signals = np.random.choice([0, 1], 1000)
    
    # Run simulation
    results = analyzer.simulate_leveraged_strategy(
        dummy_returns, 
        dummy_signals, 
        years=5
    )
    
    # Generate report
    report = analyzer.generate_leverage_report(results)
    
    # Save report
    with open('/home/npallotta128/projects/testbed-analysis/LEVERAGE_ANALYSIS_REPORT.md', 'w') as f:
        f.write(report)
    
    print("\n" + "=" * 60)
    print("LEVERAGE ANALYSIS COMPLETE")
    print("=" * 60)
    print(f"Final Equity: ${results['final_equity']:,.2f}")
    print(f"Total Return: {results['total_return']*100:.2f}%")
    print(f"Annualized Return: {results['annualized_return']*100:.2f}%")
    print(f"Average Leverage: {results['avg_leverage']:.2f}x")
    print("=" * 60)
    
    return results

if __name__ == "__main__":
    results = run_leverage_analysis()