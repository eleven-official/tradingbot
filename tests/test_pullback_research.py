"""Conservative execution and selection causality for an unvalidated hypothesis."""

from copy import deepcopy

from fastapi.testclient import TestClient
import pytest

from core.fusion.quant import ShadowConfig, _bars
from core.fusion.reversion import RECIPES, _features, _replay, evaluate_pullback
from core.copilot import LokiCopilot
from loki.api.server import app
from tests.test_fusion_quant import sample_bars


def execution_fixture():
    rows = sample_bars(104, flat=True)
    features = [None] * len(rows)
    features[99] = {"rsi": 20, "close": 100, "mean100": 99, "mean20": 110, "std20": 5, "atr": 3}
    return rows, features


def test_ambiguous_stop_and_target_takes_the_loss_and_includes_both_side_costs():
    rows, features = execution_fixture()
    rows[100].update(open=100, high=106, low=93, close=100)
    result = _replay(_bars(rows, 101), features, ShadowConfig(), RECIPES[0], 100, 102)
    trade = result["trades"][0]
    assert trade["entry_price"] == pytest.approx(100 * 1.0005)
    assert trade["exit_price"] == pytest.approx(94 * 0.9995)
    assert trade["exit_reason"] == "stop_first_if_ambiguous"
    assert trade["pnl"] < 0 and trade["fees"] > 0 and trade["slippage"] > 0
    assert result["summary"]["final_capital"] - 10000 == pytest.approx(trade["pnl"])
    assert result["summary"]["max_drawdown"] < 0


def test_gap_through_stop_fills_at_worse_open_instead_of_the_stop():
    rows, features = execution_fixture()
    rows[100].update(open=100, high=101, low=99, close=100)
    rows[101].update(open=90, high=91, low=89, close=90)
    result = _replay(_bars(rows, 101), features, ShadowConfig(), RECIPES[0], 100, 103)
    trade = result["trades"][0]
    assert trade["exit_reason"] == "stop_gap"
    assert trade["exit_price"] == pytest.approx(90 * 0.9995)
    assert trade["exit_price"] < 94


def test_entry_quantity_uses_preceding_volume_and_not_current_volume():
    rows, features = execution_fixture()
    rows[99]["volume"] = 1
    rows[100].update(open=100, high=101, low=99, close=100, volume=1_000_000_000)
    bars = _bars(rows, 101)
    result = _replay(bars, features, ShadowConfig(), RECIPES[0], 100, 102)
    assert result["trades"][0]["quantity"] == pytest.approx(0.005)
    assert result["trades"][0]["exit_reason"] == "end_of_test_liquidation"


def test_stop_risk_and_exposure_are_bounded_at_entry():
    rows, features = execution_fixture()
    result = _replay(_bars(rows, 101), features, ShadowConfig(), RECIPES[0], 100, 102)
    trade = result["trades"][0]
    outlay = trade["quantity"] * trade["entry_price"] * 1.001
    planned_stop = trade["quantity"] * (100 * 1.0005 * 1.001 - 94 * 0.9995 * 0.999)
    assert outlay <= 2000
    assert planned_stop <= 50 + 1e-8


def test_costly_tiny_reversion_is_rejected_instead_of_chasing_win_rate():
    rows, features = execution_fixture()
    features[99]["atr"] = 0.01
    result = _replay(_bars(rows, 101), features, ShadowConfig(), RECIPES[0], 100, 102)
    assert result["trades"] == []


def test_features_and_training_trials_cannot_see_later_prices():
    rows = sample_bars(500)
    modified = deepcopy(rows)
    for row in modified[300:]:
        for key in ("open", "high", "low", "close"):
            row[key] *= 2
    before = _features(_bars(rows, 260))
    after = _features(_bars(modified, 260))
    assert before[:300] == after[:300]
    original_report = evaluate_pullback(rows)
    changed_report = evaluate_pullback(modified)
    assert original_report["training_trials"] == changed_report["training_trials"]
    assert original_report["parameters"] == changed_report["parameters"]
    assert original_report["train_end"] < original_report["test_start"]
    assert original_report["data_fingerprint"] != changed_report["data_fingerprint"]


def test_cash_and_unverified_freshness_do_not_invent_70_percent_evidence():
    report = evaluate_pullback(sample_bars(300, flat=True))
    assert report["parameters"] == {}
    assert len(report["training_trials"]) == 3
    assert report["summary"]["total_return"] == 0
    assert report["summary"]["win_rate"] is None
    assert report["target_evidence"]["sample_meets_checks"] is False
    assert report["target_evidence"]["fresh_holdout_verified"] is False
    assert report["target_evidence"]["future_win_rate_guaranteed"] is False
    assert all(item["total_return"] == 0 for item in report["cost_stress"])
    assert report["live_trading_enabled"] is False


@pytest.mark.parametrize("fraction", [True, 0.49, 0.81, float("nan")])
def test_bad_training_split_rejected(fraction):
    with pytest.raises(ValueError):
        evaluate_pullback(sample_bars(300), train_fraction=fraction)


def test_public_api_and_copilot_explain_the_actual_distinct_hypothesis():
    with TestClient(app) as client:
        response = client.post(
            "/api/fusion/pullback", json={"bars": sample_bars(300, flat=True), "symbol": "TEST/USD"}
        )
        assert response.status_code == 200, response.text
        report = response.json()
        assert report["strategy_id"] == "loki_pullback_reversion_v1"
        assert (
            client.post("/api/fusion/pullback", json={"bars": sample_bars(161)}).status_code == 422
        )
    reply = LokiCopilot().respond("Explain the pullback research", {"pullback_research": report})
    assert reply.intent == "pullback"
    assert "100-close average" in reply.text
    assert "cash" in reply.text.lower()
    assert "holdout provenance has not been verified" in reply.text
    assert "win rate: unknown" in reply.text
