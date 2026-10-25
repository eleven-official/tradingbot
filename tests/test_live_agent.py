"""Offline live-order lifecycle tests. No broker credentials or network used."""
from datetime import datetime, timezone
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from core.fusion import broker_link as link, live_agent as agent


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setenv("LOKI_PAPER_AI_DB", str(tmp_path / "orders.sqlite3"))
    g = {"posts": [], "orders": {}, "equity": 10000, "positions": [], "open": [], "timeout": False,
         "clock_open": True, "quote_time": None, "signal": "BUY", "during_post": None}
    profile = link.Profile("alpaca", "live", "FIXTURE-KEY", "FIXTURE-SECRET")

    def request(client, method, path, **kw):
        stamp = datetime.now(timezone.utc).isoformat()
        if path == "/v2/account":
            return {"id": "FIXTURE-ACCOUNT", "currency": "USD", "status": "ACTIVE", "cash": "10000",
                    "equity": str(g["equity"]), "trading_blocked": False, "account_blocked": False}
        if path == "/v2/positions": return g["positions"]
        if path == "/v2/orders" and method == "GET": return g["open"]
        if path == "/v2/clock": return {"is_open": g["clock_open"], "timestamp": stamp}
        if path.startswith("/v2/assets/"):
            return {"symbol": "SPY", "tradable": True, "class": "us_equity", "status": "active"}
        if path.endswith("/quotes/latest"):
            return {"quote": {"bp": 99.99, "ap": 100, "t": g["quote_time"] or stamp}}
        if path == "/v2/orders:by_client_order_id":
            return g["orders"][kw["params"]["client_order_id"]]
        if path == "/v2/orders" and method == "POST":
            assert client.live_orders is True and client.profile.mode == "live"
            body = kw["body"]
            # The claim and execution authority must exist on disk BEFORE transport.
            with agent._db() as db:
                assert db.execute("SELECT body FROM live_claims WHERE id=?", (body["client_order_id"],)).fetchone()
            g["posts"].append(body)
            response = dict(body, id="venue-1", status="new", filled_qty="0", filled_avg_price=None)
            g["orders"][body["client_order_id"]] = response
            if g["during_post"]: g["during_post"]()
            if g["timeout"]: raise link.BrokerUnavailable()
            return response
        raise AssertionError((method, path))

    monkeypatch.setattr(link.AlpacaClient, "request", request)
    monkeypatch.setattr(agent, "_analysis", lambda symbol: {
        "trained_profile_applied": True, "director": {"posture": "long"},
        "quant": {"action": g["signal"], "stop": 98, "target": 104},
    })
    link.refresh_account(profile)
    return profile, g


def start(profile, **kw):
    return agent.start(profile, "session", "SPY", kw.get("budget", 1000), kw.get("loss", 100), 2)


def due(profile):
    with agent._db() as db:
        state = agent._read(db, profile)
        state["next_check"] = 0
        agent._save(db, profile, state)


def test_start_is_required_and_paper_never_enters_live(setup):
    p, g = setup
    with pytest.raises(ValueError): agent.tick(p, "session")
    p.mode = "paper"
    with pytest.raises(ValueError): start(p)
    assert not g["posts"]


def test_limits_brackets_and_actual_fills(setup):
    p, g = setup
    start(p, budget=500)
    result = agent.tick(p, "session")
    order = g["posts"][0]
    assert order["qty"] == "5" and order["order_class"] == "bracket"
    assert order["stop_loss"] == {"stop_price": "98.00"}
    assert order["take_profit"] == {"limit_price": "104.00"}
    assert result["journal"][0]["order"]["filled_qty"] == 0
    raw = g["orders"][order["client_order_id"]]
    raw.update(status="filled", filled_qty="5", filled_avg_price="99.98")
    result = agent.reconcile(p, "session")
    assert result["journal"][0]["order"]["filled_avg_price"] == 99.98
    due(p)
    agent.tick(p, "session")
    assert len(g["posts"]) == 1  # One entry per symbol/day, even after a completed fill.


def test_uncertain_submission_survives_restart_without_resend(setup):
    p, g = setup
    start(p)
    g["timeout"] = True
    with pytest.raises(ConnectionError): agent.tick(p, "session")
    result = agent.status(p, "session")
    assert result["running"] is False and result["pending"]
    with pytest.raises(ValueError): start(p)
    agent.reconcile(p, "session")
    assert len(g["posts"]) == 1


def test_concurrent_cycles_claim_one_order(setup):
    p, g = setup
    start(p)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: agent.tick(p, "session"), range(2)))
    assert len(results) == 2 and len(g["posts"]) == 1


def test_stop_during_transport_is_preserved(setup):
    p, g = setup
    start(p)
    g["during_post"] = lambda: agent.stop(p, "session")
    result = agent.tick(p, "session")
    assert result["running"] is False
    assert len(g["posts"]) == 1
    with pytest.raises(ValueError): agent.tick(p, "session")


def test_daily_loss_is_not_reset_by_stop_start(setup):
    p, g = setup
    start(p)
    agent.stop(p, "session")
    g["equity"] = 9899
    with pytest.raises(ValueError, match="loss limit"): start(p)
    assert not g["posts"]


def test_daily_loss_stops_new_entries(setup):
    p, g = setup
    start(p)
    g["equity"] = 9899
    assert agent.tick(p, "session")["running"] is False
    assert not g["posts"]


@pytest.mark.parametrize("field,value", [("signal", "HOLD"), ("clock_open", False), ("positions", [{"symbol": "AAPL"}])])
def test_waits_without_posting(setup, field, value):
    p, g = setup
    start(p)
    g[field] = value
    agent.tick(p, "session")
    assert not g["posts"]


def test_stale_quotes_fail_closed(setup):
    p, g = setup
    start(p)
    g["quote_time"] = "2000-01-01T00:00:00+00:00"
    with pytest.raises(ConnectionError): agent.tick(p, "session")
    assert not g["posts"]


def test_controller_and_expiry(setup):
    p, g = setup
    start(p)
    with pytest.raises(ValueError): agent.start(p, "other", "SPY", 1000, 100, 2)
    with pytest.raises(ValueError): agent.tick(p, "other")
    with agent._db() as db:
        state = agent._read(db, p)
        state["until"] = 0
        agent._save(db, p, state)
    with pytest.raises(ValueError): agent.tick(p, "session")
    assert not agent.status(p, "session")["running"]
    assert not g["posts"]


def test_live_routes_require_launcher():
    from fastapi.testclient import TestClient
    from loki.api.server import app
    with TestClient(app) as client:
        assert client.post('/api/fusion/broker/live-ai/tick', json={}).status_code == 403


def test_transport_defaults_remain_paper_only(monkeypatch):
    p = link.Profile("alpaca", "live", "FIXTURE-KEY", "FIXTURE-SECRET")
    with pytest.raises(ValueError, match="paper endpoint"):
        link.AlpacaClient(p).request("POST", "/v2/orders", body={})
    seen = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit): return b'{}'
    class Opener:
        def open(self, req, **kw):
            seen.append(req.full_url)
            return Response()
    monkeypatch.setattr(link, "build_opener", lambda *args: Opener())
    link.AlpacaClient(p, live_orders=True).request("POST", "/v2/orders", body={})
    assert seen == ["https://api.alpaca.markets/v2/orders"]
    with pytest.raises(ValueError):
        link.AlpacaClient(p, live_orders=True).request("POST", "/v2/account", body={})


def test_mismatched_confirmation_never_becomes_a_fill(setup):
    p, g = setup
    start(p)
    agent.tick(p, "session")
    cid = g["posts"][0]["client_order_id"]
    g["orders"][cid]["symbol"] = "QQQ"
    with pytest.raises(ValueError): agent.reconcile(p, "session")
    assert agent.status(p, "session")["pending"] == cid
