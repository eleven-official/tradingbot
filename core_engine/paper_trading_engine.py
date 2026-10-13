"""
Production Paper Trading System with Real Market Data Feeds
Implements realistic paper trading with live market data
"""
import asyncio
import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from decimal import Decimal

from core_engine.execution_cost_model import (
    Order, OrderType, OrderSide, Fill, RealisticExecutionSimulator,
    TransactionCostModel
)
from core_engine.academic_strategies import StrategyLibrary, StrategySignal


class OrderStatus(Enum):
    """Order status."""
    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class PositionStatus(Enum):
    """Position status."""
    OPEN = "open"
    CLOSED = "closed"


@dataclass
class Position:
    """Trading position."""
    symbol: str
    side: str  # 'LONG' or 'SHORT'
    entry_price: float
    quantity: float
    stop_loss: float
    take_profit: float
    entry_time: datetime
    status: PositionStatus = PositionStatus.OPEN
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0


@dataclass
class PaperTrade:
    """Completed paper trade."""
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    quantity: float
    entry_time: datetime
    exit_time: datetime
    pnl: float
    pnl_percent: float
    commission: float
    slippage_bps: float
    holding_period: timedelta


@dataclass
class PaperTradingAccount:
    """Paper trading account."""
    initial_balance: float
    current_balance: float
    available_balance: float
    unrealized_pnl: float
    realized_pnl: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    max_drawdown: float
    max_profit: float


class PaperTradingEngine:
    """
    Production paper trading engine with real market data feeds.
    Simulates realistic trading without real money.
    """
    
    def __init__(self, config: Dict[str, any]):
        self.config = config
        self.initial_balance = config.get('initial_balance', 100000.0)
        self.current_balance = self.initial_balance
        self.available_balance = self.initial_balance
        
        # Execution simulator
        transaction_config = TransactionCostModel(
            maker_fee_bps=config.get('maker_fee_bps', 0.02),
            taker_fee_bps=config.get('taker_fee_bps', 0.04),
            base_slippage_bps=config.get('base_slippage_bps', 1.0),
            stress_multiplier=config.get('cost_stress_multiplier', 1.0),
            random_seed=config.get('execution_random_seed')
        )
        self.execution_simulator = RealisticExecutionSimulator(transaction_config)
        
        # Strategy library
        self.strategy_library = StrategyLibrary()
        
        # State
        self.positions: Dict[str, Position] = {}
        self.pending_orders: List[Order] = []
        self.trade_history: List[PaperTrade] = []
        self.is_running = False
        
        # Market data
        self.market_data: Dict[str, Dict] = {}
        self.orderbook_data: Dict[str, Dict] = {}
        
        # Performance tracking
        self.equity_curve: List[Tuple[datetime, float]] = []
        self.daily_returns: List[float] = []
        
        self.logger = logging.getLogger(__name__)
    
    async def initialize(self):
        """Initialize the paper trading engine."""
        self.logger.info("Initializing Paper Trading Engine")
        self.is_running = True
        self.logger.info(f"Paper Trading Engine initialized with ${self.initial_balance}")
    
    async def update_market_data(self, symbol: str, market_data: Dict):
        """Update market data for a symbol."""
        self.market_data[symbol] = market_data
        
        # Update unrealized PnL for open positions
        if symbol in self.positions:
            await self._update_position_pnl(symbol, market_data['close'])
    
    async def update_orderbook(self, symbol: str, orderbook: Dict):
        """Update orderbook data for a symbol."""
        self.orderbook_data[symbol] = orderbook
    
    async def process_signal(self, signal: StrategySignal) -> Optional[Fill]:
        """Process a trading signal."""
        self.logger.info(f"Processing signal: {signal.action} {signal.symbol} @ {signal.entry_price}")

        if signal.action not in {"BUY", "SELL"} or signal.position_size <= 0:
            return None
        if not signal.symbol or not isinstance(signal.symbol, str):
            self.logger.warning("Rejecting signal with invalid instrument identity")
            return None
        
        # Check if we have an existing position
        if signal.symbol in self.positions:
            existing_position = self.positions[signal.symbol]
            
            # Check if signal is opposite to existing position
            if (existing_position.side == 'LONG' and signal.action == 'SELL') or \
               (existing_position.side == 'SHORT' and signal.action == 'BUY'):
                # Close existing position
                await self.close_position(signal.symbol, signal.entry_price)
                return None
        
        # Check if we have enough balance
        required_margin = signal.entry_price * signal.position_size
        if required_margin > self.available_balance:
            self.logger.warning(f"Insufficient balance for {signal.symbol}")
            return None
        
        # Create order
        order = Order(
            symbol=signal.symbol,
            side=OrderSide.BUY if signal.action == 'BUY' else OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=signal.position_size,
            timestamp=datetime.now()
        )
        
        # Simulate execution
        fill = await self._execute_order(order, signal.entry_price)
        
        if fill and fill.filled_quantity > 0:
            # Create position
            position = Position(
                symbol=signal.symbol,
                side='LONG' if signal.action == 'BUY' else 'SHORT',
                entry_price=fill.fill_price,
                quantity=fill.filled_quantity,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                entry_time=datetime.now()
            )
            
            self.positions[signal.symbol] = position
            self.available_balance -= fill.total_cost
            
            self.logger.info(f"Position opened: {signal.symbol} {position.side} @ {fill.fill_price}")
        
        return fill
    
    async def _execute_order(self, order: Order, execution_price: float) -> Optional[Fill]:
        """Execute an order with realistic simulation."""
        symbol = order.symbol
        
        market_data = self.market_data.get(symbol, {})
        orderbook = self.orderbook_data.get(symbol, {})

        if not market_data:
            self.logger.warning("Rejecting %s: no market data for %s", order.side.value, symbol)
            return None
        if execution_price <= 0:
            self.logger.warning("Rejecting %s: invalid reference price for %s", order.side.value, symbol)
            return None
        if not any(market_data.get(key, 0) > 0 for key in ("bid", "ask", "close")):
            self.logger.warning("Rejecting %s: market data has no executable quote for %s", order.side.value, symbol)
            return None
        
        # Add volatility to market data if not present
        if 'volatility' not in market_data:
            market_data['volatility'] = 0.02  # Default 2% daily volatility
        
        # Simulate execution
        fill = self.execution_simulator.simulate_execution(order, market_data, orderbook)
        
        return fill
    
    async def _update_position_pnl(self, symbol: str, current_price: float):
        """Update unrealized PnL for a position."""
        if symbol not in self.positions:
            return
        
        position = self.positions[symbol]
        
        if position.side == 'LONG':
            position.unrealized_pnl = (current_price - position.entry_price) * position.quantity
        else:
            position.unrealized_pnl = (position.entry_price - current_price) * position.quantity
        
        # Check stop loss and take profit
        if position.side == 'LONG':
            if current_price <= position.stop_loss or current_price >= position.take_profit:
                await self.close_position(symbol, current_price)
        else:
            if current_price >= position.stop_loss or current_price <= position.take_profit:
                await self.close_position(symbol, current_price)
    
    async def close_position(self, symbol: str, exit_price: float) -> Optional[PaperTrade]:
        """Close a position."""
        if symbol not in self.positions:
            return None
        
        position = self.positions[symbol]
        
        # Create closing order
        order = Order(
            symbol=symbol,
            side=OrderSide.SELL if position.side == 'LONG' else OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=position.quantity,
            timestamp=datetime.now()
        )
        
        # Simulate execution
        fill = await self._execute_order(order, exit_price)
        
        if fill:
            # Calculate PnL
            if position.side == 'LONG':
                pnl = (fill.fill_price - position.entry_price) * position.quantity
            else:
                pnl = (position.entry_price - fill.fill_price) * position.quantity
            
            pnl_percent = pnl / (position.entry_price * position.quantity) * 100
            
            # Create trade record
            trade = PaperTrade(
                symbol=symbol,
                side=position.side,
                entry_price=position.entry_price,
                exit_price=fill.fill_price,
                quantity=position.quantity,
                entry_time=position.entry_time,
                exit_time=datetime.now(),
                pnl=pnl,
                pnl_percent=pnl_percent,
                commission=fill.commission,
                slippage_bps=fill.slippage_bps,
                holding_period=datetime.now() - position.entry_time
            )
            
            self.trade_history.append(trade)
            self.current_balance += pnl - fill.commission
            self.available_balance += (fill.fill_price * position.quantity) - fill.commission
            
            # Update position status
            position.status = PositionStatus.CLOSED
            position.realized_pnl = pnl
            
            # Remove from open positions
            del self.positions[symbol]
            
            self.logger.info(f"Position closed: {symbol} PnL: ${pnl:.2f} ({pnl_percent:.2f}%)")
            
            return trade
        
        return None
    
    async def run_strategy(self, strategy_name: str, symbol: str,
                         data: pd.DataFrame) -> List[Fill]:
        """Run a strategy on data and execute signals."""
        strategy = self.strategy_library.get_strategy(strategy_name)
        
        if not strategy:
            self.logger.error(f"Strategy {strategy_name} not found")
            return []
        
        if not symbol or data.empty:
            return []
        data = data.copy()
        data.attrs["symbol"] = symbol
        latest = data.iloc[-1]
        await self.update_market_data(symbol, {
            "open": float(latest.get("open", latest["close"])),
            "high": float(latest.get("high", latest["close"])),
            "low": float(latest.get("low", latest["close"])),
            "close": float(latest["close"]),
            "volume": float(latest.get("volume", 0) or 0),
        })

        # Generate signals
        signals = strategy.generate_signals(data)
        
        fills = []
        for signal in signals:
            fill = await self.process_signal(signal)
            if fill:
                fills.append(fill)
        
        return fills
    
    def get_account_summary(self) -> PaperTradingAccount:
        """Get account summary."""
        realized_pnl = sum(trade.pnl for trade in self.trade_history)
        unrealized_pnl = sum(pos.unrealized_pnl for pos in self.positions.values())
        
        winning_trades = sum(1 for trade in self.trade_history if trade.pnl > 0)
        losing_trades = sum(1 for trade in self.trade_history if trade.pnl < 0)
        total_trades = len(self.trade_history)
        
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        # Calculate max drawdown
        if len(self.equity_curve) > 1:
            equity_values = [e[1] for e in self.equity_curve]
            peak = np.maximum.accumulate(equity_values)
            drawdown = (equity_values - peak) / peak
            max_drawdown = drawdown.min()
        else:
            max_drawdown = 0
        
        max_profit = max((e[1] - self.initial_balance) / self.initial_balance for e in self.equity_curve) if self.equity_curve else 0
        
        return PaperTradingAccount(
            initial_balance=self.initial_balance,
            current_balance=self.current_balance,
            available_balance=self.available_balance,
            unrealized_pnl=unrealized_pnl,
            realized_pnl=realized_pnl,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            max_drawdown=max_drawdown,
            max_profit=max_profit
        )
    
    def get_performance_metrics(self) -> Dict[str, float]:
        """Calculate performance metrics."""
        if not self.trade_history:
            return {}
        
        returns = [trade.pnl_percent / 100 for trade in self.trade_history]
        returns_series = pd.Series(returns)
        
        metrics = {}
        
        # Basic metrics
        metrics['total_return'] = (self.current_balance - self.initial_balance) / self.initial_balance
        metrics['total_trades'] = len(self.trade_history)
        metrics['win_rate'] = sum(1 for t in self.trade_history if t.pnl > 0) / len(self.trade_history)
        
        # Risk-adjusted metrics
        if len(returns) > 1:
            metrics['sharpe_ratio'] = returns_series.mean() / returns_series.std() * np.sqrt(252) if returns_series.std() > 0 else 0
            metrics['sortino_ratio'] = returns_series.mean() / returns_series[returns_series < 0].std() * np.sqrt(252) if len(returns_series[returns_series < 0]) > 0 else 0
        
        # Drawdown
        if len(self.equity_curve) > 1:
            equity_values = [e[1] for e in self.equity_curve]
            peak = np.maximum.accumulate(equity_values)
            drawdown = (equity_values - peak) / peak
            metrics['max_drawdown'] = drawdown.min()
        
        # Trade metrics
        metrics['avg_win'] = np.mean([t.pnl for t in self.trade_history if t.pnl > 0]) if any(t.pnl > 0 for t in self.trade_history) else 0
        metrics['avg_loss'] = np.mean([t.pnl for t in self.trade_history if t.pnl < 0]) if any(t.pnl < 0 for t in self.trade_history) else 0
        metrics['profit_factor'] = abs(sum(t.pnl for t in self.trade_history if t.pnl > 0) / sum(t.pnl for t in self.trade_history if t.pnl < 0)) if any(t.pnl < 0 for t in self.trade_history) else 0
        
        # Slippage
        metrics['avg_slippage_bps'] = np.mean([t.slippage_bps for t in self.trade_history])
        
        return metrics
    
    async def update_equity_curve(self):
        """Update equity curve."""
        total_value = self.current_balance + sum(pos.unrealized_pnl for pos in self.positions.values())
        self.equity_curve.append((datetime.now(), total_value))
    
    async def shutdown(self):
        """Shutdown the paper trading engine."""
        self.is_running = False
        
        # Close all open positions
        for symbol in list(self.positions.keys()):
            if symbol in self.market_data:
                await self.close_position(symbol, self.market_data[symbol]['close'])
        
        self.logger.info("Paper Trading Engine shutdown complete")
    
    def export_trades(self, output_path: str):
        """Export trade history to CSV."""
        if not self.trade_history:
            return
        
        trades_data = []
        for trade in self.trade_history:
            trades_data.append({
                'symbol': trade.symbol,
                'side': trade.side,
                'entry_price': trade.entry_price,
                'exit_price': trade.exit_price,
                'quantity': trade.quantity,
                'entry_time': trade.entry_time,
                'exit_time': trade.exit_time,
                'pnl': trade.pnl,
                'pnl_percent': trade.pnl_percent,
                'commission': trade.commission,
                'slippage_bps': trade.slippage_bps,
                'holding_period_hours': trade.holding_period.total_seconds() / 3600
            })
        
        df = pd.DataFrame(trades_data)
        df.to_csv(output_path, index=False)
        self.logger.info(f"Exported {len(trades_data)} trades to {output_path}")


class LivePaperTradingServer:
    """
    Live paper trading server that connects to real market data feeds.
    """
    
    def __init__(self, config: Dict[str, any]):
        self.config = config
        self.paper_engine = PaperTradingEngine(config)
        self.is_running = False
        
        # Market data feed (will be connected to real exchange)
        self.market_feed = None
        
        self.logger = logging.getLogger(__name__)
    
    async def initialize(self):
        """Initialize the live paper trading server."""
        await self.paper_engine.initialize()
        self.is_running = True
        self.logger.info("Live Paper Trading Server initialized")
    
    async def start(self):
        """Start the live paper trading server."""
        self.logger.info("Starting Live Paper Trading Server")
        
        # Connect to market data feed
        await self._connect_market_feed()
        
        # Main trading loop
        while self.is_running:
            await self._trading_loop()
            await asyncio.sleep(1)  # 1-second updates
    
    async def _connect_market_feed(self):
        """Connect to real market data feed."""
        # This would connect to real exchange websockets
        # For now, simulate with placeholder
        self.logger.info("Market feed connected (simulated)")
    
    async def _trading_loop(self):
        """Main trading loop."""
        # In production, this would:
        # 1. Fetch latest market data
        # 2. Update engine with new data
        # 3. Run strategies
        # 4. Execute signals
        # 5. Update equity curve
        
        await self.paper_engine.update_equity_curve()
    
    async def stop(self):
        """Stop the live paper trading server."""
        self.is_running = False
        await self.paper_engine.shutdown()
        self.logger.info("Live Paper Trading Server stopped")
