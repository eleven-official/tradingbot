"""
Tests for metrics module.
"""
import unittest
import sys
import os
from datetime import datetime
from unittest.mock import patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.metrics import MetricsCollector, MetricsTimer


class TestMetricsCollector(unittest.TestCase):
    """Test cases for MetricsCollector."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'metrics': {
                'enabled': True
            }
        }
        self.metrics = MetricsCollector(self.config)
    
    def test_initialization(self):
        """Test MetricsCollector initialization."""
        self.assertTrue(self.metrics.metrics_enabled)
        self.assertEqual(self.metrics.total_trades, 0)
        self.assertEqual(self.metrics.winning_trades, 0)
        self.assertEqual(self.metrics.total_pnl, 0.0)
    
    def test_record_winning_trade(self):
        """Test recording a winning trade."""
        trade_result = {
            'net': 1000.0,
            'strategy': 'TestStrategy'
        }
        
        self.metrics.record_trade(trade_result)
        
        self.assertEqual(self.metrics.total_trades, 1)
        self.assertEqual(self.metrics.winning_trades, 1)
        self.assertEqual(self.metrics.losing_trades, 0)
        self.assertEqual(self.metrics.total_pnl, 1000.0)
        self.assertEqual(self.metrics.best_trade, 1000.0)
    
    def test_record_losing_trade(self):
        """Test recording a losing trade."""
        trade_result = {
            'net': -500.0,
            'strategy': 'TestStrategy'
        }
        
        self.metrics.record_trade(trade_result)
        
        self.assertEqual(self.metrics.total_trades, 1)
        self.assertEqual(self.metrics.winning_trades, 0)
        self.assertEqual(self.metrics.losing_trades, 1)
        self.assertEqual(self.metrics.total_pnl, -500.0)
        self.assertEqual(self.metrics.worst_trade, -500.0)
    
    def test_record_scratch_trade(self):
        """Test recording a scratch trade."""
        trade_result = {
            'net': 0.0,
            'strategy': 'TestStrategy'
        }
        
        self.metrics.record_trade(trade_result)
        
        self.assertEqual(self.metrics.total_trades, 1)
        self.assertEqual(self.metrics.scratch_trades, 1)
        self.assertEqual(self.metrics.total_pnl, 0.0)
    
    def test_win_rate_calculation(self):
        """Test win rate calculation."""
        # Record 3 wins and 2 losses
        for _ in range(3):
            self.metrics.record_trade({'net': 100.0, 'strategy': 'Test'})
        for _ in range(2):
            self.metrics.record_trade({'net': -50.0, 'strategy': 'Test'})
        
        win_rate = self.metrics.get_win_rate()
        self.assertEqual(win_rate, 60.0)  # 3 wins out of 5 trades
    
    def test_win_rate_no_trades(self):
        """Test win rate with no trades."""
        win_rate = self.metrics.get_win_rate()
        self.assertEqual(win_rate, 0.0)
    
    def test_profit_factor(self):
        """Test profit factor calculation."""
        # Record wins and losses
        self.metrics.record_trade({'net': 200.0, 'strategy': 'Test'})
        self.metrics.record_trade({'net': 300.0, 'strategy': 'Test'})
        self.metrics.record_trade({'net': -100.0, 'strategy': 'Test'})
        self.metrics.record_trade({'net': -50.0, 'strategy': 'Test'})
        
        profit_factor = self.metrics.get_profit_factor()
        
        # Gross wins = 500, Gross losses = 150
        # Profit factor = 500 / 150 = 3.33
        self.assertAlmostEqual(profit_factor, 3.33, places=1)
    
    def test_profit_factor_no_losses(self):
        """Test profit factor with no losses."""
        self.metrics.record_trade({'net': 100.0, 'strategy': 'Test'})
        
        profit_factor = self.metrics.get_profit_factor()
        self.assertEqual(profit_factor, float('inf'))
    
    def test_strategy_performance_tracking(self):
        """Test strategy performance tracking."""
        # Record trades for different strategies
        self.metrics.record_trade({'net': 100.0, 'strategy': 'StrategyA'})
        self.metrics.record_trade({'net': -50.0, 'strategy': 'StrategyA'})
        self.metrics.record_trade({'net': 200.0, 'strategy': 'StrategyB'})
        
        summary = self.metrics.get_strategy_summary()
        
        self.assertIn('StrategyA', summary)
        self.assertIn('StrategyB', summary)
        self.assertEqual(summary['StrategyA']['trades'], 2)
        self.assertEqual(summary['StrategyB']['trades'], 1)
    
    def test_record_order_latency(self):
        """Test recording order latency."""
        self.metrics.record_order_latency(0.5)
        self.metrics.record_order_latency(0.7)
        self.metrics.record_order_latency(0.6)
        
        avg_latency = self.metrics.get_average_order_latency()
        self.assertAlmostEqual(avg_latency, 0.6, places=1)
    
    def test_record_signal_time(self):
        """Test recording signal generation time."""
        self.metrics.record_signal_time(0.1)
        self.metrics.record_signal_time(0.15)
        self.metrics.record_signal_time(0.12)
        
        avg_time = self.metrics.get_average_signal_time()
        self.assertAlmostEqual(avg_time, 0.12, places=2)
    
    def test_drawdown_tracking(self):
        """Test drawdown tracking."""
        # Start with profit
        self.metrics.record_trade({'net': 1000.0, 'strategy': 'Test'})
        self.assertEqual(self.metrics.peak_equity, 1000.0)
        self.assertEqual(self.metrics.current_drawdown, 0.0)
        
        # Take a loss
        self.metrics.record_trade({'net': -300.0, 'strategy': 'Test'})
        self.assertEqual(self.metrics.current_drawdown, 300.0)
        self.assertEqual(self.metrics.max_drawdown, 300.0)
        
        # New peak
        self.metrics.record_trade({'net': 500.0, 'strategy': 'Test'})
        self.assertEqual(self.metrics.peak_equity, 1200.0)
        self.assertEqual(self.metrics.current_drawdown, 0.0)
    
    def test_get_session_summary(self):
        """Test session summary generation."""
        self.metrics.record_trade({'net': 100.0, 'strategy': 'Test'})
        self.metrics.record_trade({'net': -50.0, 'strategy': 'Test'})
        
        summary = self.metrics.get_session_summary()
        
        self.assertIn('total_trades', summary)
        self.assertIn('win_rate', summary)
        self.assertIn('total_pnl', summary)
        self.assertEqual(summary['total_trades'], 2)
    
    def test_get_health_status(self):
        """Test health status generation."""
        health = self.metrics.get_health_status()
        
        self.assertIn('healthy', health)
        self.assertIn('session_active', health)
        self.assertTrue(health['healthy'])
        self.assertTrue(health['session_active'])
    
    def test_reset_metrics(self):
        """Test resetting metrics."""
        # Record some data
        self.metrics.record_trade({'net': 100.0, 'strategy': 'Test'})
        self.metrics.record_order_latency(0.5)
        
        # Reset
        self.metrics.reset_metrics()
        
        self.assertEqual(self.metrics.total_trades, 0)
        self.assertEqual(self.metrics.total_pnl, 0.0)
        self.assertEqual(len(self.metrics.order_latencies), 0)
    
    def test_metrics_disabled(self):
        """Test behavior when metrics are disabled."""
        config = {'metrics': {'enabled': False}}
        metrics = MetricsCollector(config)
        
        metrics.record_trade({'net': 100.0, 'strategy': 'Test'})
        metrics.record_order_latency(0.5)
        
        self.assertEqual(metrics.total_trades, 0)
        self.assertEqual(len(metrics.order_latencies), 0)


class TestMetricsTimer(unittest.TestCase):
    """Test cases for MetricsTimer."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {'metrics': {'enabled': True}}
        self.metrics = MetricsCollector(self.config)
    
    def test_timer_context_manager(self):
        """Test MetricsTimer as context manager."""
        import time
        
        with MetricsTimer(self.metrics, 'signal'):
            time.sleep(0.01)
        
        avg_time = self.metrics.get_average_signal_time()
        self.assertIsNotNone(avg_time)
        self.assertGreater(avg_time, 0)
    
    def test_timer_records_correct_metric(self):
        """Test that timer records to the correct metric."""
        import time
        
        with MetricsTimer(self.metrics, 'order'):
            time.sleep(0.01)
        
        self.assertEqual(len(self.metrics.order_latencies), 1)
        self.assertEqual(len(self.metrics.signal_generation_times), 0)


if __name__ == '__main__':
    unittest.main()