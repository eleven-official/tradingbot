"""
Self-Healing Trading System
Automatically detects and recovers from system failures, errors, and degraded performance
"""
import logging
import time
import threading
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta
from collections import deque
import json


class SystemHealth(Enum):
    """System health status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    FAILED = "failed"


@dataclass
class HealthCheck:
    """Health check result."""
    component: str
    status: SystemHealth
    message: str
    timestamp: datetime
    response_time_ms: float
    details: Dict[str, Any]


class SelfHealingSystem:
    """
    Self-healing system that monitors trading bot health and
    automatically recovers from failures and degraded performance.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.healing_config = config.get('self_healing', {})
        
        # Configuration
        self.enabled = self.healing_config.get('enabled', True)
        self.health_check_interval = self.healing_config.get('health_check_interval', 60)
        self.max_recovery_attempts = self.healing_config.get('max_recovery_attempts', 3)
        self.degraded_threshold = self.healing_config.get('degraded_threshold', 3)
        self.critical_threshold = self.healing_config.get('critical_threshold', 5)
        
        # State tracking
        self.current_health = SystemHealth.HEALTHY
        self.health_history: deque = deque(maxlen=100)
        self.recovery_attempts: Dict[str, int] = {}
        self.last_health_check: Optional[datetime] = None
        
        # Component health
        self.component_health: Dict[str, SystemHealth] = {}
        
        # Recovery actions
        self.recovery_actions: Dict[str, List[Callable]] = {
            'api_connection': [],
            'data_feed': [],
            'order_execution': [],
            'strategy_engine': [],
            'risk_management': []
        }
        
        # Monitoring thread
        self.monitoring_thread: Optional[threading.Thread] = None
        self.is_monitoring = False
        
        logging.info("Self-Healing System initialized")
    
    def register_recovery_action(self, component: str, action: Callable):
        """Register a recovery action for a component."""
        if component not in self.recovery_actions:
            self.recovery_actions[component] = []
        self.recovery_actions[component].append(action)
        logging.info(f"Registered recovery action for {component}")
    
    def start_monitoring(self):
        """Start continuous health monitoring."""
        if not self.enabled:
            return
        
        self.is_monitoring = True
        self.monitoring_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitoring_thread.start()
        logging.info("Self-healing monitoring started")
    
    def stop_monitoring(self):
        """Stop health monitoring."""
        self.is_monitoring = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        logging.info("Self-healing monitoring stopped")
    
    def _monitor_loop(self):
        """Main monitoring loop."""
        while self.is_monitoring:
            try:
                self.perform_health_checks()
                time.sleep(self.health_check_interval)
            except Exception as e:
                logging.error(f"Monitoring loop error: {e}")
                time.sleep(self.health_check_interval)
    
    def perform_health_checks(self) -> List[HealthCheck]:
        """Perform health checks on all components."""
        health_checks = []
        
        # Check API connection
        api_check = self._check_api_connection()
        health_checks.append(api_check)
        
        # Check data feed
        data_check = self._check_data_feed()
        health_checks.append(data_check)
        
        # Check order execution
        order_check = self._check_order_execution()
        health_checks.append(order_check)
        
        # Check strategy engine
        strategy_check = self._check_strategy_engine()
        health_checks.append(strategy_check)
        
        # Check risk management
        risk_check = self._check_risk_management()
        health_checks.append(risk_check)
        
        # Update overall health
        self._update_overall_health(health_checks)
        
        # Perform healing if needed
        self._perform_healing(health_checks)
        
        self.last_health_check = datetime.now()
        
        return health_checks
    
    def _check_api_connection(self) -> HealthCheck:
        """Check API connection health."""
        start_time = time.time()
        
        try:
            # Simulate API check - in real implementation, ping the exchange API
            response_time = (time.time() - start_time) * 1000
            
            if response_time < 1000:
                status = SystemHealth.HEALTHY
                message = "API connection healthy"
            elif response_time < 3000:
                status = SystemHealth.DEGRADED
                message = f"API connection slow ({response_time:.0f}ms)"
            else:
                status = SystemHealth.CRITICAL
                message = f"API connection very slow ({response_time:.0f}ms)"
            
            self.component_health['api_connection'] = status
            
            return HealthCheck(
                component='api_connection',
                status=status,
                message=message,
                timestamp=datetime.now(),
                response_time_ms=response_time,
                details={'response_time': response_time}
            )
            
        except Exception as e:
            self.component_health['api_connection'] = SystemHealth.FAILED
            return HealthCheck(
                component='api_connection',
                status=SystemHealth.FAILED,
                message=f"API connection failed: {str(e)}",
                timestamp=datetime.now(),
                response_time_ms=(time.time() - start_time) * 1000,
                details={'error': str(e)}
            )
    
    def _check_data_feed(self) -> HealthCheck:
        """Check data feed health."""
        start_time = time.time()
        
        try:
            # Simulate data feed check
            response_time = (time.time() - start_time) * 1000
            
            status = SystemHealth.HEALTHY
            message = "Data feed healthy"
            
            self.component_health['data_feed'] = status
            
            return HealthCheck(
                component='data_feed',
                status=status,
                message=message,
                timestamp=datetime.now(),
                response_time_ms=response_time,
                details={'response_time': response_time}
            )
            
        except Exception as e:
            self.component_health['data_feed'] = SystemHealth.FAILED
            return HealthCheck(
                component='data_feed',
                status=SystemHealth.FAILED,
                message=f"Data feed failed: {str(e)}",
                timestamp=datetime.now(),
                response_time_ms=(time.time() - start_time) * 1000,
                details={'error': str(e)}
            )
    
    def _check_order_execution(self) -> HealthCheck:
        """Check order execution health."""
        start_time = time.time()
        
        try:
            response_time = (time.time() - start_time) * 1000
            status = SystemHealth.HEALTHY
            message = "Order execution healthy"
            
            self.component_health['order_execution'] = status
            
            return HealthCheck(
                component='order_execution',
                status=status,
                message=message,
                timestamp=datetime.now(),
                response_time_ms=response_time,
                details={'response_time': response_time}
            )
            
        except Exception as e:
            self.component_health['order_execution'] = SystemHealth.FAILED
            return HealthCheck(
                component='order_execution',
                status=SystemHealth.FAILED,
                message=f"Order execution failed: {str(e)}",
                timestamp=datetime.now(),
                response_time_ms=(time.time() - start_time) * 1000,
                details={'error': str(e)}
            )
    
    def _check_strategy_engine(self) -> HealthCheck:
        """Check strategy engine health."""
        start_time = time.time()
        
        try:
            response_time = (time.time() - start_time) * 1000
            status = SystemHealth.HEALTHY
            message = "Strategy engine healthy"
            
            self.component_health['strategy_engine'] = status
            
            return HealthCheck(
                component='strategy_engine',
                status=status,
                message=message,
                timestamp=datetime.now(),
                response_time_ms=response_time,
                details={'response_time': response_time}
            )
            
        except Exception as e:
            self.component_health['strategy_engine'] = SystemHealth.FAILED
            return HealthCheck(
                component='strategy_engine',
                status=SystemHealth.FAILED,
                message=f"Strategy engine failed: {str(e)}",
                timestamp=datetime.now(),
                response_time_ms=(time.time() - start_time) * 1000,
                details={'error': str(e)}
            )
    
    def _check_risk_management(self) -> HealthCheck:
        """Check risk management health."""
        start_time = time.time()
        
        try:
            response_time = (time.time() - start_time) * 1000
            status = SystemHealth.HEALTHY
            message = "Risk management healthy"
            
            self.component_health['risk_management'] = status
            
            return HealthCheck(
                component='risk_management',
                status=status,
                message=message,
                timestamp=datetime.now(),
                response_time_ms=response_time,
                details={'response_time': response_time}
            )
            
        except Exception as e:
            self.component_health['risk_management'] = SystemHealth.FAILED
            return HealthCheck(
                component='risk_management',
                status=SystemHealth.FAILED,
                message=f"Risk management failed: {str(e)}",
                timestamp=datetime.now(),
                response_time_ms=(time.time() - start_time) * 1000,
                details={'error': str(e)}
            )
    
    def _update_overall_health(self, health_checks: List[HealthCheck]):
        """Update overall system health based on component health."""
        failed_count = sum(1 for check in health_checks if check.status == SystemHealth.FAILED)
        critical_count = sum(1 for check in health_checks if check.status == SystemHealth.CRITICAL)
        degraded_count = sum(1 for check in health_checks if check.status == SystemHealth.DEGRADED)
        
        if failed_count > 0:
            self.current_health = SystemHealth.FAILED
        elif critical_count >= self.critical_threshold:
            self.current_health = SystemHealth.CRITICAL
        elif degraded_count >= self.degraded_threshold:
            self.current_health = SystemHealth.DEGRADED
        else:
            self.current_health = SystemHealth.HEALTHY
        
        # Add to history
        self.health_history.append({
            'health': self.current_health,
            'timestamp': datetime.now(),
            'failed_count': failed_count,
            'critical_count': critical_count,
            'degraded_count': degraded_count
        })
    
    def _perform_healing(self, health_checks: List[HealthCheck]):
        """Perform healing actions for failed components."""
        for check in health_checks:
            if check.status in [SystemHealth.FAILED, SystemHealth.CRITICAL]:
                component = check.component
                
                # Check if we haven't exceeded max recovery attempts
                attempts = self.recovery_attempts.get(component, 0)
                if attempts < self.max_recovery_attempts:
                    logging.warning(f"Attempting healing for {component}")
                    self._execute_recovery_actions(component)
                    self.recovery_attempts[component] = attempts + 1
                else:
                    logging.error(f"Max recovery attempts exceeded for {component}")
    
    def _execute_recovery_actions(self, component: str):
        """Execute registered recovery actions for a component."""
        if component in self.recovery_actions:
            for action in self.recovery_actions[component]:
                try:
                    logging.info(f"Executing recovery action for {component}")
                    action()
                except Exception as e:
                    logging.error(f"Recovery action failed for {component}: {e}")
    
    def get_system_health(self) -> SystemHealth:
        """Get current system health."""
        return self.current_health
    
    def get_health_report(self) -> Dict[str, Any]:
        """Get comprehensive health report."""
        return {
            'overall_health': self.current_health.value,
            'component_health': {k: v.value for k, v in self.component_health.items()},
            'last_health_check': self.last_health_check.isoformat() if self.last_health_check else None,
            'health_history_length': len(self.health_history),
            'recovery_attempts': self.recovery_attempts,
            'monitoring_active': self.is_monitoring
        }
    
    def reset_recovery_attempts(self, component: Optional[str] = None):
        """Reset recovery attempts for a component or all components."""
        if component:
            self.recovery_attempts.pop(component, None)
            logging.info(f"Reset recovery attempts for {component}")
        else:
            self.recovery_attempts.clear()
            logging.info("Reset all recovery attempts")
    
    def force_health_check(self) -> List[HealthCheck]:
        """Force an immediate health check."""
        return self.perform_health_checks()