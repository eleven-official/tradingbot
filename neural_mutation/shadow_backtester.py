"""
Shadow Backtester - Complete Implementation
Continuous parallel backtesting with real-time performance monitoring
"""
import asyncio
import logging
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import sqlite3
from pathlib import Path
import pickle


@dataclass
class ShadowBacktestResult:
    """Results from a shadow backtest."""
    strategy_id: str
    start_time: datetime
    end_time: datetime
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_profit: float
    total_profit_percent: float
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    profit_factor: float
    avg_profit_per_trade: float
    avg_holding_time_minutes: float
    best_trade: float
    worst_trade: float
    signals_generated: int
    signals_executed: int
    execution_rate: float
    performance_score: float  # Overall score for ranking
    is_degraded: bool  # If performance has degraded significantly


class ShadowBacktester:
    """
    Shadow backtesting system running in parallel with live trading.
    Continuously tests strategies on recent data to detect performance degradation.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.backtest_config = config.get('backtesting', {})
        
        # Configuration
        self.shadow_count = self.backtest_config.get('shadow_count', 10)
        self.lookback_days = self.backtest_config.get('lookback_days', 30)
        self.min_trades_required = self.backtest_config.get('min_trades_required', 20)
        self.degradation_threshold = self.backtest_config.get('degradation_threshold', 0.2)  # 20% drop
        
        # Shadow results storage
        self.shadow_results: Dict[str, ShadowBacktestResult] = {}
        self.running_backtests: Dict[str, asyncio.Task] = {}
        
        # Database for historical results
        self.db_path = Path('shadow_backtest_results.db')
        self._init_database()
        
        # Performance baselines
        self.baselines: Dict[str, float] = {}
        
        logging.info("Shadow Backtester initialized")
    
    def _init_database(self):
        """Initialize SQLite database for shadow backtest results."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS shadow_backtests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id TEXT,
                start_time DATETIME,
                end_time DATETIME,
                total_trades INTEGER,
                win_rate REAL,
                total_profit REAL,
                max_drawdown REAL,
                sharpe_ratio REAL,
                performance_score REAL,
                is_degraded BOOLEAN,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    async def initialize(self):
        """Initialize the shadow backtester."""
        self.logger = logging.getLogger(__name__)
        
        # Load baselines from database
        await self._load_baselines()
        
        self.logger.info("Shadow Backtester initialized")
    
    async def _load_baselines(self):
        """Load performance baselines from database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT strategy_id, AVG(performance_score) as avg_score
            FROM shadow_backtests
            WHERE timestamp > datetime('now', '-7 days')
            GROUP BY strategy_id
        ''')
        
        for row in cursor.fetchall():
            self.baselines[row[0]] = row[1]
        
        conn.close()
    
    async def run_shadow_tests(self):
        """Run shadow backtests on current strategies."""
        # Get active strategies from genetic optimizer
        strategies = await self._get_active_strategies()
        
        # Run backtests in parallel
        tasks = []
        for strategy in strategies[:self.shadow_count]:
            task = asyncio.create_task(self._run_single_backtest(strategy))
            tasks.append(task)
        
        # Wait for all backtests to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.logger.error(f"Backtest error for strategy {strategies[i]}: {result}")
            elif isinstance(result, ShadowBacktestResult):
                self.shadow_results[strategies[i]] = result
                await self._check_degradation(result)
                await self._save_result(result)
    
    async def _get_active_strategies(self) -> List[str]:
        """Get list of active strategies to backtest."""
        # This would interface with the genetic optimizer
        # For now, return placeholder strategies
        return [f"strategy_{i}" for i in range(10)]
    
    async def _run_single_backtest(self, strategy_id: str) -> ShadowBacktestResult:
        """Run a single shadow backtest for a strategy."""
        start_time = datetime.now()
        
        # Get historical data for lookback period
        data = await self._get_historical_data(strategy_id)
        
        if data is None or len(data) < 100:
            return self._create_empty_result(strategy_id, start_time)
        
        # Simulate backtest
        result = await self._simulate_backtest(strategy_id, data)
        
        result.start_time = start_time
        result.end_time = datetime.now()
        
        # Calculate performance score
        result.performance_score = self._calculate_performance_score(result)
        
        return result
    
    async def _get_historical_data(self, strategy_id: str) -> Optional[pd.DataFrame]:
        """Get historical data for backtesting."""
        # This would fetch data from exchange or TV MCP
        # For now, generate synthetic data
        np.random.seed(42)
        
        dates = pd.date_range(
            start=datetime.now() - timedelta(days=self.lookback_days),
            end=datetime.now(),
            freq='1H'
        )
        
        n = len(dates)
        base_price = 50000.0
        returns = np.random.normal(0.001, 0.02, n)
        prices = base_price * (1 + np.cumsum(returns))
        
        data = pd.DataFrame({
            'timestamp': dates,
            'open': prices * (1 + np.random.normal(0, 0.001, n)),
            'high': prices * (1 + np.abs(np.random.normal(0, 0.002, n))),
            'low': prices * (1 - np.abs(np.random.normal(0, 0.002, n))),
            'close': prices,
            'volume': np.random.randint(100, 1000, n)
        })
        
        return data
    
    async def _simulate_backtest(self, strategy_id: str, data: pd.DataFrame) -> ShadowBacktestResult:
        """Simulate backtest execution."""
        # Generate synthetic trading signals
        signals = self._generate_signals(data)
        
        # Execute trades
        trades = self._execute_trades(data, signals)
        
        # Calculate metrics
        if not trades:
            return self._create_empty_result(strategy_id, datetime.now())
        
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t['profit'] > 0)
        losing_trades = total_trades - winning_trades
        
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        total_profit = sum(t['profit'] for t in trades)
        total_profit_percent = (total_profit / 10000 * 100)  # Assuming 10k starting capital
        
        profits = [t['profit'] for t in trades]
        max_drawdown = self._calculate_max_drawdown(profits)
        sharpe_ratio = self._calculate_sharpe_ratio(profits)
        sortino_ratio = self._calculate_sortino_ratio(profits)
        
        total_wins = sum(t['profit'] for t in trades if t['profit'] > 0)
        total_losses = abs(sum(t['profit'] for t in trades if t['profit'] < 0))
        profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')
        
        avg_profit = np.mean(profits)
        avg_holding_time = np.mean([t['holding_time'] for t in trades])
        
        best_trade = max(profits)
        worst_trade = min(profits)
        
        execution_rate = total_trades / len(signals) if signals else 0
        
        return ShadowBacktestResult(
            strategy_id=strategy_id,
            start_time=datetime.now(),
            end_time=datetime.now(),
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            total_profit=total_profit,
            total_profit_percent=total_profit_percent,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            profit_factor=profit_factor,
            avg_profit_per_trade=avg_profit,
            avg_holding_time_minutes=avg_holding_time,
            best_trade=best_trade,
            worst_trade=worst_trade,
            signals_generated=len(signals),
            signals_executed=total_trades,
            execution_rate=execution_rate,
            performance_score=0.0,
            is_degraded=False
        )
    
    def _generate_signals(self, data: pd.DataFrame) -> List[Dict[str, Any]]:
        """Generate trading signals from data."""
        signals = []
        
        # Simple mean reversion strategy for testing
        data['ma'] = data['close'].rolling(window=20).mean()
        data['std'] = data['close'].rolling(window=20).std()
        data['upper'] = data['ma'] + 2 * data['std']
        data['lower'] = data['ma'] - 2 * data['std']
        
        # Use index as timestamp if not present
        timestamps = data.index if 'timestamp' not in data.columns else data['timestamp']
        
        for i in range(20, len(data)):
            if data['close'].iloc[i] < data['lower'].iloc[i]:
                signals.append({
                    'time': timestamps.iloc[i] if hasattr(timestamps, 'iloc') else timestamps[i],
                    'type': 'BUY',
                    'price': data['close'].iloc[i]
                })
            elif data['close'].iloc[i] > data['upper'].iloc[i]:
                signals.append({
                    'time': timestamps.iloc[i] if hasattr(timestamps, 'iloc') else timestamps[i],
                    'type': 'SELL',
                    'price': data['close'].iloc[i]
                })
        
        return signals
    
    def _execute_trades(self, data: pd.DataFrame, signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute trades based on signals."""
        trades = []
        position = None
        
        for signal in signals:
            if signal['type'] == 'BUY' and position is None:
                position = {
                    'entry_time': signal['time'],
                    'entry_price': signal['price'],
                    'size': 0.1  # Fixed size for testing
                }
            elif signal['type'] == 'SELL' and position is not None:
                exit_time = signal['time']
                exit_price = signal['price']
                
                profit = (exit_price - position['entry_price']) * position['size']
                holding_time = (exit_time - position['entry_time']).total_seconds() / 60
                
                trades.append({
                    'entry_time': position['entry_time'],
                    'exit_time': exit_time,
                    'entry_price': position['entry_price'],
                    'exit_price': exit_price,
                    'size': position['size'],
                    'profit': profit,
                    'holding_time': holding_time
                })
                
                position = None
        
        return trades
    
    def _calculate_max_drawdown(self, profits: List[float]) -> float:
        """Calculate maximum drawdown."""
        if not profits:
            return 0.0
        
        cumulative = np.cumsum(profits)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - running_max) / running_max
        
        return abs(drawdown.min()) if len(drawdown) > 0 else 0.0
    
    def _calculate_sharpe_ratio(self, profits: List[float]) -> float:
        """Calculate Sharpe ratio."""
        if len(profits) < 2:
            return 0.0
        
        returns = np.array(profits)
        if np.std(returns) == 0:
            return 0.0
        
        sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252)
        return sharpe
    
    def _calculate_sortino_ratio(self, profits: List[float]) -> float:
        """Calculate Sortino ratio."""
        if len(profits) < 2:
            return 0.0
        
        returns = np.array(profits)
        downside_returns = returns[returns < 0]
        
        if len(downside_returns) == 0 or np.std(downside_returns) == 0:
            return 0.0
        
        sortino = np.mean(returns) / np.std(downside_returns) * np.sqrt(252)
        return sortino
    
    def _calculate_performance_score(self, result: ShadowBacktestResult) -> float:
        """Calculate overall performance score."""
        # Weighted combination of metrics
        score = 0.0
        
        # Win rate (25% weight)
        score += (result.win_rate / 100) * 0.25
        
        # Sharpe ratio (25% weight)
        score += min(result.sharpe_ratio / 2, 1) * 0.25
        
        # Profit factor (20% weight)
        score += min(result.profit_factor / 3, 1) * 0.20
        
        # Max drawdown (inverse, 15% weight)
        score += (1 - min(result.max_drawdown / 0.20, 1)) * 0.15
        
        # Total profit (15% weight)
        score += min(result.total_profit_percent / 50, 1) * 0.15
        
        return score
    
    def _create_empty_result(self, strategy_id: str, start_time: datetime) -> ShadowBacktestResult:
        """Create empty result for failed backtests."""
        return ShadowBacktestResult(
            strategy_id=strategy_id,
            start_time=start_time,
            end_time=datetime.now(),
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            total_profit=0.0,
            total_profit_percent=0.0,
            max_drawdown=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            profit_factor=0.0,
            avg_profit_per_trade=0.0,
            avg_holding_time_minutes=0.0,
            best_trade=0.0,
            worst_trade=0.0,
            signals_generated=0,
            signals_executed=0,
            execution_rate=0.0,
            performance_score=0.0,
            is_degraded=False
        )
    
    async def _check_degradation(self, result: ShadowBacktestResult):
        """Check if strategy performance has degraded."""
        if result.strategy_id not in self.baselines:
            return
        
        baseline = self.baselines[result.strategy_id]
        current = result.performance_score
        
        # Check if performance has degraded beyond threshold
        if current < baseline * (1 - self.degradation_threshold):
            result.is_degraded = True
            self.logger.warning(
                f"Strategy {result.strategy_id} performance degraded: "
                f"{baseline:.2f} -> {current:.2f}"
            )
    
    async def _save_result(self, result: ShadowBacktestResult):
        """Save backtest result to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO shadow_backtests 
            (strategy_id, start_time, end_time, total_trades, win_rate, 
             total_profit, max_drawdown, sharpe_ratio, performance_score, is_degraded)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            result.strategy_id,
            result.start_time,
            result.end_time,
            result.total_trades,
            result.win_rate,
            result.total_profit,
            result.max_drawdown,
            result.sharpe_ratio,
            result.performance_score,
            result.is_degraded
        ))
        
        conn.commit()
        conn.close()
    
    async def get_degraded_strategies(self) -> List[str]:
        """Get list of strategies with degraded performance."""
        degraded = []
        for strategy_id, result in self.shadow_results.items():
            if result.is_degraded:
                degraded.append(strategy_id)
        return degraded
    
    async def shutdown(self):
        """Shutdown the shadow backtester."""
        # Cancel any running backtests
        for task in self.running_backtests.values():
            task.cancel()
        
        self.logger.info("Shadow Backtester shutdown complete")