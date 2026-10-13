"""
Tests for TradingView bridge integration.
"""
import unittest
import sys
import os
import json
from datetime import datetime
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.tradingview_bridge import (
    TradingViewBridge, 
    TradingViewSignal, 
    SignalType, 
    SignalAction,
    create_tradingview_webhook_url,
    generate_tradingview_alert_config
)


class TestTradingViewBridge(unittest.TestCase):
    """Test cases for TradingViewBridge."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'tradingview': {
                'enabled': True,
                'webhook_secret': 'test_secret',
                'require_signature': False,
                'default_action': 'execute',
                'allowed_symbols': ['NIFTY', 'BANKNIFTY'],
                'max_position_size': 10
            }
        }
        self.bridge = TradingViewBridge(self.config)
    
    def test_initialization(self):
        """Test bridge initialization."""
        self.assertTrue(self.bridge.enabled)
        self.assertEqual(self.bridge.default_action, SignalAction.EXECUTE)
        self.assertEqual(len(self.bridge.allowed_symbols), 2)
    
    def test_register_handler(self):
        """Test registering signal handlers."""
        def mock_handler(signal):
            return {'executed': True}
        
        self.bridge.register_handler(SignalType.BUY, mock_handler)
        
        self.assertIn(SignalType.BUY, self.bridge.signal_handlers)
    
    def test_receive_webhook_disabled(self):
        """Test webhook reception when bridge is disabled."""
        self.bridge.enabled = False
        
        payload = json.dumps({'signal_type': 'buy', 'symbol': 'NIFTY', 'price': 15000})
        result = self.bridge.receive_webhook(payload)
        
        self.assertEqual(result['status'], 'error')
        self.assertIn('disabled', result['message'])
    
    def test_receive_webhook_invalid_json(self):
        """Test webhook reception with invalid JSON."""
        result = self.bridge.receive_webhook('invalid json')
        
        self.assertEqual(result['status'], 'error')
        self.assertIn('Invalid JSON', result['message'])
    
    def test_receive_webhook_valid_signal(self):
        """Test webhook reception with valid signal."""
        def mock_handler(signal):
            return {'executed': True}
        
        self.bridge.register_handler(SignalType.BUY, mock_handler)
        
        payload = json.dumps({
            'signal_type': 'buy',
            'symbol': 'NIFTY',
            'price': 15000
        })
        
        result = self.bridge.receive_webhook(payload)
        
        self.assertEqual(result['status'], 'success')
        self.assertEqual(self.bridge.signals_received, 1)
    
    def test_signal_parsing(self):
        """Test signal parsing from webhook data."""
        data = {
            'signal_type': 'buy',
            'symbol': 'BANKNIFTY',
            'price': 35000,
            'quantity': 5,
            'strategy': 'TestStrategy'
        }
        
        signal = self.bridge._parse_signal(data)
        
        self.assertEqual(signal.signal_type, SignalType.BUY)
        self.assertEqual(signal.symbol, 'BANKNIFTY')
        self.assertEqual(signal.price, 35000)
        self.assertEqual(signal.quantity, 5)
        self.assertEqual(signal.strategy, 'TestStrategy')
    
    def test_determine_action_allowed_symbol(self):
        """Test action determination for allowed symbol."""
        signal = TradingViewSignal(
            signal_type=SignalType.BUY,
            symbol='NIFTY',
            price=15000
        )
        
        self.bridge.register_handler(SignalType.BUY, lambda s: {})
        
        action = self.bridge._determine_action(signal)
        self.assertEqual(action, SignalAction.EXECUTE)
    
    def test_determine_action_disallowed_symbol(self):
        """Test action determination for disallowed symbol."""
        signal = TradingViewSignal(
            signal_type=SignalType.BUY,
            symbol='RELIANCE',
            price=2500
        )
        
        action = self.bridge._determine_action(signal)
        self.assertEqual(action, SignalAction.IGNORE)
    
    def test_signal_queue(self):
        """Test signal queuing."""
        self.bridge.default_action = SignalAction.QUEUE
        
        signal = TradingViewSignal(
            signal_type=SignalType.BUY,
            symbol='NIFTY',
            price=15000
        )
        
        result = self.bridge._queue_signal(signal)
        
        self.assertEqual(result['status'], 'queued')
        self.assertEqual(len(self.bridge.signal_queue), 1)
    
    def test_process_queue(self):
        """Test processing queued signals."""
        def mock_handler(signal):
            return {'executed': True}
        
        self.bridge.register_handler(SignalType.BUY, mock_handler)
        
        # Queue some signals
        for i in range(3):
            signal = TradingViewSignal(
                signal_type=SignalType.BUY,
                symbol='NIFTY',
                price=15000 + i
            )
            self.bridge._queue_signal(signal)
        
        # Process queue
        results = self.bridge.process_queue()
        
        self.assertEqual(len(results), 3)
        self.assertEqual(len(self.bridge.signal_queue), 0)
    
    def test_statistics(self):
        """Test statistics tracking."""
        def mock_handler(signal):
            return {'executed': True}
        
        self.bridge.register_handler(SignalType.BUY, mock_handler)
        
        # Execute some signals
        payload = json.dumps({'signal_type': 'buy', 'symbol': 'NIFTY', 'price': 15000})
        self.bridge.receive_webhook(payload)
        self.bridge.receive_webhook(payload)
        
        stats = self.bridge.get_statistics()
        
        self.assertEqual(stats['signals_received'], 2)
        self.assertEqual(stats['signals_executed'], 2)
    
    def test_signature_verification(self):
        """Test HMAC signature verification."""
        self.bridge.require_signature = True
        
        payload = json.dumps({'signal_type': 'buy', 'symbol': 'NIFTY', 'price': 15000})
        
        # Generate valid signature
        import hmac
        import hashlib
        signature = hmac.new(
            self.bridge.webhook_secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Test valid signature
        self.assertTrue(self.bridge._verify_signature(payload, signature))
        
        # Test invalid signature
        self.assertFalse(self.bridge._verify_signature(payload, 'invalid_signature'))
    
    def test_get_status(self):
        """Test getting bridge status."""
        status = self.bridge.get_status()
        
        self.assertTrue(status['enabled'])
        self.assertIn('allowed_symbols', status)
        self.assertIn('statistics', status)


class TestTradingViewUtilities(unittest.TestCase):
    """Test utility functions for TradingView integration."""
    
    def test_create_webhook_url(self):
        """Test webhook URL generation."""
        config = {
            'server': {
                'host': 'localhost',
                'port': 8000,
                'webhook_path': '/webhook/tradingview'
            }
        }
        
        url = create_tradingview_webhook_url(config)
        
        self.assertEqual(url, 'http://localhost:8000/webhook/tradingview')
    
    def test_generate_alert_config(self):
        """Test TradingView alert configuration generation."""
        config = {
            'server': {
                'host': 'localhost',
                'port': 8000
            }
        }
        
        alert_config = generate_tradingview_alert_config(config)
        
        # Should be valid JSON
        config_dict = json.loads(alert_config)
        
        self.assertIn('signal_type', config_dict)
        self.assertIn('symbol', config_dict)
        self.assertIn('price', config_dict)


if __name__ == '__main__':
    unittest.main()