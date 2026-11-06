"""Bounded daily research history; never silently substitute data providers."""
from datetime import datetime, timedelta, timezone
import re
import threading
import time
from typing import Any

HISTORY_YEARS = (5, 10, 15, 20)
MAX_HISTORY_BARS = 10000
_recent_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_recent_lock = threading.Lock()
RECENT_TTL_SECONDS = 300


def yahoo_history(symbol, years):
    if not re.fullmatch(r"[A-Z][A-Z0-9.]{0,9}", symbol) or years not in HISTORY_YEARS:
        raise ValueError("Choose a US equity symbol and a 5, 10, 15 or 20-year window")
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=round(years * 365.25))
    return _yahoo_rows(symbol,start,end)


def _yahoo_rows(symbol,start,end):
    import yfinance as yf
    try:
        frame = yf.Ticker(symbol).history(start=start.isoformat(), end=end.isoformat(),
                                         auto_adjust=False, actions=False, timeout=20)
    except Exception:
        raise ConnectionError("Yahoo research history is unavailable; no substitute data was used") from None
    if frame is None or frame.empty:
        raise ConnectionError("Yahoo returned no daily research history; no substitute data was used")
    if len(frame) > MAX_HISTORY_BARS:
        raise ValueError("Daily research history exceeded the 10000-bar limit")
    required = {"Open", "High", "Low", "Close", "Volume"}
    if not required <= set(frame.columns):
        raise ValueError("Yahoo daily history is missing required OHLCV columns")
    return [{"timestamp": stamp.date().isoformat(), "open": float(row["Open"]),
             "high": float(row["High"]), "low": float(row["Low"]),
             "close": float(row["Close"]), "volume": float(row["Volume"])}
             for stamp, row in frame.iterrows() if stamp.date() < end]


def yahoo_recent_history(symbol):
    if symbol not in {'SPY','QQQ','AAPL','MSFT','NVDA','TSLA'}:
        raise ValueError('Automatic daily forecasts support the trained liquid equity/ETF symbols only')
    with _recent_lock:
        cached=_recent_cache.get(symbol)
        if cached and time.monotonic()-cached[0]<RECENT_TTL_SECONDS:
            return [dict(row) for row in cached[1]]
        end=datetime.now(timezone.utc).date()
        rows=_yahoo_rows(symbol,end-timedelta(days=90),end)
        if len(rows)<20:
            raise ConnectionError('Recent Yahoo daily history has fewer than 20 completed bars')
        last_date=datetime.fromisoformat(rows[-1]['timestamp']).date()
        if (end-last_date).days>5:
            raise ConnectionError('Recent daily history is stale; no current estimate was produced')
        _recent_cache[symbol]=(time.monotonic(),rows)
        return [dict(row) for row in rows]


YAHOO_SOURCE = {
    "provider": "Yahoo Finance via yfinance", "kind": "provider daily OHLCV",
    "adjustment": "vendor split-adjusted OHLC; auto_adjust=False; dividends excluded",
    "rights": "Private research subject to Yahoo/vendor terms; no redistribution rights inferred.",
    "limitation": "Not Alpaca execution history. Vendor revisions, adjustments and venue differences can affect signals; complete requested coverage is checked before training.",
}
