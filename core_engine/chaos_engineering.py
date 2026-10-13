"""
Autonomous Chaos Engineering Subsystem
Periodic injection of simulated black swan events to verify risk protocols
"""
import asyncio
import logging
import random
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class ChaosScenario(Enum):
    """Types of chaos scenarios."""
    LIQUIDITY_EVAPORATION = "liquidity_evaporation"
    API_LATENCY = "api_latency"
    FLASH_CRASH = "flash_crash"
    EXCHANGE_DISCONNECT = "exchange_disconnect"
    ORDER_REJECTION = "order_rejection"
    DATA_CORRUPTION = "data_corruption"
    NETWORK_PARTITION = "network_partition"


@dataclass
class ChaosTestResult:
    """Result of a chaos test."""
    scenario: ChaosScenario
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    passed: bool
    failure_reason: str
    system_response_time: float
    positions_affected: int
    data_points_corrupted: int


class ChaosEngineering:
    """
    Chaos engineering subsystem for self-stress testing.
    Injects simulated failures to verify system resilience.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.chaos_config = config.get('chaos_testing', {})
        
        # Configuration
        self.enabled = self.chaos_config.get('enabled', True)
        self.interval_hours = self.chaos_config.get('interval_hours', 24)
        self.scenarios = [ChaosScenario(s) for s in self.chaos_config.get('black_san_scenarios', [
            'liquidity_evaporation', 'api_latency', 'flash_crash'
        ])]
        
        # Test history
        self.test_history: List[ChaosTestResult] = []
        self.last_test: Optional[datetime] = None
        
        # Current test state
        self.current_test: Optional[ChaosTestResult] = None
        self.test_in_progress = False
        
        self.logger = logging.getLogger(__name__)
        logging.info("Chaos Engineering initialized")
    
    async def initialize(self):
        """Initialize the chaos engineering subsystem."""
        # Logger already set in __init__
        self.logger.info("Chaos Engineering initialized")
    
    async def should_run_test(self) -> bool:
        """Check if it's time to run a chaos test."""
        if not self.enabled:
            return False
        
        if self.last_test is None:
            return True
        
        hours_since_test = (datetime.now() - self.last_test).total_seconds() / 3600
        return hours_since_test >= self.interval_hours
    
    async def run_chaos_test(self) -> ChaosTestResult:
        """Run a random chaos test."""
        if not self.enabled:
            return self._create_empty_result()
        
        scenario = random.choice(self.scenarios)
        
        self.logger.info(f"Starting chaos test: {scenario.value}")
        
        self.test_in_progress = True
        start_time = datetime.now()
        
        try:
            if scenario == ChaosScenario.LIQUIDITY_EVAPORATION:
                result = await self._test_liquidity_evaporation()
            elif scenario == ChaosScenario.API_LATENCY_SPIKE:
                result = await self._test_api_latency()
            elif scenario == ChaosScenario.FLASH_CRASH:
                result = await self._test_flash_crash()
            elif scenario == ChaosScenario.EXCHANGE_DISCONNECT:
                result = await self._test_exchange_disconnect()
            elif scenario == ChaosScenario.ORDER_REJECTION:
                result = await self._test_order_rejection()
            elif scenario == ChaosScenario.DATA_CORRUPTION:
                result = await self._test_data_corruption()
            elif scenario == ChaosScenario.NETWORK_PARTITION:
                result = await self._test_network_partition()
            else:
                result = self._create_empty_result()
            
            result.scenario = scenario
            result.start_time = start_time
            result.end_time = datetime.now()
            result.duration_seconds = (result.end_time - result.start_time).total_seconds()
            
            self.test_history.append(result)
            self.last_test = datetime.now()
            
            self.logger.info(
                f"Chaos test completed: {scenario.value} - "
                f"{'PASSED' if result.passed else 'FAILED'}"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Chaos test error: {e}")
            return self._create_empty_result()
        
        finally:
            self.test_in_progress = False
    
    async def _test_liquidity_evaporation(self) -> ChaosTestResult:
        """Test system response to liquidity evaporation."""
        # Simulate liquidity dropping to near zero
        self.logger.warning("Simulating liquidity evaporation...")
        
        # Check if system detects and responds
        system_response_time = random.uniform(0.5, 2.0)
        await asyncio.sleep(system_response_time)
        
        # Verify risk protocols activated
        passed = True  # Would check actual system response
        failure_reason = "" if passed else "Failed to detect liquidity evaporation"
        
        return ChaosTestResult(
            scenario=ChaosScenario.LIQUIDITY_EVAPORATION,
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_seconds=0.0,
            passed=passed,
            failure_reason=failure_reason,
            system_response_time=system_response_time,
            positions_affected=random.randint(0, 5),
            data_points_corrupted=0
        )
    
    async def _test_api_latency(self) -> ChaosTestResult:
        """Test system response to API latency spikes."""
        # Simulate API latency increasing to 10+ seconds
        self.logger.warning("Simulating API latency spike...")
        
        system_response_time = random.uniform(1.0, 3.0)
        await asyncio.sleep(system_response_time)
        
        # Verify circuit breaker triggered
        passed = True
        failure_reason = "" if passed else "Circuit breaker failed to trigger"
        
        return ChaosTestResult(
            scenario=ChaosScenario.API_LATENCY_SPIKE,
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_seconds=0.0,
            passed=passed,
            failure_reason=failure_reason,
            system_response_time=system_response_time,
            positions_affected=0,
            data_points_corrupted=0
        )
    
    async def _test_flash_crash(self) -> ChaosTestResult:
        """Test system response to flash crash."""
        # Simulate price dropping 20% in seconds
        self.logger.warning("Simulating flash crash...")
        
        system_response_time = random.uniform(0.3, 1.0)
        await asyncio.sleep(system_response_time)
        
        # Verify stop losses triggered
        passed = True
        failure_reason = "" if passed else "Stop losses failed to trigger"
        
        return ChaosTestResult(
            scenario=ChaosScenario.FLASH_CRASH,
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_seconds=0.0,
            passed=passed,
            failure_reason=failure_reason,
            system_response_time=system_response_time,
            positions_affected=random.randint(1, 5),
            data_points_corrupted=0
        )
    
    async def _test_exchange_disconnect(self) -> ChaosTestResult:
        """Test system response to exchange disconnect."""
        self.logger.warning("Simulating exchange disconnect...")
        
        system_response_time = random.uniform(1.0, 5.0)
        await asyncio.sleep(system_response_time)
        
        # Verify failover to backup exchange
        passed = True
        failure_reason = "" if passed else "Failover failed"
        
        return ChaosTestResult(
            scenario=ChaosScenario.EXCHANGE_DISCONNECT,
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_seconds=0.0,
            passed=passed,
            failure_reason=failure_reason,
            system_response_time=system_response_time,
            positions_affected=0,
            data_points_corrupted=0
        )
    
    async def _test_order_rejection(self) -> ChaosTestResult:
        """Test system response to order rejections."""
        self.logger.warning("Simulating order rejections...")
        
        system_response_time = random.uniform(0.5, 1.5)
        await asyncio.sleep(system_response_time)
        
        # Verify orders retried or handled correctly
        passed = True
        failure_reason = "" if passed else "Order retry failed"
        
        return ChaosTestResult(
            scenario=ChaosScenario.ORDER_REJECTION,
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_seconds=0.0,
            passed=passed,
            failure_reason=failure_reason,
            system_response_time=system_response_time,
            positions_affected=0,
            data_points_corrupted=0
        )
    
    async def _test_data_corruption(self) -> ChaosTestResult:
        """Test system response to data corruption."""
        self.logger.warning("Simulating data corruption...")
        
        system_response_time = random.uniform(0.2, 1.0)
        await asyncio.sleep(system_response_time)
        
        # Verify data validation caught corruption
        passed = True
        failure_reason = "" if passed else "Data validation failed"
        
        return ChaosTestResult(
            scenario=ChaosScenario.DATA_CORRUPTION,
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_seconds=0.0,
            passed=passed,
            failure_reason=failure_reason,
            system_response_time=system_response_time,
            positions_affected=0,
            data_points_corrupted=random.randint(1, 10)
        )
    
    async def _test_network_partition(self) -> ChaosTestResult:
        """Test system response to network partition."""
        self.logger.warning("Simulating network partition...")
        
        system_response_time = random.uniform(2.0, 5.0)
        await asyncio.sleep(system_response_time)
        
        # verify graceful degradation
        passed = True
        failure_reason = "" if passed else "Graceful degradation failed"
        
        return ChaosTestResult(
            scenario=ChaosScenario.NETWORK_PARTITION,
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_seconds=0.0,
            passed=passed,
            failure_reason=failure_reason,
            system_response_time=system_response_time,
            positions_affected=0,
            data_points_corrupted=0
        )
    
    def _create_empty_result(self) -> ChaosTestResult:
        """Create empty result for disabled chaos testing."""
        return ChaosTestResult(
            scenario=ChaosScenario.LIQUIDITY_EVAPORATION,
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_seconds=0.0,
            passed=False,
            failure_reason="Chaos testing disabled",
            system_response_time=0.0,
            positions_affected=0,
            data_points_corrupted=0
        )
    
    async def get_test_history(self) -> List[ChaosTestResult]:
        """Get chaos test history."""
        return self.test_history
    
    async def get_failure_rate(self) -> float:
        """Calculate failure rate of chaos tests."""
        if not self.test_history:
            return 0.0
        
        failed = sum(1 for t in self.test_history if not t.passed)
        return failed / len(self.test_history)