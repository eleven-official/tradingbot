"""
Tests for enhanced profit pleasure system.
"""
import unittest
import sys
import os
from datetime import datetime
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.profit_pleasure import ProfitPleasureSystem, PleasureLevel, PleasureEvent


class TestEnhancedProfitPleasureSystem(unittest.TestCase):
    """Test cases for enhanced profit pleasure system."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'profit_pleasure': {
                'enabled': True,
                'profit_threshold': 100.0,
                'max_daily_celebrations': 10,
                'streak_multiplier': 1.5,
                'sound_enabled': False,
                'visual_effects': True,
                'achievement_tracking': True,
                'milestone_rewards': {
                    500: "Milestone: $500 profit reached! 🎯",
                    1000: "Achievement: $1000 profit unlocked! 🏆"
                }
            }
        }
        self.pleasure_system = ProfitPleasureSystem(self.config)
    
    def test_initialization_with_enhanced_features(self):
        """Test enhanced system initialization."""
        self.assertTrue(self.pleasure_system.enabled)
        self.assertTrue(self.pleasure_system.achievement_tracking)
        self.assertTrue(self.pleasure_system.visual_effects)
        self.assertFalse(self.pleasure_system.sound_enabled)
        
        # Check new psychology metrics
        self.assertEqual(self.pleasure_system.focus_level, 0.5)
        self.assertEqual(self.pleasure_system.patience_level, 0.5)
        self.assertEqual(self.pleasure_system.discipline_score, 0.5)
    
    def test_milestone_tracking(self):
        """Test milestone achievement tracking."""
        # Make enough trades to reach first milestone
        for i in range(6):
            self.pleasure_system.evaluate_profit({'net': 100.0})
        
        # Check if milestone was reached
        self.assertIn(500, self.pleasure_system.milestones_reached)
        self.assertTrue(len(self.pleasure_system.achievements_unlocked) > 0)
    
    def test_psychology_metrics_update(self):
        """Test psychology metrics update."""
        # Record some profitable trades
        for i in range(5):
            self.pleasure_system.evaluate_profit({'net': 150.0})
        
        # Check that psychology metrics updated
        self.assertGreater(self.pleasure_system.confidence_level, 0.5)
        self.assertGreater(self.pleasure_system.focus_level, 0.5)
        self.assertGreater(self.pleasure_system.patience_level, 0.5)
    
    def test_recent_performance_tracking(self):
        """Test recent performance tracking."""
        # Record trades
        profits = [100.0, -50.0, 150.0, 200.0, -30.0]
        for profit in profits:
            self.pleasure_system.evaluate_profit({'net': profit})
        
        # Check recent performance
        self.assertEqual(len(self.pleasure_system.recent_performance), 5)
        self.assertEqual(self.pleasure_system.recent_performance, profits)
    
    def test_recent_performance_limit(self):
        """Test that recent performance is limited to last 10 trades."""
        # Record 15 trades
        for i in range(15):
            self.pleasure_system.evaluate_profit({'net': 100.0})
        
        # Should only keep last 10
        self.assertEqual(len(self.pleasure_system.recent_performance), 10)
    
    def test_psychology_report(self):
        """Test comprehensive psychology report."""
        self.pleasure_system.evaluate_profit({'net': 150.0})
        
        report = self.pleasure_system.get_psychology_report()
        
        self.assertIn('emotional_state', report)
        self.assertIn('confidence_level', report)
        self.assertIn('focus_level', report)
        self.assertIn('patience_level', report)
        self.assertIn('discipline_score', report)
        self.assertIn('recent_performance', report)
        self.assertIn('achievements_unlocked', report)
    
    def test_trading_recommendation(self):
        """Test trading recommendation based on psychology."""
        # High confidence and focus
        self.pleasure_system.confidence_level = 0.9
        self.pleasure_system.focus_level = 0.8
        
        recommendation = self.pleasure_system.get_trading_recommendation()
        
        self.assertIn("Optimal conditions", recommendation)
    
    def test_low_confidence_recommendation(self):
        """Test recommendation when confidence is low."""
        self.pleasure_system.confidence_level = 0.3
        
        recommendation = self.pleasure_system.get_trading_recommendation()
        
        self.assertIn("reducing position size", recommendation)
    
    def test_low_focus_recommendation(self):
        """Test recommendation when focus is low."""
        self.pleasure_system.focus_level = 0.4
        
        recommendation = self.pleasure_system.get_trading_recommendation()
        
        self.assertIn("Take a break", recommendation)
    
    def test_enhanced_pleasure_summary(self):
        """Test enhanced pleasure summary with new metrics."""
        self.pleasure_system.evaluate_profit({'net': 150.0})
        
        summary = self.pleasure_system.get_pleasure_summary()
        
        self.assertIn("Focus", summary)
        self.assertIn("$", summary)  # AUD currency
        # Note: Patience might not be updated after just one trade
    
    def test_achievement_system(self):
        """Test achievement unlocking system."""
        # Reach second milestone
        for i in range(11):
            self.pleasure_system.evaluate_profit({'net': 100.0})
        
        # Check achievements
        self.assertTrue(len(self.pleasure_system.achievements_unlocked) >= 1)
        self.assertIn(1000, self.pleasure_system.milestones_reached)


if __name__ == '__main__':
    unittest.main()