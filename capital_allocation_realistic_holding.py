"""
Realistic Capital Allocation with 2-Year Holding Period

Key Changes:
- 500 timepoints = ~2 years holding period per position
- Capital deployed over first 10 days (entry window)
- Capital returned over last 10 days (exit window)
- Tracks actual capital tied up over time
- Calculates annualized returns properly

Strategy:
- ML-ranked dropout events
- 5% capital constraint + 2% volume constraint
- Realistic simulation of capital deployment timeline
"""

import pandas as pd
import numpy as np
import joblib

# Constants
MAX_POSITION_PCT = 0.05  # 5% of equity
import os
VOLUME_CONSTRAINT_PCT = float(os.environ.get('VOLUME_CONSTRAINT_PCT', '0.05'))  # default 5% of price*volume
HOLDING_PERIOD_DAYS = 500  # 2 years
ENTRY_WINDOW_DAYS = 10
EXIT_WINDOW_DAYS = 10

MODEL_FILE = 'ml_event_model_sliding_drop_lr.pkl'
EVENTS_FILE = 'events_sliding_window_features.csv'
DATA_FILE = 'data.csv'

def load_model_and_events():
    """Load trained model and events with features"""
    print("Loading model and events...")
    model = joblib.load(MODEL_FILE)
    events = pd.read_csv(EVENTS_FILE)
    
    # Filter dropout events only
    dropout = events[events['Event_Type'] == 'DROP'].copy()
    dropout = dropout.dropna(subset=['Future_Return'])
    
    print(f"Loaded {len(dropout)} dropout events")
    return model, dropout

def get_features(df, model):
    """Extract feature columns matching training"""
    feature_cols = list(model.feature_names_in_)
    missing = [c for c in feature_cols if c not in df.columns]
    if missing:
        for col in missing:
            df[col] = 0
    return df[feature_cols].fillna(0)

def merge_price_volume(events_df):
    """Merge price and volume from data.csv"""
    print("Loading price/volume data...")
    
    data = pd.read_csv(DATA_FILE)
    
    # Calculate average price and volume per symbol
    symbol_stats = data.groupby('Symbol').agg({
        'Closing': 'mean',
        'Volume': 'mean'
    }).reset_index()
    symbol_stats.columns = ['Security', 'avg_price', 'avg_volume']
    
    # Merge with events
    merged = events_df.merge(symbol_stats, on='Security', how='left')
    
    # Fill missing with conservative defaults
    merged['avg_price'] = merged['avg_price'].fillna(50.0)
    merged['avg_volume'] = merged['avg_volume'].fillna(1000000.0)
    
    print(f"Merged price/volume for {len(merged)} events")
    return merged

def split_train_test(df):
    """Split by block (70/30 train/test)"""
    blocks = sorted(df['Block'].unique())
    train_blocks = blocks[:int(len(blocks) * 0.7)]
    
    train_df = df[df['Block'].isin(train_blocks)].copy()
    test_df = df[~df['Block'].isin(train_blocks)].copy()
    
    print(f"Train: {len(train_df)} events, Test: {len(test_df)} events")
    return train_df, test_df

def rank_events_by_model(test_df, model):
    """Rank events by model probability"""
    X_test = get_features(test_df, model)
    test_df['model_proba'] = model.predict_proba(X_test)[:, 1]
    
    # Sort by probability descending
    test_df = test_df.sort_values('model_proba', ascending=False).reset_index(drop=True)
    
    return test_df

class PortfolioSimulator:
    """Simulate portfolio with realistic holding periods and capital constraints"""
    
    def __init__(self, initial_capital, max_position_pct=0.05, volume_pct=0.02):
        self.initial_capital = initial_capital
        self.max_position_pct = max_position_pct
        self.volume_pct = volume_pct
        
        self.cash = initial_capital
        self.positions = []  # Active positions
        self.closed_positions = []  # Completed trades
        self.current_day = 0
        
    def calculate_position_size(self, price, volume, current_equity):
        """Calculate position size with both constraints"""
        capital_cap = current_equity * self.max_position_pct
        volume_cap = price * volume * self.volume_pct
        
        position_size = min(capital_cap, volume_cap)
        binding = 'capital' if capital_cap <= volume_cap else 'volume'
        
        return position_size, binding, capital_cap, volume_cap
    
    def get_current_equity(self):
        """Calculate total equity (cash + position values)"""
        # Estimate current value of open positions (assuming they appreciate linearly)
        open_value = sum(pos['current_value'] for pos in self.positions)
        return self.cash + open_value
    
    def get_exposure_to_security(self, security):
        """Calculate total current exposure to a given security across all positions"""
        total_exposure = sum(
            pos['current_value'] 
            for pos in self.positions 
            if pos['security'] == security
        )
        return total_exposure
    
    def open_position(self, event_data, day):
        """
        Open a new position over ENTRY_WINDOW_DAYS
        Returns: True if position opened, False if insufficient capital
        """
        current_equity = self.get_current_equity()
        
        # Check existing exposure to this security
        existing_exposure = self.get_exposure_to_security(event_data['Security'])
        max_allowed_exposure = current_equity * self.max_position_pct
        
        # Calculate how much more we can allocate to this security
        available_for_security = max_allowed_exposure - existing_exposure
        
        if available_for_security < 100:
            # Already at or exceeding 5% limit for this security
            return False
        
        # Calculate position size
        position_size, binding, cap_cap, vol_cap = self.calculate_position_size(
            event_data['avg_price'],
            event_data['avg_volume'],
            current_equity
        )
        
        # Further constrain by available exposure for this security
        if position_size > available_for_security:
            position_size = available_for_security
            binding = 'security_limit'
        
        # Check if we have enough cash to deploy
        if position_size < 100 or position_size > self.cash:
            return False
        
        # Deploy capital over entry window
        daily_deployment = position_size / ENTRY_WINDOW_DAYS
        
        # Create position record
        position = {
            'security': event_data['Security'],
            'block': event_data['Block'],
            'model_proba': event_data['model_proba'],
            'entry_day': day,
            'exit_day': day + HOLDING_PERIOD_DAYS,
            'position_size': position_size,
            'deployed_so_far': 0,
            'current_value': 0,
            'avg_price': event_data['avg_price'],
            'expected_return_pct': event_data['Future_Return'],
            'binding_constraint': binding,
            'capital_cap': cap_cap,
            'volume_cap': vol_cap,
                        'security_limit': max_allowed_exposure,
                        'existing_exposure': existing_exposure,
            'daily_deployment': daily_deployment,
            'status': 'entering'
        }
        
        self.positions.append(position)
        return True
    
    def process_day(self, day):
        """Process all positions for a given day"""
        
        # Process each active position
        for pos in self.positions[:]:  # Copy list to allow modification
            
            # ENTRY PHASE (first 10 days)
            if pos['status'] == 'entering':
                days_since_entry = day - pos['entry_day']
                
                if days_since_entry < ENTRY_WINDOW_DAYS:
                    # Deploy daily capital
                    deployment = min(pos['daily_deployment'], self.cash)
                    self.cash -= deployment
                    pos['deployed_so_far'] += deployment
                    
                    # Update current value (assuming gradual appreciation)
                    progress = (day - pos['entry_day']) / HOLDING_PERIOD_DAYS
                    expected_gain = pos['deployed_so_far'] * (pos['expected_return_pct'] / 100.0) * progress
                    pos['current_value'] = pos['deployed_so_far'] + expected_gain
                else:
                    # Entry complete, now holding
                    pos['status'] = 'holding'
            
            # HOLDING PHASE
            elif pos['status'] == 'holding':
                days_held = day - pos['entry_day']
                
                # Check if we should start exiting
                if days_held >= (HOLDING_PERIOD_DAYS - EXIT_WINDOW_DAYS):
                    pos['status'] = 'exiting'
                    pos['exit_start_day'] = day
                    
                    # Calculate final value
                    total_gain = pos['deployed_so_far'] * (pos['expected_return_pct'] / 100.0)
                    pos['final_value'] = pos['deployed_so_far'] + total_gain
                    pos['remaining_value'] = pos['final_value']
                    pos['daily_exit'] = pos['final_value'] / EXIT_WINDOW_DAYS
                else:
                    # Update current value based on progress
                    progress = days_held / HOLDING_PERIOD_DAYS
                    expected_gain = pos['deployed_so_far'] * (pos['expected_return_pct'] / 100.0) * progress
                    pos['current_value'] = pos['deployed_so_far'] + expected_gain
            
            # EXIT PHASE (last 10 days)
            elif pos['status'] == 'exiting':
                days_exiting = day - pos['exit_start_day']
                
                if days_exiting < EXIT_WINDOW_DAYS:
                    # Return capital gradually
                    self.cash += pos['daily_exit']
                    pos['remaining_value'] -= pos['daily_exit']
                    pos['current_value'] = pos['remaining_value']
                else:
                    # Position fully closed
                    pnl = pos['final_value'] - pos['deployed_so_far']
                    
                    closed_pos = {
                        'security': pos['security'],
                        'block': pos['block'],
                        'model_proba': pos['model_proba'],
                        'position_size': pos['deployed_so_far'],
                        'final_value': pos['final_value'],
                        'pnl': pnl,
                        'return_pct': pos['expected_return_pct'],
                        'binding_constraint': pos['binding_constraint'],
                        'capital_cap': pos['capital_cap'],
                        'volume_cap': pos['volume_cap'],
                                            'security_limit': pos.get('security_limit', 0),
                        'days_held': HOLDING_PERIOD_DAYS,
                    }
                    
                    self.closed_positions.append(closed_pos)
                    self.positions.remove(pos)
    
    def run_simulation(self, ranked_events, max_positions=None):
        """
        Run full simulation with realistic timing
        
        Args:
            ranked_events: DataFrame of events sorted by model probability
            max_positions: Maximum number of positions to open (None = all events)
        """
        print(f"\nRunning simulation with ${self.initial_capital/1e6:.1f}M capital...")
        
        events_to_trade = ranked_events.head(max_positions) if max_positions else ranked_events
        
        # Track attempted positions
        positions_opened = 0
        positions_skipped = 0
        
        # Simulate opening positions on successive days
        for idx, (_, event) in enumerate(events_to_trade.iterrows()):
            day = idx  # Each event gets attempted on a different day
            
            # Process existing positions
            self.process_day(day)
            
            # Try to open new position
            if self.open_position(event, day):
                positions_opened += 1
            else:
                positions_skipped += 1
            
            # Progress update
            if (idx + 1) % 1000 == 0:
                print(f"  Processed {idx+1}/{len(events_to_trade)} events, "
                      f"Opened: {positions_opened}, Active: {len(self.positions)}, "
                      f"Closed: {len(self.closed_positions)}")
        
        # Run out remaining positions (process through all exit windows)
        print(f"\nClosing remaining {len(self.positions)} positions...")
        max_days = max([p['exit_day'] + EXIT_WINDOW_DAYS for p in self.positions]) if self.positions else day
        
        for d in range(day + 1, max_days + 1):
            self.process_day(d)
            
            if d % 100 == 0:
                print(f"  Day {d}: {len(self.positions)} positions still active")
        
        print(f"\nSimulation complete:")
        print(f"  Attempted: {len(events_to_trade)}")
        print(f"  Opened: {positions_opened}")
        print(f"  Skipped: {positions_skipped}")
        print(f"  Closed: {len(self.closed_positions)}")
        
        return self.get_results()
    
    def get_results(self):
        """Calculate final results"""
        if len(self.closed_positions) == 0:
            return None
        
        closed_df = pd.DataFrame(self.closed_positions)
        
        total_deployed = closed_df['position_size'].sum()
        total_pnl = closed_df['pnl'].sum()
        final_equity = self.cash + sum(p['current_value'] for p in self.positions)
        
        # Calculate returns
        total_return_pct = ((final_equity - self.initial_capital) / self.initial_capital) * 100
        
        # Annualized return (2 year holding period)
        years = HOLDING_PERIOD_DAYS / 252  # Trading days per year
        annualized_return = ((final_equity / self.initial_capital) ** (1/years) - 1) * 100
        
        # Constraint analysis
        capital_constrained = (closed_df['binding_constraint'] == 'capital').sum()
        volume_constrained = (closed_df['binding_constraint'] == 'volume').sum()
        security_constrained = (closed_df['binding_constraint'] == 'security_limit').sum()
        
        win_rate = (closed_df['pnl'] > 0).mean() * 100
        
        metrics = {
            'initial_capital': self.initial_capital,
            'final_equity': final_equity,
            'total_deployed': total_deployed,
            'total_pnl': total_pnl,
            'total_return_pct': total_return_pct,
            'annualized_return_pct': annualized_return,
            'holding_period_years': years,
            'n_positions': len(closed_df),
            'positions_still_open': len(self.positions),
            'avg_position_size': closed_df['position_size'].mean(),
            'median_position_size': closed_df['position_size'].median(),
            'max_position_size': closed_df['position_size'].max(),
            'capital_constrained_pct': (capital_constrained / len(closed_df)) * 100,
            'volume_constrained_pct': (volume_constrained / len(closed_df)) * 100,
                        'security_constrained_pct': (security_constrained / len(closed_df)) * 100,
            'win_rate_pct': win_rate,
            'avg_return_pct': closed_df['return_pct'].mean(),
            'median_return_pct': closed_df['return_pct'].median(),
        }
        
        return metrics, closed_df

def run_realistic_allocation(top_n: int | None = None):
    """Run realistic capital allocation with proper holding periods"""
    
    # Load model and events
    model, events = load_model_and_events()
    
    # Merge price/volume data
    events = merge_price_volume(events)
    
    # Split train/test
    train_df, test_df = split_train_test(events)
    
    # Rank test events by model probability
    test_df = rank_events_by_model(test_df, model)
    if top_n:
        test_df = test_df.head(top_n).copy()
    
    print(f"\nTest set: {len(test_df)} events ranked by model probability")
    
    # Capital levels to test
    capital_levels = [
        1_000_000,      # $1M
        5_000_000,      # $5M
        10_000_000,     # $10M
        25_000_000,     # $25M
        50_000_000,     # $50M
        100_000_000,    # $100M
        250_000_000,    # $250M
        500_000_000,    # $500M
        1_000_000_000,  # $1B
    ]
    
    results = []
    
    print("\n" + "="*80)
    print("REALISTIC CAPITAL ALLOCATION - 2 YEAR HOLDING PERIOD")
    print("="*80)
    
    for idx, capital in enumerate(capital_levels, 1):
        print(f"\n[{idx}/{len(capital_levels)}] Testing ${capital/1e6:.0f}M capital...")
        
        simulator = PortfolioSimulator(capital, MAX_POSITION_PCT, VOLUME_CONSTRAINT_PCT)
        result = simulator.run_simulation(test_df)
        
        if result:
            metrics, positions_df = result
            results.append(metrics)
            
            print(f"\nResults for ${capital/1e6:.0f}M:")
            print(f"  Final Equity: ${metrics['final_equity']/1e6:.2f}M")
            print(f"  Total Return: {metrics['total_return_pct']:.2f}%")
            print(f"  Annualized Return: {metrics['annualized_return_pct']:.2f}%")
            print(f"  Positions Closed: {metrics['n_positions']}")
            print(f"  Avg Position: ${metrics['avg_position_size']:,.0f}")
            print(f"  Volume Constrained: {metrics['volume_constrained_pct']:.1f}%")
            print(f"  Security Limit Constrained: {metrics['security_constrained_pct']:.1f}%")
            print(f"  Win Rate: {metrics['win_rate_pct']:.1f}%")
            
            # Save details for largest capital level
            if capital == capital_levels[-1]:
                positions_df.to_csv('realistic_allocation_positions_1B.csv', index=False)
    
    # Save summary results
    if results:
        results_df = pd.DataFrame(results)
        results_df.to_csv('realistic_capital_allocation_results.csv', index=False)
        print(f"\n✓ Saved results to realistic_capital_allocation_results.csv")
        
        # Print summary
        print("\n" + "="*80)
        print("SUMMARY - ANNUALIZED RETURNS BY CAPITAL LEVEL")
        print("="*80)
        print(results_df[['initial_capital', 'annualized_return_pct', 'total_return_pct', 
                          'n_positions', 'volume_constrained_pct', 'security_constrained_pct']].to_string(index=False))
    
    return results_df

if __name__ == '__main__':
    # You can set TOP_N via env, e.g., TOP_N=1000
    top_n_env = os.environ.get('TOP_N')
    top_n = int(top_n_env) if top_n_env else None
    results = run_realistic_allocation(top_n=top_n)
