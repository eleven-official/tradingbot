"""Read-only live market snapshots from Binance Spot's public REST API.

This adapter intentionally uses only public market-data endpoints.  It has no
credential handling, account access, or order-submission code.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from math import isfinite
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
class StrategyCandidate:
    """A transparent checklist result, not a forecast or win probability."""

    key: str
    name: str
    score: int
    state: str
    summary: str
    evidence: tuple[str, ...]


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
    rsi_14: float
    ema_fast: float
    ema_slow: float
    selected_strategy: str
    setup_score: int
    setup_state: str
    strategy_candidates: tuple[StrategyCandidate, ...]
    candles: tuple[dict[str, float], ...]


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


def _extract_candles(payload: Any) -> tuple[list[dict[str, float]], list[float], list[float]]:
    if not isinstance(payload, list) or len(payload) < 22:
        raise MarketDataError("Binance Spot returned too few candles to assess the market")
    try:
        # Exclude Binance's current, still-forming candle from the strategy
        # readout so indicator values only use completed bars.
        completed = payload[:-1]
        candles = [
            {
                "time": _number("candle time", candle[0]) / 1000,
                "open": _number("candle open", candle[1]),
                "high": _number("candle high", candle[2]),
                "low": _number("candle low", candle[3]),
                "close": _number("candle close", candle[4]),
                "volume": _number("candle volume", candle[5]),
            }
            for candle in completed
        ]
    except (IndexError, TypeError) as error:
        raise MarketDataError("Binance Spot returned malformed candle data") from error
    if any(
        candle["low"] <= 0
        or candle["volume"] < 0
        or candle["high"] < max(candle["open"], candle["close"])
        or candle["low"] > min(candle["open"], candle["close"])
        for candle in candles
    ):
        raise MarketDataError("Binance Spot returned invalid candle values")
    closes = [candle["close"] for candle in candles]
    volumes = [candle["volume"] for candle in candles]
    return candles, closes, volumes


def _ema(values: list[float], period: int) -> float:
    alpha = 2 / (period + 1)
    current = values[0]
    for value in values[1:]:
        current = alpha * value + (1 - alpha) * current
    return current


def _rsi(values: list[float], period: int = 14) -> float:
    changes = [right - left for left, right in zip(values, values[1:])][-period:]
    if not changes:
        return 50.0
    gains = [change for change in changes if change > 0]
    losses = [-change for change in changes if change < 0]
    average_gain = fmean(gains) if gains else 0.0
    average_loss = fmean(losses) if losses else 0.0
    if average_loss == 0:
        return 100.0 if average_gain else 50.0
    relative_strength = average_gain / average_loss
    return 100 - 100 / (1 + relative_strength)


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
    latest_closed_volume = volumes[-1]
    baseline = fmean(volumes[-21:-1])
    return latest_closed_volume / baseline if baseline > 0 else 1.0


def _strategy_candidates(
    candles: list[dict[str, float]],
    closes: list[float],
    trend: str,
    volume_ratio: float,
    rsi_14: float,
    ema_fast: float,
    ema_slow: float,
) -> tuple[StrategyCandidate, ...]:
    """Score four simple setups by matched rules; scores are not probabilities."""
    latest = candles[-1]
    previous = candles[-2]
    recent = closes[-20:]
    average = fmean(recent)
    deviation = pstdev(recent)
    lower_band = average - 2 * deviation
    prior_high = max(candle["high"] for candle in candles[-21:-1])
    last_five_high = max(closes[-6:-1])

    checks = {
        "trend_continuation": (
            "Trend continuation",
            [
                (latest["close"] > ema_fast, "Close is above the fast EMA."),
                (ema_fast > ema_slow, "Fast EMA is above the slow EMA."),
                (50 <= rsi_14 <= 70, "RSI is in the momentum zone (50–70)."),
                (volume_ratio >= 0.8, "Participation is at least 0.8× baseline."),
                (latest["close"] > latest["open"], "The latest completed candle closed green."),
            ],
        ),
        "pullback_continuation": (
            "Trend pullback",
            [
                (ema_fast > ema_slow, "Fast EMA is above the slow EMA."),
                (latest["close"] <= ema_fast, "Close has pulled back to the fast EMA."),
                (latest["close"] > ema_slow, "Close remains above the slow EMA."),
                (40 <= rsi_14 <= 58, "RSI is in the pullback zone (40–58)."),
                (volume_ratio >= 0.7, "Participation is at least 0.7× baseline."),
            ],
        ),
        "breakout": (
            "Range breakout",
            [
                (latest["close"] > prior_high, "Close cleared the prior 20-bar high."),
                (volume_ratio >= 1.2, "Volume is at least 1.2× baseline."),
                (ema_fast > ema_slow, "Fast EMA is above the slow EMA."),
                (latest["close"] > latest["open"], "The breakout candle closed green."),
                (latest["close"] > last_five_high, "Close is above the prior five closes."),
            ],
        ),
        "mean_reversion": (
            "Oversold reversion",
            [
                (rsi_14 <= 35, "RSI is oversold (35 or lower)."),
                (latest["close"] <= lower_band, "Close reached the lower 20-bar band."),
                (trend != "BEARISH", "Trend is not classified as bearish."),
                (volume_ratio >= 0.8, "Participation is at least 0.8× baseline."),
                (latest["close"] > latest["open"] or latest["low"] < previous["low"], "Price showed a reversal attempt."),
            ],
        ),
    }

    candidates = []
    for key, (name, rules) in checks.items():
        passed = [description for matched, description in rules if matched]
        score = round(len(passed) / len(rules) * 100)
        state = "IN_FOCUS" if score >= 80 else "WATCH" if score >= 60 else "NO_SETUP"
        summary = f"{len(passed)} of {len(rules)} checklist rules match."
        candidates.append(
            StrategyCandidate(
                key=key,
                name=name,
                score=score,
                state=state,
                summary=summary,
                evidence=tuple(
                    f"{'PASS' if matched else 'MISS'} · {description}"
                    for matched, description in rules
                ),
            )
        )
    candidates.sort(key=lambda candidate: (-candidate.score, candidate.key))
    return tuple(candidates)


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

    candle_rows, closes, volumes = _extract_candles(candles)
    volume_ratio = _volume_ratio(volumes)
    fast_ema = _ema(closes, 8)
    slow_ema = _ema(closes, 20)
    trend = _trend(closes)
    rsi_14 = _rsi(closes)
    candidates = _strategy_candidates(
        candle_rows, closes, trend, volume_ratio, rsi_14, fast_ema, slow_ema
    )
    best_candidate = candidates[0]
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
        trend=trend,
        volatility_percent=_volatility_percent(closes),
        volume_ratio=volume_ratio,
        candle_count=len(candles),
        rsi_14=rsi_14,
        ema_fast=fast_ema,
        ema_slow=slow_ema,
        selected_strategy=best_candidate.key,
        setup_score=best_candidate.score,
        setup_state=best_candidate.state,
        strategy_candidates=candidates,
        candles=tuple(candle_rows),
    )
    _snapshot_cache[cache_key] = (now, snapshot)
    return snapshot




def get_binance_spot_history(
    symbol: str, interval: str = "1h", limit: int = 500
) -> tuple[dict[str, float], ...]:
    """Fetch recent completed candles from Binance Spot's public endpoint."""
    normalized_symbol = _validate_symbol(symbol)
    normalized_interval = _validate_interval(interval)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 120 <= limit <= 1000:
        raise MarketDataError("history bars must be between 120 and 1000")
    payload = _fetch_json(
        "/api/v3/klines",
        {"symbol": normalized_symbol, "interval": normalized_interval, "limit": limit},
    )
    if not isinstance(payload, list):
        raise MarketDataError("Binance Spot returned an unexpected candle response")

    now_ms = time() * 1000
    candles: list[dict[str, float]] = []
    previous_time = -1.0
    for row in payload:
        if not isinstance(row, (list, tuple)) or len(row) < 7:
            raise MarketDataError("Binance Spot returned malformed candle data")
        candle_time = _number("candle time", row[0]) / 1000
        close_time_ms = _number("candle close time", row[6])
        open_price = _number("candle open", row[1])
        high_price = _number("candle high", row[2])
        low_price = _number("candle low", row[3])
        close_price = _number("candle close", row[4])
        volume = _number("candle volume", row[5])
        if close_time_ms > now_ms:
            continue
        if candle_time <= previous_time:
            raise MarketDataError("Binance Spot returned candles out of chronological order")
        if (
            candle_time < 0
            or min(open_price, high_price, low_price, close_price) <= 0
            or volume < 0
            or high_price < max(open_price, close_price)
            or low_price > min(open_price, close_price)
            or high_price < low_price
        ):
            raise MarketDataError("Binance Spot returned invalid candle values")
        previous_time = candle_time
        candles.append(
            {
                "time": candle_time,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": volume,
            }
        )
    if len(candles) < 100:
        raise MarketDataError("Binance Spot returned too few completed candles for a replay")
    return tuple(candles)
