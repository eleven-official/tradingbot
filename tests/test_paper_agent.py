"""Paper-only venue fixtures test execution ownership and recovery, not trading edge."""

from datetime import datetime, timezone, timedelta
import json
import sqlite3
import time
from unittest.mock import patch

import pytest

from core.fusion import broker_link as link, paper_agent as agent, paper_models as models


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setenv("LOKI_PAPER_AI_DB", str(tmp_path / "paper.sqlite3"))
    gateway = {
        "qty": 0.0,
        "orders": {},
        "posts": [],
        "equity": 10000.0,
        "quote_age": 0.0,
        "bid": 100.0,
        "ask": 100.1,
        "market_open": True,
        "timeout": False,
        "missing": False,
        "crash": False,
        "partial": False,
    }

    def request(client, method, path, **kwargs):
        if path == "/v2/account":
            return {
                "id": "OFFLINE-PAPER-TEST-ACCOUNT",
                "currency": "USD",
                "status": "ACTIVE",
                "cash": "10000",
                "equity": str(gateway["equity"]),
                "trading_blocked": False,
                "account_blocked": False,
            }
        if path == "/v2/positions":
            return [{"symbol": "SPY", "qty": str(gateway["qty"])}] if gateway["qty"] else []
        if path == "/v2/orders" and method == "GET":
            return []
        if path == "/v2/clock":
            return {
                "is_open": gateway["market_open"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        if path.endswith("/quotes/latest"):
            return {
                "quote": {
                    "bp": gateway["bid"],
                    "ap": gateway["ask"],
                    "t": (
                        datetime.now(timezone.utc) - timedelta(seconds=gateway["quote_age"])
                    ).isoformat(),
                }
            }
        if path.startswith("/v2/assets/"):
            return {"symbol": "SPY", "tradable": True, "status": "active", "class": "us_equity"}
        if path == "/v2/orders:by_client_order_id":
            if gateway["missing"]:
                raise link.BrokerUnavailable(404)
            return gateway["orders"][kwargs["params"]["client_order_id"]].copy()
        if path == "/v2/orders" and method == "POST":
            assert client.profile.mode == "paper"
            body = kwargs["body"].copy()
            gateway["posts"].append(body)
            filled = float(body["qty"]) / 2 if gateway["partial"] else float(body["qty"])
            value = dict(
                body,
                id="OFFLINE-ORDER-" + str(len(gateway["posts"])),
                status="partially_filled" if gateway["partial"] else "filled",
                filled_qty=str(filled),
                filled_avg_price=body["limit_price"],
            )
            gateway["orders"][body["client_order_id"]] = value
            gateway["qty"] += filled if body["side"] == "buy" else -filled
            if gateway["crash"]:
                raise KeyboardInterrupt("Simulated crash after the mock venue accepted the order")
            if gateway["timeout"]:
                raise link.BrokerUnavailable()
            return value.copy()
        raise AssertionError((method, path))

    start = datetime.now(timezone.utc).date() - timedelta(days=65)
    bars = [
        {
            "timestamp": (start + timedelta(days=i)).isoformat(),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0 + i * 0.01,
            "volume": 10000.0,
        }
        for i in range(65)
    ]
    with (
        patch.object(link.AlpacaClient, "request", request),
        patch.object(link.AlpacaClient, "recent_bars", return_value=bars),
    ):
        profile = link.Profile("alpaca", "paper", "OFFLINE-TEST-KEY", "OFFLINE-TEST-SECRET")
        link.refresh_account(profile)
        model = {
            "id": "a" * 64,
            "symbol": "SPY",
            "artifact": {
                "threshold": 0.6,
                "model": {
                    "intercept": 10.0,
                    "weights": [0.0] * 5,
                    "means": [0.0] * 5,
                    "scales": [1.0] * 5,
                },
            },
        }
        models.save_model(profile.scope, model)
        yield profile, "offline-browser-session", model, gateway


def begin(setup):
    profile, identifier, model, gateway = setup
    agent.start(profile, identifier, model["id"], 1000.0)
    return profile, identifier, model, gateway


def test_ai_orders_are_paper_only_whole_cash_funded_and_repeat_ticks_do_not_buy_twice(setup):
    profile, identifier, _, gateway = begin(setup)
    first = agent.tick(profile, identifier)
    assert first["owned_qty"] == 9
    assert first["pending"] is None
    assert len(gateway["posts"]) == 1
    order = gateway["posts"][0]
    assert order["side"] == "buy" and order["qty"] == "9"
    assert float(order["qty"]) * float(order["limit_price"]) <= 1000
    assert "leverage" not in order
    assert first["journal"][0]["state"] == "filled"
    agent.tick(profile, identifier)
    assert len(gateway["posts"]) == 1
    gateway.update(bid=105.0, ask=105.1)
    sold = agent.tick(profile, identifier)
    assert sold["owned_qty"] == 0
    assert gateway["posts"][-1]["side"] == "sell"
    agent.tick(profile, identifier)
    assert len(gateway["posts"]) == 2  # No same-session reentry after a take profit.


@pytest.mark.parametrize("operation", ["start", "tick", "stop", "status"])
def test_live_account_never_reaches_the_automation_transport(setup, operation):
    profile, identifier, model, gateway = setup
    profile.mode = "live"
    with pytest.raises(ValueError, match="PAPER"):
        (
            getattr(agent, operation)(profile, identifier, model["id"])
            if operation == "start"
            else getattr(agent, operation)(profile, identifier)
        )
    assert not gateway["posts"]


def test_timeout_and_lost_response_reconcile_without_a_second_submission(setup):
    profile, identifier, _, gateway = begin(setup)
    gateway["timeout"] = True
    uncertain = agent.tick(profile, identifier)
    assert uncertain["pending"] and uncertain["owned_qty"] == 0
    assert uncertain["journal"][0]["state"] == "submission_unknown"
    recovered = agent.tick(profile, identifier)
    assert recovered["pending"] is None and recovered["owned_qty"] == 9
    assert len(gateway["posts"]) == 1


def test_unmatched_order_id_is_not_treated_as_proof_of_absence(setup):
    profile, identifier, _, gateway = begin(setup)
    gateway.update(timeout=True, missing=True)
    agent.tick(profile, identifier)
    for _ in range(3):
        unresolved = agent.tick(profile, identifier)
    assert unresolved["pending"]
    assert len(gateway["posts"]) == 1


def test_crash_after_claim_survives_a_new_tick_without_duplicate_order(setup):
    profile, identifier, _, gateway = begin(setup)
    gateway["crash"] = True
    with pytest.raises(KeyboardInterrupt):
        agent.tick(profile, identifier)
    recovered = agent.tick(profile, identifier)
    assert recovered["owned_qty"] == 9
    assert len(gateway["posts"]) == 1


def test_partial_fills_update_only_confirmed_units_then_reconcile_the_increment(setup):
    profile, identifier, _, gateway = begin(setup)
    gateway["partial"] = True
    first = agent.tick(profile, identifier)
    assert first["owned_qty"] == 4.5 and first["pending"]
    order = next(iter(gateway["orders"].values()))
    order.update(status="filled", filled_qty="9")
    gateway["qty"] = 9
    result = agent.tick(profile, identifier)
    assert result["owned_qty"] == 9 and result["pending"] is None
    assert len(gateway["posts"]) == 1


def test_pausing_does_not_create_exits_or_touch_existing_paper_holdings(setup):
    profile, identifier, _, gateway = begin(setup)
    agent.tick(profile, identifier)
    paused = agent.stop(profile, identifier)
    assert paused["running"] is False and gateway["qty"] == 9
    with pytest.raises(ValueError, match="paused"):
        agent.tick(profile, identifier)
    assert len(gateway["posts"]) == 1


def test_manual_positions_are_not_taken_over_or_sold(setup):
    profile, identifier, model, gateway = setup
    gateway["qty"] = 1
    with pytest.raises(ValueError, match="manual"):
        agent.start(profile, identifier, model["id"])
    gateway["qty"] = 0
    agent.start(profile, identifier, model["id"])
    agent.tick(profile, identifier)
    gateway["qty"] += 1
    gateway.update(bid=90.0, ask=90.1)
    state = agent.tick(profile, identifier)
    assert state["running"] is False and len(gateway["posts"]) == 1


@pytest.mark.parametrize(
    "change", [{"quote_age": 300.0}, {"equity": 9600.0}, {"bid": 102.0, "ask": 100.0}]
)
def test_bad_quotes_and_account_drawdown_pause_before_any_order(setup, change):
    profile, identifier, _, gateway = begin(setup)
    gateway.update(change)
    assert agent.tick(profile, identifier)["running"] is False
    assert not gateway["posts"]


def test_no_validation_edge_and_closed_market_wait_without_fabricated_orders(setup):
    profile, identifier, model, gateway = setup
    model["artifact"]["threshold"] = None
    with models.database() as db:
        db.execute("UPDATE models SET report=? WHERE owner=?", (json.dumps(model), profile.scope))
    agent.start(profile, identifier, model["id"])
    assert agent.tick(profile, identifier)["running"] is True
    assert not gateway["posts"]
    gateway["market_open"] = False
    assert "Market closed" in agent.tick(profile, identifier)["message"]
    assert not gateway["posts"]


def test_daily_claim_cap_and_expired_heartbeat_block_new_paper_orders(setup):
    profile, identifier, _, gateway = begin(setup)
    with models.database() as db:
        for index in range(5):
            db.execute(
                "INSERT INTO paper_actions VALUES(?,?,?,?,?,?)",
                (str(index), profile.scope, time.time(), "rejected", "{}", None),
            )
    assert agent.tick(profile, identifier)["running"] is False
    assert not gateway["posts"]
    with patch.object(agent.time, "time", return_value=time.time() + 100):
        with pytest.raises(ValueError, match="paused"):
            agent.tick(profile, identifier)


def test_journal_write_failure_prevents_transport_and_does_not_invent_pending_order(setup):
    profile, identifier, _, gateway = begin(setup)
    original = agent._save
    failed = False

    def fail_once(db, profile, owner, state):
        nonlocal failed
        if state["pending"] and not failed:
            failed = True
            raise sqlite3.OperationalError("simulated full journal")
        return original(db, profile, owner, state)

    with patch.object(agent, "_save", fail_once):
        result = agent.tick(profile, identifier)
    assert result["pending"] is None and result["running"] is False
    assert not result["journal"] and not gateway["posts"]


def test_verified_reconnection_can_resume_paused_owned_units_with_the_same_model(setup):
    profile, identifier, model, gateway = begin(setup)
    agent.tick(profile, identifier)
    agent.stop(profile, identifier)
    resumed = agent.start(profile, "replacement-browser-session", model["id"])
    assert resumed["owned_qty"] == 9 and resumed["running"] is True
    agent.tick(profile, "replacement-browser-session")
    assert len(gateway["posts"]) == 1
