"""Contract tests for Loki's paper-only web surface."""
from dataclasses import dataclass

from fastapi.testclient import TestClient

import loki.api.server as server

client = TestClient(server.app)


def test_console_renders_the_market_and_journal_workspace():
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Market structure" in response.text
    assert "Paper journal" in response.text


def test_health_endpoint_identifies_the_paper_only_mode():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["mode"] == "paper-tools-only"


def test_risk_plan_returns_a_non_executable_calculation():
    response = client.post(
        "/api/risk-plan",
        json={
            "side": "BUY",
            "capital": 10_000,
            "risk_percent": 1,
            "entry_price": 100,
            "stop_price": 95,
            "target_price": 110,
        },
    )

    assert response.status_code == 200
    assert response.json()["mode"] == "paper-only"
    assert response.json()["approved"] is True
    assert response.json()["quantity"] > 0
    assert "not financial advice or an order" in response.json()["disclaimer"]


def test_risk_plan_rejects_a_stop_on_the_profit_side():
    response = client.post(
        "/api/risk-plan",
        json={
            "side": "BUY",
            "capital": 10_000,
            "risk_percent": 1,
            "entry_price": 100,
            "stop_price": 105,
            "target_price": 110,
        },
    )

    assert response.status_code == 422


def test_council_returns_six_explainable_gates_without_execution():
    response = client.post(
        "/api/trade-council",
        json={
            "side": "BUY",
            "capital": 10_000,
            "risk_percent": 1,
            "entry_price": 100,
            "stop_price": 95,
            "target_price": 110,
            "current_price": 100,
            "trend": "BULLISH",
            "volatility_percent": 2,
            "volume_ratio": 2,
            "market_data_age_seconds": 0,
            "spread_percent": 0.1,
            "market_open": True,
            "setup_name": "Test continuation",
            "setup_score": 90,
        },
    )

    assert response.status_code == 200
    assert response.json()["mode"] == "paper-only"
    assert response.json()["action"] in {"BUY", "WAIT", "SKIP"}
    assert len(response.json()["reviews"]) == 6
    assert all(review["reason"] for review in response.json()["reviews"])


def test_market_snapshot_endpoint_uses_the_read_only_data_adapter(monkeypatch):
    @dataclass(frozen=True)
    class Snapshot:
        provider: str
        symbol: str
        interval: str

    requested = []

    def fake_snapshot(symbol, interval):
        requested.append((symbol, interval))
        return Snapshot("Binance Spot", symbol, interval)

    monkeypatch.setattr(server, "get_binance_spot_snapshot", fake_snapshot)
    response = client.get("/api/market-snapshot?symbol=ETHUSDT&interval=5m")

    assert response.status_code == 200
    assert response.json()["mode"] == "read-only-market-data"
    assert response.json()["snapshot"]["symbol"] == "ETHUSDT"
    assert requested == [("ETHUSDT", "5m")]
