"""
Tests for evolutionary optimizer module.
"""
import unittest
import sys
import os
import json
import tempfile
from datetime import datetime
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.evolutionary_optimizer import (
    EvolutionaryOptimizer,
    TradingParameters,
    PerformanceMetrics,
    OptimizationTarget
)


class TestTradingParameters(unittest.TestCase):
    """Test cases for TradingParameters."""
    
    def test_initialization(self):
        """Test parameter initialization."""
        params = TradingParameters()
        
        self.assertEqual(params.risk_per_trade, 1.0)
        self.assertEqual(params.stop_loss_percent, 15.0)
        self.assertEqual(params.max_trades_per_day, 5)
    
    def test_mutation(self):
        """Test parameter mutation."""
        params = TradingParameters(risk_per_trade=1.0)
        mutated = params.mutate(mutation_rate=1.0)  # Always mutate
        
        # Parameters should change (within bounds)
        self.assertNotEqual(mutated.risk_per_trade, params.risk_per_trade)
        self.assertGreater(mutated.risk_per_trade, 0)
        self.assertLess(mutated.risk_per_trade, 5.0)
    
    def test_crossover(self):
        """Test parameter crossover."""
        parent1 = TradingParameters(risk_per_trade=1.0, stop_loss_percent=15.0)
        parent2 = TradingParameters(risk_per_trade=2.0, stop_loss_percent=20.0)
        
        child = parent1.crossover(parent2)
        
        # Child should have parameters from either parent
        self.assertIn(child.risk_per_trade, [1.0, 2.0])
        self.assertIn(child.stop_loss_percent, [15.0, 20.0])
    
    def test_to_dict(self):
        """Test parameter serialization."""
        params = TradingParameters(risk_per_trade=1.5)
        data = params.to_dict()
        
        self.assertEqual(data['risk_per_trade'], 1.5)
        self.assertIn('stop_loss_percent', data)
    
    def test_from_dict(self):
        """Test parameter deserialization."""
        data = {'risk_per_trade': 1.5, 'stop_loss_percent': 20.0}
        params = TradingParameters.from_dict(data)
        
        self.assertEqual(params.risk_per_trade, 1.5)
        self.assertEqual(params.stop_loss_percent, 20.0)


class TestPerformanceMetrics(unittest.TestCase):
    """Test cases for PerformanceMetrics."""
    
    def test_initialization(self):
        """Test metrics initialization."""
        metrics = PerformanceMetrics()
        
        self.assertEqual(metrics.total_trades, 0)
        self.assertEqual(metrics.winning_trades, 0)
        self.assertEqual(metrics.win_rate, 0.0)
    
    def test_calculate_fitness_maximize_profit(self):
        """Test fitness calculation for profit maximization."""
        metrics = PerformanceMetrics(
            total_profit=1000.0,
            max_drawdown=200.0
        )
        
        fitness = metrics.calculate_fitness(OptimizationTarget.MAXIMIZE_PROFIT)
        
        # Fitness should be profit - 2*drawdown
        self.assertEqual(fitness, 1000.0 - 400.0)
    
    def test_calculate_fitness_maximize_win_rate(self):
        """Test fitness calculation for win rate maximization."""
        metrics = PerformanceMetrics(
            winning_trades=8,
            total_trades=10
        )
        metrics.win_rate = 0.8
        
        fitness = metrics.calculate_fitness(OptimizationTarget.MAXIMIZE_WIN_RATE)
        
        self.assertEqual(fitness, 80.0)
    
    def test_calculate_fitness_balanced(self):
        """Test balanced fitness calculation."""
        metrics = PerformanceMetrics(
            total_profit=1000.0,
            win_rate=0.6,
            max_drawdown=200.0
        )
        
        fitness = metrics.calculate_fitness(OptimizationTarget.BALANCED)
        
        # Should be profit * win_rate / drawdown
        expected = (1000.0 * 0.6) / 200.0
        self.assertAlmostEqual(fitness, expected)


class TestEvolutionaryOptimizer(unittest.TestCase):
    """Test cases for EvolutionaryOptimizer."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'evolutionary_optimizer': {
                'enabled': True,
                'population_size': 5,
                'mutation_rate': 0.2,
                'elite_count': 1,
                'optimization_target': 'balanced',
                'evolution_interval_days': 1
            },
            'trading_flags': {
                'risk_per_trade_percent': 1.0,
                'stop_loss_percent': 15.0,
                'max_trades_per_day': 5
            },
            'risk_management': {
                'atr_multiplier': 2.0,
                'high_vix_threshold': 22.0
            }
        }
        self.optimizer = EvolutionaryOptimizer(self.config)
    
    def test_initialization(self):
        """Test optimizer initialization."""
        self.assertTrue(self.optimizer.enabled)
        self.assertEqual(self.optimizer.population_size, 5)
        self.assertEqual(len(self.optimizer.population), 5)
    
    def test_record_performance(self):
        """Test performance recording."""
        trade_results = [
            {'net': 100.0},
            {'net': -50.0},
            {'net': 150.0}
        ]
        
        self.optimizer.record_performance(trade_results)
        
        # Check that metrics were updated
        params, metrics = self.optimizer.population[0]
        self.assertEqual(metrics.total_trades, 3)
        self.assertEqual(metrics.winning_trades, 2)
        self.assertEqual(metrics.losing_trades, 1)
    
    def test_should_evolve(self):
        """Test evolution timing."""
        # Should evolve on first call
        self.assertTrue(self.optimizer.should_evolve())
        
        # After evolution, should not evolve immediately
        self.optimizer.last_evolution_date = datetime.now()
        self.assertFalse(self.optimizer.should_evolve())
    
    def test_evolve(self):
        """Test evolution process."""
        # Record some performance data
        trade_results = [
            {'net': 100.0},
            {'net': -50.0},
            {'net': 150.0}
        ]
        self.optimizer.record_performance(trade_results)
        
        # Evolve
        new_params = self.optimizer.evolve()
        
        self.assertIsNotNone(new_params)
        self.assertEqual(self.optimizer.generation, 1)
        self.assertIsNotNone(self.optimizer.last_evolution_date)
    
    def test_evolve_disabled(self):
        """Test that evolution doesn't occur when disabled."""
        self.optimizer.enabled = False
        
        new_params = self.optimizer.evolve()
        
        self.assertIsNone(new_params)
        self.assertEqual(self.optimizer.generation, 0)
    
    def test_get_current_parameters(self):
        """Test getting current parameters."""
        params = self.optimizer.get_current_parameters()
        
        self.assertIsInstance(params, TradingParameters)
        self.assertIn('risk_per_trade', params.to_dict())
    
    def test_get_evolution_status(self):
        """Test getting evolution status."""
        status = self.optimizer.get_evolution_status()
        
        self.assertIn('enabled', status)
        self.assertIn('generation', status)
        self.assertIn('current_parameters', status)
        self.assertIn('optimization_target', status)
    
    def test_apply_parameters_to_config(self):
        """Test applying parameters to configuration."""
        new_params = TradingParameters(risk_per_trade=2.0, stop_loss_percent=20.0)
        
        updated_config = self.optimizer.apply_parameters_to_config(new_params)
        
        self.assertEqual(
            updated_config['trading_flags']['risk_per_trade_percent'],
            2.0
        )
        self.assertEqual(
            updated_config['trading_flags']['stop_loss_percent'],
            20.0
        )
    
    def test_save_and_load_state(self):
        """Test state persistence."""
        # Modify state
        self.optimizer.generation = 5
        self.optimizer.last_evolution_date = datetime.now()
        
        # Save to temp file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_path = f.name
        
        try:
            self.optimizer.save_state(temp_path)
            
            # Create new optimizer and load state
            new_optimizer = EvolutionaryOptimizer(self.config)
            new_optimizer.load_state(temp_path)
            
            self.assertEqual(new_optimizer.generation, 5)
            self.assertIsNotNone(new_optimizer.last_evolution_date)
            
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    def test_population_diversity(self):
        """Test that population maintains diversity."""
        # Get all parameters from population
        param_sets = [params for params, _ in self.optimizer.population]
        
        # Check that not all are identical
        unique_params = set()
        for params in param_sets:
            unique_params.add(tuple(params.to_dict().values()))
        
        # Should have multiple unique parameter sets
        self.assertGreater(len(unique_params), 1)


if __name__ == '__main__':
    unittest.main()