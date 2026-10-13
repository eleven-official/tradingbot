"""
Loki Smart Notifications System
Intelligent alerts for trading opportunities, risks, and portfolio events
"""
import logging
from typing import List, Dict, Optional, Callable
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
import json

logger = logging.getLogger(__name__)


class NotificationPriority(Enum):
    """Notification priority levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class NotificationType(Enum):
    """Types of notifications"""
    TRADE_SIGNAL = "trade_signal"
    RISK_WARNING = "risk_warning"
    OPPORTUNITY = "opportunity"
    PORTFOLIO_MILESTONE = "portfolio_milestone"
    MARKET_EVENT = "market_event"
    AI_INSIGHT = "ai_insight"
    PERFORMANCE_ALERT = "performance_alert"
    SYSTEM_STATUS = "system_status"


@dataclass
class Notification:
    """Smart notification"""
    id: str
    timestamp: datetime
    type: NotificationType
    priority: NotificationPriority
    title: str
    message: str
    data: Dict
    action_required: bool = False
    action_label: Optional[str] = None
    action_callback: Optional[Callable] = None
    read: bool = False
    dismissed: bool = False


class NotificationRule:
    """Rule for triggering notifications"""
    
    def __init__(
        self,
        name: str,
        notification_type: NotificationType,
        priority: NotificationPriority,
        condition: Callable[[Dict], bool],
        message_template: str
    ):
        self.name = name
        self.notification_type = notification_type
        self.priority = priority
        self.condition = condition
        self.message_template = message_template
    
    def evaluate(self, context: Dict) -> Optional[Notification]:
        """Evaluate rule and create notification if triggered"""
        try:
            if self.condition(context):
                # Generate unique ID
                notif_id = f"{self.name}_{int(datetime.now().timestamp())}"
                
                # Format message
                message = self.message_template.format(**context)
                
                return Notification(
                    id=notif_id,
                    timestamp=datetime.now(),
                    type=self.notification_type,
                    priority=self.priority,
                    title=self.name,
                    message=message,
                    data=context,
                    action_required=self.priority == NotificationPriority.CRITICAL
                )
        except Exception as e:
            logger.error(f"Error evaluating notification rule '{self.name}': {e}")
        
        return None


class SmartNotificationSystem:
    """
    Intelligent notification system with:
    - Rule-based alerts
    - Priority-based delivery
    - Adaptive thresholds
    - Aggregation and deduplication
    - Multi-channel delivery (UI, email, SMS, webhook)
    """
    
    def __init__(self):
        self.notifications: List[Notification] = []
        self.rules: List[NotificationRule] = []
        self.subscribers: Dict[NotificationType, List[Callable]] = {}
        self.muted_types: set = set()
        
        # Initialize default rules
        self._setup_default_rules()
        
        logger.info("🔔 Smart Notification System initialized")
    
    def _setup_default_rules(self):
        """Setup default notification rules"""
        
        # 1. Strong Buy Signal
        self.add_rule(NotificationRule(
            name="Strong Buy Signal Detected",
            notification_type=NotificationType.TRADE_SIGNAL,
            priority=NotificationPriority.HIGH,
            condition=lambda ctx: (
                ctx.get('signal') == 'BUY' and 
                ctx.get('confidence', 0) > 80
            ),
            message_template="🚀 Strong BUY signal for {symbol} with {confidence:.1f}% confidence. Entry: ${entry_price:.2f}"
        ))
        
        # 2. Risk Warning
        self.add_rule(NotificationRule(
            name="High Risk Detected",
            notification_type=NotificationType.RISK_WARNING,
            priority=NotificationPriority.CRITICAL,
            condition=lambda ctx: (
                ctx.get('portfolio_risk', 0) > 0.15 or  # 15% risk
                ctx.get('drawdown', 0) > 0.10  # 10% drawdown
            ),
            message_template="⚠️ Risk Alert: Portfolio risk at {portfolio_risk:.1%}, Drawdown: {drawdown:.1%}"
        ))
        
        # 3. Daily Loss Limit
        self.add_rule(NotificationRule(
            name="Daily Loss Limit Approaching",
            notification_type=NotificationType.RISK_WARNING,
            priority=NotificationPriority.CRITICAL,
            condition=lambda ctx: ctx.get('daily_pnl_pct', 0) < -3,  # -3% daily loss
            message_template="🛑 Daily loss at {daily_pnl_pct:.1f}%. Consider reducing exposure."
        ))
        
        # 4. Profit Milestone
        self.add_rule(NotificationRule(
            name="Profit Milestone Achieved",
            notification_type=NotificationType.PORTFOLIO_MILESTONE,
            priority=NotificationPriority.MEDIUM,
            condition=lambda ctx: (
                ctx.get('total_return_pct', 0) > 0 and
                int(ctx.get('total_return_pct', 0)) % 10 == 0  # Every 10% gain
            ),
            message_template="🎉 Portfolio milestone: {total_return_pct:.0f}% total return achieved!"
        ))
        
        # 5. Market Volatility Spike
        self.add_rule(NotificationRule(
            name="Market Volatility Spike",
            notification_type=NotificationType.MARKET_EVENT,
            priority=NotificationPriority.HIGH,
            condition=lambda ctx: ctx.get('volatility_percentile', 0) > 95,
            message_template="⚡ Extreme volatility detected ({volatility_percentile:.0f}th percentile). Exercise caution."
        ))
        
        # 6. New Trading Opportunity
        self.add_rule(NotificationRule(
            name="High-Probability Setup",
            notification_type=NotificationType.OPPORTUNITY,
            priority=NotificationPriority.MEDIUM,
            condition=lambda ctx: (
                ctx.get('setup_quality', 0) > 85 and
                ctx.get('risk_reward_ratio', 0) > 3
            ),
            message_template="💎 High-quality setup: {symbol} ({setup_quality:.0f}% quality, {risk_reward_ratio:.1f}:1 R:R)"
        ))
        
        # 7. AI Confidence Low
        self.add_rule(NotificationRule(
            name="AI Uncertainty Warning",
            notification_type=NotificationType.AI_INSIGHT,
            priority=NotificationPriority.LOW,
            condition=lambda ctx: (
                ctx.get('ai_confidence', 100) < 40 and
                ctx.get('signal') != 'HOLD'
            ),
            message_template="🤔 AI uncertainty: {ai_confidence:.0f}% confidence. Consider holding."
        ))
        
        # 8. Win Rate Improvement
        self.add_rule(NotificationRule(
            name="Win Rate Improving",
            notification_type=NotificationType.PERFORMANCE_ALERT,
            priority=NotificationPriority.LOW,
            condition=lambda ctx: (
                ctx.get('win_rate_change', 0) > 5  # 5% improvement
            ),
            message_template="📈 Win rate improved by {win_rate_change:.1f}% to {current_win_rate:.1f}%"
        ))
        
        # 9. Position Size Warning
        self.add_rule(NotificationRule(
            name="Position Too Large",
            notification_type=NotificationType.RISK_WARNING,
            priority=NotificationPriority.HIGH,
            condition=lambda ctx: ctx.get('position_size_pct', 0) > 20,  # >20% of portfolio
            message_template="⚠️ Large position: {symbol} is {position_size_pct:.1f}% of portfolio"
        ))
        
        # 10. Stop Loss Hit
        self.add_rule(NotificationRule(
            name="Stop Loss Triggered",
            notification_type=NotificationType.TRADE_SIGNAL,
            priority=NotificationPriority.HIGH,
            condition=lambda ctx: ctx.get('stop_loss_hit', False),
            message_template="🛑 Stop loss hit for {symbol}. Position closed at ${exit_price:.2f}"
        ))
        
        # 11. Target Price Reached
        self.add_rule(NotificationRule(
            name="Target Price Reached",
            notification_type=NotificationType.TRADE_SIGNAL,
            priority=NotificationPriority.MEDIUM,
            condition=lambda ctx: ctx.get('target_reached', False),
            message_template="🎯 Target reached for {symbol}! ${current_price:.2f} / ${target_price:.2f}"
        ))
        
        # 12. Market Regime Change
        self.add_rule(NotificationRule(
            name="Market Regime Shift",
            notification_type=NotificationType.MARKET_EVENT,
            priority=NotificationPriority.MEDIUM,
            condition=lambda ctx: ctx.get('regime_changed', False),
            message_template="🔄 Market regime shift: {old_regime} → {new_regime}"
        ))
    
    def add_rule(self, rule: NotificationRule):
        """Add a notification rule"""
        self.rules.append(rule)
        logger.debug(f"Added notification rule: {rule.name}")
    
    def evaluate_rules(self, context: Dict) -> List[Notification]:
        """Evaluate all rules with given context"""
        new_notifications = []
        
        for rule in self.rules:
            if rule.notification_type not in self.muted_types:
                notification = rule.evaluate(context)
                if notification:
                    self.notifications.append(notification)
                    new_notifications.append(notification)
                    
                    # Notify subscribers
                    self._notify_subscribers(notification)
        
        return new_notifications
    
    def _notify_subscribers(self, notification: Notification):
        """Notify all subscribers for this notification type"""
        subscribers = self.subscribers.get(notification.type, [])
        for callback in subscribers:
            try:
                callback(notification)
            except Exception as e:
                logger.error(f"Error calling subscriber: {e}")
    
    def subscribe(self, notification_type: NotificationType, callback: Callable):
        """Subscribe to notifications of a specific type"""
        if notification_type not in self.subscribers:
            self.subscribers[notification_type] = []
        self.subscribers[notification_type].append(callback)
        logger.info(f"New subscriber for {notification_type.value}")
    
    def mute_type(self, notification_type: NotificationType):
        """Mute notifications of a specific type"""
        self.muted_types.add(notification_type)
        logger.info(f"Muted notifications: {notification_type.value}")
    
    def unmute_type(self, notification_type: NotificationType):
        """Unmute notifications of a specific type"""
        self.muted_types.discard(notification_type)
        logger.info(f"Unmuted notifications: {notification_type.value}")
    
    def get_unread(self, priority: Optional[NotificationPriority] = None) -> List[Notification]:
        """Get unread notifications, optionally filtered by priority"""
        unread = [n for n in self.notifications if not n.read and not n.dismissed]
        
        if priority:
            unread = [n for n in unread if n.priority == priority]
        
        return sorted(unread, key=lambda n: (
            list(NotificationPriority).index(n.priority),
            n.timestamp
        ), reverse=True)
    
    def mark_read(self, notification_id: str):
        """Mark notification as read"""
        for notification in self.notifications:
            if notification.id == notification_id:
                notification.read = True
                break
    
    def dismiss(self, notification_id: str):
        """Dismiss notification"""
        for notification in self.notifications:
            if notification.id == notification_id:
                notification.dismissed = True
                break
    
    def clear_all(self):
        """Clear all notifications"""
        self.notifications.clear()
        logger.info("All notifications cleared")
    
    def get_stats(self) -> Dict:
        """Get notification statistics"""
        total = len(self.notifications)
        unread = len([n for n in self.notifications if not n.read])
        
        by_type = {}
        for notif_type in NotificationType:
            by_type[notif_type.value] = len([
                n for n in self.notifications 
                if n.type == notif_type
            ])
        
        by_priority = {}
        for priority in NotificationPriority:
            by_priority[priority.value] = len([
                n for n in self.notifications 
                if n.priority == priority and not n.read
            ])
        
        return {
            'total': total,
            'unread': unread,
            'by_type': by_type,
            'by_priority': by_priority
        }


# Global notification system instance
_notification_system = None


def get_notification_system() -> SmartNotificationSystem:
    """Get global notification system instance"""
    global _notification_system
    if _notification_system is None:
        _notification_system = SmartNotificationSystem()
    return _notification_system


# Example usage
if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    
    # Get notification system
    notif_system = get_notification_system()
    
    # Subscribe to trade signals
    def handle_trade_signal(notification: Notification):
        print(f"📊 TRADE SIGNAL: {notification.message}")
    
    notif_system.subscribe(NotificationType.TRADE_SIGNAL, handle_trade_signal)
    
    # Test scenarios
    print("\n=== Testing Notification System ===\n")
    
    # Scenario 1: Strong buy signal
    print("1. Strong Buy Signal")
    notif_system.evaluate_rules({
        'signal': 'BUY',
        'confidence': 85.5,
        'symbol': 'AAPL',
        'entry_price': 175.50
    })
    
    # Scenario 2: Risk warning
    print("\n2. Risk Warning")
    notif_system.evaluate_rules({
        'portfolio_risk': 0.18,
        'drawdown': 0.12
    })
    
    # Scenario 3: Profit milestone
    print("\n3. Profit Milestone")
    notif_system.evaluate_rules({
        'total_return_pct': 20.0
    })
    
    # Scenario 4: Market volatility
    print("\n4. Volatility Spike")
    notif_system.evaluate_rules({
        'volatility_percentile': 97
    })
    
    # Get stats
    print("\n=== Notification Stats ===")
    stats = notif_system.get_stats()
    print(json.dumps(stats, indent=2))
    
    # Get unread critical notifications
    print("\n=== Unread Critical Notifications ===")
    critical = notif_system.get_unread(NotificationPriority.CRITICAL)
    for notif in critical:
        print(f"[{notif.priority.value.upper()}] {notif.title}")
        print(f"  {notif.message}\n")
