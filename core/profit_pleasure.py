"""
Profit Pleasure Notification System
Provides positive reinforcement when profitable trades are executed.
"""
import logging
import time
from typing import Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass
from enum import Enum


class PleasureLevel(Enum):
    """Intensity levels of pleasure feedback."""
    MILD = "mild"
    MODERATE = "moderate"
    STRONG = "strong"
    ECSTATIC = "ecstatic"


@dataclass
class PleasureEvent:
    """Represents a pleasure feedback event."""
    timestamp: datetime
    profit_amount: float
    pleasure_level: PleasureLevel
    message: str
    trade_details: Dict[str, Any]


class ProfitPleasureSystem:
    """
    Provides positive reinforcement and pleasure feedback when
    profitable trades are executed. This creates a dopamine-like
    reward system for successful trading.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.pleasure_config = config.get('profit_pleasure', {})
        
        # Configuration parameters
        self.enabled = self.pleasure_config.get('enabled', True)
        self.profit_threshold = self.pleasure_config.get('profit_threshold', 100.0)
        self.max_daily_celebrations = self.pleasure_config.get('max_daily_celebrations', 10)
        self.streak_multiplier = self.pleasure_config.get('streak_multiplier', 1.5)
        
        # Enhanced features
        self.sound_enabled = self.pleasure_config.get('sound_enabled', False)
        self.visual_effects = self.pleasure_config.get('visual_effects', True)
        self.achievement_tracking = self.pleasure_config.get('achievement_tracking', True)
        self.milestone_rewards = self.pleasure_config.get('milestone_rewards', {
            500: "Milestone: $500 profit reached! 🎯",
            1000: "Achievement: $1000 profit unlocked! 🏆",
            2500: "Champion: $2500 profit milestone! 👑",
            5000: "Legend: $5000 profit achieved! 🌟"
        })
        
        # State tracking
        self.daily_celebrations = 0
        self.consecutive_wins = 0
        self.best_streak = 0
        self.total_profit_celebrated = 0.0
        self.last_celebration_time = None
        self.pleasure_events: list[PleasureEvent] = []
        
        # Enhanced emotional state tracking
        self.current_mood = "neutral"
        self.confidence_level = 0.5  # 0.0 to 1.0
        self.enthusiasm = 0.5  # 0.0 to 1.0
        self.focus_level = 0.5  # 0.0 to 1.0
        self.patience_level = 0.5  # 0.0 to 1.0
        
        # Achievement tracking
        self.achievements_unlocked = []
        self.milestones_reached = []
        
        # Trading psychology metrics
        self.recent_performance = []  # Last 10 trades
        self.discipline_score = 0.5  # Following the system
        self.adaptability_score = 0.5  # Adjusting to market conditions
        
        logging.info("Enhanced Profit Pleasure System initialized")
    
    def evaluate_profit(self, trade_result: Dict[str, Any]) -> Optional[PleasureEvent]:
        """
        Evaluate a trade result and provide pleasure feedback if profitable.
        
        Args:
            trade_result: Dictionary containing trade information including 'net' P&L
            
        Returns:
            PleasureEvent if profitable enough to celebrate, None otherwise
        """
        if not self.enabled:
            return None
        
        profit = trade_result.get('net', 0)
        
        # Track recent performance
        self.recent_performance.append(profit)
        if len(self.recent_performance) > 10:
            self.recent_performance.pop(0)
        
        # Only celebrate profitable trades above threshold
        if profit <= 0:
            self._handle_non_profitable(profit)
            return None
        
        # Check if profit meets or exceeds threshold
        if profit < self.profit_threshold:
            logging.debug(f"Profit ${profit:.2f} below threshold ${self.profit_threshold:.2f} - no celebration")
            return None
        
        # Check daily celebration limit
        if self.daily_celebrations >= self.max_daily_celebrations:
            logging.info("Daily celebration limit reached - no more pleasure feedback today")
            return None
        
        # Determine pleasure level based on profit amount
        pleasure_level = self._calculate_pleasure_level(profit)
        
        # Apply streak multiplier for consecutive wins
        if self.consecutive_wins > 1:
            streak_bonus = min(profit * (self.streak_multiplier - 1), profit * 0.5)
            logging.info(f"Streak bonus: +₹{streak_bonus:.2f} ({self.consecutive_wins} consecutive wins)")
        
        # Generate pleasure message
        message = self._generate_pleasure_message(profit, pleasure_level, self.consecutive_wins)
        
        # Create pleasure event
        event = PleasureEvent(
            timestamp=datetime.now(),
            profit_amount=profit,
            pleasure_level=pleasure_level,
            message=message,
            trade_details=trade_result
        )
        
        # Update state
        self._update_state_on_profit(profit, event)
        
        # Check for milestones
        self._check_milestones(profit)
        
        # Update psychology metrics
        self._update_psychology_metrics()
        
        # Log the celebration
        self._log_celebration(event)
        
        return event
    
    def _calculate_pleasure_level(self, profit: float) -> PleasureLevel:
        """Calculate pleasure level based on profit amount."""
        if profit >= self.profit_threshold * 5:
            return PleasureLevel.ECSTATIC
        elif profit >= self.profit_threshold * 3:
            return PleasureLevel.STRONG
        elif profit >= self.profit_threshold * 2:
            return PleasureLevel.MODERATE
        else:
            return PleasureLevel.MILD
    
    def _generate_pleasure_message(self, profit: float, level: PleasureLevel, consecutive_wins: int) -> str:
        """Generate an enthusiastic pleasure message."""
        emoji_map = {
            PleasureLevel.MILD: "😊",
            PleasureLevel.MODERATE: "😄",
            PleasureLevel.STRONG: "🎉",
            PleasureLevel.ECSTATIC: "🚀💰"
        }
        
        emoji = emoji_map.get(level, "😊")
        
        messages = {
            PleasureLevel.MILD: [
                f"Nice! +${profit:.2f} profit! Keep up the good work!",
                f"Great trade! +${profit:.2f} in the bag!",
                f"Solid win! +${profit:.2f} profit earned!"
            ],
            PleasureLevel.MODERATE: [
                f"Excellent! +${profit:.2f} profit! That's fantastic!",
                f"Awesome work! +${profit:.2f} - you're on fire!",
                f"Fantastic trade! +${profit:.2f} profit secured!"
            ],
            PleasureLevel.STRONG: [
                f"INCREDIBLE! +${profit:.2f} profit! Absolutely amazing!",
                f"PHENOMENAL! +${profit:.2f} - you're crushing it!",
                f"OUTSTANDING! +${profit:.2f} profit - brilliant trading!"
            ],
            PleasureLevel.ECSTATIC: [
                f"🚀 MIND-BLOWING! +${profit:.2f} profit! You're a trading genius!",
                f"💰 LEGENDARY! +${profit:.2f} - Absolutely incredible performance!",
                f"🏆 CHAMPION! +${profit:.2f} profit - This is what excellence looks like!"
            ]
        }
        
        import random
        base_message = random.choice(messages.get(level, messages[PleasureLevel.MILD]))
        
        # Add streak information
        if consecutive_wins > 1:
            streak_msg = f" 🔥 {consecutive_wins} consecutive wins!"
            base_message += streak_msg
        
        return f"{emoji} {base_message}"
    
    def _update_state_on_profit(self, profit: float, event: PleasureEvent):
        """Update internal state after a profitable trade."""
        self.consecutive_wins += 1
        self.best_streak = max(self.best_streak, self.consecutive_wins)
        self.daily_celebrations += 1
        self.total_profit_celebrated += profit
        self.last_celebration_time = datetime.now()
        self.pleasure_events.append(event)
        
        # Update emotional state
        self.confidence_level = min(1.0, self.confidence_level + 0.1)
        self.enthusiasm = min(1.0, self.enthusiasm + 0.15)
        
        # Update mood based on pleasure level
        if event.pleasure_level == PleasureLevel.ECSTATIC:
            self.current_mood = "ecstatic"
        elif event.pleasure_level == PleasureLevel.STRONG:
            self.current_mood = "excited"
        elif event.pleasure_level == PleasureLevel.MODERATE:
            self.current_mood = "happy"
        else:
            self.current_mood = "pleased"
    
    def _handle_non_profitable(self, pnl: float):
        """Handle non-profitable trades gracefully."""
        if pnl < 0:
            self.consecutive_wins = 0
            self.confidence_level = max(0.2, self.confidence_level - 0.05)
            self.enthusiasm = max(0.3, self.enthusiasm - 0.1)
            self.current_mood = "focused"
            logging.info(f"Loss recorded. Staying focused and learning from this trade.")
        else:  # Scratch trade
            self.consecutive_wins = 0
            self.current_mood = "neutral"
            logging.info(f"Scratch trade. No harm done, staying disciplined.")
    
    def _log_celebration(self, event: PleasureEvent):
        """Log the celebration event."""
        logging.info(f"🎉 PROFIT CELEBRATION: {event.message}")
        logging.info(f"   Profit: ${event.profit_amount:.2f} | Level: {event.pleasure_level.value.upper()}")
        logging.info(f"   Streak: {self.consecutive_wins} wins | Mood: {self.current_mood}")
    
    def get_emotional_state(self) -> Dict[str, Any]:
        """Get current emotional state and statistics."""
        return {
            'current_mood': self.current_mood,
            'confidence_level': self.confidence_level,
            'enthusiasm': self.enthusiasm,
            'consecutive_wins': self.consecutive_wins,
            'best_streak': self.best_streak,
            'daily_celebrations': self.daily_celebrations,
            'total_profit_celebrated': self.total_profit_celebrated,
            'last_celebration': self.last_celebration_time.isoformat() if self.last_celebration_time else None
        }
    
    def get_pleasure_summary(self) -> str:
        """Get a summary of pleasure feedback."""
        return (
            f"Emotional State: {self.current_mood.upper()} | "
            f"Confidence: {self.confidence_level:.1%} | "
            f"Enthusiasm: {self.enthusiasm:.1%} | "
            f"Focus: {self.focus_level:.1%} | "
            f"Current Streak: {self.consecutive_wins} wins | "
            f"Best Streak: {self.best_streak} wins | "
            f"Total Celebrated: ${self.total_profit_celebrated:,.2f}"
        )
    
    def _check_milestones(self, profit: float):
        """Check if profit milestones have been reached."""
        running_total = sum(self.recent_performance)
        
        for milestone, message in self.milestone_rewards.items():
            if running_total >= milestone and milestone not in self.milestones_reached:
                self.milestones_reached.append(milestone)
                self.achievements_unlocked.append(message)
                logging.info(f"🏆 MILESTONE ACHIEVED: {message}")
    
    def _update_psychology_metrics(self):
        """Update trading psychology metrics based on recent performance."""
        if not self.recent_performance:
            return
        
        # Calculate recent win rate
        wins = sum(1 for p in self.recent_performance if p > 0)
        recent_win_rate = wins / len(self.recent_performance)
        
        # Update confidence based on recent performance
        if recent_win_rate > 0.6:
            self.confidence_level = min(1.0, self.confidence_level + 0.05)
        elif recent_win_rate < 0.4:
            self.confidence_level = max(0.2, self.confidence_level - 0.05)
        
        # Update focus based on consistency
        if len(self.recent_performance) >= 5:
            variance = max(self.recent_performance) - min(self.recent_performance)
            if variance < 200:  # Consistent performance
                self.focus_level = min(1.0, self.focus_level + 0.03)
            else:
                self.focus_level = max(0.3, self.focus_level - 0.02)
        
        # Update patience based on trade frequency
        if len(self.recent_performance) >= 3:
            self.patience_level = min(1.0, self.patience_level + 0.02)
    
    def get_psychology_report(self) -> Dict[str, Any]:
        """Get comprehensive psychology report."""
        return {
            'emotional_state': self.current_mood,
            'confidence_level': self.confidence_level,
            'enthusiasm': self.enthusiasm,
            'focus_level': self.focus_level,
            'patience_level': self.patience_level,
            'discipline_score': self.discipline_score,
            'adaptability_score': self.adaptability_score,
            'recent_performance': self.recent_performance,
            'achievements_unlocked': self.achievements_unlocked,
            'milestones_reached': self.milestones_reached
        }
    
    def get_trading_recommendation(self) -> str:
        """Get trading recommendation based on psychological state."""
        if self.confidence_level < 0.4:
            return "Consider reducing position size - confidence is low"
        elif self.focus_level < 0.5:
            return "Take a break - focus is compromised"
        elif self.enthusiasm > 0.9:
            return "Maintain discipline - enthusiasm is high but avoid overtrading"
        elif self.confidence_level > 0.8 and self.focus_level > 0.7:
            return "Optimal conditions - maintain current strategy"
        else:
            return "Continue with normal trading parameters"
    
    def reset_daily_counters(self):
        """Reset daily celebration counters."""
        self.daily_celebrations = 0
        logging.info("Daily pleasure counters reset")
    
    def adjust_threshold(self, new_threshold: float):
        """Adjust the profit threshold for celebrations."""
        if new_threshold > 0:
            self.profit_threshold = new_threshold
            logging.info(f"Profit threshold adjusted to ₹{new_threshold:.2f}")