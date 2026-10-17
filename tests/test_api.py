"""Contracts of the shipped research application, including its absent broker surface.

These requests exercise the real ASGI application. They never require a default
administrator, a venue connection, or a fabricated account/market-data stream.
"""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from loki.api.server import app
from loki.version import __version__

client = TestClient(app)


def test_root_serves_unified_workspace_html():
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    for section in (
        "overview",
        "strategy-lab",
        "agent-council",
        "portfolio",
        "scenarios",
        "copilot",
        "integrations",
    ):
        assert f'data-view="{section}"' in response.text
    assert "No broker orders submitted" in response.text
    assert __version__ in response.text


def test_health_reports_service_health_without_invented_account_state():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "loki", "version": __version__}
    assert "market_connection" not in response.json()
    assert "active_strategies" not in response.json()


@pytest.mark.parametrize(
    "path,content_type",
    [("/static/css/style.css", "text/css"), ("/static/js/workspace.js", "javascript")],
)
def test_browser_assets_are_served(path, content_type):
    response = client.get(path)
    assert response.status_code == 200
    assert content_type in response.headers["content-type"]
    assert response.content


@pytest.mark.parametrize("password", ["admin123", "wrong"])
def test_no_default_administrator_login_is_installed(password):
    response = client.post("/token", data={"username": "admin", "password": password})
    assert response.status_code == 404
    assert "access_token" not in response.json()


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/v1/portfolio"),
        ("get", "/api/v1/positions"),
        ("get", "/api/v1/strategies"),
        ("put", "/api/v1/strategies/QuantumMomentum"),
        ("post", "/api/v1/strategies/QuantumMomentum/start"),
        ("post", "/api/v1/strategies/QuantumMomentum/stop"),
        ("post", "/api/v1/orders"),
        ("post", "/api/orders"),
        ("post", "/api/trade"),
        ("get", "/metrics"),
    ],
)
def test_legacy_live_or_mock_account_surface_is_not_exposed(method, path):
    response = getattr(client, method)(path, headers={"Authorization": "Bearer admin123"})
    assert response.status_code == 404


def test_no_fabricated_market_data_websocket_is_exposed():
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/market-data") as socket:
            socket.receive_json()


def test_openapi_documents_research_and_simulated_actions_only():
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    for path in (
        "/api/research/evaluate",
        "/api/risk/preview",
        "/api/copilot",
        "/api/fusion/portfolio",
    ):
        assert "post" in paths[path]
    assert "/token" not in paths
    assert not any(path.startswith("/api/v1") for path in paths)
    assert not any("/orders" in path for path in paths)


def test_paper_account_lifecycle_is_costed_and_client_owned():
    initial = client.get("/api/fusion/portfolio").json()
    assert initial["state"]["mode"] == "paper_only"
    assert initial["state"]["positions"] == {}
    assert initial["metrics"]["cash"] == initial["metrics"]["equity"] == 10000
    assert initial["metrics"]["win_rate"] is None

    buy = client.post(
        "/api/fusion/portfolio",
        json={
            "action": "buy",
            "state": initial["state"],
            "symbol": "AAPL/USD",
            "price": 100.0,
            "quantity": 2.0,
        },
    )
    assert buy.status_code == 200, buy.text
    entered = buy.json()
    assert entered["last_action"]["mode"] == "paper_only"
    assert entered["last_action"]["fees"] > 0
    assert entered["last_action"]["price"] > 100  # Adverse entry slippage.
    assert entered["metrics"]["equity"] < initial["metrics"]["equity"]

    sell = client.post(
        "/api/fusion/portfolio",
        json={
            "action": "sell",
            "state": entered["state"],
            "symbol": "AAPL/USD",
            "price": 110.0,
            "quantity": 2.0,
        },
    )
    assert sell.status_code == 200, sell.text
    closed = sell.json()
    assert closed["state"]["positions"] == {}
    assert closed["metrics"]["closed_trades"] == 1
    assert 0 < closed["metrics"]["total_pnl"] < 20  # Exit costs are included.
    assert closed["metrics"]["win_rate"] == 100  # Percentage points, one paper lifecycle.
    # The server has not persisted a user account or a broker order.
    assert client.get("/api/fusion/portfolio").json()["state"] == initial["state"]


def test_paper_endpoint_rejects_attempt_to_select_live_execution():
    response = client.post(
        "/api/fusion/portfolio",
        json={"action": "buy", "symbol": "AAPL", "price": 100.0, "quantity": 2.0, "live": True},
    )
    assert response.status_code == 422


def test_chat_declines_real_order_request():
    response = client.post("/api/copilot", json={"message": "Buy 10 BTC now"})
    assert response.status_code == 200
    reply = response.json()
    assert reply["intent"] == "action"
    assert "cannot" in reply["text"].lower() or "can't" in reply["text"].lower()
