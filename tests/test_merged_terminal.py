"""Regressions for the unified GitHub branches. All market/DB calls are mocked."""

import base64
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from loki.api import terminal_v8 as terminal
from loki.api.fusion import _LOCAL_TOKEN
from loki.api.server import app
from loki_v8.agents import LokiAgentPipeline
from loki_v8.bot import LokiBot
from loki_v8.broker import make_broker
from loki_v8.config import LokiConfig
from loki_v8.data import MarketDataProvider, normalize_symbol
from loki_v8.persistence import SupabaseLogger


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("LOKI_FUSION_LOCAL", "1")
    monkeypatch.delenv("VERCEL", raising=False)
    bot = LokiBot(LokiConfig(state_dir=str(tmp_path)))
    monkeypatch.setattr(terminal, "_bot", bot)
    with TestClient(app, base_url="http://127.0.0.1:8123", client=("127.0.0.1", 40000)) as c:
        c.headers["X-Loki-Local-Token"] = _LOCAL_TOKEN
        yield c


def test_merged_views_and_distinct_assets_are_reachable(client):
    root = client.get("/")
    assert 'data-view="advanced-terminal"' in root.text
    assert 'data-view="paper-planner"' in root.text
    for path, text in (
        ("/terminal/", "Advanced paper engine"),
        ("/paper-tools", "Market structure"),
        ("/research-desk", "profileForm"),
    ):
        response = client.get(path, headers={"Accept": "text/html"})
        assert response.status_code == 200
        assert text in response.text
    for name in ("v8_terminal", "paper_tools", "research_desk"):
        assert client.get(f"/static/css/{name}.css").status_code == 200


def test_private_terminal_and_fake_bearer_rejected(client):
    for path in ("/terminal/api/status", "/terminal/metrics", "/terminal/api/supabase/status"):
        assert client.get(path, headers={"X-Loki-Local-Token": ""}).status_code == 403
    response = client.get(
        "/terminal/api/v1/portfolio",
        headers={"Authorization": "Bearer anything", "X-Loki-Local-Token": ""},
    )
    assert response.status_code == 403
    assert (
        client.post(
            "/terminal/token", data={"username": "admin", "password": "admin123"}
        ).status_code
        == 410
    )
    assert client.get("/terminal/api/status").headers["Cache-Control"] == "private, no-store"


def test_forwarded_and_cross_origin_terminal_requests_denied(client):
    for headers in ({"Origin": "https://other.example"}, {"X-Forwarded-For": "127.0.0.1"}):
        assert client.get("/terminal/api/status", headers=headers).status_code == 403


def test_viewing_council_never_executes_an_approved_order(client, monkeypatch):
    monkeypatch.setattr(
        terminal.get_bot(), "agent_scan", lambda symbols: {"executed": 0, "symbols": symbols}
    )
    assert client.get("/terminal/api/council?symbols=AAPL").json()["executed"] == 0
    pipeline = LokiAgentPipeline(terminal.get_bot().cfg, terminal.get_bot().broker)
    monkeypatch.setattr(pipeline.provider, "fetch_history", lambda *a: pd.DataFrame())
    monkeypatch.setattr(pipeline.director, "run", lambda *a: {"posture": "long"})
    monkeypatch.setattr(pipeline.quant, "run", lambda *a: {"action": "BUY"})
    monkeypatch.setattr(
        pipeline.risk, "run", lambda *a: {"approved": True, "action": "BUY", "qty": 1}
    )
    monkeypatch.setattr(
        pipeline.executor, "run", lambda *a: pytest.fail("Council review placed an order")
    )
    trail = pipeline.run_symbol("AAPL", 10000, 0, 100)
    assert trail[-1]["reason"] == "review_only"
    assert not terminal.get_bot().broker.positions


def test_failed_live_switch_preserves_paper_ledger(client):
    bot = terminal.get_bot()
    before = bot.broker
    response = client.post("/terminal/api/mode", json={"mode": "live"})
    assert response.status_code == 400
    assert bot.mode == bot.cfg.mode == "paper"
    assert bot.broker is before
    with pytest.raises(ValueError, match="paper execution only"):
        make_broker(LokiConfig(mode="live"))
    assert client.post("/terminal/api/mode", json={"mode": "paper"}).status_code == 200
    assert bot.broker is before


@pytest.mark.parametrize(
    "payload",
    [
        {"symbol": "AAPL", "action": "BUY", "qty": -1},
        {"symbol": "AAPL", "action": "BUY", "price": 0},
        {"symbol": "AAPL", "action": "BUY", "qty": "NaN"},
        {"symbol": "AAPL", "action": "BUY", "extra": "unexpected"},
    ],
)
def test_invalid_orders_cannot_change_ledger(client, payload):
    before = terminal.get_bot().broker.cash
    assert client.post("/terminal/api/order", json=payload).status_code == 422
    assert terminal.get_bot().broker.cash == before


def test_loop_interval_and_unknown_strategy_fail_closed(client):
    assert (
        client.post(
            "/terminal/api/bot/autonomous", json={"action": "start", "interval": -1}
        ).status_code
        == 422
    )
    assert client.post("/terminal/api/v1/strategies/Invented/start").status_code == 404
    assert not terminal.auto_engine.is_running
    response = client.put(
        "/terminal/api/v1/strategies/Ensemble",
        json={"risk_per_trade_pct": 0.5, "max_open_positions": 2},
    )
    assert response.status_code == 200
    assert terminal.get_bot().cfg.risk_per_trade_pct == 0.5


def test_v1_order_does_not_invent_a_fallback_quote(client, monkeypatch):
    monkeypatch.setattr(terminal.get_bot().provider, "get_latest_price", lambda *a: 0)
    response = client.post(
        "/terminal/api/v1/orders", json={"symbol": "AAPL", "side": "buy", "quantity": 1}
    )
    assert response.status_code == 503
    assert not terminal.get_bot().broker.positions


def test_stop_during_quote_fetch_prevents_new_paper_orders(client, monkeypatch):
    bot = terminal.get_bot()
    monkeypatch.setattr(bot, "_refresh_quotes", lambda: {"AAPL": 100})
    monkeypatch.setattr(bot, "_manage_exits", lambda *a: pytest.fail("Stopped cycle executed"))
    assert bot.step(lambda: False) == bot.cfg.initial_cash


@pytest.fixture
def vault(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://test-project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "sb_secret_test_only")
    return SupabaseLogger()


def test_vault_verification_is_read_only_and_secret_not_bearer(vault, monkeypatch):
    calls = []

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return SimpleNamespace(status_code=200, content=b"[]", json=lambda: [])

    monkeypatch.setattr("requests.request", request)
    assert not vault.status()["verified"]
    assert vault.test_connection()["ok"]
    assert vault.status()["verified"]
    method, url, kwargs = calls[0]
    assert method == "GET" and kwargs["params"] == {"select": "id", "limit": "1"}
    assert kwargs["allow_redirects"] is False
    assert kwargs["headers"]["apikey"] == "sb_secret_test_only"
    assert "Authorization" not in kwargs["headers"]
    assert "sb_secret" not in json.dumps(vault.status())
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "sb_secret_rotated")
    assert not vault.status()["verified"]


def test_legacy_service_jwt_uses_bearer(vault, monkeypatch):
    claims = (
        base64.urlsafe_b64encode(json.dumps({"role": "service_role"}).encode()).decode().rstrip("=")
    )
    key = f"header.{claims}.signature"
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", key)
    headers = vault._configuration()[1]
    assert headers["apikey"] == key
    assert headers["Authorization"] == "Bearer " + key


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://example.com",
        "https://foo.supabase.co/secret",
        "https://user:pass@foo.supabase.co",
    ],
)
def test_vault_rejects_unsafe_urls_without_request(vault, monkeypatch, url):
    monkeypatch.setenv("SUPABASE_URL", url)
    monkeypatch.setattr("requests.request", lambda *a, **k: pytest.fail("Unsafe vault request"))
    assert not vault.test_connection()["ok"]


def test_vault_errors_never_return_secrets_or_response_body(vault, monkeypatch):
    def fail(*a, **k):
        raise RuntimeError("sb_secret_test_only private response body")

    monkeypatch.setattr("requests.request", fail)
    assert not vault.test_connection()["ok"]
    assert "sb_secret" not in json.dumps(vault.status())
    assert "private response body" not in json.dumps(vault.status())


def test_supabase_manager_uses_the_same_verified_transport(vault, monkeypatch):
    import supabase_manager

    monkeypatch.setattr(supabase_manager, "get_logger", lambda: vault)
    monkeypatch.setattr(
        "requests.request",
        lambda *a, **kw: SimpleNamespace(status_code=200, content=b"[]", json=lambda: []),
    )
    manager = supabase_manager.LokiSupabaseManager()
    assert not manager.connected
    assert manager.test_connection()
    assert manager.connected
    assert manager.get_trades() == []


def test_crypto_symbol_normalization_and_single_ticker_quotes(monkeypatch):
    assert normalize_symbol("BTCUSDT") == normalize_symbol("BTC/USD") == "BTC-USD"
    columns = pd.MultiIndex.from_tuples([("Close", "AAPL")])
    monkeypatch.setattr(
        "yfinance.download", lambda *a, **k: pd.DataFrame([[100], [105]], columns=columns)
    )
    assert MarketDataProvider().get_quotes(["AAPL"]) == {"AAPL": 105}


def test_historical_cache_expires(monkeypatch):
    provider = MarketDataProvider()
    calls = []

    def history(**kwargs):
        calls.append(kwargs)
        return pd.DataFrame(
            {"Open": [100], "High": [102], "Low": [99], "Close": [101], "Volume": [100]},
            index=pd.date_range("2025-01-01", periods=1),
        )

    monkeypatch.setattr("yfinance.Ticker", lambda *a: SimpleNamespace(history=history))
    provider.fetch_history("AAPL")
    provider.fetch_history("AAPL")
    assert len(calls) == 1
    provider._cached_at = {k: v - 61 for k, v in provider._cached_at.items()}
    provider.fetch_history("AAPL")
    assert len(calls) == 2


def test_vault_schema_enables_rls_and_revokes_browser_access():
    sql = (Path(__file__).parents[1] / "supabase_schema.sql").read_text()
    assert "enable row level security" in sql
    assert "from anon, authenticated" in sql


def test_trainer_reserves_final_dates_before_any_refinement(tmp_path, monkeypatch):
    from loki_v8 import train
    import numpy as np

    count = 1000
    close = 100 + np.arange(count) * 0.03 + np.sin(np.arange(count) / 10)
    history = pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                            "close": close, "volume": 100000},
                           index=pd.date_range("2020-01-01", periods=count))
    monkeypatch.setattr(train, "get_provider", lambda: SimpleNamespace(fetch_history=lambda *a: history.copy()))
    seen = []
    def fit(development, cfg, symbol, **kwargs):
        seen.append(development.copy())
        return train.SymbolReport(symbol=symbol, ok=True, good=False,
                                  best_params={"signal_threshold": 25.0})
    monkeypatch.setattr(train, "train_symbol", fit)
    cfg = LokiConfig(state_dir=str(tmp_path), lookback_bars=60)
    report = train.train(["AAPL"], cfg, grid={"signal_threshold": [25.0]}, refine_rounds=2)
    assert len(seen) == 2
    assert all(len(d) == 800 and d.index[-1] < history.index[800] for d in seen)
    holdout = report["symbols"][0]["final_holdout"]
    assert holdout["bars"] == 200
    assert holdout["used_for_selection"] is False
    assert report["evaluation_protocol"]["target_70_percent_proven"] is False
    assert len(holdout["data_sha256"]) == 64
