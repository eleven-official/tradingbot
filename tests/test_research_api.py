"""Regression checks for the research-only web surface and sizing arithmetic."""

import pytest
from fastapi.testclient import TestClient

from core.risk_preview import preview_position
from loki.api.server import app
from test_strategy_lab import sample_bars

client = TestClient(app)


def test_workspace_and_assets_resolve_outside_repo_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    response = client.get("/")
    assert response.status_code == 200
    assert "Find an edge." in response.text
    assert "Separate practice accounts" in response.text
    assert 'id="real-order-fields" disabled' in response.text
    for view in (
        "overview",
        "strategy-lab",
        "agent-council",
        "portfolio",
        "simulated-market",
        "real-market",
        "scenarios",
        "integrations",
        "copilot",
    ):
        assert f'id="{view}"' in response.text
    assert client.get("/static/css/style.css").status_code == 200
    assert client.get("/static/js/workspace.js").status_code == 200
    assert client.get("/static/js/simulated_market.js").status_code == 200
    assert client.get("/static/js/real_account.js").status_code == 200
    assert client.get("/health").json()["status"] == "ok"


def test_research_endpoint_returns_costed_forward_results():
    response = client.post("/api/research/evaluate", json={"bars": sample_bars()})
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["live_trading_enabled"] is False
    assert len(report["folds"]) == 3
    assert all(fold["train_end"] < fold["test_start"] for fold in report["folds"])
    assert report["cost_stress"][0]["total_return"] == pytest.approx(
        report["summary"]["total_return"]
    )
    assert report["summary"]["total_fees"] >= 0
    assert report["data_fingerprint"]


@pytest.mark.parametrize(
    "payload",
    [
        {"bars": []},
        {"bars": sample_bars()[:160]},
        {"bars": sample_bars()[::-1]},
        {"bars": sample_bars(), "config": {"fee_bps": -1}},
        {"bars": sample_bars(), "config": {"live_trading": True}},
        {"bars": sample_bars(), "extra": "unsupported"},
    ],
)
def test_research_endpoint_rejects_invalid_inputs(payload):
    assert client.post("/api/research/evaluate", json=payload).status_code == 422


def test_copilot_answers_followups_without_shared_session_state():
    first = client.post("/api/copilot", json={"message": "Explain the strategy"}).json()
    followup = client.post(
        "/api/copilot", json={"message": "why?", "context": {"previous_intent": first["intent"]}}
    ).json()
    assert first["intent"] == followup["intent"] == "strategy"
    separate = client.post("/api/copilot", json={"message": "why?"}).json()
    assert separate["intent"] == "help"
    action = client.post("/api/copilot", json={"message": "buy 10 BTC now"}).json()
    assert action["intent"] == "action"
    assert client.post("/api/copilot", json={"message": ""}).status_code == 422


def test_sizing_includes_round_trip_costs_and_caps_cash():
    result = preview_position(10000, 100, 95, risk_pct=0.5, max_exposure_pct=20)
    quantity = result["quantity"]
    expected_loss = quantity * (100 * 1.0005 * 1.001 - 95 * 0.9995 * 0.999)
    assert result["planned_loss_at_stop"] == pytest.approx(expected_loss)
    assert result["planned_loss_at_stop"] <= result["risk_budget"]
    assert result["cash_required"] <= 2000
    assert quantity < 10  # Stop-only math would ignore costs and give 10 units.


def test_exposure_limit_caps_quantity():
    result = preview_position(10000, 100, 99, risk_pct=5, max_exposure_pct=1)
    assert result["binding_limit"] == "exposure"
    assert result["cash_required"] == pytest.approx(100)


@pytest.mark.parametrize(
    "payload",
    [
        {"equity": True, "entry": 100, "stop": 95},
        {"equity": 10000, "entry": 100, "stop": 105},
        {"equity": 10000, "entry": 1e-308, "stop": 5e-309, "fee_bps": 0, "slippage_bps": 0},
        {"equity": 10000, "entry": 100, "stop": 95, "risk_pct": 10},
    ],
)
def test_risk_api_rejects_invalid_or_numerically_extreme_inputs(payload):
    assert client.post("/api/risk/preview", json=payload).status_code == 422


def test_generic_ungated_order_endpoints_are_absent():
    for path in ("/api/orders", "/api/v1/orders", "/api/trade"):
        assert client.post(path, json={"symbol": "BTC", "quantity": 1}).status_code == 404
