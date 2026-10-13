"""Safe ingestion of TradingView alerts.

TradingView alerts are untrusted internet input. This module validates the
payload before it reaches an execution handler, supports a shared-token flow
that TradingView can send, and rejects accidental duplicate alerts.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import hmac
import json
import logging
import math
import re
import threading
import time
from typing import Any, Callable, Dict, Optional


class SignalType(Enum):
    """Types of trading signals accepted from TradingView."""

    BUY = "buy"
    SELL = "sell"
    EXIT = "exit"
    ADJUST_SL = "adjust_sl"
    ADJUST_TARGET = "adjust_target"


class SignalAction(Enum):
    EXECUTE = "execute"
    QUEUE = "queue"
    IGNORE = "ignore"
    REQUIRE_CONFIRMATION = "require_confirmation"


@dataclass(frozen=True)
class TradingViewSignal:
    """A validated signal; no raw webhook data is executed directly."""

    signal_type: SignalType
    symbol: str
    price: float
    quantity: Optional[float] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    strategy: str = "TradingView"
    signal_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class TradingViewBridge:
    """Validate, authenticate, de-duplicate and dispatch TradingView alerts."""

    _SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9_./:-]{0,63}$")
    _AUTH_METHODS = {"none", "signature", "token", "either"}

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.tv_config = config.get("tradingview", {}) or {}
        self.enabled = bool(self.tv_config.get("enabled", False))
        self.webhook_secret = str(self.tv_config.get("webhook_secret", ""))
        self.require_signature = bool(self.tv_config.get("require_signature", True))
        default_auth = "signature" if self.require_signature else "none"
        self.auth_method = str(self.tv_config.get("auth_method", default_auth)).lower()
        if self.auth_method not in self._AUTH_METHODS:
            raise ValueError("tradingview.auth_method must be none, signature, token, or either")

        try:
            self.default_action = SignalAction(self.tv_config.get("default_action", "queue"))
        except ValueError as exc:
            raise ValueError("tradingview.default_action is invalid") from exc

        configured_symbols = self.tv_config.get("allowed_symbols", []) or []
        self.allowed_symbols = {str(symbol).upper() for symbol in configured_symbols}
        self.max_position_size = self._positive_float(
            self.tv_config.get("max_position_size", 0), "max_position_size", allow_zero=True
        )
        # Legacy callers often use this bridge for alerts that only request a
        # confirmation. The Loki execution config explicitly turns this on.
        self.require_quantity = bool(self.tv_config.get("require_quantity", False))
        self.max_signal_age_seconds = self._positive_float(
            self.tv_config.get("max_signal_age_seconds", 0), "max_signal_age_seconds", allow_zero=True
        )
        self.replay_window_seconds = self._positive_float(
            self.tv_config.get("replay_window_seconds", 0), "replay_window_seconds", allow_zero=True
        )
        self.max_queue_size = int(self.tv_config.get("max_queue_size", 100))
        if self.max_queue_size < 1:
            raise ValueError("tradingview.max_queue_size must be at least 1")

        self.signal_handlers: Dict[SignalType, Callable[[TradingViewSignal], Any]] = {}
        self.signal_queue: deque[TradingViewSignal] = deque(maxlen=self.max_queue_size)
        # Compatibility aliases for the older MarketManager queue API.
        self.alert_queue = self.signal_queue
        self.running = False
        self.processed_signals: deque[TradingViewSignal] = deque(maxlen=500)
        self._seen_signals: Dict[str, float] = {}
        self._lock = threading.RLock()

        self.signals_received = 0
        self.signals_executed = 0
        self.signals_ignored = 0
        self.signals_failed = 0
        self.signals_replayed = 0
        logging.info("TradingView Bridge initialized: auth=%s, action=%s", self.auth_method, self.default_action.value)

    @staticmethod
    def _positive_float(value: Any, field_name: str, allow_zero: bool = False) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"tradingview.{field_name} must be numeric") from exc
        if not math.isfinite(number) or number < 0 or (number == 0 and not allow_zero):
            qualifier = "non-negative" if allow_zero else "positive"
            raise ValueError(f"tradingview.{field_name} must be {qualifier}")
        return number

    @property
    def authentication_ready(self) -> bool:
        return self.auth_method == "none" or bool(self.webhook_secret)

    def register_handler(self, signal_type: SignalType, handler: Callable[[TradingViewSignal], Any]) -> None:
        if not callable(handler):
            raise TypeError("TradingView handler must be callable")
        self.signal_handlers[signal_type] = handler
        logging.info("Registered handler for %s signals", signal_type.value)

    def receive_webhook(self, payload: str, signature: Optional[str] = None) -> Dict[str, Any]:
        """Receive a raw JSON body and return a safe, machine-readable result."""
        if not self.enabled:
            return {"status": "error", "message": "TradingView bridge is disabled"}
        if not isinstance(payload, str) or len(payload) > 32_768:
            return {"status": "error", "message": "Payload must be a JSON string up to 32 KiB"}

        try:
            data = json.loads(payload)
            if not isinstance(data, dict):
                raise ValueError("JSON payload must be an object")
        except (json.JSONDecodeError, ValueError) as exc:
            with self._lock:
                self.signals_failed += 1
            return {"status": "error", "message": f"Invalid JSON: {exc}"}

        if not self._authenticate(payload, data, signature):
            with self._lock:
                self.signals_failed += 1
            logging.warning("Rejected unauthenticated TradingView alert")
            return {"status": "error", "message": "Webhook authentication failed"}

        try:
            signal = self._parse_signal(data)
            replay_key = self._replay_key(payload, signal)
            with self._lock:
                if self._is_replay(replay_key):
                    self.signals_replayed += 1
                    return {"status": "ignored", "message": "Duplicate signal rejected"}
                self._seen_signals[replay_key] = time.monotonic()
                self.signals_received += 1

            action = self._determine_action(signal)
            if action == SignalAction.EXECUTE:
                return self._execute_signal(signal)
            if action == SignalAction.QUEUE:
                return self._queue_signal(signal)
            if action == SignalAction.IGNORE:
                return self._ignore_signal(signal)
            return self._require_confirmation(signal)
        except (TypeError, ValueError) as exc:
            with self._lock:
                self.signals_failed += 1
            logging.warning("Rejected invalid TradingView signal: %s", exc)
            return {"status": "error", "message": f"Invalid signal: {exc}"}
        except Exception:
            with self._lock:
                self.signals_failed += 1
            logging.exception("Unexpected error processing TradingView signal")
            return {"status": "error", "message": "Signal processing failed"}

    def _authenticate(self, payload: str, data: Dict[str, Any], signature: Optional[str]) -> bool:
        if self.auth_method == "none":
            return True
        if not self.webhook_secret:
            logging.error("Webhook authentication is enabled but no secret has been configured")
            return False
        valid_signature = bool(signature) and self._verify_signature(payload, signature)
        token = data.get("token")
        valid_token = isinstance(token, str) and hmac.compare_digest(token, self.webhook_secret)
        if self.auth_method == "signature":
            return valid_signature
        if self.auth_method == "token":
            return valid_token
        return valid_signature or valid_token

    def _verify_signature(self, payload: str, signature: str) -> bool:
        expected = hmac.new(self.webhook_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature.strip().removeprefix("sha256="))

    def _parse_signal(self, data: Dict[str, Any]) -> TradingViewSignal:
        raw_type = str(data.get("signal_type", "")).strip().lower()
        try:
            signal_type = SignalType(raw_type)
        except ValueError as exc:
            accepted = ", ".join(item.value for item in SignalType)
            raise ValueError(f"signal_type must be one of: {accepted}") from exc

        symbol = str(data.get("symbol", "")).strip().upper()
        if not self._SYMBOL_RE.fullmatch(symbol):
            raise ValueError("symbol contains unsupported characters or is missing")
        price = self._positive_float(data.get("price"), "price")

        quantity_raw = data.get("quantity")
        if quantity_raw is None or quantity_raw == "":
            if self.require_quantity and signal_type in {SignalType.BUY, SignalType.SELL}:
                raise ValueError("quantity is required for buy and sell signals")
            quantity = None
        else:
            quantity = self._positive_float(quantity_raw, "quantity")

        timestamp = self._parse_timestamp(data.get("timestamp"))
        if self.max_signal_age_seconds and timestamp is not None:
            age = (datetime.now(timezone.utc) - timestamp).total_seconds()
            if age > self.max_signal_age_seconds:
                raise ValueError("signal timestamp is older than the configured maximum age")
            if age < -60:
                raise ValueError("signal timestamp is more than 60 seconds in the future")

        signal_id = data.get("signal_id")
        if signal_id is not None:
            signal_id = str(signal_id).strip()
            if not signal_id or len(signal_id) > 128:
                raise ValueError("signal_id must contain 1 to 128 characters")
        strategy = str(data.get("strategy", "TradingView")).strip()[:128] or "TradingView"
        excluded = {"signal_type", "symbol", "price", "quantity", "strategy", "timestamp", "signal_id", "token"}
        metadata = {key: value for key, value in data.items() if key not in excluded}
        return TradingViewSignal(
            signal_type=signal_type,
            symbol=symbol,
            price=price,
            quantity=quantity,
            timestamp=timestamp or datetime.now(timezone.utc),
            strategy=strategy,
            signal_id=signal_id,
            metadata=metadata,
        )

    @staticmethod
    def _parse_timestamp(raw_value: Any) -> Optional[datetime]:
        if raw_value is None or raw_value == "":
            return None
        if isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
            seconds = float(raw_value)
            if seconds > 10_000_000_000:
                seconds /= 1000
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        if isinstance(raw_value, str):
            value = raw_value.strip().replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("timestamp must be ISO-8601 or epoch seconds") from exc
            return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
        raise ValueError("timestamp must be ISO-8601 or epoch seconds")

    def _replay_key(self, payload: str, signal: TradingViewSignal) -> str:
        if signal.signal_id:
            return f"id:{signal.signal_id}"
        return "body:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _is_replay(self, replay_key: str) -> bool:
        if not self.replay_window_seconds:
            return False
        now = time.monotonic()
        stale = [key for key, seen_at in self._seen_signals.items() if now - seen_at > self.replay_window_seconds]
        for key in stale:
            del self._seen_signals[key]
        return replay_key in self._seen_signals

    def _determine_action(self, signal: TradingViewSignal) -> SignalAction:
        if self.allowed_symbols and signal.symbol not in self.allowed_symbols:
            logging.warning("Signal symbol %s is not in the allow-list", signal.symbol)
            return SignalAction.IGNORE
        if self.max_position_size and signal.quantity and signal.quantity > self.max_position_size:
            logging.warning("Signal quantity %s exceeds the configured maximum", signal.quantity)
            return SignalAction.IGNORE
        if signal.signal_type not in self.signal_handlers:
            logging.warning("No handler registered for %s", signal.signal_type.value)
            return SignalAction.IGNORE
        return self.default_action

    def _execute_signal(self, signal: TradingViewSignal) -> Dict[str, Any]:
        handler = self.signal_handlers[signal.signal_type]
        try:
            result = handler(signal)
        except Exception:
            with self._lock:
                self.signals_failed += 1
            logging.exception("Execution handler failed for %s", signal.symbol)
            return {"status": "error", "message": "Execution handler failed"}
        if isinstance(result, dict) and result.get("status") in {"rejected", "error"}:
            with self._lock:
                self.signals_ignored += 1
            return {"status": "rejected", "message": result.get("message", "Signal was rejected"), "result": result}
        with self._lock:
            self.signals_executed += 1
            self.processed_signals.append(signal)
        return {
            "status": "success",
            "message": f"Signal executed: {signal.signal_type.value} {signal.symbol}",
            "result": result,
        }

    def _queue_signal(self, signal: TradingViewSignal) -> Dict[str, Any]:
        with self._lock:
            if len(self.signal_queue) >= self.max_queue_size:
                self.signals_failed += 1
                return {"status": "error", "message": "Signal queue is full"}
            self.signal_queue.append(signal)
            queue_size = len(self.signal_queue)
        return {"status": "queued", "message": f"Signal queued: {signal.signal_type.value} {signal.symbol}", "queue_size": queue_size}

    def _ignore_signal(self, signal: TradingViewSignal) -> Dict[str, Any]:
        with self._lock:
            self.signals_ignored += 1
        return {"status": "ignored", "message": f"Signal ignored: {signal.signal_type.value} {signal.symbol}"}

    @staticmethod
    def _require_confirmation(signal: TradingViewSignal) -> Dict[str, Any]:
        return {
            "status": "pending_confirmation",
            "message": f"Signal requires confirmation: {signal.signal_type.value} {signal.symbol}",
            "signal": {"type": signal.signal_type.value, "symbol": signal.symbol, "price": signal.price, "quantity": signal.quantity},
        }

    def process_queue(self) -> list[Dict[str, Any]]:
        results = []
        while True:
            with self._lock:
                if not self.signal_queue:
                    return results
                signal = self.signal_queue.popleft()
            results.append(self._execute_signal(signal))

    def start(self) -> None:
        """Mark the bridge as available for the legacy market-manager API."""
        self.running = True

    def stop(self) -> None:
        """Mark the bridge as stopped; the hosting HTTP server owns sockets."""
        self.running = False

    def get_next_alert(self, timeout: float = 0.0) -> Optional[TradingViewSignal]:
        """Pop one queued alert (compatibility with the original manager)."""
        del timeout
        with self._lock:
            return self.signal_queue.popleft() if self.signal_queue else None

    def get_statistics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "signals_received": self.signals_received,
                "signals_executed": self.signals_executed,
                "signals_ignored": self.signals_ignored,
                "signals_failed": self.signals_failed,
                "signals_replayed": self.signals_replayed,
                "queue_size": len(self.signal_queue),
                "success_rate": round(self.signals_executed / self.signals_received * 100, 2) if self.signals_received else 0.0,
            }

    def get_status(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "authentication_ready": self.authentication_ready,
            "auth_method": self.auth_method,
            "allowed_symbols": sorted(self.allowed_symbols),
            "default_action": self.default_action.value,
            "registered_handlers": [item.value for item in self.signal_handlers],
            "statistics": self.get_statistics(),
        }


def create_tradingview_webhook_url(config: Dict[str, Any]) -> str:
    """Generate the local webhook URL; expose it via an HTTPS tunnel for TV."""
    server_config = config.get("server", {}) or {}
    host = server_config.get("host", "127.0.0.1")
    port = server_config.get("port", 8000)
    path = server_config.get("webhook_path", "/webhook/tradingview")
    return f"http://{host}:{port}{path}"


def generate_tradingview_alert_config(config: Dict[str, Any]) -> str:
    """Return a safe alert-body template; set ``token`` to the configured secret."""
    del config
    return json.dumps(
        {
            "token": "REPLACE_WITH_YOUR_WEBHOOK_SECRET",
            "signal_id": "{{strategy.order.id}}-{{timenow}}",
            "signal_type": "{{strategy.order.action}}",
            "symbol": "{{ticker}}",
            "price": "{{close}}",
            "quantity": "{{strategy.order.contracts}}",
            "strategy": "TradingView",
            "timestamp": "{{timenow}}",
        },
        indent=2,
    )


class TradingViewConfigGenerator:
    """Compatibility helpers used by the multi-market setup script."""

    @staticmethod
    def generate_webhook_url(base_url: str, secret: str = "") -> str:
        del secret
        return base_url.rstrip("/") + "/webhook/tradingview"

    @staticmethod
    def generate_pine_script_template(symbol: str, strategy_name: str) -> str:
        return (
            "//@version=5\n"
            f"strategy(\"{strategy_name}\", overlay=true)\n"
            f"// Configure an alert for {symbol}; use the JSON body in PAPER_TRADING_GUIDE.md.\n"
            "longSignal = ta.crossover(ta.rsi(close, 14), 50)\n"
            "if longSignal\n    strategy.entry(\"long\", strategy.long)\n"
        )

    @staticmethod
    def generate_setup_instructions(host: str, port: int, secret: str) -> str:
        return (
            f"Webhook URL: {host.rstrip('/')}:{int(port)}/webhook/tradingview\n"
            "Use token authentication in the alert body. Store this value privately: "
            f"{secret}"
        )


class TradingViewAlertParser:
    """Parse the compact ``ACTION|SYMBOL|STRATEGY|PRICE|CONFIDENCE`` format."""

    @staticmethod
    def parse_pine_script_alert(alert_text: str) -> Dict[str, Any]:
        if not isinstance(alert_text, str):
            raise ValueError("Alert must be text")
        parts = [part.strip() for part in alert_text.split("|")]
        if len(parts) != 5:
            raise ValueError("Alert must have ACTION|SYMBOL|STRATEGY|PRICE|CONFIDENCE")
        action, symbol, strategy, price, confidence = parts
        parsed = {
            "action": action.upper(),
            "symbol": symbol.upper(),
            "strategy": strategy,
            "price": float(price),
            "confidence": float(confidence),
        }
        if not TradingViewAlertParser.validate_alert(parsed):
            raise ValueError("Alert fields are invalid")
        return parsed

    @staticmethod
    def validate_alert(alert: Dict[str, Any]) -> bool:
        try:
            return (
                alert["action"] in {"BUY", "SELL", "EXIT"}
                and bool(alert["symbol"])
                and bool(alert["strategy"])
                and math.isfinite(float(alert["price"])) and float(alert["price"]) > 0
                and math.isfinite(float(alert["confidence"])) and 0 <= float(alert["confidence"]) <= 1
            )
        except (KeyError, TypeError, ValueError):
            return False

    @staticmethod
    def normalize_symbol(symbol: str, market: str) -> str:
        normalized = str(symbol).strip().upper()
        if market.lower() == "forex":
            compact = normalized.replace("_", "").replace("/", "")
            return f"{compact[:3]}_{compact[3:]}" if len(compact) == 6 else normalized
        if market.lower() == "equity":
            return normalized.replace("_", " ")
        return normalized
