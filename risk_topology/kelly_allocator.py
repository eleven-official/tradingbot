"""
Dynamic Fractional Kelly Criterion Allocator
Optimal position sizing based on win-rate probability and market entropy
"""
import asyncio
import logging
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import deque
import statistics


@dataclass
class Position:
    """Trading position."""
    position_id: str
    symbol: str
    side: str
    entry_price: float
    current_price: float
    size: float
    value: float
    stop_loss: float
    take_profit: float
    unrealized_pnl: float
    realized_pnl: float
    kelly_fraction: float
    risk_amount: float
    open_time: datetime
    close_time: Optional[datetime] = None
    status: str = "open"


class KellyAllocator:
    """
    Dynamic Fractional Kelly Criterion position allocator.
    Optimizes position sizing based on edge and market conditions.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.kelly_config = config.get('risk_topology', {})
        
        # Configuration
        self.enabled = self.kelly_config.get('kelly_enabled', True)
        self.max_risk_per_trade = self.kelly_config.get('max_risk_per_trade', 0.01)
        self.global_risk_limit = self.kelly_config.get('global_risk_limit', 0.05)
        self.max_positions = self.kelly_config.get('max_positions', 5)
        
        # Kelly parameters
        self.win_rate = 0.5
        self.avg_win = 0.02
        self.avg_loss = 0.01
        self.payoff_ratio = 2.0
        
        # Historical performance
        self.trade_history: deque = deque(maxlen=100)
        self.recent_trades: deque = deque(maxlen=20)
        
        # Current positions
        self.positions: Dict[str, Position] = {}
        self.total_exposure = 0.0
        self.total_risk = 0.0
        
        # Account state
        self.account_balance = 100000.0
        self.available_capital = 100000.0
        
        self.logger = logging.getLogger(__name__)
        logging.info("Kelly Allocator initialized")
    
    async def initialize(self):
        """Initialize the Kelly allocator."""
        self.logger.info("Kelly Allocator initialized")
    
    async def _load_historical_performance(self):
        """Load historical trade performance."""
        # In production, this would load from database
        # For now, use defaults
        pass
    
    def calculate_kelly_fraction(self, win_rate: float, avg_win: float, 
                                 avg_loss: float) -> float:
        """
        Calculate Kelly criterion fraction.
        f* = (bp - q) / b
        where b = payoff ratio, p = win probability, q = loss probability
        """
        if avg_loss == 0:
            return 0.0
        
        payoff_ratio = avg_win / avg_loss
        win_prob = win_rate
        lose_prob = 1 - win_rate
        
        kelly = (payoff_ratio * win_prob - lose_prob) / payoff_ratio
        
        # Apply safety factor (half Kelly)
        kelly = kelly * 0.5
        
        # Ensure Kelly is positive
        kelly = max(0, kelly)
        
        # Cap Kelly at 25% (very conservative)
        kelly = min(kelly, 0.25)
        
        return kelly
    
    def calculate_dynamic_kelly(self, signal_confidence: float, 
                               market_entropy: float) -> float:
        """
        Calculate dynamic Kelly fraction adjusted for market conditions.
        """
        # Base Kelly from historical performance
        base_kelly = self.calculate_kelly_fraction(
            self.win_rate, self.avg_win, self.avg_loss
        )
        
        # Adjust for signal confidence
        confidence_adjustment = signal_confidence * 0.5
        
        # Adjust for market entropy (lower entropy = higher confidence)
        entropy_adjustment = (1 - market_entropy) * 0.3
        
        # Combine adjustments
        dynamic_kelly = base_kelly * (1 + confidence_adjustment + entropy_adjustment)
        
        # Ensure reasonable bounds
        dynamic_kelly = max(0, min(dynamic_kelly, 0.25))
        
        return dynamic_kelly
    
    async def calculate_position_size(self, symbol: str, entry_price: float,
                                    stop_loss: float, signal_confidence: float = 0.5,
                                    market_entropy: float = 0.5) -> float:
        """
        Calculate optimal position size using dynamic Kelly.
        """
        if not self.enabled:
            # Use fixed percentage if Kelly disabled
            return self.available_capital * 0.02 / entry_price
        
        # Calculate dynamic Kelly
        kelly_fraction = self.calculate_dynamic_kelly(signal_confidence, market_entropy)
        
        # Calculate risk per share
        risk_per_share = abs(entry_price - stop_loss)
        
        if risk_per_share == 0:
            return 0.0
        
        # Calculate position size based on Kelly
        risk_amount = self.available_capital * kelly_fraction
        position_size = risk_amount / risk_per_share
        
        # Ensure position doesn't exceed max risk per trade
        max_risk_amount = self.available_capital * self.max_risk_per_trade
        if risk_amount > max_risk_amount:
            risk_amount = max_risk_amount
            position_size = risk_amount / risk_per_share
        
        # Check global risk limit
        if self.total_risk + risk_amount > self.available_capital * self.global_risk_limit:
            # Reduce position size to fit within global limit
            remaining_risk = (self.available_capital * self.global_risk_limit) - self.total_risk
            position_size = remaining_risk / risk_per_share
        
        # Check position limit
        if len(self.positions) >= self.max_positions:
            return 0.0
        
        return position_size
    
    async def open_position(self, symbol: str, side: str, entry_price: float,
                          stop_loss: float, take_profit: float,
                          signal_confidence: float = 0.5,
                          market_entropy: float = 0.5) -> Optional[Position]:
        """Open a new position with optimal sizing."""
        # Calculate position size
        size = await self.calculate_position_size(
            symbol, entry_price, stop_loss, signal_confidence, market_entropy
        )
        
        if size <= 0:
            self.logger.warning(f"Cannot open position for {symbol} - size too small")
            return None
        
        # Calculate position metrics
        value = size * entry_price
        risk_amount = abs(entry_price - stop_loss) * size
        kelly_fraction = risk_amount / self.available_capital
        
        # Create position
        position_id = f"pos_{int(datetime.now().timestamp() * 1000)}"
        position = Position(
            position_id=position_id,
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            current_price=entry_price,
            size=size,
            value=value,
            stop_loss=stop_loss,
            take_profit=take_profit,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            kelly_fraction=kelly_fraction,
            risk_amount=risk_amount,
            open_time=datetime.now()
        )
        
        # Update state
        self.positions[position_id] = position
        self.total_exposure += value
        self.total_risk += risk_amount
        self.available_capital -= value
        
        self.logger.info(
            f"Opened position {position_id}: {size:.4f} {symbol} @ {entry_price:.2f} "
            f"(Kelly: {kelly_fraction:.2%}, Risk: {risk_amount:.2f})"
        )
        
        return position
    
    async def close_position(self, position_id: str, exit_price: float) -> Optional[float]:
        """Close a position and return P&L."""
        if position_id not in self.positions:
            return None
        
        position = self.positions[position_id]
        
        # Calculate P&L
        if position.side == 'long':
            pnl = (exit_price - position.entry_price) * position.size
        else:
            pnl = (position.entry_price - exit_price) * position.size
        
        position.realized_pnl = pnl
        position.current_price = exit_price
        position.close_time = datetime.now()
        position.status = "closed"
        
        # Update state
        self.total_exposure -= position.value
        self.total_risk -= position.risk_amount
        self.available_capital += position.value + pnl
        self.account_balance += pnl
        
        # Add to trade history
        self.trade_history.append({
            'pnl': pnl,
            'entry_price': position.entry_price,
            'exit_price': exit_price,
            'size': position.size,
            'duration': (position.close_time - position.open_time).total_seconds(),
            'kelly_fraction': position.kelly_fraction
        })
        
        self.recent_trades.append(pnl)
        
        # Update performance metrics
        await self._update_performance_metrics()
        
        # Remove from positions
        del self.positions[position_id]
        
        self.logger.info(
            f"Closed position {position_id}: P&L ${pnl:.2f} "
            f"({pnl/position.value*100:.2f}%)"
        )
        
        return pnl
    
    async def _update_performance_metrics(self):
        """Update win rate and average win/loss."""
        if len(self.trade_history) < 10:
            return
        
        trades = list(self.trade_history)
        wins = [t for t in trades if t['pnl'] > 0]
        losses = [t for t in trades if t['pnl'] < 0]
        
        self.win_rate = len(wins) / len(trades)
        
        if wins:
            self.avg_win = sum(t['pnl'] for t in wins) / len(wins)
        
        if losses:
            self.avg_loss = abs(sum(t['pnl'] for t in losses)) / len(losses)
        
        if self.avg_loss > 0:
            self.payoff_ratio = self.avg_win / self.avg_loss
    
    async def update_position_prices(self, current_prices: Dict[str, float]):
        """Update current prices for all positions."""
        for position_id, position in self.positions.items():
            if position.symbol in current_prices:
                position.current_price = current_prices[position.symbol]
                
                # Update unrealized P&L
                if position.side == 'long':
                    position.unrealized_pnl = (position.current_price - position.entry_price) * position.size
                else:
                    position.unrealized_pnl = (position.entry_price - position.current_price) * position.size
    
    async def get_position_count(self) -> int:
        """Get number of open positions."""
        return len(self.positions)
    
    async def liquidate_all(self):
        """Liquidate all positions (emergency)."""
        self.logger.critical("LIQUIDATING ALL POSITIONS")
        
        position_ids = list(self.positions.keys())
        for position_id in position_ids:
            position = self.positions[position_id]
            await self.close_position(position_id, position.current_price)
    
    async def get_risk_metrics(self) -> Dict[str, Any]:
        """Get current risk metrics."""
        total_unrealized_pnl = sum(p.unrealized_pnl for p in self.positions.values())
        
        return {
            'account_balance': self.account_balance,
            'available_capital': self.available_capital,
            'total_exposure': self.total_exposure,
            'total_risk': self.total_risk,
            'risk_percent': self.total_risk / self.account_balance if self.account_balance > 0 else 0,
            'open_positions': len(self.positions),
            'total_unrealized_pnl': total_unrealized_pnl,
            'win_rate': self.win_rate,
            'payoff_ratio': self.payoff_ratio
        }
    
    async def shutdown(self):
        """Shutdown the Kelly allocator."""
        self.logger.info("Kelly Allocator shutdown complete")
