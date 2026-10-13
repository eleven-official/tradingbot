"""
Advanced Performance Analytics for Trading Bot
Provides sophisticated performance analysis and reporting
"""
import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
from collections import defaultdict
import json


@dataclass
class PerformanceReport:
    """Comprehensive performance report."""
    period: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    scratch_trades: int
    total_pnl: float
    win_rate: float
    profit_factor: float
    average_win: float
    average_loss: float
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    average_holding_time_hours: float
    best_trade: float
    worst_trade: float
    consecutive_wins_max: int
    consecutive_losses_max: int
    daily_pnl_series: List[float]
    weekly_pnl_series: List[float]
    strategy_performance: Dict[str, Dict[str, Any]]
    recommendations: List[str]


class AdvancedPerformanceAnalytics:
    """Advanced performance analytics and reporting system."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.analytics_config = config.get('advanced_analytics', {})
        
        # Analytics settings
        self.enabled = self.analytics_config.get('enabled', True)
        self.auto_report_generation = self.analytics_config.get('auto_report_generation', True)
        self.performance_thresholds = self.analytics_config.get('performance_thresholds', {
            'min_win_rate': 45.0,
            'min_profit_factor': 1.5,
            'max_drawdown_percent': 10.0
        })
        
        # Data storage
        self.trade_history: List[Dict[str, Any]] = []
        self.equity_curve: List[float] = []
        self.daily_performance: Dict[str, float] = {}
        self.weekly_performance: Dict[str, float] = {}
        
        # Analysis state
        self.last_analysis_date: Optional[datetime] = None
        self.analysis_frequency_days = self.analytics_config.get('analysis_frequency_days', 7)
        
        logging.info("Advanced Performance Analytics initialized")
    
    def record_trade(self, trade_result: Dict[str, Any]):
        """Record a trade for performance analysis."""
        if not self.enabled:
            return
        
        # Add timestamp if not present
        if 'timestamp' not in trade_result:
            trade_result['timestamp'] = datetime.now().isoformat()
        
        self.trade_history.append(trade_result)
        
        # Update equity curve
        pnl = trade_result.get('net', 0)
        if self.equity_curve:
            self.equity_curve.append(self.equity_curve[-1] + pnl)
        else:
            self.equity_curve.append(pnl)
        
        # Update daily performance
        trade_date = datetime.now().date().isoformat()
        self.daily_performance[trade_date] = self.daily_performance.get(trade_date, 0) + pnl
        
        logging.debug(f"Trade recorded for analytics: {pnl:.2f} AUD")
    
    def generate_performance_report(self, period_days: int = 30) -> PerformanceReport:
        """Generate comprehensive performance report for specified period."""
        try:
            if not self.trade_history:
                return self._empty_report()
            
            # Filter trades by period
            cutoff_date = datetime.now() - timedelta(days=period_days)
            recent_trades = [
                trade for trade in self.trade_history
                if datetime.fromisoformat(trade['timestamp']) >= cutoff_date
            ]
            
            if not recent_trades:
                return self._empty_report()
            
            # Calculate basic metrics
            total_trades = len(recent_trades)
            winning_trades = sum(1 for t in recent_trades if t.get('net', 0) > 0)
            losing_trades = sum(1 for t in recent_trades if t.get('net', 0) < 0)
            scratch_trades = sum(1 for t in recent_trades if t.get('net', 0) == 0)
            
            total_pnl = sum(t.get('net', 0) for t in recent_trades)
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            # Calculate profit factor
            wins = [t.get('net', 0) for t in recent_trades if t.get('net', 0) > 0]
            losses = [abs(t.get('net', 0)) for t in recent_trades if t.get('net', 0) < 0]
            
            average_win = sum(wins) / len(wins) if wins else 0
            average_loss = sum(losses) / len(losses) if losses else 0
            profit_factor = sum(wins) / sum(losses) if losses else float('inf')
            
            # Calculate drawdown
            max_drawdown = self._calculate_max_drawdown(self.equity_curve)
            
            # Calculate ratios
            sharpe_ratio = self._calculate_sharpe_ratio(recent_trades)
            sortino_ratio = self._calculate_sortino_ratio(recent_trades)
            calmar_ratio = self._calculate_calmar_ratio(recent_trades, max_drawdown)
            
            # Calculate holding time
            holding_times = []
            for i, trade in enumerate(recent_trades):
                if 'entry_time' in trade and 'exit_time' in trade:
                    entry = datetime.fromisoformat(trade['entry_time'])
                    exit = datetime.fromisoformat(trade['exit_time'])
                    holding_times.append((exit - entry).total_seconds() / 3600)
            
            average_holding_time = sum(holding_times) / len(holding_times) if holding_times else 0
            
            # Best and worst trades
            pnls = [t.get('net', 0) for t in recent_trades]
            best_trade = max(pnls) if pnls else 0
            worst_trade = min(pnls) if pnls else 0
            
            # Consecutive wins/losses
            consecutive_wins = self._calculate_consecutive_wins(recent_trades)
            consecutive_losses = self._calculate_consecutive_losses(recent_trades)
            
            # Strategy performance
            strategy_performance = self._analyze_strategy_performance(recent_trades)
            
            # Generate recommendations
            recommendations = self._generate_recommendations(
                win_rate, profit_factor, max_drawdown, consecutive_losses
            )
            
            return PerformanceReport(
                period=f"{period_days} days",
                total_trades=total_trades,
                winning_trades=winning_trades,
                losing_trades=losing_trades,
                scratch_trades=scratch_trades,
                total_pnl=total_pnl,
                win_rate=win_rate,
                profit_factor=profit_factor,
                average_win=average_win,
                average_loss=average_loss,
                max_drawdown=max_drawdown,
                sharpe_ratio=sharpe_ratio,
                sortino_ratio=sortino_ratio,
                calmar_ratio=calmar_ratio,
                average_holding_time_hours=average_holding_time,
                best_trade=best_trade,
                worst_trade=worst_trade,
                consecutive_wins_max=max(consecutive_wins) if consecutive_wins else 0,
                consecutive_losses_max=max(consecutive_losses) if consecutive_losses else 0,
                daily_pnl_series=list(self.daily_performance.values()),
                weekly_pnl_series=list(self.weekly_performance.values()),
                strategy_performance=strategy_performance,
                recommendations=recommendations
            )
            
        except Exception as e:
            logging.error(f"Performance report generation error: {e}")
            return self._empty_report()
    
    def _empty_report(self) -> PerformanceReport:
        """Return empty performance report."""
        return PerformanceReport(
            period="No data",
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            scratch_trades=0,
            total_pnl=0.0,
            win_rate=0.0,
            profit_factor=0.0,
            average_win=0.0,
            average_loss=0.0,
            max_drawdown=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            calmar_ratio=0.0,
            average_holding_time_hours=0.0,
            best_trade=0.0,
            worst_trade=0.0,
            consecutive_wins_max=0,
            consecutive_losses_max=0,
            daily_pnl_series=[],
            weekly_pnl_series=[],
            strategy_performance={},
            recommendations=["No trading data available"]
        )
    
    def _calculate_max_drawdown(self, equity_curve: List[float]) -> float:
        """Calculate maximum drawdown from equity curve."""
        if not equity_curve:
            return 0.0
        
        peak = equity_curve[0]
        max_drawdown = 0.0
        
        for value in equity_curve:
            if value > peak:
                peak = value
            drawdown = peak - value
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        return max_drawdown
    
    def _calculate_sharpe_ratio(self, trades: List[Dict[str, Any]], risk_free_rate: float = 0.02) -> float:
        """Calculate Sharpe ratio (risk-adjusted returns)."""
        try:
            if not trades:
                return 0.0
            
            returns = [t.get('net', 0) for t in trades]
            excess_returns = [r - risk_free_rate for r in returns]
            
            if not excess_returns:
                return 0.0
            
            std_dev = np.std(excess_returns)
            if std_dev == 0:
                return 0.0
            
            sharpe = np.mean(excess_returns) / std_dev
            return sharpe * np.sqrt(252)  # Annualized
            
        except Exception as e:
            logging.error(f"Sharpe ratio calculation error: {e}")
            return 0.0
    
    def _calculate_sortino_ratio(self, trades: List[Dict[str, Any]], risk_free_rate: float = 0.02) -> float:
        """Calculate Sortino ratio (downside risk-adjusted returns)."""
        try:
            if not trades:
                return 0.0
            
            returns = [t.get('net', 0) for t in trades]
            excess_returns = [r - risk_free_rate for r in returns]
            downside_returns = [r for r in excess_returns if r < 0]
            
            if not downside_returns:
                return float('inf') if any(r > 0 for r in excess_returns) else 0.0
            
            downside_dev = np.std(downside_returns)
            if downside_dev == 0:
                return float('inf') if any(r > 0 for r in excess_returns) else 0.0
            
            sortino = np.mean(excess_returns) / downside_dev
            return sortino * np.sqrt(252)  # Annualized
            
        except Exception as e:
            logging.error(f"Sortino ratio calculation error: {e}")
            return 0.0
    
    def _calculate_calmar_ratio(self, trades: List[Dict[str, Any]], max_drawdown: float) -> float:
        """Calculate Calmar ratio (drawdown-adjusted returns)."""
        try:
            if not trades or max_drawdown == 0:
                return 0.0
            
            total_return = sum(t.get('net', 0) for t in trades)
            calmar = total_return / max_drawdown
            return calmar
            
        except Exception as e:
            logging.error(f"Calmar ratio calculation error: {e}")
            return 0.0
    
    def _calculate_consecutive_wins(self, trades: List[Dict[str, Any]]) -> List[int]:
        """Calculate consecutive win streaks."""
        streaks = []
        current_streak = 0
        
        for trade in trades:
            pnl = trade.get('net', 0)
            if pnl > 0:
                current_streak += 1
            else:
                if current_streak > 0:
                    streaks.append(current_streak)
                current_streak = 0
        
        if current_streak > 0:
            streaks.append(current_streak)
        
        return streaks
    
    def _calculate_consecutive_losses(self, trades: List[Dict[str, Any]]) -> List[int]:
        """Calculate consecutive loss streaks."""
        streaks = []
        current_streak = 0
        
        for trade in trades:
            pnl = trade.get('net', 0)
            if pnl < 0:
                current_streak += 1
            else:
                if current_streak > 0:
                    streaks.append(current_streak)
                current_streak = 0
        
        if current_streak > 0:
            streaks.append(current_streak)
        
        return streaks
    
    def _analyze_strategy_performance(self, trades: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Analyze performance by strategy."""
        strategy_data = defaultdict(lambda: {
            'trades': 0, 'wins': 0, 'losses': 0, 'total_pnl': 0,
            'best_trade': 0, 'worst_trade': 0
        })
        
        for trade in trades:
            strategy = trade.get('strategy', 'unknown')
            pnl = trade.get('net', 0)
            
            strategy_data[strategy]['trades'] += 1
            strategy_data[strategy]['total_pnl'] += pnl
            
            if pnl > 0:
                strategy_data[strategy]['wins'] += 1
                strategy_data[strategy]['best_trade'] = max(strategy_data[strategy]['best_trade'], pnl)
            elif pnl < 0:
                strategy_data[strategy]['losses'] += 1
                strategy_data[strategy]['worst_trade'] = min(strategy_data[strategy]['worst_trade'], pnl)
        
        # Calculate derived metrics
        strategy_summary = {}
        for strategy, data in strategy_data.items():
            total = data['trades']
            if total > 0:
                win_rate = (data['wins'] / total * 100)
                avg_pnl = data['total_pnl'] / total
            else:
                win_rate = 0
                avg_pnl = 0
            
            strategy_summary[strategy] = {
                'trades': total,
                'wins': data['wins'],
                'losses': data['losses'],
                'win_rate': win_rate,
                'total_pnl': data['total_pnl'],
                'average_pnl': avg_pnl,
                'best_trade': data['best_trade'],
                'worst_trade': data['worst_trade']
            }
        
        return strategy_summary
    
    def _generate_recommendations(self, win_rate: float, profit_factor: float, 
                              max_drawdown: float, consecutive_losses: List[int]) -> List[str]:
        """Generate trading recommendations based on performance."""
        recommendations = []
        
        thresholds = self.performance_thresholds
        
        # Win rate analysis
        if win_rate < thresholds['min_win_rate']:
            recommendations.append(f"⚠️ Win rate ({win_rate:.1f}%) below threshold ({thresholds['min_win_rate']}%). Consider reviewing strategy.")
        elif win_rate > 70:
            recommendations.append("✅ Excellent win rate. Consider increasing position size slightly.")
        
        # Profit factor analysis
        if profit_factor < thresholds['min_profit_factor']:
            recommendations.append(f"⚠️ Profit factor ({profit_factor:.2f}) below threshold ({thresholds['min_profit_factor']}). Review risk/reward ratio.")
        elif profit_factor > 3.0:
            recommendations.append("✅ Strong profit factor. Strategy is working well.")
        
        # Drawdown analysis
        if max_drawdown > thresholds['max_drawdown_percent']:
            recommendations.append(f"⚠️ Max drawdown ({max_drawdown:.1f}%) exceeds threshold ({thresholds['max_drawdown_percent']}). Consider reducing risk.")
        
        # Consecutive losses analysis
        if consecutive_losses and max(consecutive_losses) >= 3:
            recommendations.append(f"⚠️ {max(consecutive_losses)} consecutive losses detected. Consider taking a break.")
        
        # Overall assessment
        if win_rate > thresholds['min_win_rate'] and profit_factor > thresholds['min_profit_factor']:
            recommendations.append("✅ Overall performance is good. Continue current approach.")
        
        return recommendations
    
    def export_report(self, report: PerformanceReport, filepath: str):
        """Export performance report to file."""
        try:
            report_dict = {
                'period': report.period,
                'total_trades': report.total_trades,
                'winning_trades': report.winning_trades,
                'losing_trades': report.losing_trades,
                'scratch_trades': report.scratch_trades,
                'total_pnl': report.total_pnl,
                'win_rate': report.win_rate,
                'profit_factor': report.profit_factor,
                'average_win': report.average_win,
                'average_loss': report.average_loss,
                'max_drawdown': report.max_drawdown,
                'sharpe_ratio': report.sharpe_ratio,
                'sortino_ratio': report.sortino_ratio,
                'calmar_ratio': report.calmar_ratio,
                'average_holding_time_hours': report.average_holding_time_hours,
                'best_trade': report.best_trade,
                'worst_trade': report.worst_trade,
                'consecutive_wins_max': report.consecutive_wins_max,
                'consecutive_losses_max': report.consecutive_losses_max,
                'daily_pnl_series': report.daily_pnl_series,
                'weekly_pnl_series': report.weekly_pnl_series,
                'strategy_performance': report.strategy_performance,
                'recommendations': report.recommendations,
                'generated_at': datetime.now().isoformat()
            }
            
            with open(filepath, 'w') as f:
                json.dump(report_dict, f, indent=2)
            
            logging.info(f"Performance report exported to {filepath}")
            
        except Exception as e:
            logging.error(f"Failed to export report: {e}")
    
    def get_equity_curve_data(self) -> Dict[str, Any]:
        """Get equity curve data for visualization."""
        return {
            'equity_curve': self.equity_curve,
            'trade_count': len(self.trade_history),
            'current_equity': self.equity_curve[-1] if self.equity_curve else 0,
            'peak_equity': max(self.equity_curve) if self.equity_curve else 0,
            'total_return': (self.equity_curve[-1] - self.equity_curve[0]) if len(self.equity_curve) > 1 else 0
        }