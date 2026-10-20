"""
Quantum Trading Bot - Core Engine
Main event loop, execution router, and system orchestrator
"""
import asyncio
import logging
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import json
import yaml
from pathlib import Path
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from neural_mutation.genetic_optimizer import GeneticOptimizer
from neural_mutation.shadow_backtester import ShadowBacktester
from mcp_connector.tv_mcp_client import TVMCPClient
from toxicity_filter.vpin_filter import VPINFilter
from toxicity_filter.sor_engine import SOREngine
from risk_topology.kelly_allocator import KellyAllocator
from risk_topology.var_model import VaRModel
from risk_topology.circuit_breaker import CircuitBreaker
from dashboard.metrics_dashboard import MetricsDashboard
from core_engine.chaos_engineering import ChaosEngineering
from core_engine.confluence_matrix import MultiIndicatorConfluence


class SystemState(Enum):
    """System operational states."""
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    EMERGENCY_STOP = "emergency_stop"
    MAINTENANCE = "maintenance"


@dataclass
class MarketState:
    """Current market state snapshot."""
    regime: str = "neutral"
    volatility_regime: str = "normal"
    toxicity_level: float = 0.0
    liquidity_score: float = 1.0
    macro_impact: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class SystemHealth:
    """System health metrics."""
    api_latency_ms: float = 0.0
    order_success_rate: float = 1.0
    system_load: float = 0.0
    memory_usage: float = 0.0
    last_heartbeat: datetime = field(default_factory=datetime.now)
    active_positions: int = 0
    total_drawdown: float = 0.0


class QuantumTradingEngine:
    """
    Main trading engine orchestrating all subsystems.
    Autonomous, self-evolving, production-ready HFT system.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        # No global logging side effects here: importing this class in tests
        # or hosted tools must not open a log file in the working tree.
        # Desktop `python -m core_engine.main` configures file logging below.
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        self.config_path = config_path or os.environ.get("QUANTUM_CONFIG", "config.yaml")
        self.config = self._load_config()
        self.state = SystemState.INITIALIZING
        self.market_state = MarketState()
        self.system_health = SystemHealth()
        
        # Subsystems
        self.genetic_optimizer: Optional[GeneticOptimizer] = None
        self.shadow_backtester: Optional[ShadowBacktester] = None
        self.tv_mcp_client: Optional[TVMCPClient] = None
        self.vpin_filter: Optional[VPINFilter] = None
        self.sor_engine: Optional[SOREngine] = None
        self.kelly_allocator: Optional[KellyAllocator] = None
        self.var_model: Optional[VaRModel] = None
        self.circuit_breaker: Optional[CircuitBreaker] = None
        self.dashboard: Optional[MetricsDashboard] = None
        self.chaos_engineering: Optional[ChaosEngineering] = None
        self.confluence_matrix: Optional[MultiIndicatorConfluence] = None
        
        # Event loop
        try:
            self.event_loop = asyncio.get_event_loop()
        except RuntimeError:
            # Python 3.11+ may have no implicit loop in the current thread.
            self.event_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.event_loop)
        self.is_running = False
        self.shutdown_requested = False
        
        # Performance tracking
        self.metrics = {
            'total_trades': 0,
            'winning_trades': 0,
            'total_pnl': 0.0,
            'sharpe_ratio': 0.0,
            'max_drawdown': 0.0,
            'strategy_mutations': 0,
            'toxicity_skips': 0
        }
        
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file."""
        try:
            with open(self.config_path, 'r') as f:
                loaded = yaml.safe_load(f) or {}
                if not isinstance(loaded, dict):
                    raise ValueError("Configuration must contain a mapping")
                # Older quantum config files wrapped the engine settings in a
                # top-level namespace. Accept that format while keeping one
                # canonical root-level schema internally.
                if isinstance(loaded.get("quantum_trading"), dict):
                    loaded = loaded["quantum_trading"]
                return loaded
        except FileNotFoundError:
            self.logger.warning(f"Config file not found: {self.config_path}, using defaults")
            return self._get_default_config()
        except Exception as e:
            self.logger.error(f"Error loading config: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration."""
        return {
            'exchanges': {
                'primary': 'binance',
                'backup': ['bybit', 'kraken'],
                'api_keys': {},
                'use_testnet': True
            },
            'trading': {
                'symbols': ['BTCUSDT', 'ETHUSDT', 'XRPUSDT'],
                'max_positions': 5,
                'position_size_percent': 0.02,
                'max_risk_per_trade': 0.01,
                'global_risk_limit': 0.05
            },
            'neural_mutation': {
                'enabled': True,
                'population_size': 50,
                'mutation_rate': 0.1,
                'selection_pressure': 0.7,
                'evolution_interval_hours': 1
            },
            'mcp': {
                'tv_enabled': True,
                'tv_server_url': 'ws://localhost:8080',
                'reconnect_interval': 30
            },
            'toxicity_filter': {
                'enabled': True,
                'vpin_threshold': 0.3,
                'imbalance_threshold': 0.6,
                'freeze_duration_minutes': 5
            },
            'sor': {
                'enabled': True,
                'iceberg_slices': 10,
                'randomize_venues': True,
                'min_order_size': 0.001
            },
            'risk_topology': {
                'kelly_enabled': True,
                'var_enabled': True,
                'circuit_breaker_enabled': True,
                'max_drawdown_percent': 10.0,
                'hourly_loss_limit_percent': 2.0,
                'emergency_kill_enabled': True
            },
            'dashboard': {
                'enabled': True,
                'port': 8080,
                'update_interval': 1
            },
            'chaos_testing': {
                'enabled': True,
                'interval_hours': 24,
                'black_san_scenarios': ['liquidity_evaporation', 'api_latency', 'flash_crash']
            }
        }
    
    async def initialize(self):
        """Initialize all subsystems."""
        self.logger.info("Initializing Quantum Trading Engine...")
        
        try:
            # Initialize genetic optimizer
            if self.config['neural_mutation']['enabled']:
                self.genetic_optimizer = GeneticOptimizer(self.config)
                await self.genetic_optimizer.initialize()
                self.logger.info("Genetic Optimizer initialized")
            
            # Initialize shadow backtester
            self.shadow_backtester = ShadowBacktester(self.config)
            await self.shadow_backtester.initialize()
            self.logger.info("Shadow Backtester initialized")
            
            # Initialize TV MCP client
            if self.config['mcp']['tv_enabled']:
                self.tv_mcp_client = TVMCPClient(self.config)
                await self.tv_mcp_client.connect()
                self.logger.info("TV MCP Client connected")
            
            # Initialize toxicity filter
            if self.config['toxicity_filter']['enabled']:
                self.vpin_filter = VPINFilter(self.config)
                self.sor_engine = SOREngine(self.config)
                await self.vpin_filter.initialize()
                await self.sor_engine.initialize()
                self.logger.info("Toxicity Filter initialized")
            
            # Initialize risk topology
            if self.config['risk_topology']['kelly_enabled']:
                self.kelly_allocator = KellyAllocator(self.config)
                await self.kelly_allocator.initialize()
            
            if self.config['risk_topology']['var_enabled']:
                self.var_model = VaRModel(self.config)
                await self.var_model.initialize()
            
            if self.config['risk_topology']['circuit_breaker_enabled']:
                self.circuit_breaker = CircuitBreaker(self.config)
                await self.circuit_breaker.initialize()
            
            self.logger.info("Risk Topology initialized")
            
            # Initialize dashboard
            if self.config['dashboard']['enabled']:
                self.dashboard = MetricsDashboard(self.config)
                await self.dashboard.start()
                self.logger.info("Dashboard started")
            
            # Initialize chaos engineering
            if self.config['chaos_testing']['enabled']:
                self.chaos_engineering = ChaosEngineering(self.config)
                await self.chaos_engineering.initialize()
                self.logger.info("Chaos Engineering initialized")
            
            # Initialize confluence matrix
            self.confluence_matrix = MultiIndicatorConfluence(self.config)
            await self.confluence_matrix.initialize()
            self.logger.info("Confluence Matrix initialized")
            
            self.state = SystemState.RUNNING
            self.logger.info("Quantum Trading Engine initialization complete")
            
        except Exception as e:
            self.logger.error(f"Initialization error: {e}")
            self.state = SystemState.ERROR
            raise
    
    async def run(self):
        """Main event loop."""
        self.is_running = True
        self.logger.info("Starting main event loop...")
        
        try:
            while self.is_running and not self.shutdown_requested:
                # Update market state
                await self._update_market_state()
                
                # Update system health
                await self._update_system_health()
                
                # Check circuit breakers
                if self.circuit_breaker:
                    should_stop = await self.circuit_breaker.check_breakers(self.system_health, self.market_state)
                    if should_stop:
                        self.logger.warning("Circuit breaker triggered - emergency stop")
                        await self._emergency_stop()
                        break
                
                # Run shadow backtests
                if self.shadow_backtester:
                    await self.shadow_backtester.run_shadow_tests()
                
                # Check for strategy mutations
                if self.genetic_optimizer:
                    should_mutate = await self.genetic_optimizer.should_mutate()
                    if should_mutate:
                        self.logger.info("Initiating strategy mutation...")
                        await self.genetic_optimizer.mutate_strategy()
                        self.metrics['strategy_mutations'] += 1
                
                # Process signals
                await self._process_signals()
                
                # Update dashboard
                if self.dashboard:
                    await self.dashboard.update(self.market_state, self.system_health, self.metrics)
                
                # Sleep for next iteration
                await asyncio.sleep(0.1)  # 100ms main loop interval
                
        except Exception as e:
            self.logger.error(f"Main loop error: {e}")
            self.state = SystemState.ERROR
            await self._emergency_stop()
        
        finally:
            await self.shutdown()
    
    async def _update_market_state(self):
        """Update current market state."""
        try:
            # Get toxicity levels
            if self.vpin_filter:
                self.market_state.toxicity_level = await self.vpin_filter.get_toxicity_level()
            
            # Check macro events
            macro_events = await self._check_macro_events()
            self.market_state.macro_impact = macro_events
            
            # Update regime
            if self.genetic_optimizer:
                self.market_state.regime = await self.genetic_optimizer.detect_regime()
            
            self.market_state.timestamp = datetime.now()
            
        except Exception as e:
            self.logger.error(f"Market state update error: {e}")
    
    async def _update_system_health(self):
        """Update system health metrics."""
        try:
            # Update API latency
            if self.tv_mcp_client:
                self.system_health.api_latency_ms = await self.tv_mcp_client.get_latency()
            
            # Update system load
            import psutil
            self.system_health.system_load = psutil.cpu_percent()
            self.system_health.memory_usage = psutil.virtual_memory().percent
            
            # Update position count
            if self.kelly_allocator:
                self.system_health.active_positions = await self.kelly_allocator.get_position_count()
            
            # Update drawdown
            self.system_health.total_drawdown = self.metrics['max_drawdown']
            
            self.system_health.last_heartbeat = datetime.now()
            
        except Exception as e:
            self.logger.error(f"System health update error: {e}")
    
    async def _check_macro_events(self) -> List[str]:
        """Check for macroeconomic events."""
        events = []
        
        # Check if high-impact events are upcoming
        # In production, this would check economic calendars
        current_hour = datetime.now().hour
        
        # FOMC meetings typically at 2pm EST on Wednesdays (weekday 2)
        if current_hour == 13 and datetime.now().weekday() == 2:
            events.append("FOMC Meeting")
        
        # CPI release typically at 8:30am EST — Friday is weekday 4
        if current_hour == 8 and datetime.now().weekday() == 4:
            events.append("CPI Release")
        
        # Employment data (NFP) typically at 8:30am EST on first Friday — also weekday 4
        # Distinguish from CPI by checking for the first Friday of the month (day <= 7)
        if current_hour == 8 and datetime.now().weekday() == 4 and datetime.now().day <= 7:
            events.append("Employment Data (NFP)")
        
        return events
    
    async def _process_signals(self):
        """
        Process trading signals from all active sources.

        Production implementation should:
          1. Poll self.tv_mcp_client for new OHLCV bars / screener events.
          2. Run self.confluence_matrix.evaluate(bars) for a scored signal.
          3. Size the position with self.kelly_allocator.size_position(signal).
          4. Check self.var_model.check_var_limit() before submitting.
          5. Route the order through self.sor_engine.submit(order).
          6. Record fill in self.metrics and update self.system_health.active_positions.
        
        Currently a verified stub — no live orders are placed until the above
        steps are wired to a real exchange adapter.
        """
        pass
    
    async def _emergency_stop(self):
        """Emergency stop - liquidate all positions and lock down."""
        self.logger.critical("EMERGENCY STOP INITIATED")
        self.state = SystemState.EMERGENCY_STOP
        
        # Liquidate all positions
        if self.kelly_allocator:
            await self.kelly_allocator.liquidate_all()
        
        # Lock down network sockets
        self.logger.info("Network sockets locked down")
        
        # Stop all trading
        self.is_running = False
    
    async def shutdown(self):
        """Graceful shutdown of all subsystems."""
        self.logger.info("Shutting down Quantum Trading Engine...")
        
        try:
            # Stop dashboard
            if self.dashboard:
                await self.dashboard.stop()
            
            # Disconnect MCP
            if self.tv_mcp_client:
                await self.tv_mcp_client.disconnect()
            
            # Stop subsystems
            if self.genetic_optimizer:
                await self.genetic_optimizer.shutdown()
            
            if self.shadow_backtester:
                await self.shadow_backtester.shutdown()
            
            if self.vpin_filter:
                await self.vpin_filter.shutdown()
            
            if self.sor_engine:
                await self.sor_engine.shutdown()
            
            if self.kelly_allocator:
                await self.kelly_allocator.shutdown()
            
            if self.var_model:
                await self.var_model.shutdown()
            
            if self.circuit_breaker:
                await self.circuit_breaker.shutdown()
            
            self.state = SystemState.MAINTENANCE
            self.logger.info("Shutdown complete")
            
        except Exception as e:
            self.logger.error(f"Shutdown error: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current system status."""
        return {
            'state': self.state.value,
            'market_state': {
                'regime': self.market_state.regime,
                'toxicity_level': self.market_state.toxicity_level,
                'macro_impact': self.market_state.macro_impact
            },
            'system_health': {
                'api_latency_ms': self.system_health.api_latency_ms,
                'order_success_rate': self.system_health.order_success_rate,
                'active_positions': self.system_health.active_positions,
                'total_drawdown': self.system_health.total_drawdown
            },
            'metrics': self.metrics
        }


async def main():
    """Main entry point."""
    engine = QuantumTradingEngine()
    await engine.initialize()
    await engine.run()


if __name__ == "__main__":
    # Desktop runs get a local log file; the file handle lives for the whole
    # process on purpose (this is the only entry point that writes it).
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
        handlers=[
            logging.FileHandler('quantum_trading.log'),
            logging.StreamHandler()
        ]
    )
    asyncio.run(main())
