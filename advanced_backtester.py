#!/usr/bin/env python3
"""
Advanced Backtesting System for Enhanced Trading Strategies
High-performance backtesting with walk-forward analysis, Monte Carlo simulation, and advanced metrics.
"""

import pandas as pd
import numpy as np
import datetime
from typing import Dict, List, Optional, Tuple
import logging
from dataclasses import dataclass
import sqlite3
import concurrent.futures
import warnings
warnings.filterwarnings('ignore')

@dataclass
class BacktestResult:
    """Comprehensive backtest results container."""
    strategy_name: str
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    total_trades: int
    avg_trade_return: float
    volatility: float
    calmar_ratio: float
    sortino_ratio: float
    confidence_interval: Tuple[float, float]
    
@dataclass 
class Trade:
    """Individual trade record."""
    entry_time: datetime.datetime
    exit_time: datetime.datetime
    entry_price: float
    exit_price: float
    quantity: int
    side: str  # 'BUY' or 'SELL'
    pnl: float
    confidence: float
    strategy: str
class AdvancedBacktester:
    """High-performance backtesting engine with advanced analytics."""
    
    def __init__(self, initial_capital=100000, commission=0.001, slippage=0.0005):
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self.trades = []
        self.equity_curve = []
        
    def run_backtest(self, strategy, data: pd.DataFrame, **kwargs) -> BacktestResult:
        """Run comprehensive backtest with multiple metrics."""
        logging.info(f"Starting backtest for {strategy.name}...")
        
        capital = self.initial_capital
        position = 0
        entry_price = 0
        entry_time = None
        trades = []
        equity_history = [capital]
        
        for i in range(1, len(data)):
            current_bar = data.iloc[i]
            
            try:
                # Generate signal
                signal_result = strategy.generate_signals(data, 'Bullish', index=i, **kwargs)
                
                if hasattr(signal_result, 'action'):
                    signal = signal_result.action
                    confidence = signal_result.confidence
                else:
                    signal = signal_result
                    confidence = 0.7  # Default confidence
                
                current_price = current_bar['close']
                
                # Position management
                if position == 0 and signal in ['BUY', 'SELL']:
                    # Enter position
                    position = 1 if signal == 'BUY' else -1
                    entry_price = current_price * (1 + self.slippage * position)
                    entry_time = current_bar.name
                    
                elif position != 0 and (
                    (position > 0 and signal == 'SELL') or
                    (position < 0 and signal == 'BUY') or
                    i == len(data) - 1  # Close at end
                ):
                    # Exit position
                    exit_price = current_price * (1 - self.slippage * position)
                    
                    # Calculate PnL
                    if position > 0:
                        pnl = (exit_price - entry_price) / entry_price
                    else:
                        pnl = (entry_price - exit_price) / entry_price
                    
                    # Apply commission
                    pnl -= 2 * self.commission
                    
                    # Record trade
                    trade = Trade(
                        entry_time=entry_time,
                        exit_time=current_bar.name,
                        entry_price=entry_price,
                        exit_price=exit_price,
                        quantity=int(capital * 0.95 / entry_price),
                        side='LONG' if position > 0 else 'SHORT',
                        pnl=pnl * capital,
                        confidence=confidence,
                        strategy=strategy.name
                    )
                    trades.append(trade)
                    
                    # Update capital
                    capital *= (1 + pnl)
                    position = 0
                
                equity_history.append(capital)
                
            except Exception as e:
                logging.error(f"Error in backtest at index {i}: {e}")
                continue
        
        # Calculate performance metrics
        return self._calculate_metrics(trades, equity_history, strategy.name)
    
    def _calculate_metrics(self, trades: List[Trade], equity_curve: List[float], strategy_name: str) -> BacktestResult:
        """Calculate comprehensive performance metrics."""
        
        if not trades:
            return BacktestResult(
                strategy_name=strategy_name,
                total_return=0.0, sharpe_ratio=0.0, max_drawdown=0.0,
                win_rate=0.0, profit_factor=0.0, total_trades=0,
                avg_trade_return=0.0, volatility=0.0, calmar_ratio=0.0,
                sortino_ratio=0.0, confidence_interval=(0.0, 0.0)
            )
        
        # Basic metrics
        total_return = (equity_curve[-1] - equity_curve[0]) / equity_curve[0]
        
        # Trade analysis
        winning_trades = [t.pnl for t in trades if t.pnl > 0]
        losing_trades = [abs(t.pnl) for t in trades if t.pnl < 0]
        
        win_rate = len(winning_trades) / len(trades) if trades else 0
        avg_trade_return = np.mean([t.pnl for t in trades]) / self.initial_capital
        
        profit_factor = (sum(winning_trades) / sum(losing_trades) 
                        if losing_trades else float('inf'))
        
        # Risk metrics
        returns = pd.Series(equity_curve).pct_change().dropna()
        volatility = returns.std() * np.sqrt(252)  # Annualized
        
        sharpe_ratio = (total_return / volatility) if volatility > 0 else 0
        
        # Drawdown calculation
        equity_series = pd.Series(equity_curve)
        running_max = equity_series.expanding().max()
        drawdown = (equity_series - running_max) / running_max
        max_drawdown = abs(drawdown.min())
        
        # Advanced metrics
        negative_returns = returns[returns < 0]
        downside_std = negative_returns.std() * np.sqrt(252)
        sortino_ratio = (total_return / downside_std) if downside_std > 0 else 0
        
        calmar_ratio = (total_return / max_drawdown) if max_drawdown > 0 else 0
        
        # Monte Carlo confidence interval
        confidence_interval = self._monte_carlo_confidence(returns)
        
        return BacktestResult(
            strategy_name=strategy_name,
            total_return=total_return,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=len(trades),
            avg_trade_return=avg_trade_return,
            volatility=volatility,
            calmar_ratio=calmar_ratio,
            sortino_ratio=sortino_ratio,
            confidence_interval=confidence_interval
        )
    
    def _monte_carlo_confidence(self, returns: pd.Series, simulations=1000) -> Tuple[float, float]:
        """Calculate 95% confidence interval using Monte Carlo simulation."""
        if len(returns) < 10:
            return (0.0, 0.0)
        
        annual_returns = []
        for _ in range(simulations):
            # Bootstrap sampling
            sample_returns = np.random.choice(returns.values, size=len(returns), replace=True)
            annual_return = (1 + pd.Series(sample_returns)).prod() - 1
            annual_returns.append(annual_return)
        
        return (np.percentile(annual_returns, 2.5), np.percentile(annual_returns, 97.5))
class WalkForwardOptimizer:
    """Walk-forward analysis for robust strategy optimization."""
    
    def __init__(self, train_period=252, test_period=63):
        self.train_period = train_period
        self.test_period = test_period
        
    def optimize_strategy(self, strategy_class, data: pd.DataFrame, param_ranges: Dict) -> Dict:
        """Perform walk-forward optimization."""
        results = []
        
        # Split data into walk-forward windows
        for start in range(0, len(data) - self.train_period - self.test_period, self.test_period):
            train_end = start + self.train_period
            test_end = train_end + self.test_period
            
            train_data = data.iloc[start:train_end]
            test_data = data.iloc[train_end:test_end]
            
            # Optimize on training period
            best_params = self._grid_search(strategy_class, train_data, param_ranges)
            
            # Test on out-of-sample period
            strategy = strategy_class(None, {'trading_flags': best_params})
            backtester = AdvancedBacktester()
            result = backtester.run_backtest(strategy, test_data)
            
            results.append({
                'period': f"{test_data.index[0]} to {test_data.index[-1]}",
                'params': best_params,
                'performance': result
            })
        
        return results
    
    def _grid_search(self, strategy_class, data: pd.DataFrame, param_ranges: Dict) -> Dict:
        """Simple grid search for parameter optimization."""
        best_sharpe = -999
        best_params = {}
        
        # Generate parameter combinations (simplified)
        param_keys = list(param_ranges.keys())
        if not param_keys:
            return {}
        
        # Test a few combinations (full grid search would be too slow)
        for i in range(min(10, len(param_ranges[param_keys[0]]))):
            params = {key: values[i % len(values)] for key, values in param_ranges.items()}
            
            try:
                strategy = strategy_class(None, {'trading_flags': params})
                backtester = AdvancedBacktester()
                result = backtester.run_backtest(strategy, data)
                
                if result.sharpe_ratio > best_sharpe:
                    best_sharpe = result.sharpe_ratio
                    best_params = params
            except:
                continue
        
        return best_params


def run_strategy_comparison(strategies: List, data: pd.DataFrame) -> pd.DataFrame:
    """Compare multiple strategies with parallel execution."""
    
    def test_strategy(strategy):
        backtester = AdvancedBacktester()
        return backtester.run_backtest(strategy, data)
    
    # Run backtests in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(test_strategy, strategies))
    
    # Create comparison DataFrame
    comparison_data = []
    for result in results:
        comparison_data.append({
            'Strategy': result.strategy_name,
            'Total Return': f"{result.total_return:.2%}",
            'Sharpe Ratio': f"{result.sharpe_ratio:.2f}",
            'Max Drawdown': f"{result.max_drawdown:.2%}",
            'Win Rate': f"{result.win_rate:.1%}",
            'Profit Factor': f"{result.profit_factor:.2f}",
            'Total Trades': result.total_trades,
            'Calmar Ratio': f"{result.calmar_ratio:.2f}"
        })
    
    return pd.DataFrame(comparison_data)


if __name__ == "__main__":
    # Demo usage
    logging.basicConfig(level=logging.INFO)
    
    print("🚀 Advanced Backtesting System Initialized!")
    print("Features:")
    print("  • Comprehensive performance metrics")
    print("  • Walk-forward optimization")  
    print("  • Monte Carlo confidence intervals")
    print("  • Parallel strategy comparison")
    print("  • Advanced risk analytics")
    print("\n✅ Ready for professional-grade strategy testing!")