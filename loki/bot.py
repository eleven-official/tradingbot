"""
LokiBot — the paper-only TradingView webhook execution bot.

This is the glue that turns an inbound TradingView alert into a *paper* order
through the safe execution path. It intentionally reuses the existing,
already-tested building blocks rather than reimplementing them:

* :class:`core.tradingview_bridge.TradingViewBridge` — untrusted-input
  validation, authentication, and duplicate-signal rejection.
* :class:`core.paper_broker.build_paper_broker` — paper-only execution
  (live execution is deliberately absent from this codebase).
* :class:`core.state_manager.StateManager` — P&L tracking and risk
  circuit-breakers.

The resulting bot exposes a Flask app whose ``POST /webhook/tradingview``
endpoint is safe to point a TradingView alert at.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from flask import Flask, jsonify, request

from core.exceptions import OrderExecutionError
from core.paper_broker import build_paper_broker
from core.tradingview_bridge import SignalType, TradingViewBridge, TradingViewSignal

logger = logging.getLogger(__name__)


class LokiBot:
    """Paper-only execution bot driven by TradingView webhook alerts."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config if config is not None else self.load_config()

        # Resolve StateManager lazily so tests can patch ``loki.StateManager``.
        from loki import StateManager

        self.state_manager = StateManager(self.config)
        self.execution_broker = build_paper_broker(self.config)

        self.bridge = TradingViewBridge(self.config)
        self.bridge.register_handler(SignalType.BUY, self._handle_buy)
        self.bridge.register_handler(SignalType.SELL, self._handle_sell)
        self.bridge.register_handler(SignalType.EXIT, self._handle_sell)

        self.app = self._build_app()

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        """Return the default, conservative paper-trading configuration."""
        return {
            "tradingview": {
                "enabled": True,
                "auth_method": "token",
                "require_signature": False,
                "webhook_secret": "",
                "allowed_symbols": [],
                "default_action": "execute",
                "require_quantity": True,
                "replay_window_seconds": 300,
                "max_signal_age_seconds": 60,
                "max_queue_size": 100,
            },
            "paper_broker": {
                "initial_cash": 100_000.0,
                "currency": "AUD",
                "fee_bps": 10,
                "slippage_bps": 3,
                "state_file": "loki_paper_account.json",
            },
            "execution": {
                "provider": "local_paper",
                "max_order_notional_percent": 20,
                "max_gross_exposure_percent": 30,
                "daily_loss_limit_percent": 4,
                "weekly_loss_limit_percent": 10,
                "max_consecutive_losses": 3,
            },
        }

    @classmethod
    def load_config(cls, path: Optional[str] = None) -> Dict[str, Any]:
        """Load configuration from a YAML file (or env), merged over defaults."""
        config = cls.get_default_config()
        candidate = path or os.environ.get("LOKI_CONFIG", "config.yaml")
        try:
            from pathlib import Path

            config_path = Path(candidate)
            if config_path.exists():
                import yaml

                loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
                for key, value in loaded.items():
                    if isinstance(value, dict) and isinstance(config.get(key), dict):
                        config[key] = {**config[key], **value}
                    else:
                        config[key] = value
        except Exception as exc:  # noqa: BLE001 — config is best-effort
            logger.warning("Could not load config from %s: %s", candidate, exc)
        return config

    # ------------------------------------------------------------------
    # Signal handlers (invoked by the bridge after validation/auth/dedup)
    # ------------------------------------------------------------------
    def _handle_buy(self, signal: TradingViewSignal) -> Dict[str, Any]:
        self._check_risk(signal)
        fill = self.execution_broker.submit_order(
            "buy",
            signal.symbol,
            signal.quantity,
            signal.price,
            client_order_id=signal.signal_id,
        )
        self.state_manager.record_entry(
            {
                "symbol": signal.symbol,
                "quantity": signal.quantity,
                "price": signal.price,
                "signal_id": signal.signal_id,
            }
        )
        return fill

    def _handle_sell(self, signal: TradingViewSignal) -> Dict[str, Any]:
        self._check_risk(signal)
        fill = self.execution_broker.submit_order(
            "sell",
            signal.symbol,
            signal.quantity,
            signal.price,
            client_order_id=signal.signal_id,
        )
        self.state_manager.record_trade(
            {
                "symbol": signal.symbol,
                "type": "sell",
                "net": fill.get("realized_pnl", 0.0),
                "strategy": signal.strategy,
            }
        )
        return fill

    def _check_risk(self, signal: TradingViewSignal) -> None:
        """Enforce loss-limit circuit breakers and notional/exposure caps."""
        account = self.execution_broker.get_account()
        equity = float(account.get("equity", 0.0))
        exec_cfg = self.config.get("execution", {}) or {}

        if self.state_manager.check_daily_loss_limit(
            exec_cfg.get("daily_loss_limit_percent", 0), equity
        ):
            raise OrderExecutionError("Daily loss limit reached; order blocked")
        if self.state_manager.check_weekly_loss_limit(
            exec_cfg.get("weekly_loss_limit_percent", 0), equity
        ):
            raise OrderExecutionError("Weekly loss limit reached; order blocked")
        if self.state_manager.check_consecutive_loss_limit(
            exec_cfg.get("max_consecutive_losses", 3)
        ):
            raise OrderExecutionError("Consecutive-loss limit reached; order blocked")

        notional = float(signal.price) * float(signal.quantity or 0.0)
        max_order_notional = equity * (float(exec_cfg.get("max_order_notional_percent", 20)) / 100.0)
        if max_order_notional > 0 and notional > max_order_notional:
            raise OrderExecutionError("Order notional exceeds the configured cap")

        current_market_value = sum(
            float(position.get("market_value", 0.0)) for position in self.execution_broker.get_positions()
        )
        gross_exposure = current_market_value + notional
        max_exposure = equity * (float(exec_cfg.get("max_gross_exposure_percent", 30)) / 100.0)
        if max_exposure > 0 and gross_exposure > max_exposure:
            raise OrderExecutionError("Gross exposure would exceed the configured cap")

    # ------------------------------------------------------------------
    # HTTP layer
    # ------------------------------------------------------------------
    def _build_app(self) -> Flask:
        app = Flask(__name__)
        app.config["JSON_SORT_KEYS"] = False

        @app.post("/webhook/tradingview")
        def tradingview_webhook():
            """Receive a TradingView alert, validate it, and execute paper-only."""
            payload = request.get_data(as_text=True)
            signature = request.headers.get("X-Signature")
            result = self.bridge.receive_webhook(payload, signature=signature)

            if result.get("status") == "error":
                return jsonify(result), 422

            body: Dict[str, Any] = {"message": result.get("message")}
            if "result" in result:
                body["result"] = result["result"]
            if "queue_size" in result:
                body["queue_size"] = result["queue_size"]
            return jsonify(body), 200

        @app.get("/health")
        def health():
            return jsonify(
                {
                    "status": "ok",
                    "provider": self.execution_broker.provider_name,
                    "broker_ready": bool(getattr(self.execution_broker, "is_ready", True)),
                }
            )

        return app
