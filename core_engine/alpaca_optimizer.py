"""
Alpaca Strategy Optimizer
Optimizes trading strategies specifically for Alpaca paper trading
"""
import asyncio
import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from core_engine.alpaca_broker import AlpacaBroker, AlpacaConfig, AccountType
from core_engine.academic_strategies import StrategyLibrary
from core_engine.parameter_optimization import ParameterOptimizer, ParameterRange, OptimizationMethod


class OptimizationObjective(Enum):
    """Optimization objectives."""
    SHARPE_RATIO = "sharpe_ratio"
    TOTAL_RETURN = "total_return"
    MAX_DRAWDOWN = "max_drawdown"
    PROFIT_FACTOR = "profit_factor"
    WIN_RATE = "win_rate"


@dataclass
class OptimizationResult:
    """Optimization result."""
    strategy_name: str
    best_parameters: Dict[str, float]
    best_score: float
    all_results: List[Dict[str, any]]
    objective: OptimizationObjective
    test_period: Tuple[datetime, datetime]
    sample_trades: int
    timestamp: datetime


class AlpacaStrategyOptimizer:
    """
    Optimizes trading strategies using Alpaca historical data.
    """
    
    def __init__(self, alpaca_broker: AlpacaBroker):
        self.alpaca_broker = alpaca_broker
        self.strategy_library = StrategyLibrary()
        self.optimizer = ParameterOptimizer(OptimizationMethod.GRID_SEARCH)
        self.logger = logging.getLogger(__name__)
    
    async def optimize_strategy(self, strategy_name: str, symbol: str,
                              objective: OptimizationObjective = OptimizationObjective.SHARPE_RATIO,
                              lookback_days: int = 90) -> OptimizationResult:
        """
        Optimize a strategy's parameters using historical data.
        """
        self.logger.info(f"Optimizing {strategy_name} for {symbol}...")
        
        # Get historical data
        bars = self.alpaca_broker.get_bars(symbol, '1Day', limit=lookback_days)
        
        if bars is None or len(bars) < 30:
            self.logger.error(f"Insufficient historical data for {symbol}")
            return None
        
        # Define parameter ranges for the strategy
        parameter_ranges = self._get_parameter_ranges(strategy_name)
        
        # Define objective function
        def objective_function(params):
            return self._evaluate_strategy_params(
                strategy_name, symbol, bars, params, objective
            )
        
        # Run optimization
        result = self.optimizer.optimize(
            objective_function=objective_function,
            parameter_ranges=parameter_ranges,
            n_iterations=50
        )
        
        return OptimizationResult(
            strategy_name=strategy_name,
            best_parameters=result.best_parameters,
            best_score=result.best_score,
            all_results=result.all_results,
            objective=objective,
            test_period=(bars.index[0], bars.index[-1]),
            sample_trades=len(result.all_results),
            timestamp=datetime.now()
        )
    
    def _get_parameter_ranges(self, strategy_name: str) -> List[ParameterRange]:
        """Get parameter ranges for a strategy."""
        ranges = []
        
        if strategy_name == 'momentum':
            ranges = [
                ParameterRange('lookback_period', 10, 50, 5),
                ParameterRange('entry_threshold', 0.01, 0.05, 0.01),
                ParameterRange('stop_loss_multiplier', 1.5, 3.0, 0.5)
            ]
        elif strategy_name == 'mean_reversion':
            ranges = [
                ParameterRange('lookback_period', 10, 30, 5),
                ParameterRange('entry_threshold', -2.0, -0.5, 0.5),
                ParameterRange('bb_period', 15, 25, 5)
            ]
        elif strategy_name == 'breakout':
            ranges = [
                ParameterRange('lookback_period', 10, 30, 5),
                ParameterRange('breakout_threshold', 0.005, 0.02, 0.005),
                ParameterRange('volume_multiplier', 1.5, 2.5, 0.5)
            ]
        else:
            # Default ranges
            ranges = [
                ParameterRange('lookback_period', 10, 50, 5),
                ParameterRange('entry_threshold', 0.01, 0.05, 0.01)
            ]
        
        return ranges
    
    def _evaluate_strategy_params(self, strategy_name: str, symbol: str,
                               data: pd.DataFrame, params: Dict[str, float],
                               objective: OptimizationObjective) -> float:
        """
        Evaluate strategy parameters on historical data.
        """
        try:
            # Get strategy with custom parameters
            strategy = self.strategy_library.get_strategy(strategy_name, params)
            
            if not strategy:
                return -np.inf
            
            # Attach symbol to data
            data_copy = data.copy()
            data_copy.attrs["symbol"] = symbol
            
            # Generate signals
            signals = strategy.generate_signals(data_copy)
            
            if not signals:
                return -np.inf
            
            # Simulate trading
            returns = self._simulate_trading(signals, data)
            
            if not returns or len(returns) == 0:
                return -np.inf
            
            # Calculate objective score
            if objective == OptimizationObjective.SHARPE_RATIO:
                if len(returns) > 1:
                    return returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0
                return 0
            elif objective == OptimizationObjective.TOTAL_RETURN:
                return (1 + returns).prod() - 1
            elif objective == OptimizationObjective.MAX_DRAWDOWN:
                cumulative = (1 + returns).cumprod()
                drawdown = (cumulative - cumulative.expanding().max()) / cumulative.expanding().max()
                return -drawdown.min()  # Negative because we want to minimize drawdown
            elif objective == OptimizationObjective.WIN_RATE:
                return (returns > 0).sum() / len(returns)
            elif objective == OptimizationObjective.PROFIT_FACTOR:
                wins = returns[returns > 0].sum()
                losses = abs(returns[returns < 0].sum())
                return wins / losses if losses > 0 else 0
            else:
                return 0
        
        except Exception as e:
            self.logger.error(f"Error evaluating parameters: {e}")
            return -np.inf
    
    def _simulate_trading(self, signals: List, data: pd.DataFrame) -> pd.Series:
        """Simulate trading based on signals."""
        returns = []
        position = None
        entry_price = 0
        
        for signal in signals:
            if position is None and signal.action == 'BUY':
                position = 'LONG'
                entry_price = signal.entry_price
            elif position == 'LONG' and signal.action == 'SELL':
                # Calculate return
                exit_price = signal.entry_price
                ret = (exit_price - entry_price) / entry_price
                returns.append(ret)
                position = None
        
        return pd.Series(returns)
    
    async def compare_strategies(self, symbol: str, 
                                strategies: List[str],
                                objective: OptimizationObjective = OptimizationObjective.SHARPE_RATIO) -> Dict[str, OptimizationResult]:
        """
        Compare multiple strategies and find the best one.
        """
        results = {}
        
        for strategy_name in strategies:
            self.logger.info(f"Optimizing {strategy_name}...")
            result = await self.optimize_strategy(strategy_name, symbol, objective)
            results[strategy_name] = result
        
        # Find best strategy
        best_strategy = max(results.items(), key=lambda x: x[1].best_score)
        
        self.logger.info(f"Best strategy: {best_strategy[0]} (score: {best_strategy[1].best_score:.2f})")
        
        return results


class AlpacaRiskManager:
    """
    Risk management specifically for Alpaca trading.
    """
    
    def __init__(self, alpaca_broker: AlpacaBroker):
        self.alpaca_broker = alpaca_broker
        self.logger = logging.getLogger(__name__)
        
        # Risk limits
        self.max_position_value = 10000  # Max $10,000 per position
        self.max_total_exposure = 50000  # Max $50,000 total exposure
        self.max_positions = 5  # Max 5 positions at once
        self.max_daily_loss = 1000  # Max $1,000 daily loss
    
    async def check_risk_limits(self) -> Dict[str, bool]:
        """
        Check if current positions violate risk limits.
        """
        account = self.alpaca_broker.get_account()
        positions = self.alpaca_broker.get_positions()
        
        checks = {
            'position_size_ok': True,
            'total_exposure_ok': True,
            'position_count_ok': True,
            'daily_loss_ok': True
        }
        
        # Check individual position sizes
        for pos in positions:
            if pos.market_value > self.max_position_value:
                checks['position_size_ok'] = False
                self.logger.warning(f"Position {pos.symbol} exceeds size limit: ${pos.market_value:,.2f}")
        
        # Check total exposure
        total_exposure = sum(pos.market_value for pos in positions)
        if total_exposure > self.max_total_exposure:
            checks['total_exposure_ok'] = False
            self.logger.warning(f"Total exposure exceeds limit: ${total_exposure:,.2f}")
        
        # Check position count
        if len(positions) > self.max_positions:
            checks['position_count_ok'] = False
            self.logger.warning(f"Too many positions: {len(positions)}")
        
        # Check daily loss (simplified - would need daily P&L tracking)
        # This would require tracking daily performance
        checks['daily_loss_ok'] = True  # Placeholder
        
        return checks
    
    def calculate_position_size(self, symbol: str, current_price: float,
                               account_balance: float, risk_per_trade: float = 0.02) -> int:
        """
        Calculate optimal position size based on risk.
        """
        risk_amount = account_balance * risk_per_trade
        shares = int(risk_amount / current_price)
        
        # Ensure position doesn't exceed max position value
        position_value = shares * current_price
        if position_value > self.max_position_value:
            shares = int(self.max_position_value / current_price)
        
        return max(shares, 1)  # At least 1 share
    
    async def enforce_risk_limits(self):
        """
        Enforce risk limits by closing positions that violate them.
        """
        checks = await self.check_risk_limits()
        
        positions = self.alpaca_broker.get_positions()
        
        for pos in positions:
            # Close positions that are too large
            if pos.market_value > self.max_position_value:
                self.logger.warning(f"Closing oversized position: {pos.symbol}")
                self.alpaca_broker.place_order(
                    symbol=pos.symbol,
                    side='sell',
                    qty=pos.qty,
                    order_type='market'
                )
        
        # Close excess positions
        if len(positions) > self.max_positions:
            excess_positions = positions[self.max_positions:]
            for pos in excess_positions:
                self.logger.warning(f"Closing excess position: {pos.symbol}")
                self.alpaca_broker.place_order(
                    symbol=pos.symbol,
                    side='sell',
                    qty=pos.qty,
                    order_type='market'
                )


class AlpacaPerformanceTracker:
    """
    Tracks and analyzes performance for Alpaca trading.
    """
    
    def __init__(self, alpaca_broker: AlpacaBroker):
        self.alpaca_broker = alpaca_broker
        self.performance_history = []
        self.logger = logging.getLogger(__name__)
    
    async def snapshot_performance(self):
        """Take a snapshot of current performance."""
        account = self.alpaca_broker.get_account()
        positions = self.alpaca_broker.get_positions()
        
        snapshot = {
            'timestamp': datetime.now(),
            'portfolio_value': account.get('portfolio_value', 0),
            'cash': account.get('cash', 0),
            'buying_power': account.get('buying_power', 0),
            'num_positions': len(positions),
            'total_exposure': sum(pos.market_value for pos in positions),
            'unrealized_pl': sum(pos.unrealized_pl for pos in positions)
        }
        
        self.performance_history.append(snapshot)
        
        return snapshot
    
    def calculate_daily_returns(self) -> pd.Series:
        """Calculate daily returns from performance history."""
        if len(self.performance_history) < 2:
            return pd.Series()
        
        df = pd.DataFrame(self.performance_history)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
        
        # Resample to daily
        daily = df.resample('D').last()
        
        returns = daily['portfolio_value'].pct_change().dropna()
        
        return returns
    
    def get_performance_summary(self) -> Dict[str, float]:
        """Get performance summary statistics."""
        if len(self.performance_history) < 2:
            return {}
        
        returns = self.calculate_daily_returns()
        
        if len(returns) == 0:
            return {}
        
        initial_value = self.performance_history[0]['portfolio_value']
        final_value = self.performance_history[-1]['portfolio_value']
        
        total_return = (final_value - initial_value) / initial_value
        
        summary = {
            'total_return': total_return,
            'annualized_return': returns.mean() * 252 if len(returns) > 0 else 0,
            'volatility': returns.std() * np.sqrt(252) if len(returns) > 0 else 0,
            'sharpe_ratio': returns.mean() / returns.std() * np.sqrt(252) if len(returns) > 0 and returns.std() > 0 else 0,
            'max_drawdown': self._calculate_max_drawdown(returns),
            'total_snapshots': len(self.performance_history),
            'trading_days': len(returns)
        }
        
        return summary
    
    def _calculate_max_drawdown(self, returns: pd.Series) -> float:
        """Calculate maximum drawdown."""
        if len(returns) == 0:
            return 0
        
        cumulative = (1 + returns).cumprod()
        peak = cumulative.expanding().max()
        drawdown = (cumulative - peak) / peak
        
        return drawdown.min()