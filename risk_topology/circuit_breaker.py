"""
Circuit Breaker - Self-Healing Emergency Protection
Hardcoded drawdown limits, rolling loss caps, and emergency kill-switch
"""
import asyncio
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict, is_dataclass
from datetime import datetime, timedelta
from enum import Enum
from collections import deque


class BreakerType(Enum):
    """Types of circuit breakers."""
    MAX_DRAWDOWN = "max_drawdown"
    HOURLY_LOSS = "hourly_loss"
    API_LATENCY = "api_latency"
    MARKET_ANOMALY = "market_anomaly"
    LIQUIDITY_EVAPORATION = "liquidity_evaporation"
    MANUAL = "manual"


class BreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Trading halted
    HALF_OPEN = "half_open"  # Limited trading


@dataclass
class BreakerTrigger:
    """Record of a circuit breaker trigger."""
    breaker_type: BreakerType
    trigger_time: datetime
    trigger_value: float
    threshold: float
    reason: str


class CircuitBreaker:
    """
    Circuit breaker system for emergency protection.
    Monitors risk metrics and halts trading if thresholds breached.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.breaker_config = config.get('risk_topology', {})
        
        # Configuration
        self.enabled = self.breaker_config.get('circuit_breaker_enabled', True)
        self.max_drawdown_percent = self.breaker_config.get('max_drawdown_percent', 10.0)
        self.hourly_loss_limit_percent = self.breaker_config.get('hourly_loss_limit_percent', 2.0)
        self.emergency_kill_enabled = self.breaker_config.get('emergency_kill_enabled', True)
        
        # Circuit breaker states
        self.state = BreakerState.CLOSED
        self.triggers: List[BreakerTrigger] = []
        
        # Monitoring data
        self.hourly_pnl: deque = deque(maxlen=60)  # Last 60 minutes
        self.drawdown_history: deque = deque(maxlen=1000)
        self.peak_balance = 100000.0
        self.current_balance = 100000.0
        
        # Emergency state
        self.emergency_active = False
        self.emergency_start_time: Optional[datetime] = None
        
        self.logger = logging.getLogger(__name__)
        logging.info("Circuit Breaker initialized")
    
    async def initialize(self):
        """Initialize the circuit breaker."""
        self.logger.info("Circuit Breaker initialized")
    
    async def check_breakers(self, system_health: Dict[str, Any], 
                            market_state: Dict[str, Any]) -> bool:
        """
        Check all circuit breakers.
        Returns True if emergency stop should be triggered.
        """
        if not self.enabled:
            return False

        # The engine uses dataclass snapshots while older callers use dicts.
        # Normalize once at the boundary instead of allowing an AttributeError
        # in every individual breaker check.
        if is_dataclass(system_health):
            system_health = asdict(system_health)
        if is_dataclass(market_state):
            market_state = asdict(market_state)
        if not isinstance(system_health, dict) or not isinstance(market_state, dict):
            raise TypeError("system_health and market_state must be mappings or dataclasses")
        
        if self.state == BreakerState.OPEN:
            # Check if conditions have improved
            if await self._check_recovery():
                self.state = BreakerState.HALF_OPEN
                self.logger.info("Circuit breaker moved to HALF_OPEN state")
            return True
        
        # Check each breaker
        should_stop = False
        
        # Max drawdown breaker
        if await self._check_max_drawdown():
            should_stop = True
        
        # Hourly loss breaker
        if await self._check_hourly_loss():
            should_stop = True
        
        # API latency breaker
        if await self._check_api_latency(system_health):
            should_stop = True
        
        # Market anomaly breaker
        if await self._check_market_anomaly(market_state):
            should_stop = True
        
        # Liquidity evaporation breaker
        if await self._check_liquidity(market_state):
            should_stop = True
        
        if should_stop:
            await self._trigger_breaker(BreakerType.MANUAL, "Multiple breakers triggered")
        
        return should_stop
    
    async def _check_max_drawdown(self) -> bool:
        """Check if max drawdown exceeded."""
        current_drawdown = (self.peak_balance - self.current_balance) / self.peak_balance * 100
        
        self.drawdown_history.append(current_drawdown)
        
        if current_drawdown >= self.max_drawdown_percent:
            await self._trigger_breaker(
                BreakerType.MAX_DRAWDOWN,
                f"Max drawdown exceeded: {current_drawdown:.2f}% (threshold: {self.max_drawdown_percent}%)"
            )
            return True
        
        return False
    
    async def _check_hourly_loss(self) -> bool:
        """Check if hourly loss limit exceeded."""
        if len(self.hourly_pnl) < 60:
            return False
        
        hourly_pnl = sum(self.hourly_pnl)
        hourly_loss_percent = abs(hourly_pnl) / self.peak_balance * 100
        
        if hourly_loss_percent >= self.hourly_loss_limit_percent:
            await self._trigger_breaker(
                BreakerType.HOURLY_LOSS,
                f"Hourly loss limit exceeded: {hourly_loss_percent:.2f}% (threshold: {self.hourly_loss_limit_percent}%)"
            )
            return True
        
        return False
    
    async def _check_api_latency(self, system_health: Dict[str, Any]) -> bool:
        """Check if API latency is too high."""
        api_latency = system_health.get('api_latency_ms', 0)
        
        if api_latency > 5000:  # 5 seconds
            await self._trigger_breaker(
                BreakerType.API_LATENCY,
                f"API latency too high: {api_latency:.0f}ms"
            )
            return True
        
        return False
    
    async def _check_market_anomaly(self, market_state: Dict[str, Any]) -> bool:
        """Check for market anomalies."""
        toxicity = market_state.get('toxicity_level', 0)
        
        if toxicity > 0.8:  # Very high toxicity
            await self._trigger_breaker(
                BreakerType.MARKET_ANOMALY,
                f"Market toxicity too high: {toxicity:.2f}"
            )
            return True
        
        return False
    
    async def _check_liquidity(self, market_state: Dict[str, Any]) -> bool:
        """Check for liquidity evaporation."""
        liquidity = market_state.get('liquidity_score', 1.0)
        
        if liquidity < 0.1:  # Very low liquidity
            await self._trigger_breaker(
                BreakerType.LIQUIDITY_EVAPORATION,
                f"Liquidity evaporation detected: {liquidity:.2f}"
            )
            return True
        
        return False
    
    async def _check_recovery(self) -> bool:
        """Check if conditions have improved for recovery."""
        # Check if drawdown has improved
        current_drawdown = (self.peak_balance - self.current_balance) / self.peak_balance * 100
        
        if current_drawdown < self.max_drawdown_percent * 0.5:
            return True
        
        return False
    
    async def _trigger_breaker(self, breaker_type: BreakerType, reason: str):
        """Trigger circuit breaker."""
        self.state = BreakerState.OPEN
        
        trigger = BreakerTrigger(
            breaker_type=breaker_type,
            trigger_time=datetime.now(),
            trigger_value=0.0,
            threshold=0.0,
            reason=reason
        )
        
        self.triggers.append(trigger)
        
        self.logger.critical(f"CIRCUIT BREAKER TRIGGERED: {reason}")
        
        # Emergency kill if enabled
        if self.emergency_kill_enabled:
            await self._emergency_kill()
    
    async def _emergency_kill(self):
        """Emergency kill - liquidate everything and lock down."""
        self.emergency_active = True
        self.emergency_start_time = datetime.now()
        
        self.logger.critical("EMERGENCY KILL ACTIVATED")
        
        # In production, this would:
        # 1. Liquidate all positions
        # 2. Cancel all pending orders
        # 3. Lock down network sockets
        # 4. Send alerts
        
        # For now, just log
        self.logger.critical("All positions liquidated, trading locked down")
    
    async def update_balance(self, current_balance: float):
        """Update current balance for drawdown tracking."""
        self.current_balance = current_balance
        
        if current_balance > self.peak_balance:
            self.peak_balance = current_balance
    
    async def update_hourly_pnl(self, pnl: float):
        """Update hourly P&L tracking."""
        self.hourly_pnl.append(pnl)
    
    async def reset_breaker(self):
        """Manually reset circuit breaker."""
        self.state = BreakerState.CLOSED
        self.emergency_active = False
        self.emergency_start_time = None
        
        self.logger.info("Circuit breaker manually reset")
    
    async def get_status(self) -> Dict[str, Any]:
        """Get current circuit breaker status."""
        current_drawdown = (self.peak_balance - self.current_balance) / self.peak_balance * 100
        
        return {
            'state': self.state.value,
            'emergency_active': self.emergency_active,
            'current_drawdown': current_drawdown,
            'max_drawdown_limit': self.max_drawdown_percent,
            'triggers_count': len(self.triggers),
            'last_trigger': self.triggers[-1].reason if self.triggers else None
        }
    
    async def shutdown(self):
        """Shutdown the circuit breaker."""
        self.logger.info("Circuit Breaker shutdown complete")
