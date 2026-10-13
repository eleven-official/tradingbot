#!/usr/bin/env python3
"""
Advanced Portfolio Management System
Multi-strategy portfolio with dynamic allocation, risk management, and performance attribution.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
import logging
from dataclasses import dataclass
import datetime

@dataclass
class PortfolioPosition:
    """Individual position in the portfolio."""
    symbol: str
    quantity: int
    entry_price: float
    current_price: float
    strategy: str
    entry_time: datetime.datetime
    unrealized_pnl: float
    weight: float

class AdvancedPortfolioManager:
    """Professional portfolio management with multi-strategy allocation."""
    
    def __init__(self, initial_capital=100000, max_positions=10):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.max_positions = max_positions
        self.positions = {}
        self.strategy_allocations = {}
        self.performance_history = []
        self.risk_metrics = {
            'var_95': 0.0,
            'expected_shortfall': 0.0,
            'portfolio_beta': 1.0,
            'correlation_matrix': pd.DataFrame()
        }
        
    def add_strategy(self, strategy_name: str, allocation: float, max_weight: float = 0.3):
        """Add strategy to portfolio with allocation percentage."""
        self.strategy_allocations[strategy_name] = {
            'allocation': allocation,
            'max_weight': max_weight,
            'performance': [],
            'sharpe_ratio': 0.0,
            'active_positions': 0
        }
        
    def execute_signal(self, signal, symbol: str, current_price: float, strategy_name: str):
        """Execute trading signal with portfolio management rules."""
        
        # Risk checks
        if not self._risk_check(signal, symbol, strategy_name):
            logging.warning(f"Risk check failed for {symbol} - {signal.action}")
            return False
            
        # Position sizing
        position_size = self._calculate_position_size(signal, current_price, strategy_name)
        
        if signal.action == 'BUY':
            return self._open_long_position(symbol, position_size, current_price, strategy_name, signal)
        elif signal.action == 'SELL':
            return self._open_short_position(symbol, position_size, current_price, strategy_name, signal)
        
        return False
    
    def _calculate_position_size(self, signal, price: float, strategy_name: str) -> int:
        """Dynamic position sizing based on Kelly Criterion and risk management."""
        
        # Get strategy allocation
        strategy_info = self.strategy_allocations.get(strategy_name, {'allocation': 0.1})
        base_allocation = strategy_info['allocation']
        
        # Available capital for this strategy
        available_capital = self.current_capital * base_allocation
        
        # Adjust for signal confidence
        confidence_multiplier = signal.confidence if hasattr(signal, 'confidence') else 0.7
        
        # Risk-adjusted position size (Kelly Criterion simplified)
        win_rate = strategy_info.get('win_rate', 0.6)
        avg_win = strategy_info.get('avg_win', 0.02)
        avg_loss = strategy_info.get('avg_loss', 0.01)
        
        if avg_loss > 0:
            kelly_fraction = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
            kelly_fraction = max(0.01, min(0.25, kelly_fraction))  # Cap at 25%
        else:
            kelly_fraction = 0.1
        
        # Final position size
        risk_adjusted_capital = available_capital * kelly_fraction * confidence_multiplier
        position_size = int(risk_adjusted_capital / price)
        
        # Minimum position check
        return max(1, position_size) if risk_adjusted_capital > price else 0
    
    def _risk_check(self, signal, symbol: str, strategy_name: str) -> bool:
        """Comprehensive risk management checks."""
        
        # Maximum positions check
        if len(self.positions) >= self.max_positions:
            return False
            
        # Strategy concentration check
        strategy_positions = sum(1 for pos in self.positions.values() 
                               if pos.strategy == strategy_name)
        max_strategy_positions = self.max_positions // len(self.strategy_allocations)
        
        if strategy_positions >= max_strategy_positions:
            return False
            
        # Portfolio heat check (total risk exposure)
        total_exposure = sum(abs(pos.quantity * pos.current_price) for pos in self.positions.values())
        if total_exposure > self.current_capital * 2.0:  # 200% max exposure
            return False
            
        # Correlation check (avoid highly correlated positions)
        if self._correlation_risk_check(symbol):
            return False
            
        return True
    
    def _correlation_risk_check(self, new_symbol: str) -> bool:
        """Check if adding this position would create excessive correlation risk."""
        # Simplified correlation check
        # In production, this would check actual correlation matrices
        similar_positions = [symbol for symbol in self.positions.keys() 
                           if symbol.startswith(new_symbol[:3])]  # Same sector/prefix
        
        return len(similar_positions) >= 3  # Max 3 similar positions
    
    def _open_long_position(self, symbol: str, quantity: int, price: float, strategy: str, signal) -> bool:
        """Open long position with risk management."""
        if quantity <= 0:
            return False
            
        total_cost = quantity * price
        if total_cost > self.current_capital * 0.5:  # Max 50% of capital per position
            quantity = int(self.current_capital * 0.5 / price)
            
        if quantity <= 0:
            return False
            
        position = PortfolioPosition(
            symbol=symbol,
            quantity=quantity,
            entry_price=price,
            current_price=price,
            strategy=strategy,
            entry_time=datetime.datetime.now(),
            unrealized_pnl=0.0,
            weight=total_cost / self.current_capital
        )
        
        self.positions[symbol] = position
        self.current_capital -= total_cost
        
        # Set stop loss if provided
        if hasattr(signal, 'stop_loss') and signal.stop_loss:
            self._set_stop_loss(symbol, signal.stop_loss)
            
        logging.info(f"Opened LONG {quantity} {symbol} @ {price:.2f} via {strategy}")
        return True
    
    def _open_short_position(self, symbol: str, quantity: int, price: float, strategy: str, signal) -> bool:
        """Open short position (if supported by broker)."""
        # Similar to long position but for short selling
        # Implementation would depend on broker capabilities
        logging.info(f"Short selling not implemented for {symbol}")
        return False
    
    def update_positions(self, market_data: Dict[str, float]):
        """Update all positions with current market prices."""
        for symbol, position in self.positions.items():
            if symbol in market_data:
                old_price = position.current_price
                position.current_price = market_data[symbol]
                position.unrealized_pnl = (position.current_price - position.entry_price) * position.quantity
                
                # Update portfolio value
                price_change = position.current_price - old_price
                self.current_capital += price_change * position.quantity
    
    def get_portfolio_summary(self) -> Dict:
        """Get comprehensive portfolio summary."""
        total_value = self.current_capital + sum(pos.quantity * pos.current_price 
                                               for pos in self.positions.values())
        total_pnl = total_value - self.initial_capital
        
        # Strategy breakdown
        strategy_performance = {}
        for strategy_name in self.strategy_allocations:
            strategy_positions = [pos for pos in self.positions.values() 
                                if pos.strategy == strategy_name]
            strategy_pnl = sum(pos.unrealized_pnl for pos in strategy_positions)
            strategy_performance[strategy_name] = {
                'positions': len(strategy_positions),
                'unrealized_pnl': strategy_pnl,
                'allocation': self.strategy_allocations[strategy_name]['allocation']
            }
        
        return {
            'total_value': total_value,
            'total_pnl': total_pnl,
            'total_return': total_pnl / self.initial_capital,
            'cash_balance': self.current_capital,
            'active_positions': len(self.positions),
            'strategy_performance': strategy_performance,
            'largest_position': max([pos.weight for pos in self.positions.values()], default=0),
            'portfolio_concentration': self._calculate_concentration()
        }
    
    def _calculate_concentration(self) -> float:
        """Calculate portfolio concentration (Herfindahl index)."""
        if not self.positions:
            return 0.0
            
        total_value = sum(pos.quantity * pos.current_price for pos in self.positions.values())
        if total_value == 0:
            return 0.0
            
        weights = [(pos.quantity * pos.current_price / total_value) ** 2 
                  for pos in self.positions.values()]
        return sum(weights)
    
    def rebalance_portfolio(self):
        """Rebalance portfolio based on target allocations and performance."""
        # Get current allocations
        summary = self.get_portfolio_summary()
        
        # Identify overweight/underweight strategies
        for strategy_name, allocation_info in self.strategy_allocations.items():
            target_allocation = allocation_info['allocation']
            current_performance = summary['strategy_performance'].get(strategy_name, {})
            
            # Adjust allocations based on performance (simplified)
            recent_performance = self._get_recent_performance(strategy_name)
            if recent_performance > 0.05:  # 5% outperformance
                allocation_info['allocation'] = min(allocation_info['allocation'] * 1.1, 0.4)
            elif recent_performance < -0.05:  # 5% underperformance
                allocation_info['allocation'] = max(allocation_info['allocation'] * 0.9, 0.05)
        
        logging.info("Portfolio rebalanced based on recent performance")
    
    def _get_recent_performance(self, strategy_name: str) -> float:
        """Get recent performance for a strategy (last 30 days)."""
        # Simplified - would use actual trade history in production
        return np.random.normal(0.02, 0.10)  # Placeholder
    
    def close_position(self, symbol: str, reason: str = "Manual close"):
        """Close a position and realize P&L."""
        if symbol not in self.positions:
            return False
            
        position = self.positions[symbol]
        realized_pnl = position.unrealized_pnl
        
        # Add proceeds to cash
        proceeds = position.quantity * position.current_price
        self.current_capital += proceeds
        
        # Remove position
        del self.positions[symbol]
        
        logging.info(f"Closed {symbol}: PnL = ${realized_pnl:.2f} ({reason})")
        return True