"""USD/AUD falls back to the Yahoo quote when the primary FX feed fails."""

import urllib.request

from loki.api import market_feed, server


def test_fx_uses_yahoo_when_frankfurter_is_down(monkeypatch):
    def down(*args, **kwargs):
        raise OSError("frankfurter unreachable")

    monkeypatch.setattr(urllib.request, "urlopen", down)
    monkeypatch.setattr(market_feed, "fetch_quote", lambda symbol: {"price": 1.47} if symbol == "AUD=X" else {})
    assert server._fetch_usd_aud_sync() == 1.47
