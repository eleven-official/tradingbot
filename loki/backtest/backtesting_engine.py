"""
Loki Comprehensive Backtesting Engine
Walk-forward analysis, Monte Carlo simulation, realistic execution modeling
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class OrderType(Enum):
    """Order types"""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderSide(Enum):
    """Order side"""

    BUY = "buy"
    SELL = "sell"


@dataclass
class Order:
    """Trading order"""

    id: str
    timestamp: datetime
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    filled: bool = False
    fill_price: Optional[float] = None
    fill_timestamp: Optional[datetime] = None
    commission: float = 0.0
    slippage: float = 0.0


@dataclass
class Position:
    """Open position"""

    symbol: str
    quantity: float
    entry_price: float
    entry_timestamp: datetime
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0


@dataclass
class Trade:
    """Completed trade"""

    symbol: str
    entry_timestamp: datetime
    exit_timestamp: datetime
    entry_price: float
    exit_price: float
    quantity: float
    side: OrderSide
    pnl: float
    pnl_percent: float
    commission: float
    slippage: float
    duration: timedelta
    mae: float = 0.0  # Maximum Adverse Excursion
    mfe: float = 0.0  # Maximum Favorable Excursion


@dataclass
class BacktestResult:
    """Complete backtest results"""

    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float
    total_return: float
    total_return_pct: float

    # Trade statistics
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float

    # P&L metrics
    gross_profit: float
    gross_loss: float
    profit_factor: float
    average_win: float
    average_loss: float
    largest_win: float
    largest_loss: float

    # Risk metrics
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown: float
    max_drawdown_duration: timedelta

    # Execution metrics
    total_commission: float
    total_slippage: float

    # Time series data
    equity_curve: pd.Series = field(default_factory=pd.Series)
    drawdown_series: pd.Series = field(default_factory=pd.Series)
    trades: List[Trade] = field(default_factory=list)


class ExecutionModel:
    """Realistic execution modeling with slippage and commission"""

    def __init__(
        self,
        commission_pct: float = 0.001,  # 0.1% commission
        slippage_pct: float = 0.0005,  # 0.05% slippage
        use_realistic_fills: bool = True,
    ):
        self.commission_pct = commission_pct
        self.slippage_pct = slippage_pct
        self.use_realistic_fills = use_realistic_fills

    def execute_order(
        self, order: Order, current_price: float, bar_high: float, bar_low: float
    ) -> Tuple[bool, float, float, float]:
        """
        Execute order with realistic fills

        Returns:
            (filled, fill_price, commission, slippage)
        """
        filled = False
        fill_price = 0.0
        commission = 0.0
        slippage = 0.0

        if order.order_type == OrderType.MARKET:
            # Market orders always fill
            filled = True

            # Add slippage
            if order.side == OrderSide.BUY:
                slippage_amount = current_price * self.slippage_pct
                fill_price = current_price + slippage_amount
            else:
                slippage_amount = current_price * self.slippage_pct
                fill_price = current_price - slippage_amount

            slippage = abs(fill_price - current_price) * order.quantity

        elif order.order_type == OrderType.LIMIT:
            # Limit orders only fill if price reaches limit
            if order.side == OrderSide.BUY:
                if bar_low <= order.price:
                    filled = True
                    fill_price = min(order.price, current_price)
            else:
                if bar_high >= order.price:
                    filled = True
                    fill_price = max(order.price, current_price)

        elif order.order_type == OrderType.STOP:
            # Stop orders trigger when price hits stop
            if order.side == OrderSide.BUY:
                if bar_high >= order.stop_price:
                    filled = True
                    fill_price = max(order.stop_price, current_price)
                    slippage = (fill_price - order.stop_price) * order.quantity
            else:
                if bar_low <= order.stop_price:
                    filled = True
                    fill_price = min(order.stop_price, current_price)
                    slippage = (order.stop_price - fill_price) * order.quantity

        # Calculate commission
        if filled:
            commission = fill_price * order.quantity * self.commission_pct

        return filled, fill_price, commission, slippage


class BacktestingEngine:
    """
    Comprehensive backtesting engine with:
    - Realistic execution modeling
    - Walk-forward analysis
    - Monte Carlo simulation
    - Multiple strategy support
    - Detailed performance metrics
    """

    def __init__(
        self,
        initial_capital: float = 100000.0,
        commission_pct: float = 0.001,
        slippage_pct: float = 0.0005,
        use_realistic_fills: bool = True,
    ):
        self.initial_capital = initial_capital
        self.capital = initial_capital

        self.execution_model = ExecutionModel(commission_pct, slippage_pct, use_realistic_fills)

        self.positions: Dict[str, Position] = {}
        self.orders: List[Order] = []
        self.trades: List[Trade] = []

        self.equity_curve = []
        self.timestamps = []

        logger.info(f"💼 Backtesting Engine initialized with ${initial_capital:,.2f}")

    def run_backtest(
        self, data: pd.DataFrame, strategy_func: Callable, symbol: str = "SYMBOL"
    ) -> BacktestResult:
        """
        Run backtest on historical data

        Args:
            data: OHLCV DataFrame
            strategy_func: Function that takes (data, positions, capital) and returns orders
            symbol: Trading symbol

        Returns:
            BacktestResult with complete metrics
        """
        logger.info(f"🔄 Starting backtest for {symbol}")
        logger.info(f"   Data: {len(data)} bars from {data.index[0]} to {data.index[-1]}")

        # Reset state
        self.capital = self.initial_capital
        self.positions = {}
        self.orders = []
        self.trades = []
        self.equity_curve = []
        self.timestamps = []

        # Iterate through each bar
        for i in range(1, len(data)):
            current_bar = data.iloc[i]
            timestamp = data.index[i]

            # Get strategy signals
            lookback_data = data.iloc[: i + 1]
            new_orders = strategy_func(lookback_data, self.positions, self.capital)

            if new_orders:
                self.orders.extend(new_orders)

            # Process pending orders
            self._process_orders(
                timestamp, current_bar["close"], current_bar["high"], current_bar["low"]
            )

            # Update positions
            self._update_positions(current_bar["close"])

            # Calculate equity
            equity = self._calculate_equity()
            self.equity_curve.append(equity)
            self.timestamps.append(timestamp)

        # Close all positions at end
        self._close_all_positions(data.iloc[-1]["close"], data.index[-1])

        # Calculate final metrics
        result = self._calculate_metrics(data.index[0], data.index[-1])

        logger.info(f"✓ Backtest complete!")
        logger.info(f"   Final Capital: ${result.final_capital:,.2f}")
        logger.info(f"   Total Return: {result.total_return_pct:.2f}%")
        logger.info(f"   Win Rate: {result.win_rate:.1f}%")
        logger.info(f"   Sharpe Ratio: {result.sharpe_ratio:.2f}")

        return result

    def _process_orders(
        self, timestamp: datetime, current_price: float, bar_high: float, bar_low: float
    ):
        """Process all pending orders"""
        filled_orders = []

        for order in self.orders:
            if order.filled:
                continue

            # Try to execute
            filled, fill_price, commission, slippage = self.execution_model.execute_order(
                order, current_price, bar_high, bar_low
            )

            if filled:
                order.filled = True
                order.fill_price = fill_price
                order.fill_timestamp = timestamp
                order.commission = commission
                order.slippage = slippage

                # Update position
                self._update_position_from_order(order)

                filled_orders.append(order)

        # Remove filled orders
        self.orders = [o for o in self.orders if not o.filled]

    def _update_position_from_order(self, order: Order):
        """Update position based on filled order"""
        symbol = order.symbol

        if order.side == OrderSide.BUY:
            if symbol in self.positions:
                # Add to existing position
                pos = self.positions[symbol]
                total_cost = pos.entry_price * pos.quantity + order.fill_price * order.quantity
                total_quantity = pos.quantity + order.quantity
                pos.entry_price = total_cost / total_quantity
                pos.quantity = total_quantity
            else:
                # New position
                self.positions[symbol] = Position(
                    symbol=symbol,
                    quantity=order.quantity,
                    entry_price=order.fill_price,
                    entry_timestamp=order.fill_timestamp,
                    current_price=order.fill_price,
                )

            # Deduct cost from capital
            cost = order.fill_price * order.quantity + order.commission + order.slippage
            self.capital -= cost

        else:  # SELL
            if symbol in self.positions:
                pos = self.positions[symbol]

                # Close position (full or partial)
                quantity_to_close = min(order.quantity, pos.quantity)

                # Calculate P&L
                pnl = (order.fill_price - pos.entry_price) * quantity_to_close
                pnl -= order.commission + order.slippage

                # Record trade
                trade = Trade(
                    symbol=symbol,
                    entry_timestamp=pos.entry_timestamp,
                    exit_timestamp=order.fill_timestamp,
                    entry_price=pos.entry_price,
                    exit_price=order.fill_price,
                    quantity=quantity_to_close,
                    side=OrderSide.BUY,  # Original side
                    pnl=pnl,
                    pnl_percent=(order.fill_price / pos.entry_price - 1) * 100,
                    commission=order.commission,
                    slippage=order.slippage,
                    duration=order.fill_timestamp - pos.entry_timestamp,
                )
                self.trades.append(trade)

                # Update position
                pos.quantity -= quantity_to_close
                pos.realized_pnl += pnl

                # Add proceeds to capital
                proceeds = order.fill_price * quantity_to_close - order.commission - order.slippage
                self.capital += proceeds

                # Remove if fully closed
                if pos.quantity <= 0:
                    del self.positions[symbol]

    def _update_positions(self, current_price: float):
        """Update all positions with current price"""
        for pos in self.positions.values():
            pos.current_price = current_price
            pos.unrealized_pnl = (current_price - pos.entry_price) * pos.quantity

    def _calculate_equity(self) -> float:
        """Calculate current total equity"""
        equity = self.capital
        for pos in self.positions.values():
            equity += pos.current_price * pos.quantity
        return equity

    def _close_all_positions(self, final_price: float, timestamp: datetime):
        """Close all open positions at end of backtest"""
        for symbol, pos in list(self.positions.items()):
            # Create market sell order
            order = Order(
                id=f"close_{symbol}_{timestamp}",
                timestamp=timestamp,
                symbol=symbol,
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                quantity=pos.quantity,
                filled=True,
                fill_price=final_price,
                fill_timestamp=timestamp,
            )

            self._update_position_from_order(order)

    def _calculate_metrics(self, start_date: datetime, end_date: datetime) -> BacktestResult:
        """Calculate comprehensive backtest metrics"""

        # Basic metrics
        final_capital = self.equity_curve[-1] if self.equity_curve else self.initial_capital
        total_return = final_capital - self.initial_capital
        total_return_pct = (final_capital / self.initial_capital - 1) * 100

        # Trade statistics
        total_trades = len(self.trades)
        winning_trades = len([t for t in self.trades if t.pnl > 0])
        losing_trades = len([t for t in self.trades if t.pnl < 0])
        win_rate = winning_trades / total_trades * 100 if total_trades > 0 else 0

        # P&L metrics
        gross_profit = sum(t.pnl for t in self.trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in self.trades if t.pnl < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

        average_win = gross_profit / winning_trades if winning_trades > 0 else 0
        average_loss = gross_loss / losing_trades if losing_trades > 0 else 0

        largest_win = max([t.pnl for t in self.trades], default=0)
        largest_loss = min([t.pnl for t in self.trades], default=0)

        # Risk metrics
        equity_series = pd.Series(self.equity_curve, index=self.timestamps)
        returns = equity_series.pct_change().dropna()

        sharpe_ratio = self._calculate_sharpe_ratio(returns)
        sortino_ratio = self._calculate_sortino_ratio(returns)

        max_drawdown, max_dd_duration = self._calculate_max_drawdown(equity_series)

        calmar_ratio = total_return_pct / abs(max_drawdown) if max_drawdown != 0 else 0

        # Execution costs
        total_commission = sum(t.commission for t in self.trades)
        total_slippage = sum(t.slippage for t in self.trades)

        # Drawdown series
        running_max = equity_series.expanding().max()
        drawdown_series = (equity_series - running_max) / running_max * 100

        return BacktestResult(
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.initial_capital,
            final_capital=final_capital,
            total_return=total_return,
            total_return_pct=total_return_pct,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            profit_factor=profit_factor,
            average_win=average_win,
            average_loss=average_loss,
            largest_win=largest_win,
            largest_loss=largest_loss,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            max_drawdown=max_drawdown,
            max_drawdown_duration=max_dd_duration,
            total_commission=total_commission,
            total_slippage=total_slippage,
            equity_curve=equity_series,
            drawdown_series=drawdown_series,
            trades=self.trades,
        )

    def _calculate_sharpe_ratio(self, returns: pd.Series, risk_free_rate: float = 0.02) -> float:
        """Calculate Sharpe ratio"""
        if len(returns) == 0:
            return 0.0

        excess_returns = returns - risk_free_rate / 252  # Daily risk-free rate
        return (
            np.sqrt(252) * excess_returns.mean() / excess_returns.std()
            if excess_returns.std() > 0
            else 0.0
        )

    def _calculate_sortino_ratio(self, returns: pd.Series, risk_free_rate: float = 0.02) -> float:
        """Calculate Sortino ratio (downside deviation)"""
        if len(returns) == 0:
            return 0.0

        excess_returns = returns - risk_free_rate / 252
        downside_returns = returns[returns < 0]
        downside_std = downside_returns.std()

        return np.sqrt(252) * excess_returns.mean() / downside_std if downside_std > 0 else 0.0

    def _calculate_max_drawdown(self, equity: pd.Series) -> Tuple[float, timedelta]:
        """Calculate maximum drawdown and duration"""
        running_max = equity.expanding().max()
        drawdown = (equity - running_max) / running_max * 100

        max_dd = drawdown.min()

        # Calculate drawdown duration
        in_drawdown = drawdown < -0.1  # More than 0.1% drawdown
        if in_drawdown.sum() > 0:
            drawdown_periods = (in_drawdown != in_drawdown.shift()).cumsum()
            max_duration = drawdown_periods[in_drawdown].value_counts().max()
            # Approximate duration (assuming daily data)
            max_dd_duration = timedelta(days=int(max_duration))
        else:
            max_dd_duration = timedelta(days=0)

        return max_dd, max_dd_duration


def monte_carlo_simulation(
    backtest_result: BacktestResult, n_simulations: int = 1000, confidence_level: float = 0.95
) -> Dict:
    """
    Run Monte Carlo simulation on backtest results

    Args:
        backtest_result: Original backtest results
        n_simulations: Number of simulations to run
        confidence_level: Confidence level for intervals

    Returns:
        Dict with simulation results
    """
    logger.info(f"🎲 Running {n_simulations} Monte Carlo simulations...")

    # Extract trade returns
    trade_returns = [t.pnl_percent for t in backtest_result.trades]

    if len(trade_returns) == 0:
        return {"error": "No trades to simulate"}

    # Run simulations
    final_returns = []
    max_drawdowns = []

    for _ in range(n_simulations):
        # Randomly sample trades with replacement
        simulated_returns = np.random.choice(trade_returns, size=len(trade_returns), replace=True)

        # Calculate equity curve
        equity = [100]  # Start with 100
        for ret in simulated_returns:
            equity.append(equity[-1] * (1 + ret / 100))

        # Final return
        final_return = (equity[-1] / equity[0] - 1) * 100
        final_returns.append(final_return)

        # Max drawdown
        equity_series = pd.Series(equity)
        running_max = equity_series.expanding().max()
        drawdown = (equity_series - running_max) / running_max * 100
        max_drawdowns.append(drawdown.min())

    # Calculate statistics
    final_returns = np.array(final_returns)
    max_drawdowns = np.array(max_drawdowns)

    alpha = 1 - confidence_level

    results = {
        "n_simulations": n_simulations,
        "confidence_level": confidence_level,
        "final_return": {
            "mean": float(np.mean(final_returns)),
            "median": float(np.median(final_returns)),
            "std": float(np.std(final_returns)),
            "min": float(np.min(final_returns)),
            "max": float(np.max(final_returns)),
            "confidence_interval": (
                float(np.percentile(final_returns, alpha / 2 * 100)),
                float(np.percentile(final_returns, (1 - alpha / 2) * 100)),
            ),
        },
        "max_drawdown": {
            "mean": float(np.mean(max_drawdowns)),
            "median": float(np.median(max_drawdowns)),
            "worst_case": float(np.min(max_drawdowns)),
            "confidence_interval": (
                float(np.percentile(max_drawdowns, alpha / 2 * 100)),
                float(np.percentile(max_drawdowns, (1 - alpha / 2) * 100)),
            ),
        },
    }

    logger.info(f"✓ Monte Carlo complete!")
    logger.info(
        f"   Expected Return: {results['final_return']['mean']:.2f}% ± {results['final_return']['std']:.2f}%"
    )
    logger.info(
        f"   95% CI: [{results['final_return']['confidence_interval'][0]:.2f}%, {results['final_return']['confidence_interval'][1]:.2f}%]"
    )

    return results


# Example strategy for testing
def simple_ma_crossover_strategy(
    data: pd.DataFrame, positions: Dict, capital: float
) -> List[Order]:
    """Simple moving average crossover strategy"""
    orders = []

    if len(data) < 50:
        return orders

    # Calculate moving averages
    data["sma_20"] = data["close"].rolling(20).mean()
    data["sma_50"] = data["close"].rolling(50).mean()

    # Get current values
    current_sma_20 = data["sma_20"].iloc[-1]
    prev_sma_20 = data["sma_20"].iloc[-2]
    current_sma_50 = data["sma_50"].iloc[-1]
    prev_sma_50 = data["sma_50"].iloc[-2]

    current_price = data["close"].iloc[-1]
    timestamp = data.index[-1]

    # Bullish crossover - BUY
    if prev_sma_20 <= prev_sma_50 and current_sma_20 > current_sma_50:
        if "SYMBOL" not in positions and capital > current_price * 100:
            orders.append(
                Order(
                    id=f"buy_{timestamp}",
                    timestamp=timestamp,
                    symbol="SYMBOL",
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    quantity=100,
                )
            )

    # Bearish crossover - SELL
    elif prev_sma_20 >= prev_sma_50 and current_sma_20 < current_sma_50:
        if "SYMBOL" in positions:
            pos = positions["SYMBOL"]
            orders.append(
                Order(
                    id=f"sell_{timestamp}",
                    timestamp=timestamp,
                    symbol="SYMBOL",
                    side=OrderSide.SELL,
                    order_type=OrderType.MARKET,
                    quantity=pos.quantity,
                )
            )

    return orders
