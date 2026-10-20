"""Watchtower honesty: public quotes degrade instead of pretending.

These tests keep the endpoints deterministic (provider calls are stubbed at
the module boundary) so CI never waits on a live market feed. The guarantees
under test:
- crypto pairs route to the Binance public adapter, everything else to Yahoo
- per-symbol failures are reported, never converted into fake numbers
- the fixed market floor degrades member by member, all-or-nothing never
- input boundaries (bad characters, more than eight symbols) reject honestly
- backend wiring (scripts, panels, backup keys) is actually present
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from loki.api import market_feed
from loki.api.watchtower import router

ROOT = Path(__file__).resolve().parents[1]

YAHOO_CHART_PAYLOAD = {
    "chart": {
        "result": [
            {
                "meta": {
                    "regularMarketPrice": 271.9,
                    "currency": "USD",
                    "symbol": "AAPL",
                    "previousClose": 262.9,
                },
                "indicators": {"quote": [{"close": [255.0, 260.0, 262.9, None, 271.9]}]},
            }
        ],
        "error": None,
    }
}

NEWS_PAYLOAD = {
    "news": [
        {
            "title": "Example headline about the instrument",
            "publisher": "Example Wire",
            "link": "https://example.com/a",
            "providerPublishTime": 1761000000.0,
        },
        {"title": "", "link": "https://example.com/skip"},  # dropped: no title
        {"title": "Second headline", "publisher": "Example Wire", "link": "https://example.com/b", "providerPublishTime": 1761000300.0},
    ]
}


class FakeSnapshot:
    """Duck-typed stand-in for the Binance snapshot dataclass."""

    symbol = "BTCUSDT"
    current_price = 82_000.0
    change_24h_percent = 1.5
    observed_at = 1_000.0
    candles = tuple({"close": 80_000.0 + float(index) * 10} for index in range(10))


@pytest.fixture
def client(monkeypatch):
    market_feed._quote_cache.clear()
    market_feed._news_cache.clear()
    monkeypatch.setattr(market_feed, "get_binance_spot_snapshot", lambda symbol, interval: FakeSnapshot())
    monkeypatch.setattr(market_feed, "_http_json", lambda url, timeout=8.0: dict(YAHOO_CHART_PAYLOAD))
    application = FastAPI()
    application.include_router(router)
    with TestClient(application) as test_client:
        yield test_client


def test_symbol_classification_follows_pair_shape():
    assert market_feed.classify_symbol("btc/usdt") == "binance"
    assert market_feed.classify_symbol("AAPL") == "yahoo"
    assert market_feed.classify_symbol("^GSPC") == "yahoo"
    assert market_feed.classify_symbol("GC=F") == "yahoo"
    with pytest.raises(market_feed.MarketFeedError):
        market_feed.normalize_symbol("BAD SYMBOL")


def test_watch_quotes_answers_both_providers(client):
    response = client.get("/api/watch-quotes", params={"symbols": "btc/usdt,aapl"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "public-market-quotes"
    assert payload["degraded"] == 0
    items = {item["symbol"]: item for item in payload["items"]}
    crypto = items["BTC/USDT"]
    assert crypto["ok"] is True
    assert crypto["price"] == pytest.approx(82_000.0)
    assert crypto["currency"] == "USDT"
    assert crypto["spark"][-1] == pytest.approx(80_090.0)
    assert "Binance" in crypto["provider"]
    equity = items["AAPL"]
    assert equity["ok"] is True
    assert equity["price"] == pytest.approx(271.9)
    assert equity["change_pct"] == pytest.approx((271.9 - 262.9) / 262.9 * 100.0, rel=1e-6)
    assert equity["spark"] == [255.0, 260.0, 262.9, 271.9]  # the missing close is dropped, never guessed
    assert "not advice" in payload["note"]


def test_watch_quotes_reports_provider_failures_per_symbol(client, monkeypatch):
    monkeypatch.setattr(
        market_feed,
        "_http_json",
        lambda url, timeout=8.0: (_ for _ in ()).throw(market_feed.MarketFeedError("public data provider unreachable")),
    )
    response = client.get("/api/watch-quotes", params={"symbols": "AAPL"})
    assert response.status_code == 200
    payload = response.json()
    item = payload["items"][0]
    assert item["ok"] is False
    assert "unreachable" in item["error"]
    assert payload["degraded"] == 1
    assert payload["count"] == 1


def test_watch_quotes_rejects_bad_payloads(client):
    bad_format = client.get("/api/watch-quotes", params={"symbols": "BAD SYMBOL!"})
    assert bad_format.status_code == 422
    too_many = client.get("/api/watch-quotes", params={"symbols": ",".join(f"S{i}" for i in range(9))})
    assert too_many.status_code == 422
    assert "8 instruments or fewer" in too_many.json()["detail"]
    duplicated = client.get("/api/watch-quotes", params={"symbols": "aapl,AAPL"})
    assert duplicated.status_code == 200
    assert duplicated.json()["count"] == 1


def test_symbol_cache_means_one_provider_call(client, monkeypatch):
    calls = {"count": 0}

    def counting_fetch(url, timeout=8.0):
        calls["count"] += 1
        return dict(YAHOO_CHART_PAYLOAD)

    monkeypatch.setattr(market_feed, "_http_json", counting_fetch)
    first = client.get("/api/watch-quotes", params={"symbols": "MSFT"})
    second = client.get("/api/watch-quotes", params={"symbols": "MSFT"})
    assert first.status_code == second.status_code == 200
    assert calls["count"] == 1  # second answer came from the cache, not the network


def test_market_floor_keeps_every_category_honest(client, monkeypatch):
    monkeypatch.setattr(
        market_feed,
        "_http_json",
        lambda url, timeout=8.0: dict(YAHOO_CHART_PAYLOAD),
    )
    response = client.get("/api/watch-heatmap")
    assert response.status_code == 200
    payload = response.json()
    labels = [category["label"] for category in payload["categories"]]
    assert labels == ["Crypto majors", "Mega-cap tech", "US indices", "Commodities", "FX & havens"]
    assert sum(len(category["items"]) for category in payload["categories"]) == 13
    assert payload["note"].endswith("individual symbols can be unavailable.")


def test_market_floor_degrades_without_losing_the_basket(client, monkeypatch):
    def broken(symbol, interval):
        raise market_feed.MarketDataError("provider down")

    monkeypatch.setattr(market_feed, "get_binance_spot_snapshot", broken)
    monkeypatch.setattr(
        market_feed,
        "_http_json",
        lambda url, timeout=8.0: (_ for _ in ()).throw(market_feed.MarketFeedError("provider down")),
    )
    response = client.get("/api/watch-heatmap")
    assert response.status_code == 200
    payload = response.json()
    items = [item for category in payload["categories"] for item in category["items"]]
    assert len(items) == 13
    assert all(item["ok"] is False for item in items)
    assert all("provider down" in item["error"] for item in items)
    assert "context, never advice" in payload["note"]


def test_signal_feed_maps_public_headlines(client, monkeypatch):
    monkeypatch.setattr(
        market_feed,
        "_http_json",
        lambda url, timeout=8.0: {"news": list(NEWS_PAYLOAD["news"])},
    )
    response = client.get("/api/signal-feed", params={"symbol": "aapl", "limit": 2})
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "public-headlines"
    assert payload["symbol"] == "AAPL"
    assert len(payload["items"]) == 2
    assert payload["items"][0]["title"] == "Example headline about the instrument"
    assert payload["items"][0]["published_at"] == pytest.approx(1_761_000_000.0)
    assert "never advice" in payload["note"]


def test_signal_feed_admits_it_has_nothing(client, monkeypatch):
    monkeypatch.setattr(
        market_feed,
        "_http_json",
        lambda url, timeout=8.0: (_ for _ in ()).throw(market_feed.MarketFeedError("public data provider unreachable")),
    )
    response = client.get("/api/signal-feed", params={"symbol": "AAPL"})
    payload = response.json()
    assert response.status_code == 200
    assert payload["mode"] == "public-headlines-degraded"
    assert payload["items"] == []
    assert "nothing was invented" in payload["error"] + payload.get("note", "")


def test_signal_feed_validates_limit(client):
    assert client.get("/api/signal-feed", params={"limit": 99}).status_code == 422
    assert client.get("/api/signal-feed", params={"limit": 0}).status_code == 422


def test_headlines_search_uses_public_names(client, monkeypatch):
    seen = {}

    def capture(url, timeout=8.0):
        seen["url"] = url
        return {"news": []}

    monkeypatch.setattr(market_feed, "_http_json", capture)
    client.get("/api/signal-feed", params={"symbol": "btc/usdt"})
    assert "v1/finance/search?q=Bitcoin" in seen["url"]  # the public name, not BTC-USD
    client.get("/api/signal-feed", params={"symbol": "eth/usdt"})
    assert "q=Ethereum" in seen["url"]
    client.get("/api/signal-feed", params={"symbol": "AAPL"})
    assert "q=AAPL" in seen["url"] and "q=Bitcoin" not in seen["url"]


def test_watchtower_pages_and_backup_are_wired():
    index = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    for needle in (
        "/static/js/watchtower.js?v={{ version }}",
        'id="watch-form"',
        'id="watch-cards"',
        'id="signal-inner"',
        'id="market-floor"',
        'id="floor-categories"',
        'id="floor-refresh"',
        "MARKET FLOOR",
    ):
        assert needle in index, needle
    backup = (ROOT / "static" / "js" / "backup.js").read_text(encoding="utf-8")
    assert "loki_watchlist_v1" in backup
    server = (ROOT / "loki" / "api" / "server.py").read_text(encoding="utf-8")
    assert "watchtower_router" in server
    planner = (ROOT / "static" / "js" / "planner.js").read_text(encoding="utf-8")
    assert "Watchtower handoff" in planner  # ?symbol= bridge from the watchtower
    paper_tools = (ROOT / "templates" / "paper_tools.html").read_text(encoding="utf-8")
    assert 'id="live-feed-status"' in paper_tools and 'id="live-feed-form"' in paper_tools
    styles = (ROOT / "static" / "css" / "style.css").read_text(encoding="utf-8")
    assert ".watch-card" in styles and ".floor-grid" in styles
