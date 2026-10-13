"""
Freqtrade-Inspired Advanced Backtesting Module
Enhanced backtesting with hyperparameter optimization and analysis
"""
import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import json
import sqlite3
from pathlib import Path


class BacktestMode(Enum):
    """Backtesting modes."""
    BACKTEST = "backtest"
    HYPEROPT = "hyperopt"
    RECURSIVE = "recursive"


@dataclass
class BacktestResult:
    """Results from a backtest."""
    strategy_name: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: float
    total_profit: float
    total_profit_abs: float
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    avg_profit: float
    avg_profit_abs: float
    median_profit: float
    total_volume: float
    avg_duration_minutes: float
    best_trade: float
    worst_trade: float
    trades_per_day: float
    parameters: Dict[str, Any]
    start_date: datetime
    end_date: datetime


class FreqtradeBacktester:
    """
    Freqtrade-inspired backtesting system with advanced features
    including hyperparameter optimization, trade analysis, and reporting.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.backtest_config = config.get('backtesting', {})
        
        # Configuration
        self.stake_currency = self.backtest_config.get('stake_currency', 'AUD')
        self.stake_amount = self.backtest_config.get('stake_amount', 1000.0)
        self.fee = self.backtest_config.get('fee', 0.001)  # 0.1% fee
        self.max_open_trades = self.backtest_config.get('max_open_trades', 5)
        
        # Database for trade history
        # Keep generated backtest history out of an operator-selected database
        # when a caller (especially a test) supplies its own path.
        self.db_path = Path(self.backtest_config.get('database_path', 'backtest_results.db'))
        self._init_database()
        
        logging.info("Freqtrade Backtester initialized")
    
    def _init_database(self):
        """Initialize SQLite database for backtest results."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS backtest_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_name TEXT,
                timestamp DATETIME,
                total_trades INTEGER,
                win_rate REAL,
                profit_factor REAL,
                total_profit REAL,
                max_drawdown REAL,
                sharpe_ratio REAL,
                parameters TEXT,
                UNIQUE(strategy_name, timestamp)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                backtest_id INTEGER,
                entry_time DATETIME,
                exit_time DATETIME,
                pair TEXT,
                side TEXT,
                entry_price REAL,
                exit_price REAL,
                amount REAL,
                profit_abs REAL,
                profit_ratio REAL,
                FOREIGN KEY (backtest_id) REFERENCES backtest_results (id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def run_backtest(self, strategy: Any, data: pd.DataFrame, 
                    parameters: Optional[Dict[str, Any]] = None) -> BacktestResult:
        """
        Run a backtest with the given strategy and data.
        """
        try:
            logging.info(f"Running backtest for strategy: {strategy.__class__.__name__}")
            
            # Initialize tracking
            trades = []
            current_position = None
            balance = self.stake_amount
            max_balance = balance
            max_drawdown = 0.0
            
            # Apply parameters if provided
            if parameters:
                for key, value in parameters.items():
                    if hasattr(strategy, key):
                        setattr(strategy, key, value)
            
            # Run backtest
            for i in range(len(data)):
                row = data.iloc[i]
                
                # Get signal from strategy
                signal = strategy.generate_signal(data.iloc[:i+1])
                
                # Handle entry
                if signal == 'BUY' and current_position is None:
                    entry_price = row['close']
                    amount = (balance * 0.95) / entry_price  # Use 95% of balance
                    current_position = {
                        'entry_time': row.name,
                        'entry_price': entry_price,
                        'amount': amount,
                        'side': 'long'
                    }
                
                # Handle exit
                elif signal == 'SELL' and current_position is not None:
                    exit_price = row['close']
                    profit_abs = (exit_price - current_position['entry_price']) * current_position['amount']
                    profit_ratio = (exit_price - current_position['entry_price']) / current_position['entry_price']
                    
                    # Apply fee
                    profit_abs -= (entry_price * current_position['amount'] * self.fee)
                    profit_abs -= (exit_price * current_position['amount'] * self.fee)
                    
                    trade = {
                        'entry_time': current_position['entry_time'],
                        'exit_time': row.name,
                        'pair': data.name if hasattr(data, 'name') else 'BTCUSDT',
                        'side': current_position['side'],
                        'entry_price': current_position['entry_price'],
                        'exit_price': exit_price,
                        'amount': current_position['amount'],
                        'profit_abs': profit_abs,
                        'profit_ratio': profit_ratio
                    }
                    
                    trades.append(trade)
                    balance += profit_abs
                    current_position = None
                    
                    # Track max drawdown
                    if balance > max_balance:
                        max_balance = balance
                    drawdown = (max_balance - balance) / max_balance
                    if drawdown > max_drawdown:
                        max_drawdown = drawdown
            
            # Calculate metrics
            if not trades:
                return self._create_empty_result(strategy.__class__.__name__, parameters)
            
            result = self._calculate_metrics(trades, balance, max_drawdown, parameters)
            
            # Save to database
            self._save_backtest_result(result)
            
            logging.info(f"Backtest completed: {result.total_trades} trades, {result.win_rate:.2f}% win rate")
            
            return result
            
        except Exception as e:
            logging.error(f"Backtest error: {e}")
            return self._create_empty_result(strategy.__class__.__name__, parameters)
    
    def _calculate_metrics(self, trades: List[Dict], final_balance: float, 
                          max_drawdown: float, parameters: Dict[str, Any]) -> BacktestResult:
        """Calculate comprehensive backtest metrics."""
        trades_df = pd.DataFrame(trades)
        
        winning_trades = trades_df[trades_df['profit_abs'] > 0]
        losing_trades = trades_df[trades_df['profit_abs'] < 0]
        
        total_trades = len(trades)
        winning_count = len(winning_trades)
        losing_count = len(losing_trades)
        
        win_rate = (winning_count / total_trades * 100) if total_trades > 0 else 0
        
        total_profit = final_balance - self.stake_amount
        total_profit_abs = total_profit
        
        total_wins = winning_trades['profit_abs'].sum() if len(winning_trades) > 0 else 0
        total_losses = abs(losing_trades['profit_abs'].sum()) if len(losing_trades) > 0 else 0
        profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')
        
        avg_profit = trades_df['profit_ratio'].mean()
        avg_profit_abs = trades_df['profit_abs'].mean()
        median_profit = trades_df['profit_ratio'].median()
        
        best_trade = trades_df['profit_abs'].max() if len(trades_df) > 0 else 0
        worst_trade = trades_df['profit_abs'].min() if len(trades_df) > 0 else 0
        
        # Calculate duration
        trades_df['duration'] = pd.to_datetime(trades_df['exit_time']) - pd.to_datetime(trades_df['entry_time'])
        avg_duration = trades_df['duration'].mean().total_seconds() / 60 if len(trades_df) > 0 else 0
        
        # Calculate Sharpe ratio (simplified)
        if len(trades_df) > 1:
            returns = trades_df['profit_ratio'].values
            sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0
        else:
            sharpe_ratio = 0
        
        # Calculate Sortino ratio
        if len(trades_df) > 1:
            downside_returns = returns[returns < 0]
            sortino_ratio = np.mean(returns) / np.std(downside_returns) * np.sqrt(252) if len(downside_returns) > 0 and np.std(downside_returns) > 0 else 0
        else:
            sortino_ratio = 0
        
        # Calculate Calmar ratio
        calmar_ratio = total_profit / max_drawdown if max_drawdown > 0 else 0
        
        # Calculate trades per day
        if len(trades_df) > 0:
            date_range = (pd.to_datetime(trades_df['exit_time']).max() - pd.to_datetime(trades_df['entry_time']).min()).days
            trades_per_day = total_trades / date_range if date_range > 0 else 0
        else:
            trades_per_day = 0
        
        return BacktestResult(
            strategy_name="CustomStrategy",
            total_trades=total_trades,
            winning_trades=winning_count,
            losing_trades=losing_count,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_profit=total_profit / self.stake_amount * 100,
            total_profit_abs=total_profit_abs,
            max_drawdown=max_drawdown * 100,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            avg_profit=avg_profit * 100,
            avg_profit_abs=avg_profit_abs,
            median_profit=median_profit * 100,
            total_volume=trades_df['amount'].sum() if len(trades_df) > 0 else 0,
            avg_duration_minutes=avg_duration,
            best_trade=best_trade,
            worst_trade=worst_trade,
            trades_per_day=trades_per_day,
            parameters=parameters or {},
            start_date=pd.to_datetime(trades_df['entry_time']).min() if len(trades_df) > 0 else datetime.now(),
            end_date=pd.to_datetime(trades_df['exit_time']).max() if len(trades_df) > 0 else datetime.now()
        )
    
    def _create_empty_result(self, strategy_name: str, parameters: Dict[str, Any]) -> BacktestResult:
        """Create empty result for failed backtests."""
        return BacktestResult(
            strategy_name=strategy_name,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            profit_factor=0.0,
            total_profit=0.0,
            total_profit_abs=0.0,
            max_drawdown=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            calmar_ratio=0.0,
            avg_profit=0.0,
            avg_profit_abs=0.0,
            median_profit=0.0,
            total_volume=0.0,
            avg_duration_minutes=0.0,
            best_trade=0.0,
            worst_trade=0.0,
            trades_per_day=0.0,
            parameters=parameters,
            start_date=datetime.now(),
            end_date=datetime.now()
        )
    
    def _save_backtest_result(self, result: BacktestResult):
        """Save backtest result to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO backtest_results 
            (strategy_name, timestamp, total_trades, win_rate, profit_factor, 
             total_profit, max_drawdown, sharpe_ratio, parameters)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            result.strategy_name,
            datetime.now().isoformat(),
            result.total_trades,
            result.win_rate,
            result.profit_factor,
            result.total_profit,
            result.max_drawdown,
            result.sharpe_ratio,
            json.dumps(result.parameters)
        ))
        
        backtest_id = cursor.lastrowid
        
        # Note: We would save individual trades here in a full implementation
        
        conn.commit()
        conn.close()
    
    def hyperopt(self, strategy: Any, data: pd.DataFrame, 
                param_space: Dict[str, Tuple[Any, Any, Any]], 
                max_evals: int = 100) -> BacktestResult:
        """
        Hyperparameter optimization using grid search or random search.
        param_space format: {param_name: (min, max, step)}
        """
        logging.info(f"Starting hyperparameter optimization with {max_evals} evaluations")
        
        best_result = None
        best_score = -float('inf')
        
        for i in range(max_evals):
            # Generate random parameters
            params = {}
            for param_name, (min_val, max_val, step) in param_space.items():
                import random
                params[param_name] = random.uniform(min_val, max_val)
            
            # Run backtest
            result = self.run_backtest(strategy, data, params)
            
            # Calculate score (use Sharpe ratio as primary metric)
            score = result.sharpe_ratio if result.total_trades > 0 else -float('inf')
            
            if score > best_score:
                best_score = score
                best_result = result
            
            if (i + 1) % 10 == 0:
                logging.info(f"Hyperopt progress: {i+1}/{max_evals}, best score: {best_score:.2f}")
        
        logging.info(f"Hyperopt completed. Best Sharpe ratio: {best_score:.2f}")
        
        return best_result
    
    def get_backtest_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent backtest results from database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT strategy_name, timestamp, total_trades, win_rate, 
                   profit_factor, total_profit, max_drawdown, sharpe_ratio, parameters
            FROM backtest_results
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (limit,))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'strategy_name': row[0],
                'timestamp': row[1],
                'total_trades': row[2],
                'win_rate': row[3],
                'profit_factor': row[4],
                'total_profit': row[5],
                'max_drawdown': row[6],
                'sharpe_ratio': row[7],
                'parameters': json.loads(row[8])
            })
        
        conn.close()
        return results
