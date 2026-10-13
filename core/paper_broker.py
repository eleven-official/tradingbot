"""Paper-execution adapters used by Loki's safe execution path.

The local broker is deliberately small but complete: it maintains cash,
positions, conservative simulated fills and realised P&L atomically.  The
Alpaca adapter is hard-wired to Alpaca's *paper* endpoint, so configuration
cannot accidentally turn a paper account into a live account.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import logging
import math
import os
import re
import threading
import uuid
from typing import Any, Dict, Optional

import requests

from core.exceptions import OrderExecutionError
from infra import atomic_write_json, read_json, state_path


class PaperTradingBroker:
    """Persistent local paper account with immediate, conservative fills."""

    provider_name = "local_paper"
    is_local_simulation = True

    def __init__(self, config: Dict[str, Any]):
        paper_config = config.get("paper_broker", {}) or {}
        self.currency = str(paper_config.get("currency", "AUD")).upper()
        self.initial_cash = self._positive(paper_config.get("initial_cash", 100_000), "initial_cash")
        self.fee_bps = self._non_negative(paper_config.get("fee_bps", 10), "fee_bps")
        self.slippage_bps = self._non_negative(paper_config.get("slippage_bps", 3), "slippage_bps")
        self.allow_short = bool(paper_config.get("allow_short", False))
        file_name = str(paper_config.get("state_file", "loki_paper_account.json"))
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", file_name):
            raise ValueError("paper_broker.state_file contains unsupported characters")
        self._path = state_path(file_name)
        self._lock = threading.RLock()
        self._state = self._load_state()

    @staticmethod
    def _positive(value: Any, name: str) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"paper_broker.{name} must be numeric") from exc
        if not math.isfinite(parsed) or parsed <= 0:
            raise ValueError(f"paper_broker.{name} must be positive")
        return parsed

    @staticmethod
    def _non_negative(value: Any, name: str) -> float:
        parsed = PaperTradingBroker._positive(float(value) + 1, name) - 1
        if parsed < 0:
            raise ValueError(f"paper_broker.{name} must be non-negative")
        return parsed

    def _new_state(self) -> Dict[str, Any]:
        return {
            "version": 1,
            "currency": self.currency,
            "initial_cash": self.initial_cash,
            "cash": self.initial_cash,
            "realized_pnl": 0.0,
            "positions": {},
            "fills": [],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _load_state(self) -> Dict[str, Any]:
        state = read_json(self._path, default=None)
        if not isinstance(state, dict):
            return self._new_state()
        required = {"cash", "positions", "fills", "realized_pnl"}
        if not required.issubset(state) or not isinstance(state["positions"], dict) or not isinstance(state["fills"], list):
            logging.warning("Paper-account state was invalid; creating a fresh paper account")
            return self._new_state()
        try:
            state["cash"] = float(state["cash"])
            state["realized_pnl"] = float(state["realized_pnl"])
            if not math.isfinite(state["cash"]) or not math.isfinite(state["realized_pnl"]):
                raise ValueError
        except (TypeError, ValueError):
            logging.warning("Paper-account balances were invalid; creating a fresh paper account")
            return self._new_state()
        state.setdefault("currency", self.currency)
        state.setdefault("initial_cash", self.initial_cash)
        state.setdefault("updated_at", datetime.now(timezone.utc).isoformat())
        return state

    def _save(self) -> None:
        self._state["updated_at"] = datetime.now(timezone.utc).isoformat()
        atomic_write_json(self._path, self._state)

    @staticmethod
    def _validate_order(symbol: str, side: str, quantity: Any, price: Any) -> tuple[str, str, float, float]:
        symbol = str(symbol).strip().upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9_./:-]{0,63}", symbol):
            raise OrderExecutionError("Invalid symbol")
        side = str(side).lower()
        if side not in {"buy", "sell"}:
            raise OrderExecutionError("Order side must be buy or sell")
        try:
            quantity = float(quantity)
            price = float(price)
        except (TypeError, ValueError) as exc:
            raise OrderExecutionError("Order price and quantity must be numeric") from exc
        if not all(math.isfinite(value) and value > 0 for value in (quantity, price)):
            raise OrderExecutionError("Order price and quantity must be positive finite values")
        return symbol, side, quantity, price

    def mark_price(self, symbol: str, price: Any) -> None:
        """Update a local mark without changing cash or realised P&L."""
        symbol, _, _, price = self._validate_order(symbol, "buy", 1, price)
        with self._lock:
            position = self._state["positions"].get(symbol)
            if position:
                position["last_price"] = price
                self._save()

    def submit_order(
        self,
        side: str,
        symbol: str,
        quantity: Any,
        reference_price: Any,
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fill a local paper order and persist the resulting portfolio state."""
        symbol, side, quantity, reference_price = self._validate_order(symbol, side, quantity, reference_price)
        slippage_fraction = self.slippage_bps / 10_000
        fill_price = reference_price * (1 + slippage_fraction if side == "buy" else 1 - slippage_fraction)
        gross_value = fill_price * quantity
        fee = gross_value * self.fee_bps / 10_000
        fill_id = client_order_id or f"paper-{uuid.uuid4().hex}"

        with self._lock:
            # A duplicate client id is idempotent rather than creating a second fill.
            existing = next((fill for fill in self._state["fills"] if fill.get("client_order_id") == fill_id), None)
            if existing:
                return deepcopy(existing)

            positions = self._state["positions"]
            position = positions.get(symbol)
            realised_pnl = 0.0
            if side == "buy":
                total_cost = gross_value + fee
                if self._state["cash"] + 1e-9 < total_cost:
                    raise OrderExecutionError("Insufficient paper cash for this order")
                if position and position["quantity"] < 0:
                    raise OrderExecutionError("Short-covering is not supported by this paper account")
                old_quantity = float(position["quantity"]) if position else 0.0
                old_cost = float(position["average_cost"]) * old_quantity if position else 0.0
                new_quantity = old_quantity + quantity
                positions[symbol] = {
                    "quantity": new_quantity,
                    "average_cost": (old_cost + total_cost) / new_quantity,
                    "last_price": fill_price,
                    "opened_at": position.get("opened_at") if position else datetime.now(timezone.utc).isoformat(),
                }
                self._state["cash"] -= total_cost
            else:
                if not position or float(position["quantity"]) + 1e-9 < quantity:
                    if not self.allow_short:
                        raise OrderExecutionError("Cannot sell more than the currently held paper position")
                    raise OrderExecutionError("Short paper trading is not implemented")
                proceeds = gross_value - fee
                average_cost = float(position["average_cost"])
                realised_pnl = proceeds - average_cost * quantity
                remaining = float(position["quantity"]) - quantity
                self._state["cash"] += proceeds
                self._state["realized_pnl"] += realised_pnl
                if remaining <= 1e-12:
                    del positions[symbol]
                else:
                    position["quantity"] = remaining
                    position["last_price"] = fill_price

            fill = {
                "status": "filled",
                "provider": self.provider_name,
                "order_id": fill_id,
                "client_order_id": fill_id,
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "reference_price": reference_price,
                "fill_price": fill_price,
                "gross_value": gross_value,
                "fee": fee,
                "realized_pnl": realised_pnl,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self._state["fills"].append(fill)
            self._state["fills"] = self._state["fills"][-1_000:]
            self._save()
            return deepcopy(fill)

    def get_positions(self) -> list[Dict[str, Any]]:
        with self._lock:
            return [
                {"symbol": symbol, **deepcopy(position), "market_value": float(position["quantity"]) * float(position["last_price"])}
                for symbol, position in self._state["positions"].items()
            ]

    def get_open_position_count(self) -> int:
        with self._lock:
            return len(self._state["positions"])

    def get_account(self) -> Dict[str, Any]:
        with self._lock:
            positions = self.get_positions()
            market_value = sum(position["market_value"] for position in positions)
            cash = float(self._state["cash"])
            return {
                "provider": self.provider_name,
                "currency": self.currency,
                "cash": cash,
                "buying_power": cash,
                "market_value": market_value,
                "equity": cash + market_value,
                "initial_cash": float(self._state["initial_cash"]),
                "realized_pnl": float(self._state["realized_pnl"]),
                "positions": positions,
            }

    @property
    def is_ready(self) -> bool:
        return True


class AlpacaPaperBroker:
    """Minimal REST client for Alpaca paper trading—never Alpaca live trading."""

    provider_name = "alpaca_paper"
    is_local_simulation = False
    _BASE_URL = "https://paper-api.alpaca.markets"

    def __init__(self, config: Dict[str, Any]):
        execution = config.get("execution", {}) or {}
        alpaca = config.get("alpaca", {}) or {}
        self.api_key = str(alpaca.get("api_key") or os.environ.get("ALPACA_PAPER_API_KEY", "")).strip()
        self.api_secret = str(alpaca.get("api_secret") or os.environ.get("ALPACA_PAPER_API_SECRET", "")).strip()
        timeout = execution.get("request_timeout_seconds", 15)
        try:
            self.timeout = float(timeout)
        except (TypeError, ValueError) as exc:
            raise ValueError("execution.request_timeout_seconds must be numeric") from exc
        if not 1 <= self.timeout <= 60:
            raise ValueError("execution.request_timeout_seconds must be between 1 and 60")
        self.symbol_aliases = {str(key).upper(): str(value).upper() for key, value in (alpaca.get("symbol_aliases", {}) or {}).items()}

    @property
    def is_ready(self) -> bool:
        return bool(self.api_key and self.api_secret)

    def _headers(self) -> Dict[str, str]:
        if not self.is_ready:
            raise OrderExecutionError("Alpaca paper credentials are missing")
        return {"APCA-API-KEY-ID": self.api_key, "APCA-API-SECRET-KEY": self.api_secret, "Content-Type": "application/json"}

    def _request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
        try:
            response = requests.request(
                method,
                f"{self._BASE_URL}{path}",
                headers=self._headers(),
                json=payload,
                timeout=self.timeout,
            )
            if not response.ok:
                message = response.text[:500]
                logging.warning("Alpaca paper API returned %s: %s", response.status_code, message)
                raise OrderExecutionError(f"Alpaca paper API rejected the request ({response.status_code})")
            return response.json() if response.content else {}
        except requests.RequestException as exc:
            raise OrderExecutionError("Could not reach the Alpaca paper API") from exc

    def _symbol(self, symbol: str) -> str:
        normalized = str(symbol).strip().upper()
        if not normalized:
            raise OrderExecutionError("Invalid symbol")
        return self.symbol_aliases.get(normalized, normalized)

    def submit_order(
        self,
        side: str,
        symbol: str,
        quantity: Any,
        reference_price: Any,
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        del reference_price  # The paper broker fills at its own current simulated market price.
        try:
            quantity = float(quantity)
        except (TypeError, ValueError) as exc:
            raise OrderExecutionError("Order quantity must be numeric") from exc
        if not math.isfinite(quantity) or quantity <= 0:
            raise OrderExecutionError("Order quantity must be a positive finite value")
        side = str(side).lower()
        if side not in {"buy", "sell"}:
            raise OrderExecutionError("Order side must be buy or sell")
        alpaca_symbol = self._symbol(symbol)
        order = {
            "symbol": alpaca_symbol,
            "qty": str(quantity),
            "side": side,
            "type": "market",
            "time_in_force": "gtc" if "/" in alpaca_symbol else "day",
        }
        if client_order_id:
            order["client_order_id"] = re.sub(r"[^A-Za-z0-9_-]", "-", client_order_id)[:48]
        response = self._request("POST", "/v2/orders", order)
        return {
            "status": response.get("status", "accepted"),
            "provider": self.provider_name,
            "order_id": response.get("id"),
            "client_order_id": response.get("client_order_id"),
            "symbol": response.get("symbol", alpaca_symbol),
            "side": response.get("side", side),
            "quantity": float(response.get("qty", quantity)),
            "fill_price": float(response["filled_avg_price"]) if response.get("filled_avg_price") else None,
            "realized_pnl": None,
            "timestamp": response.get("submitted_at"),
        }

    def get_account(self) -> Dict[str, Any]:
        account = self._request("GET", "/v2/account")
        return {
            "provider": self.provider_name,
            "currency": account.get("currency", "USD"),
            "cash": float(account.get("cash", 0)),
            "buying_power": float(account.get("buying_power", 0)),
            "equity": float(account.get("equity", 0)),
            "initial_cash": float(account.get("last_equity", account.get("equity", 0))),
            "realized_pnl": None,
            "positions": self.get_positions(),
        }

    def get_positions(self) -> list[Dict[str, Any]]:
        positions = self._request("GET", "/v2/positions")
        return [
            {
                "symbol": position.get("symbol"),
                "quantity": float(position.get("qty", 0)),
                "average_cost": float(position.get("avg_entry_price", 0)),
                "last_price": float(position.get("current_price", 0)),
                "market_value": float(position.get("market_value", 0)),
                "unrealized_pnl": float(position.get("unrealized_pl", 0)),
            }
            for position in positions
        ]

    def get_open_position_count(self) -> int:
        return len(self.get_positions())

    def mark_price(self, symbol: str, price: Any) -> None:
        del symbol, price


def build_paper_broker(config: Dict[str, Any]):
    """Build only a paper execution adapter; live execution is intentionally absent."""
    provider = str((config.get("execution", {}) or {}).get("provider", "local_paper")).lower()
    if provider in {"local", "local_paper", "simulation"}:
        return PaperTradingBroker(config)
    if provider in {"alpaca", "alpaca_paper"}:
        return AlpacaPaperBroker(config)
    raise ValueError("execution.provider must be local_paper or alpaca_paper; live execution is not supported")
