"""
Tests for state manager module.
"""
import unittest
import os
import sys
from datetime import date
from unittest.mock import patch, Mock, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Add state for ledger persistence
_ledger_storage = {}

# Mock infra module functions
def mock_load_daily_pnl(date_str):
    return 0.0

def mock_load_weekly_pnl(week_str):
    return 0.0

def mock_save_daily_pnl(date_str, amount):
    pass

def mock_save_weekly_pnl(week_str, amount):
    pass

def mock_state_path(filename):
    return filename

def mock_read_json(path, default=None):
    return _ledger_storage.get(path, default or {})

def mock_atomic_write_json(path, data):
    global _ledger_storage
    _ledger_storage[path] = data

def mock_load_week_trade_days():
    return []

def mock_add_week_trade_day():
    pass

# Patch infra module
mock_infra = MagicMock()
mock_infra.load_daily_pnl = mock_load_daily_pnl
mock_infra.load_weekly_pnl = mock_load_weekly_pnl
mock_infra.save_daily_pnl = mock_save_daily_pnl
mock_infra.save_weekly_pnl = mock_save_weekly_pnl
mock_infra.state_path = mock_state_path
mock_infra.read_json = mock_read_json
mock_infra.atomic_write_json = mock_atomic_write_json
mock_infra.load_week_trade_days = mock_load_week_trade_days
mock_infra.add_week_trade_day = mock_add_week_trade_day

sys.modules['infra'] = mock_infra

from core.state_manager import StateManager


class TestStateManager(unittest.TestCase):
    """Test cases for StateManager."""
    
    def setUp(self):
        """Set up test fixtures."""
        global _ledger_storage
        _ledger_storage.clear()  # Clear ledger storage for test isolation
        
        self.config = {
            'risk_management': {
                'max_daily_loss_percent': 2.5,
                'max_consecutive_losses': 3
            }
        }
        
        # Patch every persistence dependency in the module. The old setup
        # replaced sys.modules['infra'] after core.state_manager had often
        # already been imported by another test, which leaked real state and
        # created Windows temp-directory cleanup failures.
        self.patchers = [
            patch('core.state_manager.load_daily_pnl', side_effect=mock_load_daily_pnl),
            patch('core.state_manager.load_weekly_pnl', side_effect=mock_load_weekly_pnl),
            patch('core.state_manager.save_daily_pnl', side_effect=mock_save_daily_pnl),
            patch('core.state_manager.save_weekly_pnl', side_effect=mock_save_weekly_pnl),
            patch('core.state_manager.state_path', side_effect=mock_state_path),
            patch('core.state_manager.read_json', side_effect=mock_read_json),
            patch('core.state_manager.atomic_write_json', side_effect=mock_atomic_write_json),
        ]
        for patcher in self.patchers:
            patcher.start()
    
    def tearDown(self):
        """Clean up test fixtures."""
        for patcher in reversed(self.patchers):
            patcher.stop()
    
    def test_initialization(self):
        """Test StateManager initialization."""
        state_manager = StateManager(self.config)
        
        self.assertIsNotNone(state_manager.config)
        self.assertEqual(state_manager.wins_today, 0)
        self.assertEqual(state_manager.losses_today, 0)
        self.assertEqual(state_manager.consecutive_losses, 0)
    
    def test_record_winning_trade(self):
        """Test recording a winning trade."""
        state_manager = StateManager(self.config)
        
        trade_result = {
            'symbol': 'NIFTY',
            'type': 'BUY',
            'net': 1000.0,
            'strategy': 'TestStrategy'
        }
        
        state_manager.record_trade(trade_result)
        
        self.assertEqual(state_manager.wins_today, 1)
        self.assertEqual(state_manager.losses_today, 0)
        self.assertEqual(state_manager.consecutive_losses, 0)
        self.assertEqual(state_manager.realized_pnl_today, 1000.0)
    
    def test_record_losing_trade(self):
        """Test recording a losing trade."""
        state_manager = StateManager(self.config)
        
        trade_result = {
            'symbol': 'NIFTY',
            'type': 'BUY',
            'net': -500.0,
            'strategy': 'TestStrategy'
        }
        
        state_manager.record_trade(trade_result)
        
        self.assertEqual(state_manager.wins_today, 0)
        self.assertEqual(state_manager.losses_today, 1)
        self.assertEqual(state_manager.consecutive_losses, 1)
        self.assertEqual(state_manager.realized_pnl_today, -500.0)
    
    def test_consecutive_losses_counter(self):
        """Test consecutive losses counter."""
        state_manager = StateManager(self.config)
        
        # Record 2 losing trades
        for i in range(2):
            state_manager.record_trade({
                'symbol': 'NIFTY',
                'type': 'BUY',
                'net': -100.0,
                'strategy': 'TestStrategy'
            })
        
        self.assertEqual(state_manager.consecutive_losses, 2)
        
        # Record a winning trade should reset counter
        state_manager.record_trade({
            'symbol': 'NIFTY',
            'type': 'BUY',
            'net': 200.0,
            'strategy': 'TestStrategy'
        })
        
        self.assertEqual(state_manager.consecutive_losses, 0)
    
    def test_check_daily_loss_limit(self):
        """Test daily loss limit check."""
        state_manager = StateManager(self.config)
        state_manager.starting_capital = 100000.0
        
        # Should not trigger limit initially
        self.assertFalse(state_manager.check_daily_loss_limit(2.5, 100000.0))
        
        # Simulate losses
        state_manager.realized_pnl_today = -3000.0
        
        # Should trigger limit (2.5% of 100000 = 2500)
        self.assertTrue(state_manager.check_daily_loss_limit(2.5, 100000.0))
    
    def test_check_consecutive_loss_limit(self):
        """Test consecutive loss limit check."""
        state_manager = StateManager(self.config)
        
        # Should not trigger initially
        self.assertFalse(state_manager.check_consecutive_loss_limit(3))
        
        # Set consecutive losses to 3
        state_manager.consecutive_losses = 3
        
        # Should trigger limit
        self.assertTrue(state_manager.check_consecutive_loss_limit(3))
    
    def test_get_session_summary(self):
        """Test session summary generation."""
        state_manager = StateManager(self.config)
        
        # Record some trades
        state_manager.record_trade({'net': 1000.0, 'strategy': 'Test1'})
        state_manager.record_trade({'net': -500.0, 'strategy': 'Test2'})
        state_manager.record_trade({'net': 0.0, 'strategy': 'Test3'})
        
        summary = state_manager.get_session_summary()
        
        self.assertIn('1W/1L/1S', summary)
        self.assertIn('3 trades', summary)
        self.assertIn('50.0%', summary)  # win rate (1 win / 2 decisive trades)
        self.assertIn('$', summary)  # AUD currency symbol
    
    def test_save_and_load_ledger(self):
        """Test ledger persistence."""
        state_manager = StateManager(self.config)
        
        # Record some trades
        state_manager.record_trade({'net': 1000.0, 'strategy': 'Test1'})
        state_manager.record_trade({'net': -500.0, 'strategy': 'Test2'})
        
        # Save ledger
        state_manager.save_ledger()
        
        # Create new state manager (should load from disk)
        state_manager2 = StateManager(self.config)
        
        self.assertEqual(state_manager2.wins_today, 1)
        self.assertEqual(state_manager2.losses_today, 1)
        self.assertEqual(state_manager2.trades_today_count, 2)
    
    def test_reset_session_counters(self):
        """Test resetting session counters."""
        state_manager = StateManager(self.config)
        
        # Set some values
        state_manager.consecutive_losses = 3
        
        # Reset
        state_manager.reset_session_counters()
        
        self.assertEqual(state_manager.consecutive_losses, 0)


if __name__ == '__main__':
    unittest.main()
