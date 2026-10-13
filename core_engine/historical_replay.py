"""
Historical Replay Mode for Strategy Testing
Implements realistic backtesting with historical data replay
"""
import asyncio
import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from collections import deque

from core_engine.execution_cost_model import (
    Order, OrderType, OrderSide, Fill, RealisticExecutionSimulator,
    TransactionCostModel
)
from core_engine.academic_strategies import StrategyLibrary, StrategySignal
from core_engine.paper_trading_engine import PaperTrade, Position, PositionStatus


class ReplaySpeed(Enum):
    """Replay speed modes."""
    REAL_TIME = "real_time"
    FAST = "fast"
    ULTRA_FAST = "ultra_fast"
    INSTANT = "instant"


class ReplayEvent(Enum):
    """Replay event types."""
    MARKET_DATA = "market_data"
    ORDER_FILLED = "order_filled"
    SIGNAL_GENERATED = "signal_generated"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    ERROR = "error"


@dataclass
class ReplaySnapshot:
    """Snapshot of replay state at a point in time."""
    timestamp: datetime
    account_balance: float
    positions: Dict[str, Position]
    unrealized_pnl: float
    realized_pnl: float
    open_orders: List[Order]


@dataclass
class ReplayResult:
    """Replay backtest result."""
    strategy_name: str
    symbol: str
    start_date: datetime
    end_date: datetime
    initial_balance: float
    final_balance: float
    total_return: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    max_drawdown: float
    sharpe_ratio: float
    trades: List[PaperTrade]
    equity_curve: List[Tuple[datetime, float]]
    snapshots: List[ReplaySnapshot]


class HistoricalReplayEngine:
    """
    Historical data replay engine for realistic backtesting.
    Replays historical market data tick-by-tick or bar-by-bar.
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
        
        # Replay state
        self.positions: Dict[str, Position] = {}
        self.pending_orders: List[Order] = []
        self.trade_history: List[PaperTrade] = []
        self.equity_curve: List[Tuple[datetime, float]] = []
        self.snapshots: List[ReplaySnapshot] = []
        
        # Event callbacks
        self.event_callbacks: Dict[ReplayEvent, List[Callable]] = {}
        
        self.logger = logging.getLogger(__name__)
    
    def register_event_callback(self, event: ReplayEvent, callback: Callable):
        """Register a callback for a replay event."""
        if event not in self.event_callbacks:
            self.event_callbacks[event] = []
        self.event_callbacks[event].append(callback)
    
    def _trigger_event(self, event: ReplayEvent, data: any):
        """Trigger an event callback."""
        if event in self.event_callbacks:
            for callback in self.event_callbacks[event]:
                try:
                    callback(data)
                except Exception as e:
                    self.logger.error(f"Event callback error: {e}")
    
    async def replay(self, historical_data: pd.DataFrame,
                    strategy_name: str,
                    symbol: str,
                    speed: ReplaySpeed = ReplaySpeed.FAST,
                    progress_callback: Optional[Callable[[float], None]] = None) -> ReplayResult:
        """
        Replay historical data with a strategy.
        """
        self.logger.info(f"Starting replay for {symbol} with strategy {strategy_name}")

        self._validate_input_data(historical_data, symbol)
        
        # Reset state
        self._reset_state()
        
        # Get strategy
        strategy = self.strategy_library.get_strategy(strategy_name)
        if not strategy:
            raise ValueError(f"Strategy {strategy_name} not found")
        
        # Determine replay speed
        delay_ms = self._get_replay_delay(speed)
        
        # Replay data. Signals are generated after a bar closes and are
        # executed at the next bar's open. Filling on the signal bar's close
        # would introduce same-bar lookahead in OHLC backtests.
        total_bars = len(historical_data)
        pending_signals: List[StrategySignal] = []
        
        for i, (timestamp, row) in enumerate(historical_data.iterrows()):
            # Create market data snapshot
            market_data = {
                'timestamp': timestamp,
                'open': row['open'],
                'high': row['high'],
                'low': row['low'],
                'close': row['close'],
                'volume': row['volume'],
                'volatility': self._calculate_volatility(historical_data.iloc[:i+1])
            }
            
            # Trigger market data event
            self._trigger_event(ReplayEvent.MARKET_DATA, market_data)

            for signal in pending_signals:
                self._trigger_event(ReplayEvent.SIGNAL_GENERATED, signal)
                await self._process_signal(signal, market_data)
            pending_signals.clear()
            
            # Update positions
            if symbol in self.positions:
                await self._update_position_pnl(symbol, market_data['close'])
            
            # Generate signals if we have enough data
            if i >= strategy.params.get('lookback_period', 20):
                recent_data = historical_data.iloc[max(0, i-100):i+1].copy()
                # The time index is a timestamp, not an instrument identity.
                # Explicitly attach the symbol so strategies cannot silently
                # generate orders keyed by a datetime.
                recent_data.attrs["symbol"] = symbol
                signals = strategy.generate_signals(recent_data)
                pending_signals.extend(signals)
            
            # Update equity curve
            await self._update_equity_curve(timestamp)
            
            # Take snapshot periodically
            if i % 100 == 0:
                self._take_snapshot(timestamp)
            
            # Progress callback
            if progress_callback:
                progress = (i + 1) / total_bars
                progress_callback(progress)
            
            # Delay for replay speed
            if delay_ms > 0:
                await asyncio.sleep(delay_ms / 1000)
        
        # Close all positions at end
        if symbol in self.positions:
            final_price = historical_data.iloc[-1]['close']
            await self.close_position(symbol, final_price)
        
        # Calculate final metrics
        result = self._calculate_result(strategy_name, symbol, 
                                        historical_data.index[0],
                                        historical_data.index[-1])
        
        self.logger.info(f"Replay complete. Final balance: ${self.current_balance:.2f}")
        
        return result

    @staticmethod
    def _validate_input_data(historical_data: pd.DataFrame, symbol: str) -> None:
        """Fail closed on malformed or non-chronological replay data."""
        required = {"open", "high", "low", "close", "volume"}
        missing = required.difference(historical_data.columns)
        if missing:
            raise ValueError(f"Historical data is missing columns: {sorted(missing)}")
        if not symbol or not isinstance(symbol, str):
            raise ValueError("symbol must be a non-empty string")
        if historical_data.empty or len(historical_data) < 2:
            raise ValueError("Historical data must contain at least two bars")
        if not historical_data.index.is_monotonic_increasing:
            raise ValueError("Historical data must be sorted in ascending time order")
        values = historical_data[list(required)].to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values[:, :4] <= 0).any() or (values[:, 4] < 0).any():
            raise ValueError("Historical OHLCV data contains invalid values")
    
    def _reset_state(self):
        """Reset replay state."""
        self.current_balance = self.initial_balance
        self.available_balance = self.initial_balance
        self.positions.clear()
        self.pending_orders.clear()
        self.trade_history.clear()
        self.equity_curve.clear()
        self.snapshots.clear()
    
    def _get_replay_delay(self, speed: ReplaySpeed) -> float:
        """Get delay in milliseconds for replay speed."""
        delays = {
            ReplaySpeed.REAL_TIME: 1000,  # 1 second per bar
            ReplaySpeed.FAST: 100,  # 100ms per bar
            ReplaySpeed.ULTRA_FAST: 10,  # 10ms per bar
            ReplaySpeed.INSTANT: 0  # No delay
        }
        return delays.get(speed, 100)
    
    def _calculate_volatility(self, data: pd.DataFrame, period: int = 20) -> float:
        """Calculate rolling volatility."""
        if len(data) < period:
            return 0.02  # Default
        
        returns = data['close'].pct_change().dropna()
        return returns.tail(period).std() * np.sqrt(252)
    
    async def _process_signal(self, signal: StrategySignal, market_data: Dict):
        """Process a trading signal."""
        self.logger.info(f"Processing signal: {signal.action} {signal.symbol} @ {signal.entry_price}")
        
        # Check if we have an existing position
        if signal.symbol in self.positions:
            existing_position = self.positions[signal.symbol]
            
            # Check if signal is opposite to existing position
            if (existing_position.side == 'LONG' and signal.action == 'SELL') or \
               (existing_position.side == 'SHORT' and signal.action == 'BUY'):
                # Close existing position
                await self.close_position(signal.symbol, signal.entry_price)
                return
        
        # Check if we have enough balance
        required_margin = signal.entry_price * signal.position_size
        if required_margin > self.available_balance:
            self.logger.warning(f"Insufficient balance for {signal.symbol}")
            return
        
        # Create order
        order = Order(
            symbol=signal.symbol,
            side=OrderSide.BUY if signal.action == 'BUY' else OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=signal.position_size,
            timestamp=datetime.now()
        )
        
        # Simulate execution
        execution_price = float(market_data.get("open", market_data.get("close", signal.entry_price)))
        fill = await self._execute_order(order, execution_price, market_data)
        
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
            
            self._trigger_event(ReplayEvent.POSITION_OPENED, position)
            
            self.logger.info(f"Position opened: {signal.symbol} {position.side} @ {fill.fill_price}")
    
    async def _execute_order(self, order: Order, execution_price: float, 
                           market_data: Dict) -> Optional[Fill]:
        """Execute an order with realistic simulation."""
        # The simulator's market-data quote must represent the requested
        # execution bar/price, not the signal bar's close.
        execution_data = dict(market_data)
        execution_data["close"] = float(execution_price)
        execution_data["bid"] = float(execution_price) * 0.999
        execution_data["ask"] = float(execution_price) * 1.001
        orderbook = {
            'volume': market_data['volume'],
            'bid': execution_data['bid'],
            'ask': execution_data['ask']
        }
        
        fill = self.execution_simulator.simulate_execution(order, execution_data, orderbook)
        
        if fill:
            self._trigger_event(ReplayEvent.ORDER_FILLED, fill)
        
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
        
        market_data = {
            'close': exit_price,
            'volume': 1000000,
            'volatility': 0.02
        }
        
        # Simulate execution
        fill = await self._execute_order(order, exit_price, market_data)
        
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
            
            self._trigger_event(ReplayEvent.POSITION_CLOSED, trade)
            
            self.logger.info(f"Position closed: {symbol} PnL: ${pnl:.2f} ({pnl_percent:.2f}%)")
            
            return trade
        
        return None
    
    async def _update_equity_curve(self, timestamp: datetime):
        """Update equity curve."""
        total_value = self.current_balance + sum(pos.unrealized_pnl for pos in self.positions.values())
        self.equity_curve.append((timestamp, total_value))
    
    def _take_snapshot(self, timestamp: datetime):
        """Take a snapshot of current state."""
        snapshot = ReplaySnapshot(
            timestamp=timestamp,
            account_balance=self.current_balance,
            positions=self.positions.copy(),
            unrealized_pnl=sum(pos.unrealized_pnl for pos in self.positions.values()),
            realized_pnl=sum(trade.pnl for trade in self.trade_history),
            open_orders=self.pending_orders.copy()
        )
        self.snapshots.append(snapshot)
    
    def _calculate_result(self, strategy_name: str, symbol: str,
                         start_date: datetime, end_date: datetime) -> ReplayResult:
        """Calculate final replay result."""
        total_return = (self.current_balance - self.initial_balance) / self.initial_balance
        
        winning_trades = sum(1 for trade in self.trade_history if trade.pnl > 0)
        losing_trades = sum(1 for trade in self.trade_history if trade.pnl < 0)
        win_rate = winning_trades / len(self.trade_history) if self.trade_history else 0
        
        # Calculate max drawdown
        if len(self.equity_curve) > 1:
            equity_values = [e[1] for e in self.equity_curve]
            peak = np.maximum.accumulate(equity_values)
            drawdown = (equity_values - peak) / peak
            max_drawdown = drawdown.min()
        else:
            max_drawdown = 0
        
        # Calculate Sharpe ratio
        if len(self.equity_curve) > 1:
            returns = pd.Series([self.equity_curve[i][1] / self.equity_curve[i-1][1] - 1 
                                for i in range(1, len(self.equity_curve))])
            sharpe_ratio = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0
        else:
            sharpe_ratio = 0
        
        return ReplayResult(
            strategy_name=strategy_name,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            initial_balance=self.initial_balance,
            final_balance=self.current_balance,
            total_return=total_return,
            total_trades=len(self.trade_history),
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            trades=self.trade_history.copy(),
            equity_curve=self.equity_curve.copy(),
            snapshots=self.snapshots.copy()
        )


class MultiStrategyReplay:
    """
    Replay multiple strategies simultaneously for comparison.
    """
    
    def __init__(self, config: Dict[str, any]):
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    async def compare_strategies(self, historical_data: pd.DataFrame,
                                strategy_names: List[str],
                                symbol: str,
                                speed: ReplaySpeed = ReplaySpeed.ULTRA_FAST) -> Dict[str, ReplayResult]:
        """
        Compare multiple strategies on the same historical data.
        """
        results = {}
        
        for strategy_name in strategy_names:
            self.logger.info(f"Replaying strategy: {strategy_name}")
            
            engine = HistoricalReplayEngine(self.config)
            result = await engine.replay(historical_data, strategy_name, symbol, speed)
            results[strategy_name] = result
        
        return results
    
    def generate_comparison_report(self, results: Dict[str, ReplayResult]) -> str:
        """Generate a comparison report."""
        report = []
        report.append("=" * 80)
        report.append("STRATEGY COMPARISON REPORT")
        report.append("=" * 80)
        report.append("")
        
        # Summary table
        headers = ["Strategy", "Return", "Sharpe", "Max DD", "Win Rate", "Trades"]
        report.append(f"{headers[0]:<20} {headers[1]:<12} {headers[2]:<10} {headers[3]:<12} {headers[4]:<12} {headers[5]:<10}")
        report.append("-" * 80)
        
        for strategy_name, result in results.items():
            report.append(
                f"{strategy_name:<20} "
                f"{result.total_return:>10.2%} "
                f"{result.sharpe_ratio:>8.2f} "
                f"{result.max_drawdown:>10.2%} "
                f"{result.win_rate:>10.2%} "
                f"{result.total_trades:>8}"
            )
        
        report.append("")
        
        # Rankings
        report.append("RANKINGS")
        report.append("-" * 80)
        
        # Best return
        best_return = max(results.items(), key=lambda x: x[1].total_return)
        report.append(f"Best Return: {best_return[0]} ({best_return[1].total_return:.2%})")
        
        # Best Sharpe
        best_sharpe = max(results.items(), key=lambda x: x[1].sharpe_ratio)
        report.append(f"Best Sharpe: {best_sharpe[0]} ({best_sharpe[1].sharpe_ratio:.2f})")
        
        # Lowest drawdown
        lowest_dd = min(results.items(), key=lambda x: x[1].max_drawdown)
        report.append(f"Lowest Drawdown: {lowest_dd[0]} ({lowest_dd[1].max_drawdown:.2%})")
        
        report.append("")
        report.append("=" * 80)
        
        return "\n".join(report)
