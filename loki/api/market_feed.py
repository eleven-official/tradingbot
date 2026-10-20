"""Read-only public market quotes for the watchtower.

Crypto pairs are served by Binance Spot's public REST API through the same
adapter the market-snapshot dashboard already uses. Every other instrument
(equities, indices, commodities, FX) is served by Yahoo Finance's public
chart endpoint, using only the standard library. No credentials, no orders,
no advice.

A quote answers "what did the public market show last?" — it never asserts
what a market will do next. When a provider is unreachable or answers
something unusable, the failure is reported for that symbol instead of
being silently papered over, so a card that looks stale LOOKS stale.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from loki.api.binance_market_data import (
    MarketDataError,
    get_binance_spot_snapshot,
)

CRYPTO_PATTERN = re.compile(r"^[A-Z0-9]{2,10}/[A-Z0-9]{2,10}$")
INSTRUMENT_PATTERN = re.compile(r"^[A-Z0-9^.=\-/]{1,15}$")
MAX_WATCH_SYMBOLS = 8
MAX_NEWS_ITEMS = 10
QUOTE_TTL_SECONDS = 75.0
NEWS_TTL_SECONDS = 600.0
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
YAHOO_SEARCH_URL = "https://query1.finance.yahoo.com/v1/finance/search"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; LokiWatchtower/1.0; read-only anonymous quotes)",
    "Accept": "application/json",
}

_quote_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_news_cache: dict[str, tuple[float, dict[str, Any]]] = {}


class MarketFeedError(RuntimeError):
    """A public data provider was unreachable or answered something unusable."""


def normalize_symbol(symbol: str) -> str:
    """Uppercase and boundary-check one instrument identifier."""
    text = str(symbol).strip().upper()
    if not INSTRUMENT_PATTERN.fullmatch(text):
        raise MarketFeedError(
            "Use an instrument identifier of 1-15 letters, digits, or ^ . = - / separators"
        )
    return text


def classify_symbol(symbol: str) -> str:
    """Return 'binance' for crypto pairs and 'yahoo' for everything else."""
    normalized = normalize_symbol(symbol)
    if CRYPTO_PATTERN.fullmatch(normalized):
        return "binance"
    return "yahoo"


@dataclass(frozen=True)
class Quote:
    provider: str
    symbol: str
    price: float
    currency: str
    change_pct: float | None
    spark: tuple[float, ...]
    observed_at: float


def fetch_quote(symbol: str) -> dict[str, Any]:
    """One normalized public quote, cached briefly per symbol."""
    normalized = normalize_symbol(symbol)
    provider = classify_symbol(normalized)
    key = f"{provider}:{normalized}"
    now = time.time()
    cached = _quote_cache.get(key)
    if cached is not None and now - cached[0] < QUOTE_TTL_SECONDS:
        return dict(cached[1])
    if provider == "binance":
        fresh = _fetch_binance_quote(normalized)
    else:
        fresh = _fetch_yahoo_quote(normalized)
    _quote_cache[key] = (now, fresh)
    return dict(fresh)


USD_QUOTE_ALIASES = {"USD", "USDT", "USDC", "FDUSD", "BUSD", "TUSD"}

# Yahoo's public search attaches headlines to instrument NAMES (q=Bitcoin),
# not ticker spellings (q=BTC-USD answers zero news). These are the public
# names of the busiest crypto bases; rarer pairs simply fall back to the
# ticker form and show an honest "no headlines" state when it answers none.
CRYPTO_NAMES: dict[str, str] = {
    "BTC": "Bitcoin",
    "ETH": "Ethereum",
    "SOL": "Solana",
    "XRP": "XRP",
    "DOGE": "Dogecoin",
    "ADA": "Cardano",
    "LTC": "Litecoin",
    "BNB": "Binance Coin",
    "DOT": "Polkadot",
    "AVAX": "Avalanche",
    "LINK": "Chainlink",
    "MATIC": "Polygon",
}


def _search_query(symbol: str) -> str:
    """Public name for crypto majors; ticker spelling for everything else."""
    base, _, quote = symbol.partition("/")
    if base and quote:
        name = CRYPTO_NAMES.get(base)
        if name:
            return name
        return f"{base}-{'USD' if quote in USD_QUOTE_ALIASES else quote}"
    return symbol


def fetch_headlines(symbol: str, limit: int) -> dict[str, Any]:
    """Public headlines for one instrument, cached for about ten minutes."""
    normalized = normalize_symbol(symbol)
    now = time.time()
    key = f"{normalized}:{limit}"
    cached = _news_cache.get(key)
    if cached is not None and now - cached[0] < NEWS_TTL_SECONDS:
        return dict(cached[1])
    url = (
        f"{YAHOO_SEARCH_URL}?{urlencode({'q': quote(_search_query(normalized), safe='') , 'quotesCount': 0, 'newsCount': min(limit, MAX_NEWS_ITEMS) } )}"
    )
    payload = _http_json(url)
    try:
        raw_news = payload["news"]
        items: list[dict[str, Any]] = []
        for entry in raw_news:
            if not isinstance(entry, dict):
                continue
            title = str(entry.get("title") or "").strip()
            link = str(entry.get("link") or "").strip()
            if not title or not link:
                continue
            items.append(
                {
                    "title": title,
                    "publisher": str(entry.get("publisher") or "").strip(),
                    "link": link,
                    "published_at": float(entry.get("providerPublishTime") or 0.0),
                }
            )
            if len(items) >= limit:
                break
    except (KeyError, TypeError, AttributeError) as error:
        raise MarketFeedError("the public headlines feed answered unusable data") from error
    _news_cache[key] = (now, {"items": items})
    return {"items": items}


def _http_json(url: str, timeout: float = 8.0) -> Any:
    request = Request(url, headers=_HEADERS)
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise MarketFeedError(f"public data provider answered HTTP {error.code}") from error
    except (URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise MarketFeedError("public data provider unreachable") from error


def _fetch_binance_quote(symbol: str) -> dict[str, Any]:
    """Binance pairs use the snapshot adapter already shipped with the site."""
    try:
        snapshot = get_binance_spot_snapshot(symbol.replace("/", ""), "1m")
    except MarketDataError as error:
        raise MarketFeedError(str(error)) from error
    spark = tuple(float(candle["close"]) for candle in snapshot.candles[-8:])
    base, _, quote_currency = symbol.partition("/")
    return asdict(
        Quote(
            provider="Binance Spot public API",
            symbol=snapshot.symbol,  # full pair form, e.g. BTCUSDT
            price=float(snapshot.current_price),
            currency=quote_currency or "USDT",
            change_pct=float(snapshot.change_24h_percent),
            spark=spark,
            observed_at=float(snapshot.observed_at),
        )
    )


def _fetch_yahoo_quote(symbol: str) -> dict[str, Any]:
    """Public chart feed: last daily closes power both price and spark."""
    url = f"{YAHOO_CHART_URL}/{quote(symbol, safe='')}?{urlencode({'range': '5d', 'interval': '1d', 'includePrePost': 'false'})}"
    try:
        payload = _http_json(url)
        result = payload["chart"]["result"]
        if isinstance(result, list) and len(result) == 1:
            result = result[0]
        meta = result["meta"]
        price = float(meta["regularMarketPrice"])
        raw_closes: Iterable[Any] = result["indicators"]["quote"][0].get("close") or []
        closes = [float(close) for close in raw_closes if close is not None]
        if not closes:
            raise KeyError("closes")
        reference = float(meta.get("previousClose") or (closes[-2] if len(closes) >= 2 else closes[-1]))
        change_pct = ((price - reference) / reference * 100.0) if reference else None
        quote_value = str(meta.get("currency") or "")
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise MarketFeedError(f"no usable public quote for {symbol}") from error
    return asdict(
        Quote(
            provider="Yahoo Finance public chart",
            symbol=str(meta.get("symbol") or symbol),
            price=price,
            currency=quote_value or "USD",
            change_pct=change_pct,
            spark=tuple(closes[-8:]),
            observed_at=time.time(),
        )
    )


def quote_or_failure(symbol: str, label: str | None = None) -> dict[str, Any]:
    """Convert one provider call into either a quote or an honest failure."""
    try:
        normalized = normalize_symbol(symbol)
        result = fetch_quote(normalized)
    except (MarketFeedError, MarketDataError) as error:
        try:
            normalized = normalize_symbol(symbol)
        except (MarketFeedError, MarketDataError):
            normalized = str(symbol).strip().upper()
        return {
            "symbol": normalized,
            "label": label,
            "ok": False,
            "error": str(error),
            "provider": None,
        }
    result = dict(result)
    # The route reports the symbol the visitor asked for; provider-native
    # spellings (BTCUSDT, AAPL) stay inside the provider rows.
    result["symbol"] = normalized
    result["label"] = label
    result["ok"] = True
    return result
