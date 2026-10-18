"""
LOKI v7.0 - Comprehensive Performance Analytics Dashboard
Advanced metrics, visualizations, and trade analysis
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class TradeStatus(Enum):
    """Trade status"""

    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"


@dataclass
class Trade:
    """Individual trade record"""

    trade_id: str
    symbol: str
    entry_time: datetime
    entry_price: float
    quantity: float
    direction: str  # "long" or "short"
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    status: TradeStatus = TradeStatus.OPEN
    strategy: str = "unknown"
    pnl: float = 0.0
    pnl_percent: float = 0.0
    commission: float = 0.0
    slippage: float = 0.0
    tags: List[str] = field(default_factory=list)
    notes: str = ""

    @property
    def duration(self) -> Optional[timedelta]:
        """Trade duration"""
        if self.exit_time:
            return self.exit_time - self.entry_time
        return None

    @property
    def is_winner(self) -> bool:
        """Is trade profitable"""
        return self.pnl > 0

    def close_trade(self, exit_price: float, exit_time: datetime):
        """Close the trade"""
        self.exit_price = exit_price
        self.exit_time = exit_time
        self.status = TradeStatus.CLOSED

        # Calculate P&L
        if self.direction == "long":
            self.pnl = (exit_price - self.entry_price) * self.quantity
        else:  # short
            self.pnl = (self.entry_price - exit_price) * self.quantity

        self.pnl -= self.commission + self.slippage
        self.pnl_percent = (self.pnl / (self.entry_price * self.quantity)) * 100


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics"""

    # Returns
    total_pnl: float
    total_return_pct: float
    annualized_return: float
    monthly_return: float
    daily_return: float

    # Risk metrics
    volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown: float
    max_drawdown_duration: Optional[timedelta]

    # Trade statistics
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    largest_win: float
    largest_loss: float
    profit_factor: float

    # Risk/Reward
    avg_risk_reward: float
    expectancy: float

    # Timing
    avg_trade_duration: timedelta
    avg_winning_duration: timedelta
    avg_losing_duration: timedelta

    # Streaks
    max_consecutive_wins: int
    max_consecutive_losses: int
    current_streak: int
    current_streak_type: str  # "win" or "loss"

    # Advanced
    recovery_factor: float  # Net profit / Max drawdown
    kelly_criterion: float
    ulcer_index: float


@dataclass
class EquityCurve:
    """Equity curve data"""

    timestamps: List[datetime]
    equity_values: List[float]
    drawdown_series: List[float]
    returns_series: List[float]

    def to_dataframe(self) -> pd.DataFrame:
        """Convert to pandas DataFrame"""
        return pd.DataFrame(
            {
                "timestamp": self.timestamps,
                "equity": self.equity_values,
                "drawdown": self.drawdown_series,
                "returns": self.returns_series,
            }
        )


@dataclass
class TradeDistribution:
    """Trade distribution analysis"""

    pnl_bins: List[float]  # Bin edges
    pnl_counts: List[int]  # Count per bin
    duration_bins: List[str]  # Duration ranges
    duration_counts: List[int]  # Count per duration
    hourly_distribution: Dict[int, int]  # Hour -> count
    daily_distribution: Dict[str, int]  # Day name -> count
    monthly_pnl: Dict[str, float]  # Month -> total PnL


@dataclass
class StrategyComparison:
    """Compare performance across strategies"""

    strategy_metrics: Dict[str, Dict[str, float]]  # strategy -> metrics
    best_strategy: str
    worst_strategy: str
    consistency_scores: Dict[str, float]  # Lower variance = more consistent


class PerformanceAnalyzer:
    """
    Comprehensive performance analytics engine

    Features:
    - Real-time performance metrics
    - Equity curve tracking
    - Trade distribution analysis
    - Strategy comparison
    - Risk analysis
    - Detailed reporting
    """

    def __init__(self, initial_capital: float = 100000.0):
        """
        Initialize performance analyzer

        Args:
            initial_capital: Starting capital
        """
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.trades: List[Trade] = []
        self.equity_history: List[Tuple[datetime, float]] = [(datetime.now(), initial_capital)]

        logger.info(f"Performance Analyzer initialized with ${initial_capital:,.2f}")

    def add_trade(self, trade: Trade):
        """Add a trade to the analysis"""
        self.trades.append(trade)

        if trade.status == TradeStatus.CLOSED:
            self.current_capital += trade.pnl
            self.equity_history.append((trade.exit_time, self.current_capital))

        logger.debug(f"Added trade: {trade.symbol} {trade.direction} @ ${trade.entry_price:.2f}")

    def calculate_metrics(self) -> PerformanceMetrics:
        """
        Calculate comprehensive performance metrics

        Returns:
            PerformanceMetrics with all statistics
        """
        try:
            closed_trades = [t for t in self.trades if t.status == TradeStatus.CLOSED]

            if not closed_trades:
                logger.warning("No closed trades for metrics calculation")
                return self._empty_metrics()

            # Returns
            total_pnl = sum(t.pnl for t in closed_trades)
            total_return_pct = (total_pnl / self.initial_capital) * 100

            # Annualized return (assuming 252 trading days)
            if len(closed_trades) > 1:
                first_trade_date = closed_trades[0].exit_time
                last_trade_date = closed_trades[-1].exit_time
                days_elapsed = (last_trade_date - first_trade_date).days

                if days_elapsed > 0:
                    annualized_return = (
                        (1 + total_return_pct / 100) ** (365 / days_elapsed) - 1
                    ) * 100
                else:
                    annualized_return = 0.0
            else:
                annualized_return = 0.0

            # Calculate returns series for risk metrics
            returns = pd.Series([t.pnl_percent / 100 for t in closed_trades])

            # Risk metrics
            volatility = float(returns.std() * np.sqrt(252))  # Annualized

            # Sharpe ratio (assuming 2% risk-free rate)
            risk_free_rate = 0.02
            excess_returns = returns.mean() - (risk_free_rate / 252)
            sharpe_ratio = float(
                (excess_returns / returns.std() * np.sqrt(252)) if returns.std() > 0 else 0.0
            )

            # Sortino ratio (only downside deviation)
            downside_returns = returns[returns < 0]
            downside_std = downside_returns.std() if len(downside_returns) > 0 else returns.std()
            sortino_ratio = float(
                (excess_returns / downside_std * np.sqrt(252)) if downside_std > 0 else 0.0
            )

            # Maximum drawdown
            equity_curve = self._calculate_equity_curve()
            max_dd, max_dd_duration = self._calculate_max_drawdown(equity_curve)

            # Calmar ratio
            calmar_ratio = annualized_return / abs(max_dd * 100) if max_dd != 0 else 0.0

            # Trade statistics
            winning_trades = [t for t in closed_trades if t.is_winner]
            losing_trades = [t for t in closed_trades if not t.is_winner]

            total_trades = len(closed_trades)
            num_wins = len(winning_trades)
            num_losses = len(losing_trades)
            win_rate = (num_wins / total_trades * 100) if total_trades > 0 else 0.0

            avg_win = np.mean([t.pnl for t in winning_trades]) if winning_trades else 0.0
            avg_loss = np.mean([t.pnl for t in losing_trades]) if losing_trades else 0.0
            largest_win = max([t.pnl for t in winning_trades]) if winning_trades else 0.0
            largest_loss = min([t.pnl for t in losing_trades]) if losing_trades else 0.0

            # Profit factor
            gross_profit = sum(t.pnl for t in winning_trades)
            gross_loss = abs(sum(t.pnl for t in losing_trades))
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

            # Risk/Reward
            avg_risk_reward = abs(avg_win / avg_loss) if avg_loss != 0 else 0.0
            expectancy = (win_rate / 100 * avg_win) + ((100 - win_rate) / 100 * avg_loss)

            # Timing
            durations = [t.duration.total_seconds() for t in closed_trades if t.duration]
            avg_duration = timedelta(seconds=np.mean(durations)) if durations else timedelta(0)

            win_durations = [t.duration.total_seconds() for t in winning_trades if t.duration]
            avg_win_duration = (
                timedelta(seconds=np.mean(win_durations)) if win_durations else timedelta(0)
            )

            loss_durations = [t.duration.total_seconds() for t in losing_trades if t.duration]
            avg_loss_duration = (
                timedelta(seconds=np.mean(loss_durations)) if loss_durations else timedelta(0)
            )

            # Streaks
            max_cons_wins, max_cons_losses, current_streak, streak_type = self._calculate_streaks(
                closed_trades
            )

            # Advanced metrics
            recovery_factor = total_pnl / abs(max_dd * self.initial_capital) if max_dd != 0 else 0.0

            # Kelly Criterion
            if avg_loss != 0:
                kelly = (win_rate / 100) - ((100 - win_rate) / 100) / abs(avg_win / avg_loss)
            else:
                kelly = 0.0

            # Ulcer Index (measure of downside volatility)
            ulcer_index = self._calculate_ulcer_index(equity_curve)

            # Monthly/daily returns
            monthly_return = (annualized_return / 12) if annualized_return != 0 else 0.0
            daily_return = (annualized_return / 252) if annualized_return != 0 else 0.0

            metrics = PerformanceMetrics(
                total_pnl=total_pnl,
                total_return_pct=total_return_pct,
                annualized_return=annualized_return,
                monthly_return=monthly_return,
                daily_return=daily_return,
                volatility=volatility,
                sharpe_ratio=sharpe_ratio,
                sortino_ratio=sortino_ratio,
                calmar_ratio=calmar_ratio,
                max_drawdown=max_dd,
                max_drawdown_duration=max_dd_duration,
                total_trades=total_trades,
                winning_trades=num_wins,
                losing_trades=num_losses,
                win_rate=win_rate,
                avg_win=avg_win,
                avg_loss=avg_loss,
                largest_win=largest_win,
                largest_loss=largest_loss,
                profit_factor=profit_factor,
                avg_risk_reward=avg_risk_reward,
                expectancy=expectancy,
                avg_trade_duration=avg_duration,
                avg_winning_duration=avg_win_duration,
                avg_losing_duration=avg_loss_duration,
                max_consecutive_wins=max_cons_wins,
                max_consecutive_losses=max_cons_losses,
                current_streak=current_streak,
                current_streak_type=streak_type,
                recovery_factor=recovery_factor,
                kelly_criterion=kelly,
                ulcer_index=ulcer_index,
            )

            logger.info(
                f"Metrics calculated: {total_trades} trades, {win_rate:.1f}% win rate, {total_return_pct:+.2f}% return"
            )

            return metrics

        except Exception as e:
            logger.error(f"Metrics calculation failed: {e}")
            return self._empty_metrics()

    def get_equity_curve(self) -> EquityCurve:
        """
        Generate equity curve data

        Returns:
            EquityCurve with historical data
        """
        if len(self.equity_history) < 2:
            return EquityCurve([], [], [], [])

        timestamps = [t for t, _ in self.equity_history]
        equity_values = [v for _, v in self.equity_history]

        # Calculate drawdown series
        drawdown_series = []
        running_max = equity_values[0]

        for equity in equity_values:
            running_max = max(running_max, equity)
            drawdown = (equity - running_max) / running_max if running_max > 0 else 0
            drawdown_series.append(drawdown)

        # Calculate returns series
        returns_series = [0.0]  # First return is 0
        for i in range(1, len(equity_values)):
            ret = (
                (equity_values[i] - equity_values[i - 1]) / equity_values[i - 1]
                if equity_values[i - 1] > 0
                else 0
            )
            returns_series.append(ret)

        return EquityCurve(
            timestamps=timestamps,
            equity_values=equity_values,
            drawdown_series=drawdown_series,
            returns_series=returns_series,
        )

    def analyze_trade_distribution(self) -> TradeDistribution:
        """
        Analyze trade distribution patterns

        Returns:
            TradeDistribution with various distributions
        """
        closed_trades = [t for t in self.trades if t.status == TradeStatus.CLOSED]

        if not closed_trades:
            return TradeDistribution([], [], [], [], {}, {}, {})

        # P&L distribution (histogram)
        pnls = [t.pnl for t in closed_trades]
        pnl_counts, pnl_bins = np.histogram(pnls, bins=20)

        # Duration distribution
        durations = []
        for t in closed_trades:
            if t.duration:
                hours = t.duration.total_seconds() / 3600
                if hours < 1:
                    durations.append("< 1h")
                elif hours < 4:
                    durations.append("1-4h")
                elif hours < 24:
                    durations.append("4-24h")
                elif hours < 168:  # 1 week
                    durations.append("1-7d")
                else:
                    durations.append("> 7d")

        from collections import Counter

        duration_counter = Counter(durations)
        duration_bins = list(duration_counter.keys())
        duration_counts = list(duration_counter.values())

        # Hourly distribution
        hourly_dist = {}
        for t in closed_trades:
            if t.exit_time:
                hour = t.exit_time.hour
                hourly_dist[hour] = hourly_dist.get(hour, 0) + 1

        # Daily distribution
        daily_dist = {}
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for t in closed_trades:
            if t.exit_time:
                day_name = day_names[t.exit_time.weekday()]
                daily_dist[day_name] = daily_dist.get(day_name, 0) + 1

        # Monthly P&L
        monthly_pnl = {}
        for t in closed_trades:
            if t.exit_time:
                month_key = t.exit_time.strftime("%Y-%m")
                monthly_pnl[month_key] = monthly_pnl.get(month_key, 0.0) + t.pnl

        return TradeDistribution(
            pnl_bins=pnl_bins.tolist(),
            pnl_counts=pnl_counts.tolist(),
            duration_bins=duration_bins,
            duration_counts=duration_counts,
            hourly_distribution=hourly_dist,
            daily_distribution=daily_dist,
            monthly_pnl=monthly_pnl,
        )

    def compare_strategies(self) -> StrategyComparison:
        """
        Compare performance across different strategies

        Returns:
            StrategyComparison with metrics per strategy
        """
        closed_trades = [t for t in self.trades if t.status == TradeStatus.CLOSED]

        if not closed_trades:
            return StrategyComparison({}, "", "", {})

        # Group trades by strategy
        strategy_trades = {}
        for trade in closed_trades:
            if trade.strategy not in strategy_trades:
                strategy_trades[trade.strategy] = []
            strategy_trades[trade.strategy].append(trade)

        # Calculate metrics for each strategy
        strategy_metrics = {}
        consistency_scores = {}

        for strategy, trades in strategy_trades.items():
            total_pnl = sum(t.pnl for t in trades)
            num_trades = len(trades)
            num_wins = sum(1 for t in trades if t.is_winner)
            win_rate = (num_wins / num_trades * 100) if num_trades > 0 else 0.0

            winning = [t.pnl for t in trades if t.is_winner]
            losing = [t.pnl for t in trades if not t.is_winner]
            avg_win = np.mean(winning) if winning else 0.0
            avg_loss = np.mean(losing) if losing else 0.0

            profit_factor = (
                sum(winning) / abs(sum(losing)) if losing and sum(losing) != 0 else float("inf")
            )

            strategy_metrics[strategy] = {
                "total_pnl": total_pnl,
                "num_trades": num_trades,
                "win_rate": win_rate,
                "avg_win": avg_win,
                "avg_loss": avg_loss,
                "profit_factor": profit_factor,
            }

            # Consistency score (inverse of PnL standard deviation)
            pnl_std = np.std([t.pnl for t in trades])
            consistency_scores[strategy] = 1.0 / (pnl_std + 1) if pnl_std > 0 else 0.0

        # Find best and worst strategies
        best_strategy = max(strategy_metrics.keys(), key=lambda s: strategy_metrics[s]["total_pnl"])
        worst_strategy = min(
            strategy_metrics.keys(), key=lambda s: strategy_metrics[s]["total_pnl"]
        )

        return StrategyComparison(
            strategy_metrics=strategy_metrics,
            best_strategy=best_strategy,
            worst_strategy=worst_strategy,
            consistency_scores=consistency_scores,
        )

    def generate_report(self) -> str:
        """
        Generate comprehensive performance report

        Returns:
            Formatted report string
        """
        metrics = self.calculate_metrics()

        report = []
        report.append("=" * 80)
        report.append(" LOKI PERFORMANCE ANALYTICS REPORT")
        report.append("=" * 80)
        report.append("")

        # Overview
        report.append("OVERVIEW")
        report.append("-" * 80)
        report.append(f"Initial Capital:        ${self.initial_capital:>15,.2f}")
        report.append(f"Current Capital:        ${self.current_capital:>15,.2f}")
        report.append(f"Total P&L:              ${metrics.total_pnl:>15,.2f}")
        report.append(f"Total Return:           {metrics.total_return_pct:>15.2f}%")
        report.append(f"Annualized Return:      {metrics.annualized_return:>15.2f}%")
        report.append("")

        # Risk Metrics
        report.append("RISK METRICS")
        report.append("-" * 80)
        report.append(f"Volatility:             {metrics.volatility:>15.2f}%")
        report.append(f"Sharpe Ratio:           {metrics.sharpe_ratio:>15.2f}")
        report.append(f"Sortino Ratio:          {metrics.sortino_ratio:>15.2f}")
        report.append(f"Calmar Ratio:           {metrics.calmar_ratio:>15.2f}")
        report.append(f"Max Drawdown:           {metrics.max_drawdown:>15.2%}")
        report.append(f"Recovery Factor:        {metrics.recovery_factor:>15.2f}")
        report.append(f"Ulcer Index:            {metrics.ulcer_index:>15.2f}")
        report.append("")

        # Trade Statistics
        report.append("TRADE STATISTICS")
        report.append("-" * 80)
        report.append(f"Total Trades:           {metrics.total_trades:>15}")
        report.append(f"Winning Trades:         {metrics.winning_trades:>15}")
        report.append(f"Losing Trades:          {metrics.losing_trades:>15}")
        report.append(f"Win Rate:               {metrics.win_rate:>15.2f}%")
        report.append(f"Average Win:            ${metrics.avg_win:>15,.2f}")
        report.append(f"Average Loss:           ${metrics.avg_loss:>15,.2f}")
        report.append(f"Largest Win:            ${metrics.largest_win:>15,.2f}")
        report.append(f"Largest Loss:           ${metrics.largest_loss:>15,.2f}")
        report.append(f"Profit Factor:          {metrics.profit_factor:>15.2f}")
        report.append(f"Expectancy:             ${metrics.expectancy:>15,.2f}")
        report.append("")

        # Streaks
        report.append("STREAKS")
        report.append("-" * 80)
        report.append(f"Max Consecutive Wins:   {metrics.max_consecutive_wins:>15}")
        report.append(f"Max Consecutive Losses: {metrics.max_consecutive_losses:>15}")
        report.append(
            f"Current Streak:         {metrics.current_streak:>15} {metrics.current_streak_type}"
        )
        report.append("")

        # Timing
        report.append("TIMING ANALYSIS")
        report.append("-" * 80)
        report.append(f"Avg Trade Duration:     {str(metrics.avg_trade_duration):>15}")
        report.append(f"Avg Winning Duration:   {str(metrics.avg_winning_duration):>15}")
        report.append(f"Avg Losing Duration:    {str(metrics.avg_losing_duration):>15}")
        report.append("")

        report.append("=" * 80)

        return "\n".join(report)

    # Private helper methods

    def _calculate_equity_curve(self) -> pd.Series:
        """Calculate equity curve as pandas Series"""
        if not self.equity_history:
            return pd.Series()

        timestamps = [t for t, _ in self.equity_history]
        values = [v for _, v in self.equity_history]

        return pd.Series(values, index=timestamps)

    def _calculate_max_drawdown(self, equity_curve: pd.Series) -> Tuple[float, Optional[timedelta]]:
        """Calculate maximum drawdown and duration"""
        if len(equity_curve) == 0:
            return 0.0, None

        running_max = equity_curve.expanding().max()
        drawdown = (equity_curve - running_max) / running_max
        max_dd = float(drawdown.min())

        # Find drawdown duration
        dd_duration = None
        in_drawdown = False
        dd_start = None
        max_dd_length = timedelta(0)

        for i, dd_value in enumerate(drawdown):
            if dd_value < -0.001 and not in_drawdown:
                in_drawdown = True
                dd_start = equity_curve.index[i]
            elif dd_value >= -0.001 and in_drawdown:
                in_drawdown = False
                if dd_start:
                    dd_length = equity_curve.index[i] - dd_start
                    max_dd_length = max(max_dd_length, dd_length)

        dd_duration = max_dd_length if max_dd_length.total_seconds() > 0 else None

        return max_dd, dd_duration

    def _calculate_ulcer_index(self, equity_curve: pd.Series) -> float:
        """Calculate Ulcer Index (measure of downside risk)"""
        if len(equity_curve) < 2:
            return 0.0

        running_max = equity_curve.expanding().max()
        drawdown_pct = (equity_curve - running_max) / running_max * 100

        ulcer = np.sqrt(np.mean(drawdown_pct**2))

        return float(ulcer)

    def _calculate_streaks(self, trades: List[Trade]) -> Tuple[int, int, int, str]:
        """Calculate win/loss streaks"""
        if not trades:
            return 0, 0, 0, "none"

        max_wins = 0
        max_losses = 0
        current_wins = 0
        current_losses = 0

        for trade in trades:
            if trade.is_winner:
                current_wins += 1
                current_losses = 0
                max_wins = max(max_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                max_losses = max(max_losses, current_losses)

        # Current streak
        current_streak = current_wins if current_wins > 0 else current_losses
        streak_type = "wins" if current_wins > 0 else "losses"

        return max_wins, max_losses, current_streak, streak_type

    def _empty_metrics(self) -> PerformanceMetrics:
        """Return empty metrics when no data available"""
        return PerformanceMetrics(
            total_pnl=0.0,
            total_return_pct=0.0,
            annualized_return=0.0,
            monthly_return=0.0,
            daily_return=0.0,
            volatility=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            calmar_ratio=0.0,
            max_drawdown=0.0,
            max_drawdown_duration=None,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            avg_win=0.0,
            avg_loss=0.0,
            largest_win=0.0,
            largest_loss=0.0,
            profit_factor=0.0,
            avg_risk_reward=0.0,
            expectancy=0.0,
            avg_trade_duration=timedelta(0),
            avg_winning_duration=timedelta(0),
            avg_losing_duration=timedelta(0),
            max_consecutive_wins=0,
            max_consecutive_losses=0,
            current_streak=0,
            current_streak_type="none",
            recovery_factor=0.0,
            kelly_criterion=0.0,
            ulcer_index=0.0,
        )


def demo_performance_analytics():
    """Demonstration of performance analytics"""
    print("\n" + "=" * 80)
    print(" LOKI PERFORMANCE ANALYTICS DEMO")
    print("=" * 80 + "\n")

    # Initialize analyzer
    analyzer = PerformanceAnalyzer(initial_capital=100000.0)

    # Generate sample trades
    np.random.seed(42)
    base_time = datetime.now() - timedelta(days=90)

    for i in range(50):
        # Random trade
        is_winner = np.random.random() > 0.4  # 60% win rate
        direction = np.random.choice(["long", "short"])
        entry_price = 100 + np.random.random() * 50
        quantity = np.random.randint(10, 100)

        entry_time = base_time + timedelta(hours=i * 24)
        exit_time = entry_time + timedelta(hours=np.random.randint(1, 48))

        if is_winner:
            exit_price = entry_price * (1 + np.random.uniform(0.01, 0.05))
        else:
            exit_price = entry_price * (1 - np.random.uniform(0.01, 0.03))

        trade = Trade(
            trade_id=f"trade_{i}",
            symbol=np.random.choice(["AAPL", "GOOGL", "MSFT", "AMZN"]),
            entry_time=entry_time,
            entry_price=entry_price,
            quantity=quantity,
            direction=direction,
            strategy=np.random.choice(["momentum", "mean_reversion", "breakout"]),
        )

        trade.close_trade(exit_price, exit_time)
        analyzer.add_trade(trade)

    # Generate report
    print(analyzer.generate_report())

    # Strategy comparison
    print("\n" + "=" * 80)
    print(" STRATEGY COMPARISON")
    print("=" * 80 + "\n")

    comparison = analyzer.compare_strategies()

    for strategy, metrics in comparison.strategy_metrics.items():
        print(f"\n{strategy.upper()}:")
        print(f"  Total P&L:      ${metrics['total_pnl']:>12,.2f}")
        print(f"  Trades:         {metrics['num_trades']:>12}")
        print(f"  Win Rate:       {metrics['win_rate']:>12.1f}%")
        print(f"  Profit Factor:  {metrics['profit_factor']:>12.2f}")
        print(f"  Consistency:    {comparison.consistency_scores[strategy]:>12.2f}")

    print(f"\n✓ Best Strategy: {comparison.best_strategy}")
    print(f"✗ Worst Strategy: {comparison.worst_strategy}")


if __name__ == "__main__":
    demo_performance_analytics()
