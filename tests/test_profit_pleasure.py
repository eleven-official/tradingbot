"""
Tests for profit pleasure notification system.
"""
import unittest
import sys
import os
from datetime import datetime
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.profit_pleasure import ProfitPleasureSystem, PleasureLevel, PleasureEvent


class TestProfitPleasureSystem(unittest.TestCase):
    """Test cases for ProfitPleasureSystem."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'profit_pleasure': {
                'enabled': True,
                'profit_threshold': 100.0,
                'max_daily_celebrations': 10,
                'streak_multiplier': 1.5
            }
        }
        self.pleasure_system = ProfitPleasureSystem(self.config)
    
    def test_initialization(self):
        """Test system initialization."""
        self.assertTrue(self.pleasure_system.enabled)
        self.assertEqual(self.pleasure_system.profit_threshold, 100.0)
        self.assertEqual(self.pleasure_system.daily_celebrations, 0)
        self.assertEqual(self.pleasure_system.consecutive_wins, 0)
    
    def test_evaluate_profit_below_threshold(self):
        """Test that profits below threshold don't trigger celebration."""
        trade_result = {'net': 50.0, 'strategy': 'TestStrategy'}
        event = self.pleasure_system.evaluate_profit(trade_result)
        
        self.assertIsNone(event)
        self.assertEqual(self.pleasure_system.daily_celebrations, 0)
    
    def test_evaluate_profit_above_threshold(self):
        """Test that profits above threshold trigger celebration."""
        trade_result = {'net': 150.0, 'strategy': 'TestStrategy'}
        event = self.pleasure_system.evaluate_profit(trade_result)
        
        self.assertIsNotNone(event)
        self.assertEqual(event.profit_amount, 150.0)
        self.assertEqual(self.pleasure_system.daily_celebrations, 1)
        self.assertEqual(self.pleasure_system.consecutive_wins, 1)
        # Check that the message contains AUD currency
        self.assertIn("$", event.message)
        # Check that psychology metrics are updated
        self.assertIsNotNone(self.pleasure_system.recent_performance)
    
    def test_evaluate_loss(self):
        """Test that losses don't trigger celebration."""
        trade_result = {'net': -50.0, 'strategy': 'TestStrategy'}
        event = self.pleasure_system.evaluate_profit(trade_result)
        
        self.assertIsNone(event)
        self.assertEqual(self.pleasure_system.consecutive_wins, 0)
    
    def test_pleasure_level_calculation(self):
        """Test pleasure level calculation based on profit amount."""
        # Mild pleasure
        self.assertEqual(
            self.pleasure_system._calculate_pleasure_level(150.0),
            PleasureLevel.MILD
        )
        
        # Moderate pleasure
        self.assertEqual(
            self.pleasure_system._calculate_pleasure_level(250.0),
            PleasureLevel.MODERATE
        )
        
        # Strong pleasure
        self.assertEqual(
            self.pleasure_system._calculate_pleasure_level(400.0),
            PleasureLevel.STRONG
        )
        
        # Ecstatic pleasure
        self.assertEqual(
            self.pleasure_system._calculate_pleasure_level(600.0),
            PleasureLevel.ECSTATIC
        )
    
    def test_consecutive_wins_tracking(self):
        """Test consecutive wins tracking."""
        # First win
        self.pleasure_system.evaluate_profit({'net': 150.0})
        self.assertEqual(self.pleasure_system.consecutive_wins, 1)
        
        # Second win
        self.pleasure_system.evaluate_profit({'net': 200.0})
        self.assertEqual(self.pleasure_system.consecutive_wins, 2)
        
        # Third win
        self.pleasure_system.evaluate_profit({'net': 300.0})
        self.assertEqual(self.pleasure_system.consecutive_wins, 3)
        
        # Loss resets streak
        self.pleasure_system.evaluate_profit({'net': -100.0})
        self.assertEqual(self.pleasure_system.consecutive_wins, 0)
    
    def test_best_streak_tracking(self):
        """Test best streak tracking."""
        # Build a streak
        for _ in range(5):
            self.pleasure_system.evaluate_profit({'net': 150.0})
        
        self.assertEqual(self.pleasure_system.best_streak, 5)
        
        # Reset with loss
        self.pleasure_system.evaluate_profit({'net': -100.0})
        self.assertEqual(self.pleasure_system.consecutive_wins, 0)
        self.assertEqual(self.pleasure_system.best_streak, 5)  # Best streak preserved
    
    def test_daily_celebration_limit(self):
        """Test daily celebration limit."""
        # Set low limit for testing
        self.pleasure_system.max_daily_celebrations = 2
        
        # First celebration
        event1 = self.pleasure_system.evaluate_profit({'net': 150.0})
        self.assertIsNotNone(event1)
        
        # Second celebration
        event2 = self.pleasure_system.evaluate_profit({'net': 200.0})
        self.assertIsNotNone(event2)
        
        # Third celebration should be blocked
        event3 = self.pleasure_system.evaluate_profit({'net': 300.0})
        self.assertIsNone(event3)
    
    def test_emotional_state_updates(self):
        """Test emotional state updates on profits."""
        # Initial state
        state = self.pleasure_system.get_emotional_state()
        self.assertEqual(state['current_mood'], 'neutral')
        self.assertEqual(state['confidence_level'], 0.5)
        
        # After profit
        self.pleasure_system.evaluate_profit({'net': 150.0})
        state = self.pleasure_system.get_emotional_state()
        self.assertNotEqual(state['current_mood'], 'neutral')
        self.assertGreater(state['confidence_level'], 0.5)
    
    def test_system_disabled(self):
        """Test that disabled system doesn't celebrate."""
        self.pleasure_system.enabled = False
        
        event = self.pleasure_system.evaluate_profit({'net': 500.0})
        self.assertIsNone(event)
        self.assertEqual(self.pleasure_system.daily_celebrations, 0)
    
    def test_pleasure_message_generation(self):
        """Test pleasure message generation."""
        message = self.pleasure_system._generate_pleasure_message(
            150.0, PleasureLevel.MILD, 1
        )
        
        self.assertIn("150.00", message)
        self.assertIn("$", message)
        self.assertIn("😊", message)
    
    def test_get_pleasure_summary(self):
        """Test pleasure summary generation."""
        self.pleasure_system.evaluate_profit({'net': 150.0})
        self.pleasure_system.evaluate_profit({'net': 200.0})
        
        summary = self.pleasure_system.get_pleasure_summary()
        
        self.assertIn("Emotional State", summary)
        self.assertIn("Confidence", summary)
        self.assertIn("Streak", summary)
    
    def test_reset_daily_counters(self):
        """Test daily counter reset."""
        self.pleasure_system.evaluate_profit({'net': 150.0})
        self.assertEqual(self.pleasure_system.daily_celebrations, 1)
        
        self.pleasure_system.reset_daily_counters()
        self.assertEqual(self.pleasure_system.daily_celebrations, 0)
    
    def test_adjust_threshold(self):
        """Test threshold adjustment."""
        self.assertEqual(self.pleasure_system.profit_threshold, 100.0)
        
        self.pleasure_system.adjust_threshold(200.0)
        self.assertEqual(self.pleasure_system.profit_threshold, 200.0)
        
        # Profit below new threshold shouldn't celebrate
        event = self.pleasure_system.evaluate_profit({'net': 150.0})
        self.assertIsNone(event)


if __name__ == '__main__':
    unittest.main()