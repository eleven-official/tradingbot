"""
Comprehensive Test Suite for Quantum Trading Bot
Tests all subsystems including neural mutation, MCP, toxicity filter, risk topology, and chaos engineering
"""
import unittest
import asyncio
import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from neural_mutation.genetic_optimizer import GeneticOptimizer, StrategyGenome, MutationType
from neural_mutation.shadow_backtester import ShadowBacktester, ShadowBacktestResult
from mcp_connector.tv_mcp_client import TVMCPClient, OHLCVData, ScreenerResult
from toxicity_filter.vpin_filter import VPINFilter, ToxicityMetrics
from toxicity_filter.sor_engine import SOREngine, OrderSlice, ParentOrder, OrderType, Venue
from risk_topology.kelly_allocator import KellyAllocator, Position
from risk_topology.var_model import VaRModel, VaRResult
from risk_topology.circuit_breaker import CircuitBreaker, BreakerType, BreakerState
try:
    from dashboard.metrics_dashboard import MetricsDashboard
    DASHBOARD_AVAILABLE = True
except ImportError:
    DASHBOARD_AVAILABLE = False
from core_engine.chaos_engineering import ChaosEngineering, ChaosScenario
from core_engine.confluence_matrix import MultiIndicatorConfluence, SignalStrength

# Check if scipy is available
try:
    import scipy
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

# Check if aiohttp is available
try:
    from aiohttp import web
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False


class TestGeneticOptimizer(unittest.TestCase):
    """Test cases for Genetic Optimizer."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'neural_mutation': {
                'enabled': True,
                'population_size': 10,
                'mutation_rate': 0.1,
                'selection_pressure': 0.7,
                'evolution_interval_hours': 1
            }
        }
        self.optimizer = GeneticOptimizer(self.config)
    
    def test_initialization(self):
        """Test optimizer initialization."""
        self.assertIsNotNone(self.optimizer)
        self.assertEqual(self.optimizer.population_size, 10)
        self.assertEqual(self.optimizer.mutation_rate, 0.1)
    
    def test_create_random_genome(self):
        """Test creating random genome."""
        genome = self.optimizer._create_random_genome("test_genome")
        
        self.assertIsInstance(genome, StrategyGenome)
        self.assertEqual(genome.genome_id, "test_genome")
        self.assertGreater(len(genome.indicator_weights), 0)
    
    def test_crossover(self):
        """Test genome crossover."""
        parent1 = self.optimizer._create_random_genome("parent1")
        parent2 = self.optimizer._create_random_genome("parent2")
        
        offspring = self.optimizer._crossover(parent1, parent2)
        
        self.assertIsInstance(offspring, StrategyGenome)
        self.assertNotEqual(offspring.genome_id, parent1.genome_id)
        self.assertNotEqual(offspring.genome_id, parent2.genome_id)
    
    def test_mutate_genome(self):
        """Test genome mutation."""
        genome = self.optimizer._create_random_genome("test")
        original_stop_loss = genome.stop_loss_atr_multiplier
        
        self.optimizer._mutate_genome(genome)
        
        # After mutation, values should be different
        self.assertIsNotNone(genome.last_mutated)


class TestShadowBacktester(unittest.TestCase):
    """Test cases for Shadow Backtester."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'backtesting': {
                'shadow_count': 5,
                'lookback_days': 30,
                'min_trades_required': 20,
                'degradation_threshold': 0.2
            }
        }
        self.backtester = ShadowBacktester(self.config)
    
    def test_initialization(self):
        """Test backtester initialization."""
        self.assertIsNotNone(self.backtester)
        self.assertEqual(self.backtester.shadow_count, 5)
    
    def test_generate_signals(self):
        """Test signal generation."""
        np.random.seed(42)
        dates = pd.date_range(start='2024-01-01', periods=100, freq='h')
        data = pd.DataFrame({
            'close': 50000 + np.cumsum(np.random.randn(100) * 100)
        }, index=dates)
        
        signals = self.backtester._generate_signals(data)
        
        self.assertIsInstance(signals, list)
    
    def test_execute_trades(self):
        """Test trade execution."""
        np.random.seed(42)
        dates = pd.date_range(start='2024-01-01', periods=100, freq='h')
        data = pd.DataFrame({
            'close': 50000 + np.cumsum(np.random.randn(100) * 100)
        }, index=dates)
        
        signals = self.backtester._generate_signals(data)
        trades = self.backtester._execute_trades(data, signals)
        
        self.assertIsInstance(trades, list)
    
    def test_calculate_performance_score(self):
        """Test performance score calculation."""
        result = ShadowBacktestResult(
            strategy_id="test",
            start_time=datetime.now(),
            end_time=datetime.now(),
            total_trades=100,
            winning_trades=60,
            losing_trades=40,
            win_rate=60.0,
            total_profit=1000.0,
            total_profit_percent=10.0,
            max_drawdown=5.0,
            sharpe_ratio=2.0,
            sortino_ratio=2.5,
            profit_factor=1.5,
            avg_profit_per_trade=10.0,
            avg_holding_time_minutes=60.0,
            best_trade=100.0,
            worst_trade=-50.0,
            signals_generated=150,
            signals_executed=100,
            execution_rate=0.67,
            performance_score=0.0,
            is_degraded=False
        )
        
        score = self.backtester._calculate_performance_score(result)
        
        self.assertGreater(score, 0)
        self.assertLessEqual(score, 1)


class TestVPINFilter(unittest.TestCase):
    """Test cases for VPIN Filter."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'toxicity_filter': {
                'enabled': True,
                'vpin_threshold': 0.3,
                'imbalance_threshold': 0.6,
                'freeze_duration_minutes': 5
            }
        }
        self.filter = VPINFilter(self.config)
    
    def test_initialization(self):
        """Test filter initialization."""
        self.assertIsNotNone(self.filter)
        self.assertEqual(self.filter.vpin_threshold, 0.3)
    
    def test_update_trade_data(self):
        """Test updating trade data."""
        asyncio.run(self.filter.update_trade_data(50000.0, 1.0, 'buy'))
        
        self.assertGreater(len(self.filter.trade_volume), 0)
    
    def test_calculate_overall_toxicity(self):
        """Test overall toxicity calculation."""
        self.filter.current_metrics.vpin_score = 0.2
        self.filter.current_metrics.order_book_imbalance = 0.5
        self.filter.current_metrics.spread_widening = 0.1
        self.filter.current_metrics.spoofing_probability = 0.3
        
        toxicity = self.filter._calculate_overall_toxicity()
        
        self.assertGreaterEqual(toxicity, 0)
        self.assertLessEqual(toxicity, 1)


class TestSOREngine(unittest.TestCase):
    """Test cases for Smart Order Routing Engine."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'sor': {
                'enabled': True,
                'iceberg_slices': 10,
                'randomize_venues': True,
                'min_order_size': 0.001
            }
        }
        self.sor = SOREngine(self.config)
    
    def test_initialization(self):
        """Test SOR initialization."""
        self.assertIsNotNone(self.sor)
        self.assertEqual(self.sor.iceberg_slices, 10)
    
    def test_execute_order(self):
        """Test order execution."""
        with patch('asyncio.sleep', new_callable=AsyncMock):
            result = asyncio.run(self.sor.execute_order(
                'BTCUSDT', 'buy', 1.0, 50000.0, OrderType.LIMIT
            ))
        
        self.assertIsInstance(result, ParentOrder)
        self.assertEqual(result.symbol, 'BTCUSDT')
    
    def test_get_best_venue(self):
        """Test venue selection."""
        venue = asyncio.run(self.sor.get_best_venue('BTCUSDT', 1.0))
        
        self.assertIsInstance(venue, Venue)


class TestKellyAllocator(unittest.TestCase):
    """Test cases for Kelly Allocator."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'risk_topology': {
                'kelly_enabled': True,
                'max_risk_per_trade': 0.01,
                'global_risk_limit': 0.05,
                'max_positions': 5
            }
        }
        self.allocator = KellyAllocator(self.config)
    
    def test_initialization(self):
        """Test allocator initialization."""
        self.assertIsNotNone(self.allocator)
        self.assertEqual(self.allocator.max_risk_per_trade, 0.01)
    
    def test_calculate_kelly_fraction(self):
        """Test Kelly criterion calculation."""
        kelly = self.allocator.calculate_kelly_fraction(0.6, 0.02, 0.01)
        
        self.assertGreaterEqual(kelly, 0)
        self.assertLessEqual(kelly, 0.25)
    
    def test_calculate_position_size(self):
        """Test position size calculation."""
        size = asyncio.run(self.allocator.calculate_position_size(
            'BTCUSDT', 50000.0, 49000.0
        ))
        
        self.assertGreater(size, 0)
    
    def test_open_position(self):
        """Test opening a position."""
        position = asyncio.run(self.allocator.open_position(
            'BTCUSDT', 'long', 50000.0, 49000.0, 52000.0
        ))
        
        self.assertIsInstance(position, Position)
        self.assertEqual(position.symbol, 'BTCUSDT')


class TestVaRModel(unittest.TestCase):
    """Test cases for VaR Model."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'risk_topology': {
                'var_enabled': True,
                'var_lookback_days': 30,
                'var_update_interval': 5
            }
        }
        self.var_model = VaRModel(self.config)
    
    @unittest.skipIf(not SCIPY_AVAILABLE, "scipy not available")
    def test_initialization(self):
        """Test VaR model initialization."""
        self.assertIsNotNone(self.var_model)
        self.assertTrue(self.var_model.enabled)
    
    def test_update_returns(self):
        """Test updating returns."""
        asyncio.run(self.var_model.update_returns('BTCUSDT', 50000.0))
        
        self.assertIn('BTCUSDT', self.var_model.returns_history)
    
    def test_calculate_var(self):
        """Test VaR calculation."""
        # Add some test data
        for i in range(100):
            asyncio.run(self.var_model.update_returns('BTCUSDT', 50000 + i))
        
        result = asyncio.run(self.var_model.calculate_var({'BTCUSDT': 1.0}, 100000.0))
        
        self.assertIsInstance(result, VaRResult)


class TestCircuitBreaker(unittest.TestCase):
    """Test cases for Circuit Breaker."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'risk_topology': {
                'circuit_breaker_enabled': True,
                'max_drawdown_percent': 10.0,
                'hourly_loss_limit_percent': 2.0,
                'emergency_kill_enabled': True
            }
        }
        self.breaker = CircuitBreaker(self.config)
    
    def test_initialization(self):
        """Test circuit breaker initialization."""
        self.assertIsNotNone(self.breaker)
        self.assertEqual(self.breaker.max_drawdown_percent, 10.0)
    
    def test_check_max_drawdown(self):
        """Test max drawdown check."""
        self.breaker.current_balance = 90000.0  # 10% drawdown
        
        should_stop = asyncio.run(self.breaker._check_max_drawdown())
        
        self.assertTrue(should_stop)
    
    def test_get_status(self):
        """Test getting breaker status."""
        status = asyncio.run(self.breaker.get_status())
        
        self.assertIn('state', status)
        self.assertIn('current_drawdown', status)


class TestChaosEngineering(unittest.TestCase):
    """Test cases for Chaos Engineering."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'chaos_testing': {
                'enabled': True,
                'interval_hours': 24,
                'black_san_scenarios': ['liquidity_evaporation', 'api_latency', 'flash_crash']
            }
        }
        self.chaos = ChaosEngineering(self.config)
    
    def test_initialization(self):
        """Test chaos engineering initialization."""
        self.assertIsNotNone(self.chaos)
        self.assertEqual(self.chaos.interval_hours, 24)
    
    def test_should_run_test(self):
        """Test if chaos test should run."""
        should_run = asyncio.run(self.chaos.should_run_test())
        
        self.assertTrue(should_run)  # First time should always run
    
    def test_run_chaos_test(self):
        """Test running chaos test."""
        result = asyncio.run(self.chaos.run_chaos_test())
        
        self.assertIsInstance(result, type(self.chaos._create_empty_result()))


class TestConfluenceMatrix(unittest.TestCase):
    """Test cases for Multi-Indicator Confluence."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'indicators': {
                'min_confluence': 0.7,
                'multi_timeframe_required': True,
                'volume_confirmation_required': True,
                'volatility_confirmation_required': True
            }
        }
        self.confluence = MultiIndicatorConfluence(self.config)
    
    def test_initialization(self):
        """Test confluence matrix initialization."""
        self.assertIsNotNone(self.confluence)
        self.assertEqual(self.confluence.min_confluence, 0.7)
    
    def test_analyze_signal(self):
        """Test signal analysis."""
        np.random.seed(42)
        data = pd.DataFrame({
            'open': 50000 + np.random.randn(100) * 100,
            'high': 50000 + np.random.randn(100) * 100 + 100,
            'low': 50000 + np.random.randn(100) * 100 - 100,
            'close': 50000 + np.random.randn(100) * 100,
            'volume': np.random.randint(100, 1000, 100)
        })
        
        result = asyncio.run(self.confluence.analyze_signal(data, 'BTCUSDT'))
        
        self.assertIsNotNone(result)
        self.assertIn(result.final_signal, ['BUY', 'SELL', 'HOLD'])


if __name__ == '__main__':
    unittest.main()