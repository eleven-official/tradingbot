"""Live markets board: parallel public quotes, honest failures, session clock."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from loki.api import live_markets
from loki.api.server import app

client = TestClient(app)


def _fake_quote(symbol, label=None, max_age=None):
    if symbol == "TSLA":
        return {"symbol": symbol, "label": label, "ok": False, "error": "provider down", "provider": None}
    change = (sum(map(ord, symbol)) % 21) - 10.0  # deterministic, both signs
    return {
        "symbol": symbol,
        "label": label,
        "ok": True,
        "price": 100.0,
        "change_pct": change,
        "spark": [99.0, 100.0],
        "provider": "fake",
    }


def test_board_returns_every_category_and_keeps_failures_visible(monkeypatch):
    seen = []

    def spy(symbol, label=None, max_age=None):
        seen.append(max_age)
        return _fake_quote(symbol, label, max_age)

    monkeypatch.setattr(live_markets, "quote_or_failure", spy)
    response = client.get("/api/markets/live")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    data = response.json()
    keys = [c["key"] for c in data["categories"]]
    assert keys == ["crypto", "stocks", "indices", "commodities", "fx"]
    tsla = next(i for c in data["categories"] for i in c["items"] if i["symbol"] == "TSLA")
    assert tsla["ok"] is False and tsla["error"] == "provider down"
    assert data["degraded"] == 1
    assert set(seen) == {live_markets.LIVE_MAX_AGE_SECONDS}
    gainers, losers = data["movers"]["gainers"], data["movers"]["losers"]
    assert gainers and all(g["change_pct"] > 0 for g in gainers)
    assert losers and all(m["change_pct"] < 0 for m in losers)
    assert gainers == sorted(gainers, key=lambda g: -g["change_pct"])


def test_custom_quotes_validate_and_dedupe(monkeypatch):
    monkeypatch.setattr(live_markets, "quote_or_failure", _fake_quote)
    data = client.get("/api/markets/quotes", params={"symbols": "aapl, AAPL,btc/usdt"}).json()
    assert [i["symbol"] for i in data["items"]] == ["AAPL", "BTC/USDT"]
    assert client.get("/api/markets/quotes", params={"symbols": "bad symbol!"}).status_code == 422
    many = ",".join(f"S{i}" for i in range(25))
    assert client.get("/api/markets/quotes", params={"symbols": many}).status_code == 422


def test_session_clock():
    def state(when):
        return {s["market"]: s["state"] for s in live_markets.market_sessions(when)}

    # Wednesday 2026-03-11: 15:00 UTC is 11:00 ET (DST) -> open
    assert state(datetime(2026, 3, 11, 15, 0, tzinfo=timezone.utc))["US stocks"] == "open"
    assert state(datetime(2026, 3, 11, 12, 0, tzinfo=timezone.utc))["US stocks"] == "pre"
    assert state(datetime(2026, 3, 11, 21, 0, tzinfo=timezone.utc))["US stocks"] == "post"
    saturday = state(datetime(2026, 3, 14, 15, 0, tzinfo=timezone.utc))
    assert saturday["US stocks"] == "closed" and saturday["FX"] == "closed"
    assert saturday["Crypto"] == "open"
