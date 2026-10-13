"""
Tests for configuration validator module.
"""
import unittest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config_validator import (
    ConfigValidator,
    ConfigurationError,
    TradingFlags,
    RiskManagement,
    EmailConfig,
    validate_config
)


class TestConfigValidator(unittest.TestCase):
    """Test cases for ConfigValidator."""
    
    def test_valid_trading_flags(self):
        """Test validation of valid trading flags."""
        flags = {
            'underlying_instrument': 'NIFTY 50',
            'chart_timeframe': '5minute',
            'product_type': 'MIS',
            'risk_per_trade_percent': 1.0,
            'stop_loss_percent': 15.0,
            'max_trades_per_day': 5,
            'paper_trading': True
        }
        
        # Should not raise exception
        TradingFlags(**flags)
    
    def test_invalid_risk_per_trade(self):
        """Test validation rejects invalid risk per trade."""
        flags = {
            'risk_per_trade_percent': 15.0,  # Too high
            'stop_loss_percent': 15.0,
            'max_trades_per_day': 5
        }
        
        with self.assertRaises(ConfigurationError):
            TradingFlags(**flags)
    
    def test_invalid_stop_loss(self):
        """Test validation rejects invalid stop loss."""
        flags = {
            'risk_per_trade_percent': 1.0,
            'stop_loss_percent': 75.0,  # Too high
            'max_trades_per_day': 5
        }
        
        with self.assertRaises(ConfigurationError):
            TradingFlags(**flags)
    
    def test_invalid_product_type(self):
        """Test validation rejects invalid product type."""
        flags = {
            'product_type': 'INVALID',
            'risk_per_trade_percent': 1.0,
            'stop_loss_percent': 15.0,
            'max_trades_per_day': 5
        }
        
        with self.assertRaises(ConfigurationError):
            TradingFlags(**flags)
    
    def test_valid_risk_management(self):
        """Test validation of valid risk management config."""
        risk_config = {
            'atr_multiplier': 2.0,
            'enable_daily_loss_limit': True,
            'max_daily_loss_percent': 2.5,
            'max_consecutive_losses': 3
        }
        
        # Should not raise exception
        RiskManagement(**risk_config)
    
    def test_invalid_max_daily_loss(self):
        """Test validation rejects invalid max daily loss."""
        risk_config = {
            'max_daily_loss_percent': 25.0,  # Too high
            'max_consecutive_losses': 3
        }
        
        with self.assertRaises(ConfigurationError):
            RiskManagement(**risk_config)
    
    def test_valid_email_config(self):
        """Test validation of valid email config."""
        email_config = {
            'send_daily_report': True,
            'smtp_server': 'smtp.gmail.com',
            'smtp_port': 587,
            'sender_email': 'test@gmail.com',
            'sender_password': 'password',
            'receiver_email': 'receiver@gmail.com'
        }
        
        # Should not raise exception
        EmailConfig(**email_config)
    
    def test_email_config_required_fields(self):
        """Test email config requires fields when daily report enabled."""
        email_config = {
            'send_daily_report': True,
            'sender_email': 'test@gmail.com'
            # Missing required fields
        }
        
        with self.assertRaises(ConfigurationError):
            EmailConfig(**email_config)
    
    def test_config_validator_integration(self):
        """Test full configuration validation."""
        config = {
            'zerodha': {
                'api_key': 'test_key',
                'api_secret': 'test_secret'
            },
            'trading_flags': {
                'risk_per_trade_percent': 1.0,
                'stop_loss_percent': 15.0,
                'max_trades_per_day': 5,
                'paper_trading': True
            },
            'risk_management': {
                'max_daily_loss_percent': 2.5,
                'max_consecutive_losses': 3
            },
            'email_settings': {
                'send_daily_report': False
            }
        }
        
        # Should not raise exception
        validator = ConfigValidator(config)
        validated = validator.validate()
        
        self.assertEqual(validated, config)
    
    def test_get_paper_trading_mode(self):
        """Test getting paper trading mode."""
        config = {
            'trading_flags': {
                'paper_trading': True
            }
        }
        
        validator = ConfigValidator(config)
        self.assertTrue(validator.get_paper_trading_mode())
    
    def test_get_underlying_instrument(self):
        """Test getting underlying instrument."""
        config = {
            'trading_flags': {
                'underlying_instrument': 'BANKNIFTY'
            }
        }
        
        validator = ConfigValidator(config)
        self.assertEqual(validator.get_underlying_instrument(), 'BANKNIFTY')


if __name__ == '__main__':
    unittest.main()