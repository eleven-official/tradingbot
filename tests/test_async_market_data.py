"""
Tests for async market data module.
"""
import unittest
import asyncio
import sys
import os
from unittest.mock import Mock, patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Only test the PerformanceOptimizer which doesn't require aiohttp
from core.async_market_data import PerformanceOptimizer


class TestPerformanceOptimizer(unittest.TestCase):
    """Test cases for PerformanceOptimizer."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'performance': {
                'enabled': True,
                'async_operations': True
            }
        }
        self.optimizer = PerformanceOptimizer(self.config)
        self.mock_kite = Mock()
    
    def test_initialization(self):
        """Test PerformanceOptimizer initialization."""
        self.assertTrue(self.optimizer.enabled)
        self.assertTrue(self.optimizer.async_enabled)
    
    def test_initialization_disabled(self):
        """Test PerformanceOptimizer with performance disabled."""
        config = {'performance': {'enabled': False}}
        optimizer = PerformanceOptimizer(config)
        
        self.assertFalse(optimizer.enabled)
    
    def test_batch_requests(self):
        """Test request batching."""
        items = list(range(25))
        batches = list(self.optimizer.batch_requests(items, batch_size=10))
        
        self.assertEqual(len(batches), 3)
        self.assertEqual(len(batches[0]), 10)
        self.assertEqual(len(batches[1]), 10)
        self.assertEqual(len(batches[2]), 5)
    
    def test_batch_requests_single_batch(self):
        """Test batching when items fit in single batch."""
        items = list(range(5))
        batches = list(self.optimizer.batch_requests(items, batch_size=10))
        
        self.assertEqual(len(batches), 1)
        self.assertEqual(len(batches[0]), 5)
    
    def test_batch_requests_empty_list(self):
        """Test batching with empty list."""
        items = []
        batches = list(self.optimizer.batch_requests(items, batch_size=10))
        
        self.assertEqual(len(batches), 0)
    
    def test_sync_fetch_quote(self):
        """Test synchronous quote fetching."""
        self.mock_kite.quote.return_value = {'price': 100}
        
        results = self.optimizer._sync_fetch(self.mock_kite, ['NIFTY'], 'quote')
        
        self.assertIn('NIFTY', results)
        self.assertEqual(results['NIFTY'], {'price': 100})
    
    def test_sync_fetch_error_handling(self):
        """Test sync fetch error handling."""
        self.mock_kite.quote.side_effect = Exception("API Error")
        
        results = self.optimizer._sync_fetch(self.mock_kite, ['NIFTY'], 'quote')
        
        self.assertIn('NIFTY', results)
        self.assertIsNone(results['NIFTY'])
    
    def test_sync_fetch_ohlc(self):
        """Test synchronous OHLC fetching."""
        self.mock_kite.ohlc.return_value = {'NIFTY': {'open': 100, 'high': 110}}
        
        results = self.optimizer._sync_fetch(self.mock_kite, ['NIFTY'], 'ohlc')
        
        self.assertEqual(results, {'NIFTY': {'open': 100, 'high': 110}})


if __name__ == '__main__':
    unittest.main()