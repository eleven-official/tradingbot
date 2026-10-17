"""
Enhanced Backtesting Engine
Supports multi-year historical data backtesting
Integrates features from Vibe-Trading and FinceptTerminal
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import json


@dataclass
class BacktestResult:
    """Standardized backtest result."""
    symbol: str
    strategy: str
    start_date: str
    end_date: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_return: float
    annualized_return: float
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    avg_r_multiple: float
    trades: List[Dict[str, Any]]


class EnhancedBacktester:
    """
    Enhanced backtesting engine with multi-year historical data support.
    Integrates advanced metrics and walk-forward analysis.
    """
    
    def __init__(self, initial_capital: float = 25000):
        self.initial_capital = initial_capital
        self.commission = 0.001  # 0.1% commission
        self.slippage = 0.0005  # 0.05% slippage
    
    def fetch_historical_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        source: str = 'yfinance'
    ) -> pd.DataFrame:
        """
        Fetch historical data for long-term backtesting.
        
        Args:
            symbol: Trading symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            source: Data source ('yfinance', 'ccxt', 'alphavantage')
        
        Returns:
            DataFrame with OHLCV data
        """
        try:
            if source == 'yfinance':
                import yfinance as yf
                ticker = yf.Ticker(symbol)
                df = ticker.history(start=start_date, end=end_date)
                df.reset_index(inplace=True)
                df.columns = ['date', 'open', 'high', 'low', 'close', 'volume', 'dividends', 'stock_splits']
                df = df[['date', 'open', 'high', 'low', 'close', 'volume']]
                return df
            elif source == 'ccxt':
                import ccxt
                exchange = ccxt.binance()
                # CCXT fetch_ohlcv returns list of lists
                ohlcv = exchange.fetch_ohlcv(symbol, '1d', since=int(pd.Timestamp(start_date).timestamp() * 1000))
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['date'] = pd.to_datetime(df['timestamp'], unit='ms')
                df = df[['date', 'open', 'high', 'low', 'close', 'volume']]
                return df
            else:
                raise ValueError(f"Unknown data source: {source}")
        except Exception as e:
            print(f"Error fetching data: {e}")
            return pd.DataFrame()
    
    def run_backtest(
        self,
        data: pd.DataFrame,
        strategy_func: callable,
        strategy_params: Dict[str, Any],
        symbol: str = "TEST"
    ) -> BacktestResult:
        """
        Run a backtest with given strategy function.
        
        Args:
            data: Historical OHLCV data
            strategy_func: Strategy function that generates signals
            strategy_params: Parameters for the strategy
            symbol: Symbol name for reporting
        
        Returns:
            BacktestResult with all metrics
        """
        if data.empty:
            raise ValueError("No data provided for backtesting")
        
        # Generate signals
        signals = strategy_func(data, **strategy_params)
        
        # Simulate trading
        trades = self._simulate_trades(data, signals)
        
        # Calculate metrics
        metrics = self._calculate_metrics(trades, data)
        
        return BacktestResult(
            symbol=symbol,
            strategy=strategy_params.get('name', 'unknown'),
            start_date=str(data['date'].iloc[0]),
            end_date=str(data['date'].iloc[-1]),
            total_trades=metrics['total_trades'],
            winning_trades=metrics['winning_trades'],
            losing_trades=metrics['losing_trades'],
            win_rate=metrics['win_rate'],
            total_return=metrics['total_return'],
            annualized_return=metrics['annualized_return'],
            max_drawdown=metrics['max_drawdown'],
            sharpe_ratio=metrics['sharpe_ratio'],
            sortino_ratio=metrics['sortino_ratio'],
            profit_factor=metrics['profit_factor'],
            avg_win=metrics['avg_win'],
            avg_loss=metrics['avg_loss'],
            avg_r_multiple=metrics['avg_r_multiple'],
            trades=trades
        )
    
    def _simulate_trades(
        self,
        data: pd.DataFrame,
        signals: pd.Series
    ) -> List[Dict[str, Any]]:
        """Simulate trades based on signals."""
        trades = []
        position = None
        entry_price = 0
        entry_date = None
        stop_loss = 0
        take_profit = 0
        
        for i in range(len(data)):
            current_date = data['date'].iloc[i]
            current_price = data['close'].iloc[i]
            signal = signals.iloc[i] if i < len(signals) else 0
            
            # Entry
            if position is None and signal == 1:  # Buy signal
                position = 'LONG'
                entry_price = current_price * (1 + self.slippage)
                entry_date = current_date
                # Calculate SL/TP based on ATR
                if i > 14:
                    atr = self._calculate_atr(data.iloc[:i+1])
                    stop_loss = entry_price * (1 - atr * 1.5)
                    take_profit = entry_price * (1 + atr * 2.5)
                else:
                    stop_loss = entry_price * 0.95
                    take_profit = entry_price * 1.05
            
            # Exit
            elif position == 'LONG':
                exit_price = None
                exit_reason = None
                
                # Check stop loss
                if current_price <= stop_loss:
                    exit_price = stop_loss
                    exit_reason = 'stop_loss'
                # Check take profit
                elif current_price >= take_profit:
                    exit_price = take_profit
                    exit_reason = 'take_profit'
                # Check sell signal
                elif signal == -1:
                    exit_price = current_price * (1 - self.slippage)
                    exit_reason = 'signal'
                # End of data
                elif i == len(data) - 1:
                    exit_price = current_price * (1 - self.slippage)
                    exit_reason = 'end_of_data'
                
                if exit_price:
                    # Calculate P&L
                    pnl_pct = (exit_price - entry_price) / entry_price - self.commission
                    pnl = self.initial_capital * pnl_pct * 0.1  # 10% position size
                    
                    trades.append({
                        'entry_date': str(entry_date),
                        'exit_date': str(current_date),
                        'entry_price': entry_price,
                        'exit_price': exit_price,
                        'pnl_pct': pnl_pct,
                        'pnl': pnl,
                        'exit_reason': exit_reason
                    })
                    
                    position = None
                    entry_price = 0
                    entry_date = None
        
        return trades
    
    def _calculate_atr(self, data: pd.DataFrame, window: int = 14) -> float:
        """Calculate Average True Range."""
        high_low = data['high'] - data['low']
        high_close = np.abs(data['high'] - data['close'].shift())
        low_close = np.abs(data['low'] - data['close'].shift())
        
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        
        return true_range.rolling(window=window).mean().iloc[-1]
    
    def _calculate_metrics(
        self,
        trades: List[Dict],
        data: pd.DataFrame
    ) -> Dict[str, float]:
        """Calculate comprehensive backtest metrics."""
        if not trades:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0,
                'total_return': 0,
                'annualized_return': 0,
                'max_drawdown': 0,
                'sharpe_ratio': 0,
                'sortino_ratio': 0,
                'profit_factor': 0,
                'avg_win': 0,
                'avg_loss': 0,
                'avg_r_multiple': 0
            }
        
        # Basic metrics
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t['pnl'] > 0)
        losing_trades = total_trades - winning_trades
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        # Returns
        total_pnl = sum(t['pnl'] for t in trades)
        total_return = total_pnl / self.initial_capital
        
        # Annualized return
        days = (data['date'].iloc[-1] - data['date'].iloc[0]).days
        years = days / 365.25
        annualized_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
        
        # Drawdown
        equity_curve = [self.initial_capital]
        for trade in trades:
            equity_curve.append(equity_curve[-1] + trade['pnl'])
        
        peak = equity_curve[0]
        max_drawdown = 0
        for equity in equity_curve:
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak
            if dd > max_drawdown:
                max_drawdown = dd
        
        # Sharpe Ratio
        returns = [t['pnl'] / self.initial_capital for t in trades]
        if len(returns) > 1:
            sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0
        else:
            sharpe_ratio = 0
        
        # Sortino Ratio
        downside_returns = [r for r in returns if r < 0]
        if len(downside_returns) > 1:
            downside_std = np.std(downside_returns)
            sortino_ratio = np.mean(returns) / downside_std * np.sqrt(252) if downside_std > 0 else 0
        else:
            sortino_ratio = 0
        
        # Profit Factor
        gross_profit = sum(t['pnl'] for t in trades if t['pnl'] > 0)
        gross_loss = abs(sum(t['pnl'] for t in trades if t['pnl'] < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        # Average Win/Loss
        wins = [t['pnl'] for t in trades if t['pnl'] > 0]
        losses = [t['pnl'] for t in trades if t['pnl'] < 0]
        avg_win = np.mean(wins) if wins else 0
        avg_loss = np.mean(losses) if losses else 0
        
        # Average R:Multiple
        avg_r_multiple = avg_win / abs(avg_loss) if avg_loss != 0 else 0
        
        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'total_return': total_return,
            'annualized_return': annualized_return,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'profit_factor': profit_factor,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'avg_r_multiple': avg_r_multiple
        }
    
    def run_walk_forward_analysis(
        self,
        data: pd.DataFrame,
        strategy_func: callable,
        strategy_params: Dict[str, Any],
        in_sample_months: int = 12,
        out_sample_months: int = 3
    ) -> List[BacktestResult]:
        """
        Run walk-forward analysis (rolling backtest).
        
        Args:
            data: Historical data
            strategy_func: Strategy function
            strategy_params: Strategy parameters
            in_sample_months: In-sample period in months
            out_sample_months: Out-of-sample period in months
        
        Returns:
            List of backtest results for each walk-forward window
        """
        results = []
        total_months = (data['date'].iloc[-1] - data['date'].iloc[0]).days / 30
        
        start_idx = 0
        window = 0
        
        while start_idx + in_sample_months + out_sample_months < total_months:
            # In-sample period
            in_sample_end = start_idx + in_sample_months
            in_sample_data = data.iloc[start_idx:in_sample_end]
            
            # Out-of-sample period
            out_sample_end = in_sample_end + out_sample_months
            out_sample_data = data.iloc[in_sample_end:out_sample_end]
            
            if len(out_sample_data) < 10:
                break
            
            # Run backtest on out-of-sample
            result = self.run_backtest(
                out_sample_data,
                strategy_func,
                strategy_params,
                f"WALK_FORWARD_{window}"
            )
            results.append(result)
            
            # Move window
            start_idx += out_sample_months
            window += 1
        
        return results
    
    def run_multi_strategy_comparison(
        self,
        data: pd.DataFrame,
        strategies: Dict[str, Tuple[callable, Dict[str, Any]]]
    ) -> Dict[str, BacktestResult]:
        """
        Compare multiple strategies on the same data.
        
        Args:
            data: Historical data
            strategies: Dict of {name: (strategy_func, params)}
        
        Returns:
            Dict of {strategy_name: BacktestResult}
        """
        results = {}
        
        for name, (func, params) in strategies.items():
            params['name'] = name
            try:
                result = self.run_backtest(data, func, params, name)
                results[name] = result
            except Exception as e:
                print(f"Error backtesting {name}: {e}")
        
        return results
    
    def generate_report(self, result: BacktestResult) -> str:
        """Generate a readable backtest report."""
        report = f"""
Backtest Report for {result.symbol}
================================
Strategy: {result.strategy}
Period: {result.start_date} to {result.end_date}

Performance Metrics:
- Total Trades: {result.total_trades}
- Winning Trades: {result.winning_trades}
- Losing Trades: {result.losing_trades}
- Win Rate: {result.win_rate:.2%}
- Total Return: {result.total_return:.2%}
- Annualized Return: {result.annualized_return:.2%}
- Max Drawdown: {result.max_drawdown:.2%}
- Sharpe Ratio: {result.sharpe_ratio:.2f}
- Sortino Ratio: {result.sortino_ratio:.2f}
- Profit Factor: {result.profit_factor:.2f}
- Average Win: ${result.avg_win:.2f}
- Average Loss: ${result.avg_loss:.2f}
- Average R:Multiple: {result.avg_r_multiple:.2f}
"""
        return report
