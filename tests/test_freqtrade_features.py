"""
Tests for Freqtrade-inspired components
"""
import unittest
import sys
import os
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.freqtrade_backtester import FreqtradeBacktester, BacktestResult
from core.pairlist_manager import PairlistManager
from core.edge_positioning import EdgePositioning, Position
from core.strategy_interface import RSI_MACD_Strategy, Bollinger_Reversal_Strategy

# Check if ccxt is available
try:
    import ccxt
    CCXT_AVAILABLE = True
except ImportError:
    CCXT_AVAILABLE = False


class TestFreqtradeBacktester(unittest.TestCase):
    """Test cases for Freqtrade backtester."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'backtesting': {
                'stake_currency': 'AUD',
                'stake_amount': 1000.0,
                'fee': 0.001,
                'max_open_trades': 5,
                'database_path': 'state/.test_backtest_results.sqlite'
            }
        }
        self.backtester = FreqtradeBacktester(self.config)
        
        # Create sample data
        np.random.seed(42)
        dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
        close_prices = 50000 + np.cumsum(np.random.randn(100) * 100)
        
        self.sample_data = pd.DataFrame({
            'open': close_prices + np.random.randn(100) * 50,
            'high': close_prices + np.abs(np.random.randn(100) * 100),
            'low': close_prices - np.abs(np.random.randn(100) * 100),
            'close': close_prices,
            'volume': np.random.randint(1000, 10000, 100)
        }, index=dates)
        
        self.strategy = RSI_MACD_Strategy()

    def tearDown(self):
        """Remove the test-only database without touching operator history."""
        Path(self.config['backtesting']['database_path']).unlink(missing_ok=True)
    
    def test_initialization(self):
        """Test backtester initialization."""
        self.assertIsNotNone(self.backtester)
        self.assertEqual(self.backtester.stake_currency, 'AUD')
        self.assertEqual(self.backtester.stake_amount, 1000.0)
    
    def test_run_backtest(self):
        """Test running a backtest."""
        result = self.backtester.run_backtest(self.strategy, self.sample_data)
        
        self.assertIsInstance(result, BacktestResult)
        self.assertGreaterEqual(result.total_trades, 0)
    
    def test_backtest_metrics(self):
        """Test backtest metrics calculation."""
        result = self.backtester.run_backtest(self.strategy, self.sample_data)
        
        if result.total_trades > 0:
            self.assertGreaterEqual(result.win_rate, 0)
            self.assertLessEqual(result.win_rate, 100)
            self.assertGreaterEqual(result.profit_factor, 0)
    
    def test_empty_backtest(self):
        """Test backtest with no data."""
        empty_data = pd.DataFrame()
        result = self.backtester.run_backtest(self.strategy, empty_data)
        
        self.assertEqual(result.total_trades, 0)
    
    def test_database_save(self):
        """Test saving backtest results to database."""
        result = self.backtester.run_backtest(self.strategy, self.sample_data)
        
        # Should not raise an error
        self.backtester._save_backtest_result(result)
    
    def test_get_backtest_history(self):
        """Test retrieving backtest history."""
        result = self.backtester.run_backtest(self.strategy, self.sample_data)
        
        history = self.backtester.get_backtest_history(limit=5)
        
        self.assertIsInstance(history, list)
        self.assertLessEqual(len(history), 5)


class TestPairlistManager(unittest.TestCase):
    """Test cases for pairlist manager."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'pairlist': {
                'method': 'static',
                'number_of_pairs': 5,
                'static_pairs': ['BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'ADA/USDT', 'SOL/USDT'],
                'blacklist': [],
                'whitelist': []
            },
            'crypto_broker': {
                'exchange': 'binance'
            }
        }
        self.pairlist_manager = PairlistManager(self.config)
    
    @unittest.skipIf(not CCXT_AVAILABLE, "ccxt not available")
    def test_volume_pairlist(self):
        """Test volume-based pairlist generation."""
        self.pairlist_manager.method = self.pairlist_manager.PairlistMethod.VOLUME_PAIRLIST
        pairs = self.pairlist_manager.get_pairlist()
        
        self.assertIsInstance(pairs, list)
    
    def test_initialization(self):
        """Test pairlist manager initialization."""
        self.assertIsNotNone(self.pairlist_manager)
        self.assertEqual(len(self.pairlist_manager.static_pairs), 5)
    
    def test_static_pairlist(self):
        """Test static pairlist generation."""
        pairs = self.pairlist_manager.get_pairlist()
        
        self.assertIsInstance(pairs, list)
        self.assertEqual(len(pairs), 5)
    
    def test_blacklist(self):
        """Test blacklist functionality."""
        self.pairlist_manager.add_to_blacklist('BTC/USDT')
        
        pairs = self.pairlist_manager.get_pairlist()
        
        self.assertNotIn('BTC/USDT', pairs)
        self.assertEqual(len(pairs), 4)
    
    def test_whitelist(self):
        """Test whitelist functionality."""
        self.pairlist_manager.add_to_whitelist('BTC/USDT')
        self.pairlist_manager.add_to_whitelist('ETH/USDT')
        
        pairs = self.pairlist_manager.get_pairlist()
        
        self.assertIn('BTC/USDT', pairs)
        self.assertIn('ETH/USDT', pairs)
        self.assertEqual(len(pairs), 2)
    
    def test_pairlist_status(self):
        """Test getting pairlist status."""
        status = self.pairlist_manager.get_pairlist_status()
        
        self.assertIn('method', status)
        self.assertIn('total_pairs', status)
        self.assertIn('pairs', status)


class TestEdgePositioning(unittest.TestCase):
    """Test cases for edge positioning."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'positioning': {
                'method': 'edge',
                'available_capital': 10000.0,
                'max_risk_per_trade': 0.01,
                'max_risk_total': 0.05,
                'max_position_size': 0.5,
                'min_position_size': 0.01,
                'win_rate': 0.5,
                'risk_reward_ratio': 2.0
            }
        }
        self.positioning = EdgePositioning(self.config)
    
    def test_initialization(self):
        """Test edge positioning initialization."""
        self.assertIsNotNone(self.positioning)
        self.assertEqual(self.positioning.available_capital, 10000.0)
        self.assertEqual(self.positioning.max_risk_per_trade, 0.01)
    
    def test_edge_position_size(self):
        """Test edge-based position sizing."""
        position = self.positioning.calculate_position_size(
            'BTC/USDT',
            entry_price=50000.0,
            stop_loss=49000.0,
            take_profit=52000.0,
            confidence=0.7
        )
        
        self.assertIsInstance(position, Position)
        self.assertEqual(position.symbol, 'BTC/USDT')
        self.assertGreater(position.size, 0)
        self.assertGreater(position.value, 0)
    
    def test_fixed_position_size(self):
        """Test fixed position sizing."""
        from core.edge_positioning import PositioningMethod
        self.positioning.method = PositioningMethod.FIXED
        self.positioning.positioning_config = {'fixed_amount': 500.0}
        
        position = self.positioning.calculate_position_size(
            'BTC/USDT',
            entry_price=50000.0,
            stop_loss=49000.0,
            take_profit=52000.0
        )
        
        self.assertEqual(position.value, 500.0)
    
    def test_percentage_position_size(self):
        """Test percentage-based position sizing."""
        from core.edge_positioning import PositioningMethod
        self.positioning.method = PositioningMethod.PERCENTAGE
        self.positioning.positioning_config = {'position_percent': 0.1}
        
        position = self.positioning.calculate_position_size(
            'BTC/USDT',
            entry_price=50000.0,
            stop_loss=49000.0,
            take_profit=52000.0
        )
        
        self.assertEqual(position.value, 1000.0)  # 10% of 10000
    
    def test_can_open_position(self):
        """Test checking if position can be opened."""
        position = self.positioning.calculate_position_size(
            'BTC/USDT',
            entry_price=50000.0,
            stop_loss=49000.0,
            take_profit=52000.0
        )
        
        can_open = self.positioning.can_open_position(position)
        
        self.assertTrue(can_open)
    
    def test_open_and_close_position(self):
        """Test opening and closing positions."""
        position = self.positioning.calculate_position_size(
            'BTC/USDT',
            entry_price=50000.0,
            stop_loss=49000.0,
            take_profit=52000.0
        )
        
        self.positioning.open_position(position)
        
        self.assertIn('BTC/USDT', self.positioning.current_positions)
        
        pnl = self.positioning.close_position('BTC/USDT', 51000.0)
        
        self.assertNotIn('BTC/USDT', self.positioning.current_positions)
    
    def test_position_status(self):
        """Test getting position status."""
        status = self.positioning.get_position_status()
        
        self.assertIn('method', status)
        self.assertIn('available_capital', status)
        self.assertIn('total_risk', status)
        self.assertIn('open_positions', status)


class TestStrategyInterface(unittest.TestCase):
    """Test cases for strategy interface."""
    
    def test_rsi_macd_strategy(self):
        """Test RSI + MACD strategy."""
        strategy = RSI_MACD_Strategy()
        
        # Create sample data
        np.random.seed(42)
        data = pd.DataFrame({
            'close': 50000 + np.cumsum(np.random.randn(50) * 100),
            'high': 50000 + np.cumsum(np.random.randn(50) * 100) + 100,
            'low': 50000 + np.cumsum(np.random.randn(50) * 100) - 100
        })
        
        signal = strategy.generate_signal(data)
        
        self.assertIn(signal, ['BUY', 'SELL', 'HOLD'])
    
    def test_strategy_parameters(self):
        """Test strategy parameter management."""
        strategy = RSI_MACD_Strategy()
        
        params = strategy.get_parameters()
        
        self.assertIn('rsi_period', params)
        self.assertIn('macd_fast', params)
        
        strategy.set_parameters({'rsi_period': 20})
        
        self.assertEqual(strategy.rsi_period, 20)
    
    def test_bollinger_reversal_strategy(self):
        """Test Bollinger Bands reversal strategy."""
        strategy = Bollinger_Reversal_Strategy()
        
        # Create sample data
        np.random.seed(42)
        data = pd.DataFrame({
            'close': 50000 + np.cumsum(np.random.randn(50) * 100)
        })
        
        signal = strategy.generate_signal(data)
        
        self.assertIn(signal, ['BUY', 'SELL', 'HOLD'])


if __name__ == '__main__':
    unittest.main()
