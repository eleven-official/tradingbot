"""Practice exchange accounting and causal order behavior; synthetic inputs only."""

from copy import deepcopy

from fastapi.testclient import TestClient
import pytest

from core.fusion.simulated_market import (
    act,
    market_path,
    new_session,
    snapshot,
    _advance_one,
    HALF_SPREAD,
)
from core.fusion.portfolio import new_portfolio, validate_portfolio
from loki.api.server import app


def order(state, **kwargs):
    return act(
        {
            "action": "order",
            "state": state,
            "symbol": "BTC/USD",
            "side": "buy",
            "quantity": 0.01,
            **kwargs,
        }
    )


def next_bar(history, **values):
    for rows in history.values():
        rows.append(dict(rows[-1]))
    history["BTC/USD"][-1].update(values)
    return history


def test_seeded_future_generation_preserves_the_entire_past_and_changes_with_seed():
    before, after = market_path(42, "balanced", 0), market_path(42, "balanced", 30)
    for symbol in before:
        assert after[symbol][:120] == before[symbol]
    assert before != market_path(43, "balanced", 0)
    assert before != market_path(42, "downtrend", 0)


def test_flat_quote_round_trip_loses_spread_slippage_and_fees_without_mutating_original():
    initial = new_session()
    original = deepcopy(initial)
    bought = order(initial)
    assert initial == original
    q = bought["quotes"][0]
    fill = bought["state"]["account"]["trades"][-1]
    assert fill["price"] == pytest.approx(q["ask"] * 1.0005)
    assert bought["state"]["account"]["positions"]["BTC/USD"]["mark_price"] == q["price"]
    sold = order(bought["state"], side="sell")
    assert sold["metrics"]["closed_trades"] == 1
    assert sold["metrics"]["total_pnl"] < 0
    assert sold["metrics"]["winning_trades"] == 0
    validate_portfolio(sold["state"]["account"])
    assert sold["performance_evidence_eligible"] is False
    assert sold["live_trading_enabled"] is False
    assert initial["account"] == new_portfolio()


def test_insufficient_cash_or_unheld_sell_never_creates_a_fill():
    state = new_session()
    with pytest.raises(ValueError, match="cash|liquidity"):
        order(state, quantity=1)
    with pytest.raises(ValueError, match="held"):
        order(state, side="sell")
    assert state["account"]["trades"] == []


def test_limit_waits_for_next_bar_and_never_exceeds_its_buy_price():
    state = new_session()
    q = snapshot(state)["quotes"][0]
    limit = q["ask"] * 1.01
    pending = order(state, order_type="limit", limit_price=limit)
    assert pending["state"]["account"]["trades"] == []
    later = act({"action": "advance", "state": pending["state"]})
    fill = later["state"]["account"]["trades"][-1]
    assert fill["price"] <= limit + 1e-8
    assert fill["simulation_step"] == 1
    assert later["state"]["orders"][0]["status"] == "filled"


def test_cancelled_or_expired_limit_cannot_fill():
    state = order(new_session(), order_type="limit", limit_price=1e6)["state"]
    cancelled = act({"action": "cancel", "state": state, "order_id": state["orders"][0]["id"]})
    assert (
        act({"action": "advance", "state": cancelled["state"]})["state"]["account"]["trades"] == []
    )
    state["orders"][0]["expires_step"] = 1
    state["orders"][0]["limit_price"] = 1
    result = act({"action": "advance", "state": state, "steps": 2})
    assert result["state"]["orders"][0]["status"] == "expired"


def test_stop_gap_uses_worse_open_and_precedes_ambiguous_profit_limit():
    session = new_session()
    q = snapshot(session)["quotes"][0]
    stop = q["price"] * 0.97
    state = order(session, stop_loss=stop)["state"]
    state = order(state, side="sell", order_type="limit", limit_price=q["price"] * 1.03)["state"]
    history = next_bar(
        market_path(42, "balanced", 0),
        open=stop * 0.95,
        low=stop * 0.9,
        high=q["price"] * 1.1,
        close=q["price"],
    )
    _advance_one(state, history)
    assert state["account"]["trades"][-1]["side"] == "SELL"
    assert state["account"]["trades"][-1]["price"] == pytest.approx(
        stop * 0.95 * (1 - HALF_SPREAD) * 0.9995
    )
    assert state["orders"][0]["status"] == "rejected"
    assert not state["account"]["positions"]


def test_crash_scenario_emits_a_real_synthetic_shock_only_when_clock_reaches_it():
    history = market_path(42, "crash", 41)["BTC/USD"]
    assert history[-1]["close"] / history[-2]["close"] < 0.9
    assert market_path(42, "crash", 40)["BTC/USD"] == history[:-1]
    first = act({"action": "advance", "state": new_session(scenario="crash"), "steps": 30})
    assert not any("flash-crash" in event["message"] for event in first["state"]["events"])
    last = act({"action": "advance", "state": first["state"], "steps": 11})
    assert any("flash-crash" in event["message"] for event in last["state"]["events"])


def test_synthetic_council_cannot_approve_performance_target():
    result = act({"action": "council", "state": new_session()})
    assert result["council"]["synthetic"] is True
    assert result["council"]["performance_target"]["supported"] is False
    assert result["council"]["director"]["decision"] == "wait"
    assert result["state"]["account"]["trades"] == []


@pytest.mark.parametrize(
    "change",
    [
        {"step": True},
        {"seed": -1},
        {"scenario": "guaranteed_profit"},
        {"account": None},
        {"schema_version": True},
    ],
)
def test_invalid_imported_state_is_rejected(change):
    with pytest.raises((TypeError, ValueError)):
        act({"action": "snapshot", "state": {**new_session(), **change}})


def test_import_cannot_remove_declared_costs_or_fabricate_cash():
    state = new_session()
    state["account"]["fee_bps"] = 0
    with pytest.raises(ValueError, match="costs"):
        act({"action": "snapshot", "state": state})
    state = new_session()
    state["account"]["cash"] += 100
    with pytest.raises(ValueError, match="reconcile"):
        act({"action": "snapshot", "state": state})


def test_api_state_roundtrip_and_request_limits_without_network():
    with TestClient(app) as client:
        response = client.post("/api/fusion/simulated-market", json={"action": "create"})
        assert response.status_code == 200, response.text
        state = response.json()["state"]
        result = client.post(
            "/api/fusion/simulated-market", json={"action": "advance", "state": state, "steps": 10}
        )
        assert result.status_code == 200, result.text
        assert result.json()["state"]["step"] == 10
        assert (
            client.post(
                "/api/fusion/simulated-market",
                json={"action": "advance", "state": state, "steps": 500},
            ).status_code
            == 422
        )
