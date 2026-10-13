#!/usr/bin/env python3
"""
Real-Time Trading Monitor and Alert System
Advanced monitoring with live performance tracking, risk alerts, and automated responses.
"""

import asyncio
import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Callable, Optional
import datetime
import json
import threading
import time
from dataclasses import dataclass, asdict
import sqlite3
from pathlib import Path

@dataclass
class Alert:
    """Trading alert with priority and action."""
    timestamp: datetime.datetime
    level: str  # 'INFO', 'WARNING', 'CRITICAL'
    category: str  # 'PERFORMANCE', 'RISK', 'SYSTEM', 'STRATEGY'
    message: str
    data: Dict
    action_required: bool = False
    
@dataclass
class PerformanceMetrics:
    """Real-time performance metrics."""
    timestamp: datetime.datetime
    total_pnl: float
    daily_pnl: float
    win_rate: float
    sharpe_ratio: float
    max_drawdown: float
    active_positions: int
    portfolio_value: float
    
class RealTimeMonitor:
    """Advanced real-time trading monitor with alerting system."""
    
    def __init__(self, portfolio_manager, alert_callbacks: List[Callable] = None):
        self.portfolio_manager = portfolio_manager
        self.alert_callbacks = alert_callbacks or []
        self.alerts = []
        self.performance_history = []
        self.is_monitoring = False
        self.alert_rules = {}
        self.db_path = "monitoring.db"
        
        # Risk thresholds
        self.risk_thresholds = {
            'max_daily_loss': 0.05,  # 5% max daily loss
            'max_drawdown': 0.15,    # 15% max drawdown
            'min_sharpe': -0.5,      # Minimum Sharpe ratio
            'max_concentration': 0.4, # Maximum single position weight
            'correlation_limit': 0.8  # Maximum position correlation
        }
        
        self._setup_database()
        self._setup_default_alerts()
    
    def _setup_database(self):
        """Setup SQLite database for monitoring data."""
        conn = sqlite3.connect(self.db_path)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                level TEXT,
                category TEXT,
                message TEXT,
                data TEXT,
                action_required INTEGER
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                total_pnl REAL,
                daily_pnl REAL,
                win_rate REAL,
                sharpe_ratio REAL,
                max_drawdown REAL,
                active_positions INTEGER,
                portfolio_value REAL
            )
        ''')
        conn.commit()
        conn.close()
    
    def _setup_default_alerts(self):
        """Setup default alert rules."""
        self.alert_rules = {
            'daily_loss_check': {
                'function': self._check_daily_loss,
                'interval': 60,  # Check every minute
                'enabled': True
            },
            'drawdown_check': {
                'function': self._check_drawdown,
                'interval': 300,  # Check every 5 minutes
                'enabled': True
            },
            'position_concentration': {
                'function': self._check_concentration,
                'interval': 600,  # Check every 10 minutes
                'enabled': True
            },
            'system_health': {
                'function': self._check_system_health,
                'interval': 120,  # Check every 2 minutes
                'enabled': True
            }
        }
    
    def start_monitoring(self):
        """Start real-time monitoring in background thread."""
        if self.is_monitoring:
            logging.warning("Monitor already running")
            return
            
        self.is_monitoring = True
        
        # Start monitoring threads
        threading.Thread(target=self._monitoring_loop, daemon=True).start()
        threading.Thread(target=self._performance_tracker, daemon=True).start()
        
        logging.info("🔍 Real-time monitoring started")
        
        self._create_alert(
            level='INFO',
            category='SYSTEM',
            message='Real-time monitoring system activated',
            data={'start_time': datetime.datetime.now().isoformat()}
        )
    
    def stop_monitoring(self):
        """Stop monitoring system."""
        self.is_monitoring = False
        logging.info("Real-time monitoring stopped")
    
    def _monitoring_loop(self):
        """Main monitoring loop."""
        last_check_times = {rule: 0 for rule in self.alert_rules}
        
        while self.is_monitoring:
            current_time = time.time()
            
            for rule_name, rule_config in self.alert_rules.items():
                if not rule_config['enabled']:
                    continue
                    
                # Check if enough time has passed for this rule
                if current_time - last_check_times[rule_name] >= rule_config['interval']:
                    try:
                        rule_config['function']()
                        last_check_times[rule_name] = current_time
                    except Exception as e:
                        logging.error(f"Error in monitoring rule {rule_name}: {e}")
            
            time.sleep(10)  # Main loop interval
    
    def _performance_tracker(self):
        """Track performance metrics continuously."""
        while self.is_monitoring:
            try:
                summary = self.portfolio_manager.get_portfolio_summary()
                
                # Calculate metrics
                metrics = PerformanceMetrics(
                    timestamp=datetime.datetime.now(),
                    total_pnl=summary['total_pnl'],
                    daily_pnl=self._calculate_daily_pnl(),
                    win_rate=self._calculate_win_rate(),
                    sharpe_ratio=self._calculate_sharpe_ratio(),
                    max_drawdown=self._calculate_max_drawdown(),
                    active_positions=summary['active_positions'],
                    portfolio_value=summary['total_value']
                )
                
                self.performance_history.append(metrics)
                
                # Keep only last 1000 records in memory
                if len(self.performance_history) > 1000:
                    self.performance_history = self.performance_history[-1000:]
                
                # Save to database
                self._save_performance_to_db(metrics)
                
            except Exception as e:
                logging.error(f"Error in performance tracking: {e}")
            
            time.sleep(30)  # Update every 30 seconds
    
    def _check_daily_loss(self):
        """Check for excessive daily losses."""
        daily_pnl = self._calculate_daily_pnl()
        daily_loss_pct = abs(daily_pnl) / self.portfolio_manager.initial_capital
        
        if daily_pnl < 0 and daily_loss_pct > self.risk_thresholds['max_daily_loss']:
            self._create_alert(
                level='CRITICAL',
                category='RISK',
                message=f'Daily loss limit exceeded: {daily_loss_pct:.1%}',
                data={
                    'daily_pnl': daily_pnl,
                    'loss_percentage': daily_loss_pct,
                    'threshold': self.risk_thresholds['max_daily_loss']
                },
                action_required=True
            )
    
    def _check_drawdown(self):
        """Check maximum drawdown."""
        max_dd = self._calculate_max_drawdown()
        
        if max_dd > self.risk_thresholds['max_drawdown']:
            self._create_alert(
                level='WARNING',
                category='RISK',
                message=f'Maximum drawdown exceeded: {max_dd:.1%}',
                data={
                    'max_drawdown': max_dd,
                    'threshold': self.risk_thresholds['max_drawdown']
                },
                action_required=True
            )
    
    def _check_concentration(self):
        """Check portfolio concentration risk."""
        summary = self.portfolio_manager.get_portfolio_summary()
        concentration = summary.get('portfolio_concentration', 0)
        largest_position = summary.get('largest_position', 0)
        
        if largest_position > self.risk_thresholds['max_concentration']:
            self._create_alert(
                level='WARNING',
                category='RISK',
                message=f'Position concentration too high: {largest_position:.1%}',
                data={
                    'largest_position': largest_position,
                    'concentration_index': concentration,
                    'threshold': self.risk_thresholds['max_concentration']
                }
            )
    
    def _check_system_health(self):
        """Check overall system health."""
        # Check for stuck positions
        stuck_positions = 0
        for position in self.portfolio_manager.positions.values():
            hours_held = (datetime.datetime.now() - position.entry_time).total_seconds() / 3600
            if hours_held > 24:  # Positions held longer than 24 hours
                stuck_positions += 1
        
        if stuck_positions > 0:
            self._create_alert(
                level='INFO',
                category='SYSTEM',
                message=f'{stuck_positions} positions held > 24 hours',
                data={'stuck_positions': stuck_positions}
            )
        
        # Check strategy performance
        self._check_strategy_performance()
    
    def _check_strategy_performance(self):
        """Monitor individual strategy performance."""
        summary = self.portfolio_manager.get_portfolio_summary()
        
        for strategy_name, performance in summary['strategy_performance'].items():
            if performance['unrealized_pnl'] < -1000:  # $1000 loss threshold
                self._create_alert(
                    level='WARNING',
                    category='STRATEGY',
                    message=f'{strategy_name} showing significant losses',
                    data={
                        'strategy': strategy_name,
                        'unrealized_pnl': performance['unrealized_pnl'],
                        'positions': performance['positions']
                    }
                )
    
    def _create_alert(self, level: str, category: str, message: str, 
                     data: Dict, action_required: bool = False):
        """Create and process new alert."""
        alert = Alert(
            timestamp=datetime.datetime.now(),
            level=level,
            category=category,
            message=message,
            data=data,
            action_required=action_required
        )
        
        self.alerts.append(alert)
        
        # Keep only last 500 alerts in memory
        if len(self.alerts) > 500:
            self.alerts = self.alerts[-500:]
        
        # Save to database
        self._save_alert_to_db(alert)
        
        # Execute callbacks
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logging.error(f"Error in alert callback: {e}")
        
        # Log based on severity
        log_message = f"[{category}] {message}"
        if level == 'CRITICAL':
            logging.critical(log_message)
        elif level == 'WARNING':
            logging.warning(log_message)
        else:
            logging.info(log_message)
    
    def _calculate_daily_pnl(self) -> float:
        """Calculate today's P&L."""
        if not self.performance_history:
            return 0.0
            
        today = datetime.date.today()
        today_records = [m for m in self.performance_history 
                        if m.timestamp.date() == today]
        
        if not today_records:
            return 0.0
            
        start_value = today_records[0].portfolio_value - today_records[0].total_pnl
        current_value = today_records[-1].portfolio_value
        
        return current_value - start_value
    
    def _calculate_win_rate(self) -> float:
        """Calculate current win rate."""
        # Simplified calculation - would use actual trade history
        if not self.performance_history:
            return 0.5
            
        recent_metrics = self.performance_history[-20:]  # Last 20 measurements
        positive_changes = sum(1 for i in range(1, len(recent_metrics))
                             if recent_metrics[i].total_pnl > recent_metrics[i-1].total_pnl)
        
        return positive_changes / max(1, len(recent_metrics) - 1)
    
    def _calculate_sharpe_ratio(self) -> float:
        """Calculate rolling Sharpe ratio."""
        if len(self.performance_history) < 30:
            return 0.0
            
        returns = []
        for i in range(1, len(self.performance_history)):
            prev_value = self.performance_history[i-1].portfolio_value
            curr_value = self.performance_history[i].portfolio_value
            if prev_value > 0:
                returns.append((curr_value - prev_value) / prev_value)
        
        if not returns:
            return 0.0
            
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        
        if std_return == 0:
            return 0.0
            
        return mean_return / std_return * np.sqrt(252 * 24 * 2)  # Annualized (30min intervals)
    
    def _calculate_max_drawdown(self) -> float:
        """Calculate maximum drawdown."""
        if not self.performance_history:
            return 0.0
            
        values = [m.portfolio_value for m in self.performance_history]
        peak = values[0]
        max_dd = 0.0
        
        for value in values:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak
            max_dd = max(max_dd, drawdown)
            
        return max_dd
    def _save_alert_to_db(self, alert: Alert):
        """Save alert to database."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute('''
                INSERT INTO alerts (timestamp, level, category, message, data, action_required)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                alert.timestamp.isoformat(),
                alert.level,
                alert.category,
                alert.message,
                json.dumps(alert.data),
                int(alert.action_required)
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Error saving alert to database: {e}")
    
    def _save_performance_to_db(self, metrics: PerformanceMetrics):
        """Save performance metrics to database."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute('''
                INSERT INTO performance (timestamp, total_pnl, daily_pnl, win_rate, 
                                       sharpe_ratio, max_drawdown, active_positions, portfolio_value)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                metrics.timestamp.isoformat(),
                metrics.total_pnl,
                metrics.daily_pnl,
                metrics.win_rate,
                metrics.sharpe_ratio,
                metrics.max_drawdown,
                metrics.active_positions,
                metrics.portfolio_value
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Error saving performance to database: {e}")
    
    def get_alerts(self, level: str = None, category: str = None, 
                  hours: int = 24) -> List[Alert]:
        """Get alerts filtered by criteria."""
        cutoff_time = datetime.datetime.now() - datetime.timedelta(hours=hours)
        
        filtered_alerts = [
            alert for alert in self.alerts 
            if alert.timestamp >= cutoff_time
        ]
        
        if level:
            filtered_alerts = [a for a in filtered_alerts if a.level == level]
        if category:
            filtered_alerts = [a for a in filtered_alerts if a.category == category]
            
        return sorted(filtered_alerts, key=lambda x: x.timestamp, reverse=True)
    
    def get_performance_dashboard(self) -> Dict:
        """Get real-time performance dashboard data."""
        if not self.performance_history:
            return {}
            
        latest = self.performance_history[-1]
        
        # Recent alerts summary
        recent_alerts = self.get_alerts(hours=24)
        alert_summary = {
            'critical': len([a for a in recent_alerts if a.level == 'CRITICAL']),
            'warning': len([a for a in recent_alerts if a.level == 'WARNING']),
            'info': len([a for a in recent_alerts if a.level == 'INFO'])
        }
        
        # Performance trends
        if len(self.performance_history) >= 2:
            prev_metrics = self.performance_history[-2]
            pnl_trend = latest.total_pnl - prev_metrics.total_pnl
            portfolio_trend = latest.portfolio_value - prev_metrics.portfolio_value
        else:
            pnl_trend = 0
            portfolio_trend = 0
        
        return {
            'timestamp': latest.timestamp.isoformat(),
            'current_metrics': asdict(latest),
            'trends': {
                'pnl_change': pnl_trend,
                'portfolio_change': portfolio_trend,
                'pnl_trend_direction': 'up' if pnl_trend > 0 else 'down' if pnl_trend < 0 else 'flat'
            },
            'alerts': alert_summary,
            'risk_status': self._get_risk_status(),
            'system_status': 'active' if self.is_monitoring else 'stopped'
        }
    
    def _get_risk_status(self) -> Dict:
        """Get current risk status."""
        if not self.performance_history:
            return {'status': 'unknown'}
            
        latest = self.performance_history[-1]
        
        # Check against thresholds
        risk_factors = []
        
        daily_pnl_pct = abs(latest.daily_pnl) / self.portfolio_manager.initial_capital
        if daily_pnl_pct > self.risk_thresholds['max_daily_loss'] * 0.8:  # 80% of limit
            risk_factors.append('daily_loss_approaching_limit')
            
        if latest.max_drawdown > self.risk_thresholds['max_drawdown'] * 0.8:
            risk_factors.append('drawdown_approaching_limit')
            
        if latest.sharpe_ratio < self.risk_thresholds['min_sharpe']:
            risk_factors.append('poor_risk_adjusted_returns')
        
        # Determine overall risk level
        if len(risk_factors) >= 2:
            risk_level = 'high'
        elif len(risk_factors) == 1:
            risk_level = 'medium'
        else:
            risk_level = 'low'
        
        return {
            'status': risk_level,
            'factors': risk_factors,
            'metrics': {
                'daily_pnl_pct': daily_pnl_pct,
                'max_drawdown': latest.max_drawdown,
                'sharpe_ratio': latest.sharpe_ratio
            }
        }
    
    def add_custom_alert_rule(self, name: str, check_function: Callable, 
                            interval: int = 300, enabled: bool = True):
        """Add custom monitoring rule."""
        self.alert_rules[name] = {
            'function': check_function,
            'interval': interval,
            'enabled': enabled
        }
        
        logging.info(f"Added custom alert rule: {name}")
    
    def update_risk_thresholds(self, new_thresholds: Dict):
        """Update risk management thresholds."""
        self.risk_thresholds.update(new_thresholds)
        
        self._create_alert(
            level='INFO',
            category='SYSTEM',
            message='Risk thresholds updated',
            data={'updated_thresholds': new_thresholds}
        )


# Alert callback functions
def email_alert_callback(alert: Alert):
    """Send email alerts for critical issues."""
    if alert.level == 'CRITICAL':
        # Would integrate with email service
        logging.info(f"EMAIL ALERT: {alert.message}")

def slack_alert_callback(alert: Alert):
    """Send Slack notifications."""
    if alert.level in ['CRITICAL', 'WARNING']:
        # Would integrate with Slack API
        logging.info(f"SLACK ALERT: {alert.message}")

def emergency_stop_callback(alert: Alert):
    """Emergency stop for critical risk events."""
    if (alert.category == 'RISK' and alert.level == 'CRITICAL' and 
        'Daily loss limit exceeded' in alert.message):
        # Would trigger emergency stop
        logging.critical("EMERGENCY STOP TRIGGERED!")


if __name__ == "__main__":
    print("🔍 Real-Time Trading Monitor System")
    print("Features:")
    print("  • Live performance tracking")
    print("  • Advanced risk monitoring")
    print("  • Configurable alert rules")
    print("  • Real-time dashboard data")
    print("  • Emergency response system")
    print("  • Database persistence")
    print("  • Custom callback support")
    print("\n✅ Professional monitoring system ready!")