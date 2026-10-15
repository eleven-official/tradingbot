"""Read-only live market snapshots from Binance Spot's public REST API.

This adapter intentionally uses only public market-data endpoints.  It has no
credential handling, account access, or order-submission code.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from math import isfinite, sqrt
from statistics import fmean, pstdev
from time import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import re


BINANCE_SPOT_URL = "https://api.binance.com"
ALLOWED_INTERVALS = frozenset({"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d"})
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]{5,20}$")
_CACHE_TTL_SECONDS = 10.0
_snapshot_cache: dict[tuple[str, str], tuple[float, "MarketSnapshot"]] = {}


class MarketDataError(RuntimeError):
    """A public market-data response was unavailable or malformed."""


@dataclass(frozen=True)
class MarketSnapshot:
    """A compact, provider-neutral snapshot used to pre-fill Scout inputs."""

    provider: str
    symbol: str
    interval: str
    observed_at: float
    data_age_seconds: float
    current_price: float
    bid_price: float
    ask_price: float
    spread_percent: float
    change_24h_percent: float
    trend: str
    volatility_percent: float
    volume_ratio: float
    candle_count: int


def _validate_symbol(symbol: str) -> str:
    normalized = str(symbol).upper().strip()
    if not SYMBOL_PATTERN.fullmatch(normalized):
        raise MarketDataError("symbol must contain 5-20 uppercase letters or digits, for example BTCUSDT")
    return normalized


def _validate_interval(interval: str) -> str:
    normalized = str(interval).strip()
    if normalized not in ALLOWED_INTERVALS:
        raise MarketDataError("interval is not supported by the Binance Spot snapshot adapter")
    return normalized


def _fetch_json(path: str, params: dict[str, Any]) -> Any:
    url = f"{BINANCE_SPOT_URL}{path}?{urlencode(params)}"
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "LokiPaperScout/1.0"})
    try:
        with urlopen(request, timeout=5) as response:
            payload = response.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise MarketDataError("Binance Spot market data is temporarily unavailable") from error
    try:
        return json.loads(payload)
    except json.JSONDecodeError as error:
        raise MarketDataError("Binance Spot returned an invalid market-data response") from error


def _number(name: str, value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise MarketDataError(f"Binance Spot response has an invalid {name}") from error
    if not isfinite(number):
        raise MarketDataError(f"Binance Spot response has a non-finite {name}")
    return number


def _extract_candles(payload: Any) -> tuple[list[float], list[float]]:
    if not isinstance(payload, list) or len(payload) < 22:
        raise MarketDataError("Binance Spot returned too few candles to assess the market")
    try:
        closes = [_number("candle close", candle[4]) for candle in payload]
        volumes = [_number("candle volume", candle[5]) for candle in payload]
    except (IndexError, TypeError) as error:
        raise MarketDataError("Binance Spot returned malformed candle data") from error
    if any(close <= 0 for close in closes) or any(volume < 0 for volume in volumes):
        raise MarketDataError("Binance Spot returned invalid candle values")
    return closes, volumes


def _trend(closes: list[float]) -> str:
    fast_average = fmean(closes[-8:])
    slow_average = fmean(closes[-20:])
    deviation_percent = (fast_average - slow_average) / slow_average * 100
    if deviation_percent > 0.1:
        return "BULLISH"
    if deviation_percent < -0.1:
        return "BEARISH"
    return "NEUTRAL"


def _volatility_percent(closes: list[float]) -> float:
    returns = [(right / left - 1) * 100 for left, right in zip(closes, closes[1:]) if left > 0]
    return pstdev(returns) if len(returns) > 1 else 0.0


def _volume_ratio(volumes: list[float]) -> float:
    latest_closed_volume = volumes[-2]
    baseline = fmean(volumes[-22:-2])
    return latest_closed_volume / baseline if baseline > 0 else 1.0


def get_binance_spot_snapshot(symbol: str, interval: str = "1m") -> MarketSnapshot:
    """Fetch a read-only public snapshot and cache it briefly to respect limits."""
    symbol = _validate_symbol(symbol)
    interval = _validate_interval(interval)
    cache_key = (symbol, interval)
    now = time()
    cached = _snapshot_cache.get(cache_key)
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    ticker = _fetch_json("/api/v3/ticker/24hr", {"symbol": symbol})
    book = _fetch_json("/api/v3/ticker/bookTicker", {"symbol": symbol})
    candles = _fetch_json("/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": 30})
    if not isinstance(ticker, dict) or not isinstance(book, dict):
        raise MarketDataError("Binance Spot returned an unexpected ticker response")

    bid = _number("bid price", book.get("bidPrice"))
    ask = _number("ask price", book.get("askPrice"))
    current_price = _number("last price", ticker.get("lastPrice"))
    close_time_seconds = _number("ticker close time", ticker.get("closeTime")) / 1000
    if bid <= 0 or ask <= 0 or current_price <= 0 or ask < bid:
        raise MarketDataError("Binance Spot returned an invalid bid, ask, or last price")

    closes, volumes = _extract_candles(candles)
    snapshot = MarketSnapshot(
        provider="Binance Spot public market data",
        symbol=symbol,
        interval=interval,
        observed_at=now,
        data_age_seconds=max(0.0, now - close_time_seconds),
        current_price=current_price,
        bid_price=bid,
        ask_price=ask,
        spread_percent=(ask - bid) / ((ask + bid) / 2) * 100,
        change_24h_percent=_number("24h price change", ticker.get("priceChangePercent")),
        trend=_trend(closes),
        volatility_percent=_volatility_percent(closes),
        volume_ratio=_volume_ratio(volumes),
        candle_count=len(closes),
    )
    _snapshot_cache[cache_key] = (now, snapshot)
    return snapshot

