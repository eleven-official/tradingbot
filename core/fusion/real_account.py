"""Real exchange readiness and read-only balances. A mode switch never orders.

Use the actual CCXT venue client rather than the legacy placeholder Binance
adapter. Credentials stay in the host environment. Manual orders have a separate
host opt-in and confirmation workflow in real_execution; readiness is not authentication.
"""

from __future__ import annotations
import importlib.util
import math
import os

VENUES = {"kraken", "coinbase", "binance"}


def status(environ=None):
    env = os.environ if environ is None else environ
    venue = env.get("LOKI_REAL_EXCHANGE", "kraken")
    if venue not in VENUES:
        raise ValueError("Real exchange must be kraken, coinbase or binance")
    configured = bool(env.get("LOKI_REAL_API_KEY") and env.get("LOKI_REAL_API_SECRET"))
    installed = importlib.util.find_spec("ccxt") is not None
    enabled = env.get("LOKI_REAL_READS_ENABLED") == "1"
    reasons = []
    if not configured:
        reasons.append("Real exchange credentials are not configured on this host.")
    if not enabled:
        reasons.append("The host has not enabled real-account reads.")
    if not installed:
        reasons.append("The CCXT exchange dependency is not installed.")
    orders_enabled = env.get("LOKI_REAL_ORDERS_ENABLED") == "1"
    manual_orders = not reasons and orders_enabled and venue == "kraken"
    return {
        "mode": "real_account",
        "exchange": venue,
        "configured": configured,
        "reads_enabled": enabled,
        "dependency_ready": installed,
        "ready_to_connect": not reasons,
        "authenticated": False,
        "order_submission_available": manual_orders,
        "orders_enabled_by_host": orders_enabled,
        "live_trading_enabled": False,
        "status": "ready_to_connect" if not reasons else "not_connected",
        "reasons": reasons,
        "message": "Selecting Real opens account inspection. It does not arm trading or authenticate an exchange.",
        "execution_status": "Manual Kraken spot limit orders require host opt-in, a fresh preview and typed confirmation. Automatic bot execution is disabled; synthetic and paper accounts stay separate.",
    }


def make_client(env):
    import ccxt

    return getattr(ccxt, env.get("LOKI_REAL_EXCHANGE", "kraken"))(
        {
            "apiKey": env["LOKI_REAL_API_KEY"],
            "secret": env["LOKI_REAL_API_SECRET"],
            "password": env.get("LOKI_REAL_API_PASSPHRASE"),
            "enableRateLimit": True,
            "timeout": 10000,
            "maxRetriesOnFailure": 0,
            "options": {"defaultType": "spot", "maxRetriesOnFailure": 0},
        }
    )


def account_snapshot(environ=None):
    env = os.environ if environ is None else environ
    state = status(env)
    if not state["ready_to_connect"]:
        raise ValueError(" ".join(state["reasons"]))
    client = make_client(env)
    try:
        balance = client.fetch_balance()
        if not isinstance(balance, dict) or not isinstance(balance.get("total"), dict):
            raise ValueError("Exchange did not return structured asset balances")
        assets = []

        def finite(value):
            return (
                float(value)
                if isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
                else None
            )

        for currency, value in balance["total"].items():
            total = finite(value)
            if (
                not isinstance(currency, str)
                or not 1 <= len(currency) <= 20
                or total is None
                or total == 0
            ):
                continue
            assets.append(
                {
                    "currency": currency,
                    "total": total,
                    "free": finite((balance.get("free") or {}).get(currency)),
                    "used": finite((balance.get("used") or {}).get(currency)),
                }
            )
        return {
            **state,
            "authenticated": True,
            "status": "connected_read_only",
            "assets": assets[:100],
            "valuation": None,
            "orders_submitted": 0,
            "message": "Real spot balances read from the configured exchange. No common-currency valuation or trading permission is inferred.",
        }
    except Exception as exc:
        raise ConnectionError(
            "The real exchange account could not be read. Check host configuration and read-only key permissions locally."
        ) from exc
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass
