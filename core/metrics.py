"""
Metrics collection and monitoring for the trading bot.
"""
import time
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from collections import deque


class MetricsCollector:
    """Collects and aggregates trading metrics for monitoring and analysis."""
    
    def __init__(self, config):
        self.config = config
        self.metrics_enabled = config.get('metrics', {}).get('enabled', True)
        
        # Trade metrics
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.scratch_trades = 0
        
        # Performance metrics
        self.total_pnl = 0.0
        self.best_trade = 0.0
        self.worst_trade = 0.0
        self.average_win = 0.0
        self.average_loss = 0.0
        
        # Timing metrics
        self.order_latencies = deque(maxlen=100)
        self.signal_generation_times = deque(maxlen=100)
        
        # Strategy performance tracking
        self.strategy_performance: Dict[str, Dict[str, Any]] = {}
        
        # Session metrics
        self.session_start = datetime.now()
        self.last_trade_time = None
        
        # Risk metrics
        self.max_drawdown = 0.0
        self.current_drawdown = 0.0
        self.peak_equity = 0.0
    
    def record_trade(self, trade_result: Dict[str, Any]):
        """Record metrics for a completed trade."""
        if not self.metrics_enabled:
            return
        
        self.total_trades += 1
        pnl = trade_result.get('net', 0)
        strategy = trade_result.get('strategy', 'unknown')
        
        # Update basic trade counts
        if pnl > 0:
            self.winning_trades += 1
            self.best_trade = max(self.best_trade, pnl)
        elif pnl < 0:
            self.losing_trades += 1
            self.worst_trade = min(self.worst_trade, pnl)
        else:
            self.scratch_trades += 1
        
        # Update P&L metrics
        self.total_pnl += pnl
        self.last_trade_time = datetime.now()
        
        # Update averages
        if pnl > 0:
            self.average_win = ((self.average_win * (self.winning_trades - 1)) + pnl) / self.winning_trades
        elif pnl < 0:
            self.average_loss = ((self.average_loss * (self.losing_trades - 1)) + pnl) / self.losing_trades
        
        # Update strategy performance
        if strategy not in self.strategy_performance:
            self.strategy_performance[strategy] = {
                'trades': 0,
                'wins': 0,
                'losses': 0,
                'total_pnl': 0.0,
                'best_trade': 0.0,
                'worst_trade': 0.0
            }
        
        strat_metrics = self.strategy_performance[strategy]
        strat_metrics['trades'] += 1
        strat_metrics['total_pnl'] += pnl
        
        if pnl > 0:
            strat_metrics['wins'] += 1
            strat_metrics['best_trade'] = max(strat_metrics['best_trade'], pnl)
        elif pnl < 0:
            strat_metrics['losses'] += 1
            strat_metrics['worst_trade'] = min(strat_metrics['worst_trade'], pnl)
        
        # Update drawdown
        self._update_drawdown(pnl)
    
    def record_order_latency(self, latency_seconds: float):
        """Record order placement latency."""
        if self.metrics_enabled:
            self.order_latencies.append(latency_seconds)
    
    def record_signal_time(self, generation_time_seconds: float):
        """Record signal generation time."""
        if self.metrics_enabled:
            self.signal_generation_times.append(generation_time_seconds)
    
    def _update_drawdown(self, pnl: float):
        """Update drawdown metrics based on current P&L."""
        current_equity = self.total_pnl
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity
            self.current_drawdown = 0.0
        else:
            self.current_drawdown = self.peak_equity - current_equity
            self.max_drawdown = max(self.max_drawdown, self.current_drawdown)
    
    def get_win_rate(self) -> float:
        """Calculate current win rate."""
        total = self.winning_trades + self.losing_trades
        if total == 0:
            return 0.0
        return (self.winning_trades / total) * 100
    
    def get_profit_factor(self) -> float:
        """Calculate profit factor (gross wins / gross losses)."""
        gross_wins = self.average_win * self.winning_trades
        gross_losses = abs(self.average_loss * self.losing_trades)
        if gross_losses == 0:
            return float('inf') if gross_wins > 0 else 0.0
        return gross_wins / gross_losses
    
    def get_average_order_latency(self) -> Optional[float]:
        """Get average order latency."""
        if not self.order_latencies:
            return None
        return sum(self.order_latencies) / len(self.order_latencies)
    
    def get_average_signal_time(self) -> Optional[float]:
        """Get average signal generation time."""
        if not self.signal_generation_times:
            return None
        return sum(self.signal_generation_times) / len(self.signal_generation_times)
    
    def get_strategy_summary(self) -> Dict[str, Dict[str, Any]]:
        """Get summary of strategy performance."""
        summary = {}
        for strategy, metrics in self.strategy_performance.items():
            total = metrics['wins'] + metrics['losses']
            win_rate = (metrics['wins'] / total * 100) if total > 0 else 0
            avg_pnl = metrics['total_pnl'] / metrics['trades'] if metrics['trades'] > 0 else 0
            
            summary[strategy] = {
                'trades': metrics['trades'],
                'win_rate': win_rate,
                'total_pnl': metrics['total_pnl'],
                'average_pnl': avg_pnl,
                'best_trade': metrics['best_trade'],
                'worst_trade': metrics['worst_trade']
            }
        
        return summary
    
    def get_session_summary(self) -> Dict[str, Any]:
        """Get comprehensive session metrics summary."""
        duration = (datetime.now() - self.session_start).total_seconds()
        
        return {
            'session_duration_seconds': duration,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'scratch_trades': self.scratch_trades,
            'win_rate': self.get_win_rate(),
            'total_pnl': self.total_pnl,
            'best_trade': self.best_trade,
            'worst_trade': self.worst_trade,
            'average_win': self.average_win,
            'average_loss': self.average_loss,
            'profit_factor': self.get_profit_factor(),
            'max_drawdown': self.max_drawdown,
            'current_drawdown': self.current_drawdown,
            'average_order_latency': self.get_average_order_latency(),
            'average_signal_time': self.get_average_signal_time(),
            'strategy_performance': self.get_strategy_summary()
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get health status for monitoring."""
        return {
            'healthy': True,
            'session_active': True,
            'session_duration': (datetime.now() - self.session_start).total_seconds(),
            'trades_today': self.total_trades,
            'last_trade_time': self.last_trade_time.isoformat() if self.last_trade_time else None,
            'current_pnl': self.total_pnl,
            'drawdown': self.current_drawdown,
            'metrics_enabled': self.metrics_enabled
        }
    
    def reset_metrics(self):
        """Reset all metrics (for new session)."""
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.scratch_trades = 0
        self.total_pnl = 0.0
        self.best_trade = 0.0
        self.worst_trade = 0.0
        self.average_win = 0.0
        self.average_loss = 0.0
        self.order_latencies.clear()
        self.signal_generation_times.clear()
        self.strategy_performance.clear()
        self.session_start = datetime.now()
        self.last_trade_time = None
        self.max_drawdown = 0.0
        self.current_drawdown = 0.0
        self.peak_equity = 0.0
        
        logging.info("Metrics reset for new session")


class MetricsTimer:
    """Context manager for timing operations."""
    
    def __init__(self, metrics_collector: MetricsCollector, operation_name: str):
        self.metrics_collector = metrics_collector
        self.operation_name = operation_name
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time is not None:
            elapsed = time.time() - self.start_time
            if self.operation_name == 'order':
                self.metrics_collector.record_order_latency(elapsed)
            elif self.operation_name == 'signal':
                self.metrics_collector.record_signal_time(elapsed)
            
            logging.debug(f"{self.operation_name} took {elapsed:.3f}s")
        return False