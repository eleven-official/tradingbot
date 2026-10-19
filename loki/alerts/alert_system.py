"""
LOKI v7.0 - Advanced Alert System
Multi-channel notifications with custom conditions and smart triggers
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Callable, Any
from enum import Enum
import json
import os

logger = logging.getLogger(__name__)


class AlertType(Enum):
    """Types of alerts"""

    PRICE = "price"
    INDICATOR = "indicator"
    VOLUME = "volume"
    PATTERN = "pattern"
    SIGNAL = "signal"
    PORTFOLIO = "portfolio"
    SYSTEM = "system"


class AlertPriority(Enum):
    """Alert priority levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertChannel(Enum):
    """Notification channels"""

    DESKTOP = "desktop"
    EMAIL = "email"
    SMS = "sms"
    WEBHOOK = "webhook"
    LOG = "log"
    SOUND = "sound"


class ConditionOperator(Enum):
    """Comparison operators"""

    EQUALS = "=="
    NOT_EQUALS = "!="
    GREATER_THAN = ">"
    GREATER_EQUAL = ">="
    LESS_THAN = "<"
    LESS_EQUAL = "<="
    BETWEEN = "between"
    OUTSIDE = "outside"
    CROSSES_ABOVE = "crosses_above"
    CROSSES_BELOW = "crosses_below"


@dataclass
class AlertCondition:
    """Single alert condition"""

    field: str  # e.g., "price", "rsi", "volume"
    operator: ConditionOperator
    value: Any  # Threshold value
    value2: Optional[Any] = None  # For BETWEEN/OUTSIDE operators

    def evaluate(self, current_value: float, previous_value: Optional[float] = None) -> bool:
        """
        Evaluate if condition is met

        Args:
            current_value: Current value to check
            previous_value: Previous value (for cross conditions)

        Returns:
            True if condition is met
        """
        try:
            if self.operator == ConditionOperator.EQUALS:
                return abs(current_value - self.value) < 0.0001

            elif self.operator == ConditionOperator.NOT_EQUALS:
                return abs(current_value - self.value) >= 0.0001

            elif self.operator == ConditionOperator.GREATER_THAN:
                return current_value > self.value

            elif self.operator == ConditionOperator.GREATER_EQUAL:
                return current_value >= self.value

            elif self.operator == ConditionOperator.LESS_THAN:
                return current_value < self.value

            elif self.operator == ConditionOperator.LESS_EQUAL:
                return current_value <= self.value

            elif self.operator == ConditionOperator.BETWEEN:
                if self.value2 is None:
                    return False
                return self.value <= current_value <= self.value2

            elif self.operator == ConditionOperator.OUTSIDE:
                if self.value2 is None:
                    return False
                return current_value < self.value or current_value > self.value2

            elif self.operator == ConditionOperator.CROSSES_ABOVE:
                if previous_value is None:
                    return False
                return previous_value <= self.value < current_value

            elif self.operator == ConditionOperator.CROSSES_BELOW:
                if previous_value is None:
                    return False
                return previous_value >= self.value > current_value

            return False

        except Exception as e:
            logger.error(f"Condition evaluation failed: {e}")
            return False


@dataclass
class Alert:
    """Alert definition"""

    alert_id: str
    name: str
    alert_type: AlertType
    symbol: Optional[str]  # For asset-specific alerts
    conditions: List[AlertCondition]
    priority: AlertPriority
    channels: List[AlertChannel]
    message_template: str
    enabled: bool = True
    cooldown_minutes: int = 5  # Minimum time between repeat alerts
    expiry: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    last_triggered: Optional[datetime] = None
    trigger_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_active(self) -> bool:
        """Check if alert is currently active"""
        if not self.enabled:
            return False

        if self.expiry and datetime.now() > self.expiry:
            return False

        return True

    def can_trigger(self) -> bool:
        """Check if alert can trigger (respects cooldown)"""
        if not self.is_active():
            return False

        if self.last_triggered is None:
            return True

        elapsed = (datetime.now() - self.last_triggered).total_seconds() / 60
        return elapsed >= self.cooldown_minutes

    def should_trigger(self, market_data: Dict[str, Any]) -> bool:
        """
        Check if all conditions are met

        Args:
            market_data: Current market data with previous values

        Returns:
            True if alert should trigger
        """
        if not self.can_trigger():
            return False

        # All conditions must be met (AND logic)
        for condition in self.conditions:
            field_name = condition.field

            current_value = market_data.get(f"current_{field_name}")
            previous_value = market_data.get(f"previous_{field_name}")

            if current_value is None:
                logger.warning(f"Missing data for condition field: {field_name}")
                return False

            if not condition.evaluate(current_value, previous_value):
                return False

        return True

    def format_message(self, market_data: Dict[str, Any]) -> str:
        """
        Format alert message with current data

        Args:
            market_data: Current market data for template substitution

        Returns:
            Formatted message string
        """
        try:
            return self.message_template.format(**market_data)
        except KeyError as e:
            logger.error(f"Message template error: missing key {e}")
            return self.message_template

    def mark_triggered(self):
        """Mark alert as triggered"""
        self.last_triggered = datetime.now()
        self.trigger_count += 1


@dataclass
class AlertHistory:
    """Alert trigger history record"""

    alert_id: str
    alert_name: str
    triggered_at: datetime
    message: str
    priority: AlertPriority
    channels_sent: List[AlertChannel]
    market_data: Dict[str, Any]


class AlertNotifier:
    """Handles sending alerts through various channels"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize alert notifier

        Args:
            config: Configuration for notification channels
        """
        self.config = config or {}
        self.notification_history: List[AlertHistory] = []

        # Desktop notification support
        self.desktop_enabled = True
        try:
            from plyer import notification

            self.plyer_notification = notification
        except ImportError:
            logger.warning("Desktop notifications disabled (install plyer)")
            self.desktop_enabled = False

        # Sound support
        self.sound_enabled = True
        try:
            import winsound

            self.winsound = winsound
        except ImportError:
            logger.warning("Sound alerts disabled (winsound not available)")
            self.sound_enabled = False

        logger.info("Alert Notifier initialized")

    def send_alert(
        self, alert: Alert, message: str, market_data: Dict[str, Any]
    ) -> List[AlertChannel]:
        """
        Send alert through configured channels

        Args:
            alert: Alert definition
            message: Formatted message
            market_data: Current market data

        Returns:
            List of channels successfully sent to
        """
        sent_channels = []

        for channel in alert.channels:
            try:
                if channel == AlertChannel.DESKTOP:
                    if self._send_desktop(alert, message):
                        sent_channels.append(channel)

                elif channel == AlertChannel.EMAIL:
                    if self._send_email(alert, message):
                        sent_channels.append(channel)

                elif channel == AlertChannel.SMS:
                    if self._send_sms(alert, message):
                        sent_channels.append(channel)

                elif channel == AlertChannel.WEBHOOK:
                    if self._send_webhook(alert, message, market_data):
                        sent_channels.append(channel)

                elif channel == AlertChannel.LOG:
                    if self._send_log(alert, message):
                        sent_channels.append(channel)

                elif channel == AlertChannel.SOUND:
                    if self._send_sound(alert):
                        sent_channels.append(channel)

            except Exception as e:
                logger.error(f"Failed to send alert via {channel.value}: {e}")

        # Record in history
        history = AlertHistory(
            alert_id=alert.alert_id,
            alert_name=alert.name,
            triggered_at=datetime.now(),
            message=message,
            priority=alert.priority,
            channels_sent=sent_channels,
            market_data=market_data,
        )
        self.notification_history.append(history)

        logger.info(f"Alert sent: {alert.name} via {[c.value for c in sent_channels]}")

        return sent_channels

    def _send_desktop(self, alert: Alert, message: str) -> bool:
        """Send desktop notification"""
        if not self.desktop_enabled:
            return False

        try:
            title = f"LOKI Alert: {alert.name}"

            # Truncate message if too long
            if len(message) > 256:
                message = message[:253] + "..."

            self.plyer_notification.notify(
                title=title, message=message, app_name="LOKI Trading Platform", timeout=10
            )
            return True

        except Exception as e:
            logger.error(f"Desktop notification failed: {e}")
            return False

    def _send_email(self, alert: Alert, message: str) -> bool:
        """Send email notification"""
        # Stub - requires email configuration
        email_config = self.config.get("email", {})

        if not email_config.get("enabled", False):
            logger.debug("Email notifications not configured")
            return False

        # Would implement SMTP sending here
        logger.info(f"Email notification: {message[:50]}...")
        return True

    def _send_sms(self, alert: Alert, message: str) -> bool:
        """Send SMS notification"""
        # Stub - requires SMS service (Twilio, etc.)
        sms_config = self.config.get("sms", {})

        if not sms_config.get("enabled", False):
            logger.debug("SMS notifications not configured")
            return False

        # Would implement SMS service here
        logger.info(f"SMS notification: {message[:50]}...")
        return True

    def _send_webhook(self, alert: Alert, message: str, market_data: Dict[str, Any]) -> bool:
        """Send webhook notification"""
        webhook_config = self.config.get("webhook", {})

        if not webhook_config.get("enabled", False):
            logger.debug("Webhook notifications not configured")
            return False

        try:
            import requests

            url = webhook_config.get("url")
            if not url:
                return False

            payload = {
                "alert_id": alert.alert_id,
                "alert_name": alert.name,
                "priority": alert.priority.value,
                "message": message,
                "timestamp": datetime.now().isoformat(),
                "market_data": market_data,
            }

            response = requests.post(url, json=payload, timeout=5)
            return response.status_code == 200

        except Exception as e:
            logger.error(f"Webhook failed: {e}")
            return False

    def _send_log(self, alert: Alert, message: str) -> bool:
        """Log alert to file"""
        try:
            log_dir = "data/alerts"
            os.makedirs(log_dir, exist_ok=True)

            log_file = os.path.join(log_dir, f"alerts_{datetime.now().strftime('%Y%m%d')}.log")

            with open(log_file, "a", encoding="utf-8") as f:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{timestamp}] [{alert.priority.value.upper()}] {alert.name}: {message}\n")

            return True

        except Exception as e:
            logger.error(f"Log alert failed: {e}")
            return False

    def _send_sound(self, alert: Alert) -> bool:
        """Play sound alert"""
        if not self.sound_enabled:
            return False

        try:
            # Different sounds for different priorities
            if alert.priority == AlertPriority.CRITICAL:
                frequency = 1000
                duration = 500
            elif alert.priority == AlertPriority.HIGH:
                frequency = 800
                duration = 300
            else:
                frequency = 600
                duration = 200

            self.winsound.Beep(frequency, duration)
            return True

        except Exception as e:
            logger.error(f"Sound alert failed: {e}")
            return False


class AlertManager:
    """
    Central alert management system

    Features:
    - Create and manage alerts
    - Monitor conditions
    - Trigger notifications
    - Alert history and analytics
    """

    def __init__(self, notifier: Optional[AlertNotifier] = None):
        """
        Initialize alert manager

        Args:
            notifier: AlertNotifier instance (creates default if None)
        """
        self.notifier = notifier or AlertNotifier()
        self.alerts: Dict[str, Alert] = {}
        self.previous_data: Dict[str, Dict[str, Any]] = {}  # symbol -> field -> value

        # Load saved alerts
        self._load_alerts()

        logger.info("Alert Manager initialized")

    def create_alert(
        self,
        name: str,
        alert_type: AlertType,
        conditions: List[AlertCondition],
        priority: AlertPriority = AlertPriority.MEDIUM,
        channels: Optional[List[AlertChannel]] = None,
        message_template: str = "{name} triggered",
        symbol: Optional[str] = None,
        cooldown_minutes: int = 5,
        expiry: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Alert:
        """
        Create a new alert

        Args:
            name: Alert name
            alert_type: Type of alert
            conditions: List of conditions (all must be met)
            priority: Alert priority level
            channels: Notification channels (default: desktop + log)
            message_template: Message template with {field} placeholders
            symbol: Asset symbol (for asset-specific alerts)
            cooldown_minutes: Cooldown between repeated alerts
            expiry: Optional expiry datetime
            metadata: Additional metadata

        Returns:
            Created Alert object
        """
        alert_id = f"{alert_type.value}_{name.replace(' ', '_')}_{datetime.now().timestamp()}"

        if channels is None:
            channels = [AlertChannel.DESKTOP, AlertChannel.LOG, AlertChannel.SOUND]

        alert = Alert(
            alert_id=alert_id,
            name=name,
            alert_type=alert_type,
            symbol=symbol,
            conditions=conditions,
            priority=priority,
            channels=channels,
            message_template=message_template,
            cooldown_minutes=cooldown_minutes,
            expiry=expiry,
            metadata=metadata or {},
        )

        self.alerts[alert_id] = alert
        self._save_alerts()

        logger.info(f"Created alert: {name} (ID: {alert_id})")

        return alert

    def create_price_alert(
        self,
        symbol: str,
        price: float,
        operator: ConditionOperator = ConditionOperator.GREATER_THAN,
        priority: AlertPriority = AlertPriority.HIGH,
    ) -> Alert:
        """
        Quick helper to create price alert

        Args:
            symbol: Asset symbol
            price: Target price
            operator: Comparison operator
            priority: Alert priority

        Returns:
            Created Alert
        """
        condition = AlertCondition(field="price", operator=operator, value=price)

        op_text = {
            ConditionOperator.GREATER_THAN: "above",
            ConditionOperator.LESS_THAN: "below",
            ConditionOperator.CROSSES_ABOVE: "crosses above",
            ConditionOperator.CROSSES_BELOW: "crosses below",
        }.get(operator, str(operator.value))

        return self.create_alert(
            name=f"{symbol} {op_text} ${price:.2f}",
            alert_type=AlertType.PRICE,
            conditions=[condition],
            priority=priority,
            symbol=symbol,
            message_template=f"{symbol} price is {{current_price:.2f}} ({op_text} ${price:.2f})",
        )

    def create_rsi_alert(
        self,
        symbol: str,
        rsi_threshold: float,
        operator: ConditionOperator = ConditionOperator.LESS_THAN,
        priority: AlertPriority = AlertPriority.MEDIUM,
    ) -> Alert:
        """
        Quick helper to create RSI alert

        Args:
            symbol: Asset symbol
            rsi_threshold: RSI threshold
            operator: Comparison operator
            priority: Alert priority

        Returns:
            Created Alert
        """
        condition = AlertCondition(field="rsi", operator=operator, value=rsi_threshold)

        return self.create_alert(
            name=f"{symbol} RSI {operator.value} {rsi_threshold}",
            alert_type=AlertType.INDICATOR,
            conditions=[condition],
            priority=priority,
            symbol=symbol,
            message_template=f"{symbol} RSI is {{current_rsi:.1f}} (threshold: {rsi_threshold})",
        )

    def check_alerts(self, symbol: str, market_data: Dict[str, Any]):
        """
        Check all alerts for a symbol

        Args:
            symbol: Asset symbol
            market_data: Current market data (price, indicators, etc.)
        """
        # Add previous values for cross conditions
        if symbol in self.previous_data:
            for field, value in self.previous_data[symbol].items():
                market_data[f"previous_{field}"] = value

        # Add current values with "current_" prefix
        current_data = {}
        for field, value in market_data.items():
            if not field.startswith("previous_"):
                market_data[f"current_{field}"] = value
                current_data[field] = value

        # Check each alert
        for alert in self.alerts.values():
            if not alert.is_active():
                continue

            # Skip if alert is symbol-specific and doesn't match
            if alert.symbol and alert.symbol != symbol:
                continue

            # Check if should trigger
            if alert.should_trigger(market_data):
                message = alert.format_message(market_data)
                self.notifier.send_alert(alert, message, market_data)
                alert.mark_triggered()
                self._save_alerts()

        # Store current data as previous for next check
        self.previous_data[symbol] = current_data

    def remove_alert(self, alert_id: str) -> bool:
        """Remove an alert"""
        if alert_id in self.alerts:
            del self.alerts[alert_id]
            self._save_alerts()
            logger.info(f"Removed alert: {alert_id}")
            return True
        return False

    def enable_alert(self, alert_id: str, enabled: bool = True):
        """Enable or disable an alert"""
        if alert_id in self.alerts:
            self.alerts[alert_id].enabled = enabled
            self._save_alerts()
            logger.info(f"Alert {alert_id} {'enabled' if enabled else 'disabled'}")

    def get_alert_stats(self) -> Dict[str, Any]:
        """Get alert system statistics"""
        active_alerts = sum(1 for a in self.alerts.values() if a.is_active())
        total_triggers = sum(a.trigger_count for a in self.alerts.values())

        return {
            "total_alerts": len(self.alerts),
            "active_alerts": active_alerts,
            "disabled_alerts": len(self.alerts) - active_alerts,
            "total_triggers": total_triggers,
            "notifications_sent": len(self.notifier.notification_history),
        }

    def _save_alerts(self):
        """Save alerts to file"""
        try:
            os.makedirs("data/alerts", exist_ok=True)

            # Convert to serializable format
            alerts_data = []
            for alert in self.alerts.values():
                alert_dict = {
                    "alert_id": alert.alert_id,
                    "name": alert.name,
                    "alert_type": alert.alert_type.value,
                    "symbol": alert.symbol,
                    "priority": alert.priority.value,
                    "channels": [c.value for c in alert.channels],
                    "message_template": alert.message_template,
                    "enabled": alert.enabled,
                    "cooldown_minutes": alert.cooldown_minutes,
                    "trigger_count": alert.trigger_count,
                    "conditions": [
                        {
                            "field": c.field,
                            "operator": c.operator.value,
                            "value": c.value,
                            "value2": c.value2,
                        }
                        for c in alert.conditions
                    ],
                }
                alerts_data.append(alert_dict)

            with open("data/alerts/alerts.json", "w") as f:
                json.dump(alerts_data, f, indent=2)

        except Exception as e:
            logger.error(f"Failed to save alerts: {e}")

    def _load_alerts(self):
        """Load alerts from file"""
        try:
            if not os.path.exists("data/alerts/alerts.json"):
                return

            with open("data/alerts/alerts.json", "r") as f:
                alerts_data = json.load(f)

            for alert_dict in alerts_data:
                conditions = [
                    AlertCondition(
                        field=c["field"],
                        operator=ConditionOperator(c["operator"]),
                        value=c["value"],
                        value2=c.get("value2"),
                    )
                    for c in alert_dict["conditions"]
                ]

                alert = Alert(
                    alert_id=alert_dict["alert_id"],
                    name=alert_dict["name"],
                    alert_type=AlertType(alert_dict["alert_type"]),
                    symbol=alert_dict.get("symbol"),
                    conditions=conditions,
                    priority=AlertPriority(alert_dict["priority"]),
                    channels=[AlertChannel(c) for c in alert_dict["channels"]],
                    message_template=alert_dict["message_template"],
                    enabled=alert_dict.get("enabled", True),
                    cooldown_minutes=alert_dict.get("cooldown_minutes", 5),
                    trigger_count=alert_dict.get("trigger_count", 0),
                )

                self.alerts[alert.alert_id] = alert

            logger.info(f"Loaded {len(self.alerts)} alerts")

        except Exception as e:
            logger.error(f"Failed to load alerts: {e}")


def demo_alert_system():
    """Demonstration of alert system"""
    print(f"\n{'='*70}")
    print("LOKI ADVANCED ALERT SYSTEM DEMO")
    print(f"{'='*70}\n")

    # Initialize alert manager
    manager = AlertManager()

    # Create price alert
    alert1 = manager.create_price_alert(
        symbol="AAPL",
        price=150.0,
        operator=ConditionOperator.GREATER_THAN,
        priority=AlertPriority.HIGH,
    )
    print(f"✓ Created price alert: {alert1.name}")

    # Create RSI alert
    alert2 = manager.create_rsi_alert(
        symbol="AAPL",
        rsi_threshold=30,
        operator=ConditionOperator.LESS_THAN,
        priority=AlertPriority.MEDIUM,
    )
    print(f"✓ Created RSI alert: {alert2.name}")

    # Create custom multi-condition alert
    alert3 = manager.create_alert(
        name="AAPL Overbought",
        alert_type=AlertType.SIGNAL,
        conditions=[
            AlertCondition("rsi", ConditionOperator.GREATER_THAN, 70),
            AlertCondition("volume", ConditionOperator.GREATER_THAN, 1000000),
        ],
        priority=AlertPriority.HIGH,
        symbol="AAPL",
        message_template="AAPL overbought: RSI={current_rsi:.1f}, Volume={current_volume:,.0f}",
    )
    print(f"✓ Created custom alert: {alert3.name}")

    # Simulate market data that triggers alerts
    print(f"\n{'='*70}")
    print("CHECKING MARKET CONDITIONS")
    print(f"{'='*70}\n")

    market_data = {"price": 151.50, "rsi": 28.5, "volume": 1500000, "symbol": "AAPL"}

    print(
        f"Market Data: Price=${market_data['price']:.2f}, RSI={market_data['rsi']:.1f}, Volume={market_data['volume']:,.0f}"
    )
    print("\nChecking alerts...")

    manager.check_alerts("AAPL", market_data)

    # Show statistics
    print(f"\n{'='*70}")
    print("ALERT SYSTEM STATISTICS")
    print(f"{'='*70}\n")

    stats = manager.get_alert_stats()
    print(f"Total Alerts: {stats['total_alerts']}")
    print(f"Active Alerts: {stats['active_alerts']}")
    print(f"Total Triggers: {stats['total_triggers']}")
    print(f"Notifications Sent: {stats['notifications_sent']}")


if __name__ == "__main__":
    demo_alert_system()
