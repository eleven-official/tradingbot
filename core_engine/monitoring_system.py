"""
Comprehensive Monitoring and Alerting System
Implements real-time monitoring, metrics tracking, and multi-channel alerting
"""
import logging
import asyncio
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from collections import deque
import json


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertChannel(Enum):
    """Alert delivery channels."""
    LOG = "log"
    EMAIL = "email"
    WEBHOOK = "webhook"
    SLACK = "slack"
    TELEGRAM = "telegram"
    DISCORD = "discord"


class MetricType(Enum):
    """Metric types."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@dataclass
class Alert:
    """Alert notification."""
    id: str
    severity: AlertSeverity
    title: str
    message: str
    timestamp: datetime
    source: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    acknowledged: bool = False


@dataclass
class Metric:
    """System metric."""
    name: str
    value: float
    metric_type: MetricType
    timestamp: datetime
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class HealthCheck:
    """Health check result."""
    component: str
    status: str  # 'healthy', 'degraded', 'unhealthy'
    message: str
    timestamp: datetime
    response_time_ms: float


class MetricsCollector:
    """
    Collects and aggregates system metrics.
    """
    
    def __init__(self, retention_period: timedelta = timedelta(hours=24)):
        self.retention_period = retention_period
        self.metrics: Dict[str, deque] = {}
        self.logger = logging.getLogger(__name__)
    
    def record_metric(self, name: str, value: float, metric_type: MetricType = MetricType.GAUGE,
                     labels: Optional[Dict[str, str]] = None):
        """Record a metric."""
        metric = Metric(
            name=name,
            value=value,
            metric_type=metric_type,
            timestamp=datetime.now(),
            labels=labels or {}
        )
        
        if name not in self.metrics:
            self.metrics[name] = deque()
        
        self.metrics[name].append(metric)
        
        # Cleanup old metrics
        self._cleanup_old_metrics(name)
    
    def _cleanup_old_metrics(self, name: str):
        """Remove metrics older than retention period."""
        cutoff = datetime.now() - self.retention_period
        
        while self.metrics[name] and self.metrics[name][0].timestamp < cutoff:
            self.metrics[name].popleft()
    
    def get_metric(self, name: str) -> Optional[List[Metric]]:
        """Get all values for a metric."""
        if name in self.metrics:
            return list(self.metrics[name])
        return None
    
    def get_metric_stats(self, name: str) -> Dict[str, float]:
        """Get statistics for a metric."""
        metrics = self.get_metric(name)
        
        if not metrics:
            return {}
        
        values = [m.value for m in metrics]
        
        return {
            'count': len(values),
            'min': min(values),
            'max': max(values),
            'mean': np.mean(values),
            'median': np.median(values),
            'std': np.std(values),
            'p95': np.percentile(values, 95),
            'p99': np.percentile(values, 99)
        }
    
    def get_all_metrics(self) -> Dict[str, Dict[str, float]]:
        """Get statistics for all metrics."""
        return {name: self.get_metric_stats(name) for name in self.metrics.keys()}


class AlertManager:
    """
    Manages alert generation and delivery.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.alerts: List[Alert] = []
        self.alert_rules: List[Dict[str, Any]] = []
        self.channels: Dict[AlertChannel, Callable] = {}
        self.logger = logging.getLogger(__name__)
        
        # Setup channels
        self._setup_channels()
    
    def _setup_channels(self):
        """Setup alert delivery channels."""
        # Log channel (always available)
        self.channels[AlertChannel.LOG] = self._send_log_alert
        
        # Email channel
        if self.config.get('email', {}).get('enabled', False):
            self.channels[AlertChannel.EMAIL] = self._send_email_alert
        
        # Webhook channel
        if self.config.get('webhook', {}).get('enabled', False):
            self.channels[AlertChannel.WEBHOOK] = self._send_webhook_alert
    
    def add_alert_rule(self, rule: Dict[str, Any]):
        """Add an alert rule."""
        self.alert_rules.append(rule)
        self.logger.info(f"Added alert rule: {rule['name']}")
    
    def check_alert_rules(self, metrics: Dict[str, Dict[str, float]]):
        """Check all alert rules against current metrics."""
        for rule in self.alert_rules:
            try:
                if self._evaluate_rule(rule, metrics):
                    self._trigger_alert(rule)
            except Exception as e:
                self.logger.error(f"Error evaluating rule {rule['name']}: {e}")
    
    def _evaluate_rule(self, rule: Dict[str, Any], metrics: Dict[str, Dict[str, float]]) -> bool:
        """Evaluate a single alert rule."""
        metric_name = rule['metric']
        condition = rule['condition']
        threshold = rule['threshold']
        
        if metric_name not in metrics:
            return False
        
        metric_stats = metrics[metric_name]
        current_value = metric_stats.get('mean', 0)
        
        if condition == 'greater_than':
            return current_value > threshold
        elif condition == 'less_than':
            return current_value < threshold
        elif condition == 'equals':
            return current_value == threshold
        elif condition == 'not_equals':
            return current_value != threshold
        
        return False
    
    def _trigger_alert(self, rule: Dict[str, Any]):
        """Trigger an alert based on a rule."""
        alert = Alert(
            id=str(datetime.now().timestamp()),
            severity=AlertSeverity(rule.get('severity', 'warning')),
            title=rule['name'],
            message=rule.get('message', f"Alert triggered: {rule['name']}"),
            timestamp=datetime.now(),
            source=rule.get('source', 'system'),
            metadata=rule.get('metadata', {})
        )
        
        self.alerts.append(alert)
        
        # Send to all configured channels
        for channel in rule.get('channels', [AlertChannel.LOG]):
            if channel in self.channels:
                try:
                    self.channels[channel](alert)
                except Exception as e:
                    self.logger.error(f"Error sending alert to {channel}: {e}")
    
    def _send_log_alert(self, alert: Alert):
        """Send alert to log."""
        log_method = {
            AlertSeverity.INFO: self.logger.info,
            AlertSeverity.WARNING: self.logger.warning,
            AlertSeverity.ERROR: self.logger.error,
            AlertSeverity.CRITICAL: self.logger.critical
        }.get(alert.severity, self.logger.info)
        
        log_method(f"ALERT: {alert.title} - {alert.message}")
    
    def _send_email_alert(self, alert: Alert):
        """Send alert via email."""
        # Placeholder for email implementation
        self.logger.info(f"Email alert would be sent: {alert.title}")
    
    def _send_webhook_alert(self, alert: Alert):
        """Send alert via webhook."""
        import aiohttp
        
        webhook_url = self.config['webhook']['url']
        
        payload = {
            'id': alert.id,
            'severity': alert.severity.value,
            'title': alert.title,
            'message': alert.message,
            'timestamp': alert.timestamp.isoformat(),
            'source': alert.source,
            'metadata': alert.metadata
        }
        
        async def send():
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(webhook_url, json=payload) as response:
                        if response.status != 200:
                            self.logger.error(f"Webhook failed: {response.status}")
            except Exception as e:
                self.logger.error(f"Webhook error: {e}")
        
        asyncio.create_task(send())
    
    def get_recent_alerts(self, limit: int = 100) -> List[Alert]:
        """Get recent alerts."""
        return self.alerts[-limit:]


class HealthMonitor:
    """
    Monitors system health and performs health checks.
    """
    
    def __init__(self):
        self.health_checks: Dict[str, Callable] = {}
        self.health_history: Dict[str, deque] = {}
        self.logger = logging.getLogger(__name__)
    
    def register_health_check(self, component: str, check_func: Callable):
        """Register a health check for a component."""
        self.health_checks[component] = check_func
        self.health_history[component] = deque(maxlen=100)
        self.logger.info(f"Registered health check for: {component}")
    
    async def run_health_checks(self) -> Dict[str, HealthCheck]:
        """Run all registered health checks."""
        results = {}
        
        for component, check_func in self.health_checks.items():
            try:
                start_time = datetime.now()
                result = await check_func()
                response_time = (datetime.now() - start_time).total_seconds() * 1000
                
                health_check = HealthCheck(
                    component=component,
                    status=result.get('status', 'healthy'),
                    message=result.get('message', 'OK'),
                    timestamp=datetime.now(),
                    response_time_ms=response_time
                )
                
                results[component] = health_check
                self.health_history[component].append(health_check)
                
            except Exception as e:
                health_check = HealthCheck(
                    component=component,
                    status='unhealthy',
                    message=str(e),
                    timestamp=datetime.now(),
                    response_time_ms=0
                )
                
                results[component] = health_check
                self.health_history[component].append(health_check)
        
        return results
    
    def get_component_health(self, component: str) -> Optional[HealthCheck]:
        """Get latest health check result for a component."""
        if component in self.health_history and self.health_history[component]:
            return self.health_history[component][-1]
        return None
    
    def get_overall_health(self) -> str:
        """Get overall system health status."""
        if not self.health_history:
            return 'unknown'
        
        statuses = []
        for component_history in self.health_history.values():
            if component_history:
                statuses.append(component_history[-1].status)
        
        if not statuses:
            return 'unknown'
        
        if all(s == 'healthy' for s in statuses):
            return 'healthy'
        elif any(s == 'unhealthy' for s in statuses):
            return 'unhealthy'
        else:
            return 'degraded'


class MonitoringSystem:
    """
    Comprehensive monitoring system combining metrics, alerts, and health checks.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.metrics_collector = MetricsCollector()
        self.alert_manager = AlertManager(config.get('alerts', {}))
        self.health_monitor = HealthMonitor()
        self.is_running = False
        self.logger = logging.getLogger(__name__)
        
        # Setup default alert rules
        self._setup_default_alert_rules()
    
    def _setup_default_alert_rules(self):
        """Setup default alert rules."""
        default_rules = [
            {
                'name': 'High Memory Usage',
                'metric': 'memory_usage_percent',
                'condition': 'greater_than',
                'threshold': 90,
                'severity': 'warning',
                'channels': [AlertChannel.LOG]
            },
            {
                'name': 'High CPU Usage',
                'metric': 'cpu_usage_percent',
                'condition': 'greater_than',
                'threshold': 90,
                'severity': 'warning',
                'channels': [AlertChannel.LOG]
            },
            {
                'name': 'High Drawdown',
                'metric': 'max_drawdown',
                'condition': 'greater_than',
                'threshold': 0.2,
                'severity': 'error',
                'channels': [AlertChannel.LOG]
            },
            {
                'name': 'Low Win Rate',
                'metric': 'win_rate',
                'condition': 'less_than',
                'threshold': 0.4,
                'severity': 'warning',
                'channels': [AlertChannel.LOG]
            }
        ]
        
        for rule in default_rules:
            self.alert_manager.add_alert_rule(rule)
    
    async def start(self):
        """Start the monitoring system."""
        self.is_running = True
        self.logger.info("Monitoring system started")
        
        # Start monitoring loop
        asyncio.create_task(self._monitoring_loop())
    
    async def stop(self):
        """Stop the monitoring system."""
        self.is_running = False
        self.logger.info("Monitoring system stopped")
    
    async def _monitoring_loop(self):
        """Main monitoring loop."""
        while self.is_running:
            try:
                # Collect system metrics
                await self._collect_system_metrics()
                
                # Check alert rules
                metrics = self.metrics_collector.get_all_metrics()
                self.alert_manager.check_alert_rules(metrics)
                
                # Run health checks
                await self.health_monitor.run_health_checks()
                
                # Sleep for next cycle
                await asyncio.sleep(self.config.get('monitoring_interval', 60))
            
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(10)
    
    async def _collect_system_metrics(self):
        """Collect system metrics."""
        import psutil
        
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        self.metrics_collector.record_metric('cpu_usage_percent', cpu_percent)
        
        # Memory usage
        memory = psutil.virtual_memory()
        self.metrics_collector.record_metric('memory_usage_percent', memory.percent)
        self.metrics_collector.record_metric('memory_available_gb', memory.available / (1024**3))
        
        # Disk usage
        disk = psutil.disk_usage('/')
        self.metrics_collector.record_metric('disk_usage_percent', disk.percent)
        self.metrics_collector.record_metric('disk_free_gb', disk.free / (1024**3))
    
    def record_trading_metric(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Record a trading-specific metric."""
        self.metrics_collector.record_metric(name, value, labels=labels)
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get overall system status."""
        return {
            'health': self.health_monitor.get_overall_health(),
            'metrics': self.metrics_collector.get_all_metrics(),
            'recent_alerts': self.alert_manager.get_recent_alerts(10),
            'health_checks': {comp: self.health_monitor.get_component_health(comp).status 
                            for comp in self.health_monitor.health_checks.keys()}
        }
    
    def export_metrics(self, format: str = 'json') -> str:
        """Export metrics in specified format."""
        metrics = self.metrics_collector.get_all_metrics()
        
        if format == 'json':
            return json.dumps(metrics, indent=2, default=str)
        elif format == 'prometheus':
            return self._export_prometheus(metrics)
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    def _export_prometheus(self, metrics: Dict[str, Dict[str, float]]) -> str:
        """Export metrics in Prometheus format."""
        lines = []
        
        for metric_name, stats in metrics.items():
            for stat_name, value in stats.items():
                prometheus_name = f"{metric_name}_{stat_name}"
                lines.append(f"{prometheus_name} {value}")
        
        return "\n".join(lines)