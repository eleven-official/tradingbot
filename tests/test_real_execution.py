"""Offline venue mocks exercise irreversible-call boundaries, not funded accounts."""

import ast
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
import threading
import time
import sqlite3
from unittest.mock import MagicMock, patch

import ccxt
from fastapi.testclient import TestClient
import pytest

from core.fusion import real_execution as real
from loki.api.server import app


@pytest.fixture
def env(tmp_path):
    return {
        "LOKI_REAL_API_KEY": "mock-key-not-a-real-credential",
        "LOKI_REAL_API_SECRET": "mock-secret-not-a-real-credential",
        "LOKI_REAL_READS_ENABLED": "1",
        "LOKI_REAL_ORDERS_ENABLED": "1",
        "LOKI_REAL_ORDER_JOURNAL": str(tmp_path / "orders.sqlite3"),
    }


@pytest.fixture
def venue():
    client = MagicMock()
    client.load_markets.return_value = {
        symbol: {
            "spot": True,
            "active": True,
            "maker": 0.002,
            "taker": 0.004,
            "limits": {"amount": {"min": 0.001}, "cost": {"min": 5}},
        }
        for symbol in real.SYMBOLS
    }
    client.amount_to_precision.side_effect = lambda symbol, value: str(
        Decimal(str(value)).quantize(Decimal(".0001"), rounding=ROUND_DOWN)
    )
    client.price_to_precision.side_effect = lambda symbol, value: str(
        Decimal(str(value)).quantize(Decimal(".01"))
    )
    client.fetch_ticker.return_value = {"bid": 99.9, "ask": 100.1, "timestamp": None}
    client.fetch_balance.return_value = {"free": {"USD": 1000, "BTC": 2, "ETH": 2, "SOL": 2}}
    client.create_order.side_effect = lambda symbol, kind, side, qty, price, params: {
        "id": "TEST-ORDER-1",
        "symbol": symbol,
        "side": side,
        "type": kind,
        "clientOrderId": params["clientOrderId"],
        "status": "open",
        "filled": 0,
    }
    with patch.object(real, "make_client", return_value=client):
        yield client


def request(**changes):
    return dict(
        symbol="BTC/USD",
        side="buy",
        quantity=0.5,
        notional=None,
        order_type="limit",
        limit_price=100.0,
        time_in_force="gtc",
        **changes,
    )


def prepared(env):
    return real.preview_order(request(), env)


def test_original_vibe_order_validator_is_used_unchanged():
    root = Path(__file__).resolve().parents[1] / "third_party/vibe_trading"

    def contract(path):
        return next(
            n
            for n in ast.parse(path.read_text(encoding="utf-8")).body
            if isinstance(n, ast.ClassDef) and n.name == "PendingOrderRequest"
        )

    assert ast.dump(contract(root / "upstream/pending_action.py")) == ast.dump(
        contract(root / "order_contracts.py")
    )


def test_actual_ccxt_kraken_mapper_preserves_client_id_limit_and_gtc_without_network():
    client = ccxt.kraken({"options": {"maxRetriesOnFailure": 0}})
    client.set_markets(
        [
            {
                "id": "XXBTZUSD",
                "symbol": "BTC/USD",
                "base": "BTC",
                "quote": "USD",
                "baseId": "XXBT",
                "quoteId": "ZUSD",
                "type": "spot",
                "spot": True,
                "precision": {"amount": 0.0001, "price": 0.01},
                "limits": {},
            }
        ]
    )
    with patch.object(
        client, "privatePostAddOrder", return_value={"result": {"txid": ["MOCK-ONLY"]}}
    ) as transport:
        result = client.create_order(
            "BTC/USD", "limit", "buy", 0.5, 100.0, {"clientOrderId": "a" * 32, "timeInForce": "GTC"}
        )
    assert result["id"] == "MOCK-ONLY"
    assert transport.call_args.args[0] == {
        "pair": "XXBTZUSD",
        "type": "buy",
        "ordertype": "limit",
        "volume": "0.5",
        "price": "100",
        "cl_ord_id": "a" * 32,
        "timeinforce": "GTC",
    }


def test_preview_never_submits_and_shows_normalized_price_costs_and_quote_uncertainty(env, venue):
    order = request()
    order.update(quantity=0.5123456, limit_price=100.004)
    result = real.preview_order(order, env)
    assert result["request"]["quantity"] == 0.5123
    assert result["request"]["limit_price"] == 100
    assert Decimal(result["preview"]["fee_buffer_usd"]) == Decimal(".5123")
    assert result["preview"]["venue_timestamp"] is None
    assert result["expires_at"] - result["created_at"] == 60
    assert result["state"] == "prepared"
    assert "mock-secret" not in str(result)
    venue.create_order.assert_not_called()


@pytest.mark.parametrize(
    "change",
    [
        {"quantity": True},
        {"quantity": float("inf")},
        {"notional": 20},
        {"symbol": "BTC/USDT"},
        {"order_type": "market", "limit_price": None},
        {"quantity": 0.00001},
        {"quantity": 2},
        {"side": "short"},
        {"limit_price": 1},
        {"leverage": 2},
    ],
)
def test_invalid_requests_cannot_reach_transport(env, venue, change):
    order = request()
    order.update(change)
    with pytest.raises(ValueError):
        real.preview_order(order, env)
    venue.create_order.assert_not_called()


@pytest.mark.parametrize(
    "change",
    [
        {"LOKI_REAL_ORDERS_ENABLED": "0"},
        {"LOKI_REAL_READS_ENABLED": "0"},
        {"LOKI_REAL_EXCHANGE": "binance"},
        {"LOKI_REAL_API_SECRET": ""},
        {"LOKI_REAL_MAX_ORDER_USD": "nan"},
        {"LOKI_REAL_DAILY_ORDER_LIMIT": "2.5"},
    ],
)
def test_host_configuration_cannot_be_bypassed_by_order_payload(env, venue, change):
    with pytest.raises(ValueError):
        real.preview_order(request(), dict(env, **change))
    venue.load_markets.assert_not_called()


@pytest.mark.parametrize(
    "ticker",
    [
        {"bid": None, "ask": 100},
        {"bid": 101, "ask": 100},
        {"bid": 90, "ask": 100},
        {"bid": 100, "ask": 100, "timestamp": (time.time() - 120) * 1000},
    ],
)
def test_bad_market_evidence_fails_closed(env, venue, ticker):
    venue.fetch_ticker.return_value = ticker
    with pytest.raises(ValueError):
        prepared(env)
    venue.create_order.assert_not_called()


def test_balance_recheck_and_sell_holdings_gate_prevent_borrowing(env, venue):
    result = prepared(env)
    venue.fetch_balance.return_value = {"free": {"USD": 0, "BTC": 0.1}}
    with pytest.raises(ValueError, match="Insufficient"):
        real.submit_order(result["id"], real.CONFIRMATION, env)
    sell = request()
    sell["side"] = "sell"
    with pytest.raises(ValueError, match="Insufficient"):
        real.preview_order(sell, env)
    venue.create_order.assert_not_called()
    assert real.list_orders(env)["orders"][0]["state"] == "prepared"


def test_confirmation_freshness_and_account_scope_are_enforced(env, venue):
    result = prepared(env)
    with pytest.raises(ValueError, match="Type PLACE"):
        real.submit_order(result["id"], "yes", env)
    with pytest.raises(ValueError, match="Unknown"):
        real.submit_order(
            result["id"], real.CONFIRMATION, dict(env, LOKI_REAL_API_KEY="different-account")
        )
    assert real.list_orders(dict(env, LOKI_REAL_API_KEY="different-account"))["orders"] == []
    with patch.object(real.time, "time", return_value=time.time() + 61):
        with pytest.raises(ValueError, match="expired"):
            real.submit_order(result["id"], real.CONFIRMATION, env)
    venue.create_order.assert_not_called()


def test_submission_is_persisted_and_duplicate_requests_do_not_repeat_transport(env, venue):
    preview = prepared(env)
    result = real.submit_order(preview["id"], real.CONFIRMATION, env)
    assert result["state"] == "submitted"
    assert result["order"]["id"] == "TEST-ORDER-1"
    assert real.submit_order(preview["id"], real.CONFIRMATION, dict(env)) == result
    venue.create_order.assert_called_once_with(
        "BTC/USD",
        "limit",
        "buy",
        0.5,
        100.0,
        {"clientOrderId": preview["id"], "timeInForce": "GTC"},
    )
    assert real.list_orders(env)["orders"][0] == result


def test_concurrent_double_click_creates_at_most_one_venue_order(env, venue):
    preview = prepared(env)
    entered, release = threading.Event(), threading.Event()
    original = venue.create_order.side_effect

    def slow_create(*args):
        entered.set()
        assert release.wait(10)
        return original(*args)

    venue.create_order.side_effect = slow_create
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(real.submit_order, preview["id"], real.CONFIRMATION, env)
        assert entered.wait(10)
        try:
            second = pool.submit(real.submit_order, preview["id"], real.CONFIRMATION, env).result(
                10
            )
            assert second["state"] == "submitting"
        finally:
            release.set()
        assert first.result(10)["state"] == "submitted"
    venue.create_order.assert_called_once()


def test_journal_claim_failure_prevents_any_venue_order(env, venue):
    preview = prepared(env)
    with patch.object(real, "_update", side_effect=sqlite3.OperationalError("disk full")):
        with pytest.raises(ConnectionError):
            real.submit_order(preview["id"], real.CONFIRMATION, env)
    venue.create_order.assert_not_called()
    assert real.list_orders(env)["orders"][0]["state"] == "prepared"


def test_timeout_is_not_retried_and_unmatched_reconciliation_does_not_prove_absence(env, venue):
    preview = prepared(env)
    venue.create_order.side_effect = ccxt.RequestTimeout("signed URL mock-secret")
    unknown = real.submit_order(preview["id"], real.CONFIRMATION, env)
    assert unknown["state"] == "submission_unknown"
    assert "mock-secret" not in str(unknown)
    assert real.submit_order(preview["id"], real.CONFIRMATION, env)["state"] == "submission_unknown"
    another = prepared(env)
    with pytest.raises(ValueError, match="Resolve"):
        real.submit_order(another["id"], real.CONFIRMATION, env)
    venue.fetch_open_orders.return_value = []
    venue.fetch_closed_orders.return_value = []
    assert real.reconcile_order(preview["id"], env)["state"] == "submission_unknown"
    venue.create_order.assert_called_once()


def test_crash_after_durable_claim_cannot_resubmit_and_recovers_by_client_id(env, venue):
    preview = prepared(env)
    venue.create_order.side_effect = KeyboardInterrupt("simulated process crash")
    with pytest.raises(KeyboardInterrupt):
        real.submit_order(preview["id"], real.CONFIRMATION, env)
    assert real.submit_order(preview["id"], real.CONFIRMATION, dict(env))["state"] == "submitting"
    venue.fetch_open_orders.return_value = [
        {
            "id": "RECOVERED",
            "clientOrderId": preview["id"],
            "status": "open",
            "symbol": "BTC/USD",
            "side": "buy",
        }
    ]
    venue.fetch_closed_orders.return_value = []
    with patch.object(real.time, "time", return_value=time.time() + 61):
        recovered = real.reconcile_order(preview["id"], env)
    assert recovered["order"]["id"] == "RECOVERED"
    assert recovered["state"] == "submitted"
    venue.create_order.assert_called_once()


def test_definite_rejection_stays_rejected_and_unknown_evidence_stays_uncertain(env, venue):
    preview = prepared(env)
    venue.create_order.side_effect = ccxt.InsufficientFunds("secret")
    assert real.submit_order(preview["id"], real.CONFIRMATION, env)["state"] == "rejected"
    venue.create_order.side_effect = lambda *args: {"id": "WRONG", "symbol": "ETH/USD"}
    second = prepared(env)
    assert real.submit_order(second["id"], real.CONFIRMATION, env)["state"] == "submission_unknown"


def test_one_open_order_and_daily_claim_limit_survive_reconciliation(env, venue):
    env["LOKI_REAL_DAILY_ORDER_LIMIT"] = "1"
    first = prepared(env)
    real.submit_order(first["id"], real.CONFIRMATION, env)
    second = prepared(env)
    with pytest.raises(ValueError, match="existing real order"):
        real.submit_order(second["id"], real.CONFIRMATION, env)
    venue.fetch_order.return_value = {"id": "TEST-ORDER-1", "status": "closed", "filled": 0.5}
    assert real.reconcile_order(first["id"], env)["state"] == "closed"
    with pytest.raises(ValueError, match="daily"):
        real.submit_order(second["id"], real.CONFIRMATION, env)
    venue.create_order.assert_called_once()


def test_cancel_remains_available_with_new_orders_disabled_and_needs_reconciliation(env, venue):
    preview = prepared(env)
    real.submit_order(preview["id"], real.CONFIRMATION, env)
    env["LOKI_REAL_ORDERS_ENABLED"] = "0"
    with pytest.raises(ValueError, match="Type CANCEL"):
        real.cancel_order(preview["id"], "yes", env)
    venue.cancel_order.return_value = {"id": "TEST-ORDER-1"}
    result = real.cancel_order(preview["id"], real.CANCEL_CONFIRMATION, env)
    assert result["state"] == "cancel_unknown"
    assert (
        real.cancel_order(preview["id"], real.CANCEL_CONFIRMATION, env)["state"] == "cancel_unknown"
    )
    venue.cancel_order.assert_called_once()
    venue.fetch_order.return_value = {"id": "TEST-ORDER-1", "status": "canceled", "filled": 0.2}
    assert real.reconcile_order(preview["id"], env)["order"]["filled"] == "0.2"
    assert real.list_orders(env)["orders"][0]["state"] == "canceled"


def test_local_routes_require_token_same_origin_and_do_not_accept_overrides(
    env, venue, monkeypatch
):
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("LOKI_FUSION_LOCAL", "1")
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 12345)) as client:
        headers = {
            "X-Loki-Local-Token": client.get("/api/fusion/capabilities").json()["local_token"]
        }
        payload = {"symbol": "BTC/USD", "side": "buy", "quantity": 0.5, "limit_price": 100.0}
        assert client.post("/api/fusion/real/orders/preview", json=payload).status_code == 403
        assert (
            client.get(
                "/api/fusion/real/orders", headers=dict(headers, Origin="https://evil.test")
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/fusion/real/orders/preview", json=dict(payload, leverage=2), headers=headers
            ).status_code
            == 422
        )
        response = client.post("/api/fusion/real/orders/preview", json=payload, headers=headers)
        assert response.status_code == 200, response.text
        assert response.headers["Cache-Control"] == "private, no-store"
        identifier = response.json()["id"]
        action = {"identifier": identifier, "confirmation": real.CONFIRMATION}
        assert (
            client.post(
                "/api/fusion/real/orders/submit", json=dict(action, quantity=1), headers=headers
            ).status_code
            == 422
        )
        assert client.post("/api/fusion/real/orders/submit", json=action).status_code == 403
        assert (
            client.post("/api/fusion/real/orders/submit", json=action, headers=headers).status_code
            == 200
        )
        assert (
            client.post(
                "/api/fusion/real/orders/cancel",
                json={"identifier": identifier, "confirmation": real.CANCEL_CONFIRMATION},
            ).status_code
            == 403
        )
        assert client.post(f"/api/fusion/real/orders/{identifier}/reconcile").status_code == 403
    venue.create_order.assert_called_once()
