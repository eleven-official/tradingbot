"""
Tests for risk controller module.
"""
import unittest
import sys
import os
from unittest.mock import Mock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.risk_controller import RiskController


class TestRiskController(unittest.TestCase):
    """Test cases for RiskController."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'risk_management': {
                'atr_multiplier': 2.0,
                'enable_daily_loss_limit': True,
                'enable_volatility_adjustment': True,
                'high_vix_risk_reduction_factor': 0.5,
                'high_vix_threshold': 22.0,
                'max_daily_loss_percent': 2.5,
                'enable_consecutive_loss_limit': True,
                'max_consecutive_losses': 3,
                'enable_weekly_loss_limit': False,
                'max_weekly_loss_percent': 5.0
            },
            'trading_flags': {
                'risk_per_trade_percent': 1.0,
                'stop_loss_percent': 15.0,
                'max_trades_per_day': 5
            },
            'risk_tiers': [
                {'max_capital': 100000, 'risk_pct': 5},
                {'max_capital': 300000, 'risk_pct': 3},
                {'max_capital': None, 'risk_pct': 2}
            ]
        }
        self.risk_controller = RiskController(self.config)
    
    def test_initialization(self):
        """Test RiskController initialization."""
        self.assertEqual(self.risk_controller.base_risk_per_trade, 1.0)
        self.assertEqual(self.risk_controller.stop_loss_percent, 15.0)
        self.assertEqual(self.risk_controller.max_trades_per_day, 5)
    
    def test_get_risk_per_trade_with_tiers(self):
        """Test risk per trade calculation with tiers."""
        # Small capital - should use 5%
        risk = self.risk_controller.get_risk_per_trade(50000)
        self.assertEqual(risk, 5.0)
        
        # Medium capital - should use 3%
        risk = self.risk_controller.get_risk_per_trade(200000)
        self.assertEqual(risk, 3.0)
        
        # Large capital - should use 2%
        risk = self.risk_controller.get_risk_per_trade(500000)
        self.assertEqual(risk, 2.0)
    
    def test_get_risk_per_trade_without_tiers(self):
        """Test risk per trade calculation without tiers."""
        config = self.config.copy()
        config['risk_tiers'] = []
        risk_controller = RiskController(config)
        
        risk = risk_controller.get_risk_per_trade(100000)
        self.assertEqual(risk, 1.0)  # base risk
    
    def test_calculate_position_size(self):
        """Test position size calculation."""
        capital = 100000
        option_price = 100
        
        # Risk amount = 100000 * 0.01 = 1000
        # Risk per lot = 100 * 0.15 = 15
        # Lots = 1000 / 15 = 66.67 -> 66 lots
        lots = self.risk_controller.calculate_position_size(capital, option_price)
        
        self.assertGreater(lots, 0)
        self.assertLessEqual(lots, 500)  # reasonable upper bound for testing
    
    def test_reduce_size_after_loss(self):
        """Test position size reduction after loss."""
        initial_multiplier = self.risk_controller._trade_size_multiplier
        
        self.risk_controller.reduce_size_after_loss()
        
        self.assertLess(self.risk_controller._trade_size_multiplier, initial_multiplier)
    
    def test_restore_size_after_win(self):
        """Test position size restoration after win."""
        self.risk_controller._trade_size_multiplier = 0.5
        
        self.risk_controller.restore_size_after_win()
        
        self.assertGreater(self.risk_controller._trade_size_multiplier, 0.5)
        self.assertLessEqual(self.risk_controller._trade_size_multiplier, 1.0)
    
    def test_adjust_for_volatility_high_vix(self):
        """Test risk adjustment for high VIX."""
        base_risk = 2.0
        vix = 25.0  # Above threshold of 22.0
        
        adjusted_risk = self.risk_controller.adjust_for_volatility(vix, base_risk)
        
        self.assertLess(adjusted_risk, base_risk)
        self.assertEqual(adjusted_risk, base_risk * 0.5)  # 50% reduction
    
    def test_adjust_for_volatility_low_vix(self):
        """Test risk adjustment for low VIX."""
        base_risk = 2.0
        vix = 15.0  # Below threshold of 22.0
        
        adjusted_risk = self.risk_controller.adjust_for_volatility(vix, base_risk)
        
        self.assertEqual(adjusted_risk, base_risk)  # No adjustment
    
    def test_adjust_for_volatility_disabled(self):
        """Test risk adjustment when disabled."""
        config = self.config.copy()
        config['risk_management']['enable_volatility_adjustment'] = False
        risk_controller = RiskController(config)
        
        base_risk = 2.0
        vix = 25.0
        
        adjusted_risk = risk_controller.adjust_for_volatility(vix, base_risk)
        
        self.assertEqual(adjusted_risk, base_risk)  # No adjustment when disabled
    
    def test_can_take_trade_all_checks_pass(self):
        """Test trade permission when all checks pass."""
        mock_state_manager = Mock()
        mock_state_manager.check_daily_loss_limit.return_value = False
        mock_state_manager.check_consecutive_loss_limit.return_value = False
        mock_state_manager.check_weekly_loss_limit.return_value = False
        mock_state_manager.starting_capital = 100000
        
        can_trade, reason = self.risk_controller.can_take_trade(2, mock_state_manager)
        
        self.assertTrue(can_trade)
        self.assertEqual(reason, "All risk checks passed")
    
    def test_can_take_trade_max_trades_reached(self):
        """Test trade permission when max trades reached."""
        mock_state_manager = Mock()
        mock_state_manager.starting_capital = 100000
        
        can_trade, reason = self.risk_controller.can_take_trade(5, mock_state_manager)
        
        self.assertFalse(can_trade)
        self.assertIn("Max trades per day", reason)
    
    def test_can_take_trade_daily_loss_limit(self):
        """Test trade permission when daily loss limit reached."""
        mock_state_manager = Mock()
        mock_state_manager.check_daily_loss_limit.return_value = True
        mock_state_manager.starting_capital = 100000
        
        can_trade, reason = self.risk_controller.can_take_trade(2, mock_state_manager)
        
        self.assertFalse(can_trade)
        self.assertIn("Daily loss limit", reason)
    
    def test_can_take_trade_consecutive_loss_limit(self):
        """Test trade permission when consecutive loss limit reached."""
        mock_state_manager = Mock()
        mock_state_manager.check_daily_loss_limit.return_value = False
        mock_state_manager.check_consecutive_loss_limit.return_value = True
        mock_state_manager.starting_capital = 100000
        
        can_trade, reason = self.risk_controller.can_take_trade(2, mock_state_manager)
        
        self.assertFalse(can_trade)
        self.assertIn("Consecutive loss limit", reason)
    
    def test_get_max_daily_loss_percent(self):
        """Test getting max daily loss percentage."""
        self.assertEqual(self.risk_controller.get_max_daily_loss_percent(), 2.5)
    
    def test_get_max_consecutive_losses(self):
        """Test getting max consecutive losses."""
        self.assertEqual(self.risk_controller.get_max_consecutive_losses(), 3)
    
    def test_should_enable_daily_loss_limit(self):
        """Test daily loss limit enablement."""
        self.assertTrue(self.risk_controller.should_enable_daily_loss_limit())
    
    def test_should_enable_consecutive_loss_limit(self):
        """Test consecutive loss limit enablement."""
        self.assertTrue(self.risk_controller.should_enable_consecutive_loss_limit())
    
    def test_should_enable_weekly_loss_limit(self):
        """Test weekly loss limit enablement."""
        self.assertFalse(self.risk_controller.should_enable_weekly_loss_limit())


if __name__ == '__main__':
    unittest.main()