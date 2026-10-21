"""Alpaca paper-account relay: key validation, account facts, explicit orders.

The browser holds the paper-trading keys (they never persist server-side) and
hands them to this relay per request. The relay talks ONLY to Alpaca's PAPER
endpoint. Reading is account facts; writing is orders the user clicked, one
place-order call per request, day-only, regular hours, hard relay caps
(100 shares a ticket, limit price ceiling) so a stray click can type neither
a fortune nor a flood. Error answers are honest: a rejection says the keys
were rejected, a refused order says Alpaca refused it, and an unreachable
Alpaca never pretends otherwise.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

import loki.api.site_access as site_access

router = APIRouter(prefix="/api/broker/alpaca", tags=["Broker relay"])

_PAPER_BASE = "https://paper-api.alpaca.markets"
_DATA_BASE = "https://data.alpaca.markets"
_RELAY_UA = "Mozilla/5.0 (compatible; LokiWorkspace/2.0; Alpaca paper relay)"
# Relay-side guards for the order rail. They are not advice and not a neutral
# opinion about sizing — they exist so the relay cannot be a fire hose.
ORDER_QTY_MAX = 100
LIMIT_PRICE_MAX = 10_000.0
BARS_MAX = 60

_ORDER_FIELDS = (
    "id", "symbol", "qty", "side", "type", "time_in_force", "status",
    "created_at", "submitted_at", "filled_qty", "filled_avg_price",
)


class AlpacaPaperKeys(BaseModel):
    """Paper-trading API keys as handed in by the browser, never stored."""

    model_config = ConfigDict(extra="forbid")

    key_id: str = Field(min_length=10, max_length=32, pattern=r"^[A-Za-z0-9]{10,32}$")
    secret_key: str = Field(min_length=32, max_length=96, pattern=r"^[A-Za-z0-9_+\-/=]{32,96}$")


class AlpacaOrder(AlpacaPaperKeys):
    """One explicit paper order, exactly as the user shaped it on screen."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=10, pattern=r"^[A-Z][A-Z0-9.]{0,9}$")
    side: Literal["buy", "sell"]
    quantity: int = Field(ge=1, le=ORDER_QTY_MAX)
    order_type: Literal["market", "limit"]
    limit_price: Optional[float] = Field(default=None, ge=0.01, le=LIMIT_PRICE_MAX)


class AlpacaBarsRequest(AlpacaPaperKeys):
    """A read-only bars request for the autopilot's published rule."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=10, pattern=r"^[A-Za-z][A-Za-z0-9.]{0,9}$")
    minutes: int = Field(default=25, ge=12, le=60)


def _require_gate(request: Request) -> None:
    """The relay serves people who already passed the workspace's door."""
    cookie = request.cookies.get(site_access.GATE_COOKIE)
    if not site_access.verify_gate_cookie_value(cookie or ""):
        raise HTTPException(403, "Open the workspace through its access door first.")


def _alpaca_error_detail(error: urllib.error.HTTPError) -> str:
    """Alpaca explains refusals in JSON; pass the human part through, clipped."""
    snippet = ""
    try:
        body = error.read()
        if body:
            parsed = json.loads(body.decode())
            if isinstance(parsed, dict):
                snippet = str(parsed.get("message") or parsed.get("detail") or "")
    except Exception:  # noqa: BLE001 - the detail must never become a crash
        snippet = ""
    if not snippet:
        snippet = str(error.reason or f"HTTP {error.code}")
    return snippet[:200]


def _paper_exchange(
    method: str, path: str, keys: AlpacaPaperKeys, body: Optional[Dict[str, Any]] = None
) -> Any:
    """One credentialed round-trip to Alpaca's PAPER endpoint, honest errors."""
    return _exchange(method, path, keys, body, _PAPER_BASE)


def _exchange(
    method: str, path: str, keys: AlpacaPaperKeys, body: Optional[Dict[str, Any]] = None,
    base: str = _PAPER_BASE,
) -> Any:
    """One credentialed round-trip to a pinned Alpaca host, honest errors."""
    data = json.dumps(body).encode() if body is not None else None
    headers: Dict[str, str] = {
        "User-Agent": _RELAY_UA,
        "APCA-API-KEY-ID": keys.key_id,
        "APCA-API-SECRET-KEY": keys.secret_key,
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(  # noqa: S310 - fixed https URLs only
        f"{base}{path}", data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as res:
            raw = res.read().decode()
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise HTTPException(401, "Alpaca rejected those keys — copy them again from the Alpaca dashboard (paper keys).") from error
        if error.code in (400, 422):
            raise HTTPException(422, f"Alpaca refused this order: {_alpaca_error_detail(error)}") from error
        if error.code == 429:
            raise HTTPException(503, "Alpaca is rate-limiting this account; wait a minute and check again.") from error
        if error.code == 404:
            raise HTTPException(502, "Alpaca's paper endpoint answered 404; its API may have moved.") from error
        raise HTTPException(502, f"Alpaca answered HTTP {error.code}; try again shortly.") from error
    except (urllib.error.URLError, OSError) as error:
        raise HTTPException(503, "Alpaca is unreachable right now; try again shortly.") from error
    try:
        payload = json.loads(raw)
    except ValueError as error:
        raise HTTPException(502, "Alpaca sent something this relay could not parse.") from error
    return payload


def _number_or_none(value: Any) -> Optional[float]:
    """Round money numbers to cents; junk becomes None, never 0 (no invention)."""
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> Optional[int]:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _account_view(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Whitelist the fields that leave the relay; nothing else passes through."""
    account_number = str(payload.get("account_number") or "")
    return {
        "paper": True,
        "status": str(payload.get("status") or "unknown"),
        "account_number": account_number[-6:] or None,
        "currency": str(payload.get("currency") or "USD"),
        "cash": _number_or_none(payload.get("cash")),
        "equity": _number_or_none(payload.get("equity")),
        "buying_power": _number_or_none(payload.get("buying_power")),
        "trading_blocked": bool(payload.get("trading_blocked", False)),
        "account_blocked": bool(payload.get("account_blocked", False)),
    }


def _order_view(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Whitelist the order fields that leave the relay; status stays honest."""
    view: Dict[str, Any] = {}
    for field in _ORDER_FIELDS:
        value = payload.get(field)
        if value is None:
            continue
        if field == "qty":
            quantity = _int_or_none(value)
            if quantity is None:
                continue
            value = quantity
        if field == "filled_avg_price":
            value = _number_or_none(value)
            if value is None:
                continue
        view[field] = str(value) if not isinstance(value, (int, float)) else value
    return view


def _dict_payload(payload: Any, what: str) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(502, f"Alpaca's answer was not the expected {what} payload.")
    return payload


@router.post("/test", include_in_schema=False)
async def alpaca_test_keys(request: Request, keys: AlpacaPaperKeys) -> Dict[str, Any]:
    _require_gate(request)
    payload = await run_in_threadpool(_paper_exchange, "GET", "/v2/account", keys)
    return {"ok": True, "account_status": str(_dict_payload(payload, "account").get("status") or "unknown"), "paper": True}


@router.post("/account", include_in_schema=False)
async def alpaca_account(request: Request, keys: AlpacaPaperKeys) -> Dict[str, Any]:
    _require_gate(request)
    payload = await run_in_threadpool(_paper_exchange, "GET", "/v2/account", keys)
    return _account_view(_dict_payload(payload, "account"))


@router.post("/order", include_in_schema=False)
async def alpaca_place_order(request: Request, order: AlpacaOrder) -> Dict[str, Any]:
    _require_gate(request)
    if order.order_type == "limit" and order.limit_price is None:
        raise HTTPException(422, "A limit order needs a limit price before it can travel.")
    if order.order_type == "market" and order.limit_price is not None:
        raise HTTPException(422, "A market order takes no limit price — send it as a limit order instead.")
    body: Dict[str, Any] = {
        "symbol": order.symbol,
        "qty": str(order.quantity),
        "side": order.side,
        "type": order.order_type,
        "time_in_force": "day",
        "extended_hours": False,
    }
    if order.order_type == "limit":
        body["limit_price"] = f"{order.limit_price:.2f}"
    payload = await run_in_threadpool(
        _paper_exchange, "POST", "/v2/orders", order, body
    )
    return {"ok": True, "paper": True, "order": _order_view(_dict_payload(payload, "order"))}


@router.post("/orders", include_in_schema=False)
async def alpaca_recent_orders(request: Request, keys: AlpacaPaperKeys) -> Dict[str, Any]:
    """The paper book's recent orders — the log the panel reads, whitelisted."""
    _require_gate(request)
    payload = await run_in_threadpool(
        _paper_exchange, "GET", "/v2/orders?status=all&limit=12&direction=desc", keys
    )
    if not isinstance(payload, list):
        raise HTTPException(502, "Alpaca's order log was not the expected list.")
    orders: List[Dict[str, Any]] = [_order_view(order) for order in payload if isinstance(order, dict)]
    orders.sort(key=lambda view: str(view.get("created_at") or ""), reverse=True)
    return {"ok": True, "paper": True, "orders": orders}


@router.post("/bars", include_in_schema=False)
async def alpaca_bars(request: Request, bars: AlpacaBarsRequest) -> Dict[str, Any]:
    """One-minute bars from Alpaca's data feed (the free IEX feed), whitelisted.

    Read-only against data.alpaca.markets; the panel's published rule eats the
    closes. No signals are computed here — the relay just fetches facts.
    """
    _require_gate(request)
    symbol = bars.symbol.upper()
    path = f"/v2/stocks/{symbol}/bars?timeframe=1Min&limit={bars.minutes}&feed=iex&sort=asc"
    payload = await run_in_threadpool(_exchange, "GET", path, bars, None, _DATA_BASE)
    if not isinstance(payload, dict) or not isinstance(payload.get("bars"), list):
        raise HTTPException(502, "Alpaca's bar feed arrived in an unexpected shape.")
    views: List[Dict[str, Any]] = []
    for bar in payload["bars"][:BARS_MAX]:
        if not isinstance(bar, dict):
            continue
        timestamp = str(bar.get("t") or "")
        close = _number_or_none(bar.get("c"))
        if not timestamp or close is None:
            continue
        views.append({
            "t": timestamp,
            "o": _number_or_none(bar.get("o")),
            "h": _number_or_none(bar.get("h")),
            "l": _number_or_none(bar.get("l")),
            "c": close,
            "v": _number_or_none(bar.get("v")),
        })
    return {"ok": True, "paper": True, "symbol": symbol, "bars": views}
