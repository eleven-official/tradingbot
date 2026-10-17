"""
Freqtrade-Inspired Edge Positioning
Advanced position sizing based on account balance, stop loss, and risk management
"""
import logging
import numpy as np
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass
from enum import Enum

__all__ = ['PositioningMethod', 'Position', 'EdgePositioning']


class PositioningMethod(Enum):
    """Position sizing methods."""
    FIXED = "fixed"
    PERCENTAGE = "percentage"
    EDGE = "edge"
    KELLY = "kelly"
    OPTIMAL_F = "optimal_f"


@dataclass
class Position:
    """Position information."""
    symbol: str
    side: str
    entry_price: float
    stop_loss: float
    take_profit: float
    size: float
    value: float
    risk_amount: float
    risk_percent: float
    leverage: float = 1.0


class EdgePositioning:
    """
    Freqtrade-inspired edge positioning system for optimal position sizing.
    Calculates position sizes based on risk, account balance, and edge.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.positioning_config = config.get('positioning', {})
        
        # Configuration
        self.method = PositioningMethod(self.positioning_config.get('method', 'edge'))
        self.available_capital = self.positioning_config.get('available_capital', 10000.0)
        self.max_risk_per_trade = self.positioning_config.get('max_risk_per_trade', 0.01)  # 1%
        self.max_risk_total = self.positioning_config.get('max_risk_total', 0.05)  # 5%
        self.max_position_size = self.positioning_config.get('max_position_size', 0.5)  # 50% of capital
        self.min_position_size = self.positioning_config.get('min_position_size', 0.01)  # 1% of capital
        
        # Edge parameters
        self.win_rate = self.positioning_config.get('win_rate', 0.5)
        self.risk_reward_ratio = self.positioning_config.get('risk_reward_ratio', 2.0)
        
        # Current positions
        self.current_positions: Dict[str, Position] = {}
        self.total_risk = 0.0
        
        logging.info("Edge Positioning initialized")
    
    def calculate_position_size(self, symbol: str, entry_price: float, 
                              stop_loss: float, take_profit: float,
                              confidence: float = 0.5) -> Position:
        """
        Calculate optimal position size using the configured method.
        """
        risk_per_share = abs(entry_price - stop_loss)
        risk_reward = abs(take_profit - entry_price) / risk_per_share if risk_per_share > 0 else 0
        
        if self.method == PositioningMethod.FIXED:
            return self._fixed_position_size(symbol, entry_price, stop_loss, take_profit)
        elif self.method == PositioningMethod.PERCENTAGE:
            return self._percentage_position_size(symbol, entry_price, stop_loss, take_profit)
        elif self.method == PositioningMethod.EDGE:
            return self._edge_position_size(symbol, entry_price, stop_loss, take_profit, confidence)
        elif self.method == PositioningMethod.KELLY:
            return self._kelly_position_size(symbol, entry_price, stop_loss, take_profit)
        elif self.method == PositioningMethod.OPTIMAL_F:
            return self._optimal_f_position_size(symbol, entry_price, stop_loss, take_profit)
        else:
            return self._edge_position_size(symbol, entry_price, stop_loss, take_profit, confidence)
    
    def _fixed_position_size(self, symbol: str, entry_price: float, 
                           stop_loss: float, take_profit: float) -> Position:
        """Fixed position size (constant amount)."""
        fixed_amount = self.positioning_config.get('fixed_amount', 100.0)
        size = fixed_amount / entry_price
        
        risk_amount = abs(entry_price - stop_loss) * size
        risk_percent = risk_amount / self.available_capital
        
        return Position(
            symbol=symbol,
            side='long',
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            size=size,
            value=fixed_amount,
            risk_amount=risk_amount,
            risk_percent=risk_percent
        )
    
    def _percentage_position_size(self, symbol: str, entry_price: float,
                                 stop_loss: float, take_profit: float) -> Position:
        """Percentage-based position sizing."""
        position_percent = self.positioning_config.get('position_percent', 0.1)  # 10%
        position_value = self.available_capital * position_percent
        size = position_value / entry_price
        
        risk_amount = abs(entry_price - stop_loss) * size
        risk_percent = risk_amount / self.available_capital
        
        return Position(
            symbol=symbol,
            side='long',
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            size=size,
            value=position_value,
            risk_amount=risk_amount,
            risk_percent=risk_percent
        )
    
    def _edge_position_size(self, symbol: str, entry_price: float,
                          stop_loss: float, take_profit: float,
                          confidence: float) -> Position:
        """
        Edge-based position sizing (Freqtrade's default).
        Adjusts position size based on edge (win rate, risk/reward, confidence).
        """
        risk_per_share = abs(entry_price - stop_loss)
        
        # Calculate edge
        if self.risk_reward_ratio > 0:
            edge = (self.win_rate * self.risk_reward_ratio - (1 - self.win_rate))
        else:
            edge = 0
        
        # Adjust edge with confidence
        adjusted_edge = edge * confidence
        
        # Calculate position size based on edge
        if adjusted_edge > 0:
            # Higher edge = larger position
            position_multiplier = min(adjusted_edge * 2, 2.0)  # Cap at 2x
        else:
            # Negative edge = smaller position
            position_multiplier = max(adjusted_edge * 2, 0.25)  # Minimum 25%
        
        # Calculate risk amount
        risk_amount = self.available_capital * self.max_risk_per_trade * position_multiplier
        
        # Calculate position size
        size = risk_amount / risk_per_share if risk_per_share > 0 else 0
        position_value = size * entry_price
        
        # Ensure position doesn't exceed max position size
        if position_value > self.available_capital * self.max_position_size:
            position_value = self.available_capital * self.max_position_size
            size = position_value / entry_price
        
        # Ensure minimum position size
        if position_value < self.available_capital * self.min_position_size:
            position_value = self.available_capital * self.min_position_size
            size = position_value / entry_price
        
        risk_percent = risk_amount / self.available_capital
        
        return Position(
            symbol=symbol,
            side='long',
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            size=size,
            value=position_value,
            risk_amount=risk_amount,
            risk_percent=risk_percent
        )
    
    def _kelly_position_size(self, symbol: str, entry_price: float,
                           stop_loss: float, take_profit: float) -> Position:
        """
        Kelly criterion position sizing.
        f* = (bp - q) / b
        where b = odds, p = win probability, q = loss probability
        """
        risk_per_share = abs(entry_price - stop_loss)
        reward_per_share = abs(take_profit - entry_price)
        
        if risk_per_share > 0:
            odds = reward_per_share / risk_per_share
        else:
            odds = 1.0
        
        # Kelly fraction
        kelly_fraction = (self.win_rate * odds - (1 - self.win_rate)) / odds
        
        # Cap Kelly fraction (avoid overbetting)
        kelly_fraction = max(0, min(kelly_fraction, 0.25))  # Max 25% of capital
        
        # Calculate position size
        position_value = self.available_capital * kelly_fraction
        size = position_value / entry_price
        
        risk_amount = abs(entry_price - stop_loss) * size
        risk_percent = risk_amount / self.available_capital
        
        return Position(
            symbol=symbol,
            side='long',
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            size=size,
            value=position_value,
            risk_amount=risk_amount,
            risk_percent=risk_percent
        )
    
    def _optimal_f_position_size(self, symbol: str, entry_price: float,
                                stop_loss: float, take_profit: float) -> Position:
        """
        Optimal F position sizing (similar to Kelly but more conservative).
        Uses risk of ruin calculations.
        """
        risk_per_share = abs(entry_price - stop_loss)
        reward_per_share = abs(take_profit - entry_price)
        
        if risk_per_share > 0:
            odds = reward_per_share / risk_per_share
        else:
            odds = 1.0
        
        # Optimal F (more conservative than Kelly)
        optimal_f = (self.win_rate * odds - (1 - self.win_rate)) / odds
        
        # Apply safety factor (half Kelly)
        optimal_f = max(0, min(optimal_f, 0.15))  # Max 15% of capital
        
        # Calculate position size
        position_value = self.available_capital * optimal_f
        size = position_value / entry_price
        
        risk_amount = abs(entry_price - stop_loss) * size
        risk_percent = risk_amount / self.available_capital
        
        return Position(
            symbol=symbol,
            side='long',
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            size=size,
            value=position_value,
            risk_amount=risk_amount,
            risk_percent=risk_percent
        )
    
    def can_open_position(self, position: Position) -> bool:
        """Check if we can open a new position given risk limits."""
        # Check if we already have a position in this symbol
        if position.symbol in self.current_positions:
            return False
        
        # Check total risk
        if self.total_risk + position.risk_amount > self.available_capital * self.max_risk_total:
            return False
        
        # Check position size limits
        if position.value > self.available_capital * self.max_position_size:
            return False
        
        return True
    
    def open_position(self, position: Position):
        """Open a new position."""
        if not self.can_open_position(position):
            logging.warning(f"Cannot open position for {position.symbol} - risk limits exceeded")
            return
        
        self.current_positions[position.symbol] = position
        self.total_risk += position.risk_amount
        
        logging.info(f"Opened position: {position.symbol} | Size: {position.size:.4f} | Risk: {position.risk_percent:.2%}")
    
    def close_position(self, symbol: str, exit_price: float) -> float:
        """Close a position and return profit/loss."""
        if symbol not in self.current_positions:
            return 0.0
        
        position = self.current_positions[symbol]
        
        # Calculate P&L
        if position.side == 'long':
            pnl = (exit_price - position.entry_price) * position.size
        else:
            pnl = (position.entry_price - exit_price) * position.size
        
        # Update risk
        self.total_risk -= position.risk_amount
        
        # Remove position
        del self.current_positions[symbol]
        
        logging.info(f"Closed position: {symbol} | P&L: ${pnl:.2f}")
        
        return pnl
    
    def update_win_rate(self, recent_trades: List[float]):
        """Update win rate based on recent trades."""
        if not recent_trades:
            return
        
        wins = sum(1 for trade in recent_trades if trade > 0)
        self.win_rate = wins / len(recent_trades)
        
        logging.info(f"Updated win rate: {self.win_rate:.2%}")
    
    def get_position_status(self) -> Dict[str, Any]:
        """Get current position status."""
        positions = []
        total_value = 0.0
        
        for symbol, position in self.current_positions.items():
            positions.append({
                'symbol': symbol,
                'side': position.side,
                'entry_price': position.entry_price,
                'size': position.size,
                'value': position.value,
                'risk_amount': position.risk_amount,
                'risk_percent': position.risk_percent
            })
            total_value += position.value
        
        return {
            'method': self.method.value,
            'available_capital': self.available_capital,
            'total_risk': self.total_risk,
            'total_risk_percent': self.total_risk / self.available_capital,
            'open_positions': len(self.current_positions),
            'positions': positions,
            'total_position_value': total_value,
            'win_rate': self.win_rate
        }