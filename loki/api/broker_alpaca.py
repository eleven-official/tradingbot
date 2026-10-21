"""Alpaca paper-account relay: key validation + read-only account facts.

The browser holds the paper-trading keys (they never persist server-side) and
hands them to this relay per request. The relay talks ONLY to Alpaca's PAPER
endpoint, only with GET, only for account facts — no orders, no transfers, no
storage. Error answers are honest: a rejection says the keys were rejected,
and an unreachable Alpaca never pretends otherwise.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

import loki.api.site_access as site_access

router = APIRouter(prefix="/api/broker/alpaca", tags=["Broker relay"])

_PAPER_BASE = "https://paper-api.alpaca.markets"
_RELAY_UA = "Mozilla/5.0 (compatible; LokiWorkspace/2.0; read-only Alpaca paper relay)"


class AlpacaPaperKeys(BaseModel):
    """Paper-trading API keys as handed in by the browser, never stored."""

    model_config = ConfigDict(extra="forbid")

    key_id: str = Field(min_length=10, max_length=32, pattern=r"^[A-Za-z0-9]{10,32}$")
    secret_key: str = Field(min_length=32, max_length=96, pattern=r"^[A-Za-z0-9_+\-/=]{32,96}$")


def _require_gate(request: Request) -> None:
    """The relay serves people who already passed the workspace's door."""
    cookie = request.cookies.get(site_access.GATE_COOKIE)
    if not site_access.verify_gate_cookie_value(cookie or ""):
        raise HTTPException(403, "Open the workspace through its access door first.")


def _paper_get(path: str, keys: AlpacaPaperKeys) -> Dict[str, Any]:
    request = urllib.request.Request(
        f"{_PAPER_BASE}{path}",
        headers={
            "User-Agent": _RELAY_UA,
            "APCA-API-KEY-ID": keys.key_id,
            "APCA-API-SECRET-KEY": keys.secret_key,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as res:  # noqa: S310 - fixed https URL
            raw = res.read().decode()
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise HTTPException(401, "Alpaca rejected those keys — copy them again from the Alpaca dashboard (paper keys).") from error
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
    if not isinstance(payload, dict):
        raise HTTPException(502, "Alpaca's answer was not the expected account payload.")
    return payload


def _number_or_none(value: Any):
    """Round money numbers to cents; junk becomes None, never 0 (no invention)."""
    try:
        return round(float(value), 2)
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


@router.post("/test", include_in_schema=False)
async def alpaca_test_keys(request: Request, keys: AlpacaPaperKeys) -> Dict[str, Any]:
    _require_gate(request)
    payload = await run_in_threadpool(_paper_get, "/v2/account", keys)
    return {"ok": True, "account_status": str(payload.get("status") or "unknown"), "paper": True}


@router.post("/account", include_in_schema=False)
async def alpaca_account(request: Request, keys: AlpacaPaperKeys) -> Dict[str, Any]:
    _require_gate(request)
    payload = await run_in_threadpool(_paper_get, "/v2/account", keys)
    return _account_view(payload)
