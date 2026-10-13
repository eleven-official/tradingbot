"""
Tests for evolutionary features (ML strategy selector, regime detector, self-healing)
"""
import unittest
import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime
from collections import defaultdict

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.ml_strategy_selector import MLStrategySelector, MarketCondition
from core.regime_detector import RealTimeRegimeDetector, MarketRegime
from core.self_healing import SelfHealingSystem, SystemHealth


class TestMLStrategySelector(unittest.TestCase):
    """Test cases for ML strategy selector."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'ml_strategy_selector': {
                'enabled': True,
                'learning_rate': 0.1,
                'retrain_interval_hours': 24,
                'min_samples': 10
            }
        }
        self.ml_selector = MLStrategySelector(self.config)
        
        # Create sample price data
        self.sample_data = self._create_sample_data()
    
    def _create_sample_data(self, periods: int = 100) -> pd.DataFrame:
        """Create sample price data for testing."""
        np.random.seed(42)
        close_prices = 50000 + np.cumsum(np.random.randn(periods) * 100)
        
        df = pd.DataFrame({
            'open': close_prices + np.random.randn(periods) * 50,
            'high': close_prices + np.abs(np.random.randn(periods) * 100),
            'low': close_prices - np.abs(np.random.randn(periods) * 100),
            'close': close_prices,
            'volume': np.random.randint(100, 1000, periods)
        })
        
        return df
    
    def test_initialization(self):
        """Test ML selector initialization."""
        self.assertTrue(self.ml_selector.enabled)
        self.assertEqual(self.ml_selector.learning_rate, 0.1)
        self.assertEqual(self.ml_selector.min_samples, 10)
    
    def test_market_condition_analysis(self):
        """Test market condition analysis."""
        condition = self.ml_selector.analyze_market_condition(self.sample_data)
        
        self.assertIsInstance(condition, MarketCondition)
        self.assertIn(condition, [MarketCondition.TRENDING_UP, MarketCondition.TRENDING_DOWN,
                                MarketCondition.RANGING, MarketCondition.VOLATILE, 
                                MarketCondition.QUIET, MarketCondition.BREAKOUT])
    
    def test_strategy_selection(self):
        """Test strategy selection."""
        available_strategies = ['strategy1', 'strategy2', 'strategy3']
        selected = self.ml_selector.select_strategy(self.sample_data, available_strategies)
        
        self.assertIn(selected, available_strategies)
    
    def test_performance_recording(self):
        """Test performance recording."""
        trade_result = {'net': 150.0, 'strategy': 'test_strategy'}
        condition = MarketCondition.TRENDING_UP
        
        self.ml_selector.record_strategy_performance('test_strategy', trade_result, condition)
        
        self.assertIn('test_strategy', self.ml_selector.strategy_performance)
        perf = self.ml_selector.strategy_performance['test_strategy']
        self.assertEqual(perf.total_trades, 1)
    
    def test_fitness_score_calculation(self):
        """Test fitness score calculation."""
        # Record some trades
        for i in range(15):
            pnl = 100 if i % 2 == 0 else -50
            trade_result = {'net': pnl, 'strategy': 'test_strategy'}
            condition = MarketCondition.TRENDING_UP
            self.ml_selector.record_strategy_performance('test_strategy', trade_result, condition)
        
        perf = self.ml_selector.strategy_performance['test_strategy']
        self.assertGreater(perf.fitness_score, 0)
        self.assertGreater(perf.total_trades, 10)
    
    def test_condition_weights_update(self):
        """Test condition weights update."""
        # Record enough trades to trigger weight updates
        for i in range(15):
            pnl = 100 if i % 2 == 0 else -30
            trade_result = {'net': pnl, 'strategy': 'test_strategy'}
            condition = MarketCondition.TRENDING_UP
            self.ml_selector.record_strategy_performance('test_strategy', trade_result, condition)
        
        weights = self.ml_selector.condition_strategy_weights[condition.value]
        self.assertIn('test_strategy', weights)
    
    def test_strategy_rankings(self):
        """Test strategy rankings."""
        # Record performance for multiple strategies
        for strategy in ['strategy1', 'strategy2']:
            for i in range(15):
                pnl = 100 if strategy == 'strategy1' else 50
                trade_result = {'net': pnl, 'strategy': strategy}
                condition = MarketCondition.TRENDING_UP
                self.ml_selector.record_strategy_performance(strategy, trade_result, condition)
        
        rankings = self.ml_selector.get_strategy_rankings()
        self.assertGreater(len(rankings), 0)
    
    def test_model_state_persistence(self):
        """Test model state save and load."""
        # Record some performance
        trade_result = {'net': 100.0, 'strategy': 'test_strategy'}
        condition = MarketCondition.TRENDING_UP
        self.ml_selector.record_strategy_performance('test_strategy', trade_result, condition)
        
        # Save state
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_file = f.name
        
        try:
            self.ml_selector.save_state(temp_file)
            
            # Create new selector and load state
            new_selector = MLStrategySelector(self.config)
            new_selector.load_state(temp_file)
            
            # Verify state was loaded
            self.assertIn('test_strategy', new_selector.strategy_performance)
        finally:
            import os
            if os.path.exists(temp_file):
                os.remove(temp_file)


class TestRegimeDetector(unittest.TestCase):
    """Test cases for regime detector."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'regime_detector': {
                'enabled': True,
                'lookback_period': 100,
                'volatility_threshold': 0.02,
                'trend_threshold': 0.01,
                'min_regime_duration': 30
            }
        }
        self.regime_detector = RealTimeRegimeDetector(self.config)
    
    def test_initialization(self):
        """Test regime detector initialization."""
        self.assertTrue(self.regime_detector.enabled)
        self.assertEqual(self.regime_detector.lookback_period, 100)
        self.assertEqual(self.regime_detector.volatility_threshold, 0.02)
    
    def test_market_data_update(self):
        """Test market data update."""
        self.regime_detector.update_market_data(50000.0, 1000.0)
        
        self.assertEqual(len(self.regime_detector.price_history), 1)
        self.assertEqual(len(self.regime_detector.volume_history), 1)
    
    def test_regime_detection(self):
        """Test regime detection."""
        # Update with enough data for detection
        for i in range(25):
            price = 50000 + i * 10 + np.random.randn() * 50
            volume = 1000 + np.random.randint(-100, 100)
            self.regime_detector.update_market_data(price, volume)
        
        regime = self.regime_detector.get_current_regime()
        self.assertIsNotNone(regime)
        self.assertIn(regime, [MarketRegime.BULL_TREND, MarketRegime.BEAR_TREND,
                              MarketRegime.SIDEWAYS, MarketRegime.HIGH_VOLATILITY,
                              MarketRegime.LOW_VOLATILITY, MarketRegime.BREAKOUT_UP,
                              MarketRegime.BREAKOUT_DOWN, MarketRegime.UNCERTAIN])
    
    def test_regime_characteristics(self):
        """Test regime characteristics."""
        # Update with data
        for i in range(25):
            price = 50000 + i * 10 + np.random.randn() * 50
            volume = 1000 + np.random.randint(-100, 100)
            self.regime_detector.update_market_data(price, volume)
        
        characteristics = self.regime_detector.get_regime_characteristics()
        
        if characteristics:
            self.assertIsNotNone(characteristics.regime)
            self.assertGreater(characteristics.volatility, 0)
            self.assertIsNotNone(characteristics.support_level)
            self.assertIsNotNone(characteristics.resistance_level)
    
    def test_regime_recommendations(self):
        """Test regime-based recommendations."""
        # Update with data
        for i in range(25):
            price = 50000 + i * 10 + np.random.randn() * 50
            volume = 1000 + np.random.randint(-100, 100)
            self.regime_detector.update_market_data(price, volume)
        
        recommendations = self.regime_detector.get_regime_recommendations()
        
        self.assertGreater(len(recommendations), 0)
        self.assertIsInstance(recommendations, list)
    
    def test_regime_statistics(self):
        """Test regime statistics."""
        stats = self.regime_detector.get_regime_statistics()
        
        self.assertIn('current_regime', stats)
        self.assertIn('current_volatility', stats)
        self.assertIn('current_trend_strength', stats)
    
    def test_regime_transition(self):
        """Test regime transition handling."""
        # Update with trend data
        for i in range(25):
            price = 50000 + i * 10 + np.random.randn() * 50
            volume = 1000 + np.random.randint(-100, 100)
            self.regime_detector.update_market_data(price, volume)
        
        first_regime = self.regime_detector.get_current_regime()
        
        # Update with different trend
        for i in range(25):
            price = 50000 - i * 10 + np.random.randn() * 50
            volume = 1000 + np.random.randint(-100, 100)
            self.regime_detector.update_market_data(price, volume)
        
        second_regime = self.regime_detector.get_current_regime()
        
        # Regime may or may not change depending on data
        self.assertIsNotNone(second_regime)


class TestSelfHealingSystem(unittest.TestCase):
    """Test cases for self-healing system."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'self_healing': {
                'enabled': True,
                'health_check_interval': 60,
                'max_recovery_attempts': 3,
                'degraded_threshold': 3,
                'critical_threshold': 5
            }
        }
        self.healing_system = SelfHealingSystem(self.config)
    
    def test_initialization(self):
        """Test self-healing system initialization."""
        self.assertTrue(self.healing_system.enabled)
        self.assertEqual(self.healing_system.max_recovery_attempts, 3)
        self.assertEqual(self.healing_system.degraded_threshold, 3)
    
    def test_health_checks(self):
        """Test health check execution."""
        health_checks = self.healing_system.perform_health_checks()
        
        self.assertEqual(len(health_checks), 5)  # 5 components
        for check in health_checks:
            self.assertIsInstance(check.status, SystemHealth)
    
    def test_component_health_tracking(self):
        """Test component health tracking."""
        self.healing_system.perform_health_checks()
        
        self.assertIn('api_connection', self.healing_system.component_health)
        self.assertIn('data_feed', self.healing_system.component_health)
        self.assertIn('order_execution', self.healing_system.component_health)
    
    def test_overall_health_update(self):
        """Test overall health update."""
        self.healing_system.perform_health_checks()
        
        health = self.healing_system.get_system_health()
        self.assertIn(health, [SystemHealth.HEALTHY, SystemHealth.DEGRADED, 
                              SystemHealth.CRITICAL, SystemHealth.FAILED])
    
    def test_health_report(self):
        """Test health report generation."""
        self.healing_system.perform_health_checks()
        
        report = self.healing_system.get_health_report()
        
        self.assertIn('overall_health', report)
        self.assertIn('component_health', report)
        self.assertIn('last_health_check', report)
    
    def test_recovery_action_registration(self):
        """Test recovery action registration."""
        def dummy_action():
            pass
        
        self.healing_system.register_recovery_action('api_connection', dummy_action)
        
        self.assertIn('api_connection', self.healing_system.recovery_actions)
        self.assertEqual(len(self.healing_system.recovery_actions['api_connection']), 1)
    
    def test_recovery_attempts_reset(self):
        """Test recovery attempts reset."""
        self.healing_system.recovery_attempts['api_connection'] = 3
        
        self.healing_system.reset_recovery_attempts('api_connection')
        
        self.assertNotIn('api_connection', self.healing_system.recovery_attempts)
    
    def test_force_health_check(self):
        """Test forced health check."""
        health_checks = self.healing_system.force_health_check()
        
        self.assertEqual(len(health_checks), 5)
        self.assertIsNotNone(self.healing_system.last_health_check)


if __name__ == '__main__':
    unittest.main()