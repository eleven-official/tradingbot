"""News desk: fixed public basket, keyword chips, honest degradation.

The suite stubs Yahoo's HTTP boundary only, so the real query normalizing,
parsing and caching code runs in every test. Stories seen by two terms must
merge with both themes. Partial feed failures ride inside the 200 response;
when every query fails the page says so instead of pretending the market
stood still. Chips are plain keyword matches — never called analysis.
"""

from urllib.parse import parse_qs, urlsplit
from pathlib import Path

from fastapi.testclient import TestClient

import loki.api.news_desk as module
from loki.api import market_feed
from loki.api.server import app

client = TestClient(app)

NOW = 1_900_000_000.0

STORIES = {
    "stock market": [
        {"title": "Markets steady as traders weigh the week", "publisher": "Reuters",
         "link": "https://news.invalid/markets/1", "providerPublishTime": NOW - 900},
        {"title": "Retail earnings season opens gently", "publisher": "Bloomberg",
         "link": "https://news.invalid/markets/2", "providerPublishTime": NOW - 3_600},
    ],
    "Federal Reserve": [
        {"title": "Fed holds rates steady and flags inflation progress", "publisher": "Reuters",
         "link": "https://news.invalid/fed/1", "providerPublishTime": NOW - 300},
        # same link as a markets story: the merge must keep it once, with two themes
        {"title": "Markets steady as traders weigh the week", "publisher": "Reuters",
         "link": "https://news.invalid/markets/1", "providerPublishTime": NOW - 900},
    ],
    "inflation": [
        {"title": "CPI shows shelter costs cooling in the latest report", "publisher": "WSJ",
         "link": "https://news.invalid/cpi/1", "providerPublishTime": NOW - 1_800},
    ],
    "oil prices": [
        {"title": "Oil slips after OPEC review and rising crude inventories", "publisher": "Reuters",
         "link": "https://news.invalid/oil/1", "providerPublishTime": NOW - 5_400},
    ],
    "semiconductors": [
        {"title": "Nvidia demands lift the chip forecast as Taiwan exports jump", "publisher": "CNBC",
         "link": "https://news.invalid/chips/1", "providerPublishTime": NOW - 200},
    ],
    "Bitcoin": [
        {"title": "Bitcoin ETF inflows push crypto volumes higher", "publisher": "The Block",
         "link": "https://news.invalid/crypto/1", "providerPublishTime": NOW - 60},
    ],
}


class _FeedStub:
    """Deterministic _http_json answers per search term, with a call counter."""

    def __init__(self):
        self.calls: list[str] = []

    def __call__(self, url, timeout=None):
        term = parse_qs(urlsplit(url).query)["q"][0].replace("+", " ")
        self.calls.append(term)
        return {"news": STORIES.get(term, [])}


class TestNewsDeskShape:
    def test_basket_merges_tags_and_sorts(self, monkeypatch):
        stub = _FeedStub()
        monkeypatch.setattr(market_feed, "_http_json", stub)
        monkeypatch.setattr(market_feed, "_news_cache", {})
        response = client.get("/api/news")
        assert response.status_code == 200
        body = response.json()
        assert stub.calls == [term for term, _ in module.NEWS_BASKET], "every basket term fetched exactly once per request"
        assert body["mode"] == "news-desk"
        links = [item["link"] for item in body["items"]]
        assert len(links) == len(set(links)), "duplicate links collapse into one story"
        published = [item["published_at"] for item in body["items"]]
        assert published == sorted(published, reverse=True), "newest first"
        assert "public" in body["note"].lower() and "never advice" in body["note"]
        merged = [item for item in body["items"] if item["link"] == "https://news.invalid/markets/1"]
        assert len(merged) == 1
        assert merged[0]["themes"] == ["markets", "rates"]

    def test_keyword_signals_match_plain_words(self, monkeypatch):
        stub = _FeedStub()
        monkeypatch.setattr(market_feed, "_http_json", stub)
        monkeypatch.setattr(market_feed, "_news_cache", {})
        body = client.get("/api/news").json()
        titles = {item["title"]: item["signals"] for item in body["items"]}
        assert "rates" in titles["Fed holds rates steady and flags inflation progress"]
        assert "inflation" in titles["Fed holds rates steady and flags inflation progress"]
        assert "inflation" in titles["CPI shows shelter costs cooling in the latest report"]
        assert "chips" in titles["Nvidia demands lift the chip forecast as Taiwan exports jump"]
        assert "crypto" in titles["Bitcoin ETF inflows push crypto volumes higher"]

    def test_limit_truncates(self, monkeypatch):
        stub = _FeedStub()
        monkeypatch.setattr(market_feed, "_http_json", stub)
        monkeypatch.setattr(market_feed, "_news_cache", {})
        body = client.get("/api/news", params={"limit": 3}).json()
        assert len(body["items"]) == 3

    def test_out_of_range_limit_is_422(self, monkeypatch):
        monkeypatch.setattr(market_feed, "_http_json", _FeedStub())
        assert client.get("/api/news", params={"limit": 0}).status_code == 422
        assert client.get("/api/news", params={"limit": 25}).status_code == 422

    def test_second_request_within_ten_minutes_does_not_refetch(self, monkeypatch):
        stub = _FeedStub()
        monkeypatch.setattr(market_feed, "_http_json", stub)
        monkeypatch.setattr(market_feed, "_news_cache", {})
        client.get("/api/news")
        client.get("/api/news")
        assert len(stub.calls) == len(module.NEWS_BASKET), "the desk serves from the per-term caches within the TTL"


class TestNewsDeskDegradation:
    def test_partial_failure_rides_inside_the_200(self, monkeypatch):
        stub = _FeedStub()
        monkeypatch.setattr(market_feed, "_http_json", stub)
        monkeypatch.setattr(market_feed, "_news_cache", {})

        def one_term_fails(url, timeout=None):
            term = parse_qs(urlsplit(url).query)["q"][0].replace("+", " ")
            if term == "oil prices":
                raise market_feed.MarketFeedError("public data provider unreachable")
            return stub(url, timeout)

        monkeypatch.setattr(market_feed, "_http_json", one_term_fails)
        body = client.get("/api/news").json()
        assert body["mode"] == "news-desk"
        assert body["errors"] and "oil prices" in body["errors"][0]
        assert body["items"], "the terms that answered still publish"

    def test_every_query_failing_answers_honestly(self, monkeypatch):
        def all_fail(url, timeout=None):
            raise market_feed.MarketFeedError("public data provider unreachable")

        monkeypatch.setattr(market_feed, "_http_json", all_fail)
        monkeypatch.setattr(market_feed, "_news_cache", {})
        body = client.get("/api/news").json()
        assert body["mode"] == "news-desk-degraded"
        assert body["items"] == []
        assert "nothing was invented" in body["note"]
        assert len(body["errors"]) == len(module.NEWS_BASKET)


class TestWiring:
    def test_the_view_is_wired_into_the_workspace(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "templates" / "index.html").read_text(encoding="utf-8")
        assert 'data-view="news"' in source
        assert 'id="news-list"' in source
        assert "/static/js/news_view.js" in source
        group_start = source.index('id="nav-more-group"')
        assert source.index('data-view="news"') < group_start, "News is a primary nav item, outside the More group"
        assert source.index('data-view="game"') > source.index('id="nav-more-group"'), "Bored? stays inside the group"
        server = (root / "loki" / "api" / "server.py").read_text(encoding="utf-8")
        assert "news_desk_router" in server
