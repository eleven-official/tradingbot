"""Paper ledger accounting, lifecycle statistics and stress are real arithmetic."""

from copy import deepcopy
import math

import pytest

from core.fusion.portfolio import (
    apply_portfolio_action,
    new_portfolio,
    portfolio_metrics,
    stress_portfolio,
)


def action(state=None, **kwargs):
    return apply_portfolio_action(dict(state=state, **kwargs))


def test_new_account_has_no_invented_win_rate_or_expectancy():
    result = action()
    assert result["metrics"]["equity"] == 10000
    assert result["metrics"]["win_rate"] is None
    assert result["metrics"]["expectancy"] is None
    assert result["state"]["mode"] == "paper_only"


def test_roundtrip_charges_both_fees_and_adverse_slippage():
    bought = action(action="buy", symbol="BTC/USD", price=100, quantity=10)
    sold = action(bought["state"], action="sell", symbol="BTC/USD", price=105, quantity=10)
    entry = 100 * 1.0005
    exit_ = 105 * 0.9995
    expected = 10 * (exit_ - entry) - 10 * (entry + exit_) * 0.001
    assert sold["metrics"]["total_pnl"] == pytest.approx(expected)
    assert sold["last_action"]["completed_pnl"] == pytest.approx(expected)
    assert sold["metrics"]["closed_trades"] == 1
    assert sold["metrics"]["win_rate"] == 100
    assert sold["metrics"]["profit_factor"] is None


def test_partial_exits_do_not_inflate_closed_trade_count():
    first = action(action="buy", symbol="BTC/USD", price=100, quantity=10)
    partial = action(first["state"], action="sell", symbol="BTC/USD", price=110, quantity=4)
    assert partial["metrics"]["closed_trades"] == 0
    assert partial["metrics"]["win_rate"] is None
    final = action(partial["state"], action="sell", symbol="BTC/USD", price=90, quantity=6)
    assert final["metrics"]["closed_trades"] == 1
    assert final["metrics"]["win_rate"] == 0
    assert final["last_action"]["completed_pnl"] == pytest.approx(final["metrics"]["total_pnl"])
    assert final["metrics"]["realized_pnl"] == pytest.approx(final["metrics"]["total_pnl"])


def test_realized_and_unrealized_reconcile_after_adding_and_partially_exiting():
    result = action(action="buy", symbol="BTC/USD", price=100, quantity=10)
    result = action(result["state"], action="buy", symbol="BTC/USD", price=110, quantity=2)
    result = action(result["state"], action="sell", symbol="BTC/USD", price=105, quantity=3)
    result = action(result["state"], action="mark", marks={"BTC/USD": 98})
    metrics = result["metrics"]
    assert metrics["realized_pnl"] + metrics["unrealized_pnl"] == pytest.approx(
        metrics["total_pnl"]
    )
    assert metrics["closed_trades"] == 0
    assert result["state"]["positions"]["BTC/USD"]["quantity"] == 9


def test_failed_order_does_not_mutate_caller_state():
    state = new_portfolio()
    before = deepcopy(state)
    with pytest.raises(ValueError, match="insufficient cash"):
        action(state, action="buy", symbol="BTC/USD", price=10000, quantity=10)
    assert state == before


@pytest.mark.parametrize(
    "changes",
    [
        {"quantity": True},
        {"quantity": -1},
        {"price": float("nan")},
        {"price": float("inf")},
        {"stop_loss": 101},
        {"symbol": "../secret"},
    ],
)
def test_invalid_orders_rejected(changes):
    values = dict(action="buy", symbol="BTC/USD", price=100, quantity=1)
    values.update(changes)
    with pytest.raises(ValueError):
        action(**values)


def test_short_sales_and_unknown_actions_rejected():
    with pytest.raises(ValueError, match="held long quantity"):
        action(action="sell", symbol="BTC/USD", price=100, quantity=1)
    with pytest.raises(ValueError, match="Choose"):
        action(action="execute_live")


def test_currency_mismatch_cannot_invent_an_fx_conversion():
    with pytest.raises(ValueError, match="quote currencies"):
        action(action="buy", symbol="BTC/USDT", price=100, quantity=1)


def test_price_marks_do_not_claim_guaranteed_stop_execution():
    result = action(action="buy", symbol="BTC/USD", price=100, quantity=1, stop_loss=95)
    marked = action(result["state"], action="mark", marks={"BTC/USD": 80})
    assert "BTC/USD" in marked["state"]["positions"]
    assert marked["metrics"]["total_pnl"] < -20
    assert any("not automatic" in item for item in marked["assumptions"])


def test_hypothetical_stress_keeps_cash_fixed_and_scales_shock_explicitly():
    account = action(action="buy", symbol="BTC/USD", price=100, quantity=10)
    result = stress_portfolio(account["state"], -10, 2)
    assert result["effective_shock_pct"] == -20
    assert result["pnl"] == pytest.approx(-200)
    assert result["stressed_equity"] == pytest.approx(result["baseline_equity"] - 200)
    assert result["mode"] == "hypothetical_stress"
    assert any("not a MiroFish simulation" in item for item in result["assumptions"])


def test_stress_rejects_negative_prices_and_nonfinite_inputs():
    with pytest.raises(ValueError):
        stress_portfolio(None, -99, 2)
    with pytest.raises(ValueError):
        stress_portfolio(None, float("nan"))


def test_import_validation_rejects_missing_completed_pnl_and_overflowing_positions():
    state = new_portfolio()
    state["trades"] = [
        dict(side="SELL", symbol="BTC/USD", quantity=1, price=1, fees=0, position_closed=True)
    ]
    with pytest.raises(ValueError, match="lifecycle"):
        portfolio_metrics(state)
    state = new_portfolio()
    state["positions"] = {
        "BTC/USD": dict(quantity=1e12, average_price=1e12, mark_price=1e12, entry_fees=0)
    }
    with pytest.raises(ValueError, match="numeric range"):
        portfolio_metrics(state)


def test_reset_explicitly_creates_empty_account_in_requested_currency():
    bought = action(action="buy", symbol="BTC/USD", price=100, quantity=1)
    reset = action(
        bought["state"], action="reset", initial_capital=25000, quote_currency="USDT", fee_bps=2
    )
    assert reset["metrics"]["equity"] == 25000
    assert reset["state"]["positions"] == {}
    assert reset["state"]["trades"] == []
    assert reset["state"]["quote_currency"] == "USDT"


def test_import_cannot_mark_a_buy_as_a_completed_winning_trade():
    bought = action(action="buy", symbol="BTC/USD", price=100, quantity=1)
    corrupted = deepcopy(bought["state"])
    corrupted["trades"][0].update(position_closed=True, completed_pnl=1000)
    with pytest.raises(ValueError, match="BUY fill"):
        portfolio_metrics(corrupted)


@pytest.mark.parametrize(
    "field,change",
    [
        ("cash", 1000),
        ("quantity", 1),
        ("average_price", 50),
        ("entry_fees", 1),
    ],
)
def test_import_reconciles_cash_inventory_and_cost_basis_against_fills(field, change):
    bought = action(action="buy", symbol="BTC/USD", price=100, quantity=2)
    corrupted = deepcopy(bought["state"])
    if field == "cash":
        corrupted[field] += change
    else:
        corrupted["positions"]["BTC/USD"][field] += change
    with pytest.raises(ValueError, match="reconcile"):
        portfolio_metrics(corrupted)


def test_import_cannot_turn_partial_exit_into_closed_winning_lifecycle():
    bought = action(action="buy", symbol="BTC/USD", price=100, quantity=10)
    partial = action(bought["state"], action="sell", symbol="BTC/USD", price=110, quantity=4)
    corrupted = deepcopy(partial["state"])
    corrupted["trades"][-1].update(position_closed=True, completed_pnl=12345)
    with pytest.raises(ValueError, match="lifecycle closure"):
        portfolio_metrics(corrupted)


def test_import_cannot_rewrite_realized_profit_or_lifecycle_profit():
    bought = action(action="buy", symbol="BTC/USD", price=100, quantity=1)
    sold = action(bought["state"], action="sell", symbol="BTC/USD", price=90, quantity=1)
    for field in ("pnl", "completed_pnl"):
        corrupted = deepcopy(sold["state"])
        corrupted["trades"][-1][field] = 99999
        with pytest.raises(ValueError, match="reconcile"):
            portfolio_metrics(corrupted)


def test_marked_multi_lifecycle_ledger_still_reconciles_and_does_not_mutate_input():
    result = action(action="buy", symbol="BTC/USD", price=100, quantity=10)
    result = action(result["state"], action="sell", symbol="BTC/USD", price=110, quantity=10)
    result = action(result["state"], action="buy", symbol="BTC/USD", price=105, quantity=5)
    result = action(result["state"], action="buy", symbol="ETH/USD", price=10, quantity=4)
    result = action(result["state"], action="sell", symbol="BTC/USD", price=90, quantity=2)
    result = action(result["state"], action="mark", marks={"BTC/USD": 88, "ETH/USD": 13})
    before = deepcopy(result["state"])
    metrics = portfolio_metrics(result["state"])
    assert metrics["closed_trades"] == 1
    assert metrics["realized_pnl"] + metrics["unrealized_pnl"] == pytest.approx(
        metrics["total_pnl"]
    )
    assert result["state"] == before
