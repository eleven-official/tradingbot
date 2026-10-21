"""Display-currency reference rate endpoint: server-side fetch, cached, honest liveness."""

from fastapi.testclient import TestClient

import loki.api.server as server_module
from loki.api.server import app

client = TestClient(app)


class TestFxRate:
    def test_single_fetch_served_from_cache(self, monkeypatch):
        monkeypatch.setattr(server_module, "_FX_CACHE", {})
        calls = []

        def fake_fetch():
            calls.append(1)
            return 1.5321

        monkeypatch.setattr(server_module, "_fetch_usd_aud_sync", fake_fetch)
        first = client.get("/api/fx/rate")
        second = client.get("/api/fx/rate")
        assert first.status_code == 200
        assert first.json() == {"from": "USD", "to": "AUD", "rate": 1.5321, "live": True}
        assert second.json() == first.json()
        assert len(calls) == 1  # second call is served from the cache

    def test_outage_returns_stale_rate_flagged_not_live(self, monkeypatch):
        stale = (-1e12, 1.5555)  # far in the past: outside the TTL
        monkeypatch.setattr(server_module, "_FX_CACHE", {"usd_aud": stale})

        def broken_fetch():
            raise OSError("rate service down")

        monkeypatch.setattr(server_module, "_fetch_usd_aud_sync", broken_fetch)
        response = client.get("/api/fx/rate")
        assert response.status_code == 200
        body = response.json()
        assert body["rate"] == 1.5555
        assert body["live"] is False  # honesty flag: not a fresh quote

    def test_outage_without_cache_returns_fallback_not_live(self, monkeypatch):
        monkeypatch.setattr(server_module, "_FX_CACHE", {})

        def broken_fetch():
            raise OSError("rate service down")

        monkeypatch.setattr(server_module, "_fetch_usd_aud_sync", broken_fetch)
        response = client.get("/api/fx/rate")
        assert response.status_code == 200
        body = response.json()
        assert body["rate"] > 0
        assert body["live"] is False

    def test_provider_fetch_carries_a_user_agent(self, monkeypatch):
        # frankfurter.app answers HTTP 403 to python's stock User-Agent, which
        # silently pinned the currency bar to the fallback rate. The request
        # must identify itself, exactly like the other public feeds.
        captured = {}

        class FakeResponse:
            def read(self):
                return b'{"rates": {"AUD": 1.4317}}'

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake_urlopen(request, timeout=None):
            captured["headers"] = dict(getattr(request, "headers", {}) or {})
            captured["url"] = getattr(request, "full_url", "")
            return FakeResponse()

        monkeypatch.setattr(server_module.urllib.request, "urlopen", fake_urlopen)
        assert server_module._fetch_usd_aud_sync() == 1.4317
        assert captured["url"].startswith("https://api.frankfurter.app/latest")
        user_agent = captured["headers"].get("User-agent", "")
        assert "LokiWorkspace" in user_agent, f"frankfurter must receive an identifying UA: {captured['headers']}"
