"""LOKI v8 — unified market-data layer.

A single provider that fetches OHLCV bars and live quotes for US stocks,
crypto, and NSE instruments. yfinance is the default (free) source; the
provider is structured so Alpaca/Binance/Kite adapters can be dropped in
later without touching the rest of the engine.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd

# Point TLS libraries at a known CA bundle (silences cert-verify warnings on
# this machine; data still flows without it, but this keeps it clean).
try:
    import certifi  # type: ignore
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("CURL_CA_BUNDLE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
except Exception:  # noqa: BLE001
    pass

logger = logging.getLogger(__name__)

OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]

# Map a friendly instrument class to the yfinance ticker form.
# Crypto uses Yahoo's "-USD" convention; NSE uses ".NS" / "^NSEI".
_CRYPTO_BASE = {"BTC", "ETH", "SOL", "ADA", "XRP", "DOGE", "LINK", "MATIC", "AVAX", "DOT"}


def normalize_symbol(symbol: str) -> str:
    """Normalize a user-supplied symbol to the yfinance ticker."""
    s = symbol.strip().upper()
    if s.endswith("USDT") or s.endswith("USD"):
        return s[:-3] + "-USD" if s.endswith("USDT") else s
    if s in _CRYPTO_BASE:
        return f"{s}-USD"
    return s


def is_crypto(symbol: str) -> bool:
    return symbol.endswith("-USD") or symbol.endswith("USDT")


def is_nse(symbol: str) -> bool:
    return symbol.endswith(".NS") or symbol.startswith("^")


class MarketDataProvider:
    """Fetches historical bars and live quotes with a small cache."""

    def __init__(self):
        self._cache: Dict[str, pd.DataFrame] = {}

    # ------------------------------------------------------------------
    # Historical bars
    # ------------------------------------------------------------------
    def fetch_history(self, symbol: str, period: str = "2y",
                      interval: str = "1d") -> pd.DataFrame:
        """Return normalized OHLCV DataFrame (datetime index)."""
        ticker = normalize_symbol(symbol)
        cache_key = f"{ticker}:{period}:{interval}"
        if cache_key in self._cache:
            return self._cache[cache_key].copy()

        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError("yfinance is not installed") from exc

        df = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=False)
        if df is None or df.empty:
            logger.warning("No data for %s", ticker)
            return pd.DataFrame(columns=OHLCV_COLUMNS)

        df = df.rename(columns={c: c.lower() for c in df.columns})
        keep = [c for c in OHLCV_COLUMNS if c in df.columns]
        df = df[keep].copy()
        df.index = pd.to_datetime(df.index)
        df.index.name = "datetime"
        df = df[~df.index.duplicated(keep="last")].sort_index()
        self._cache[cache_key] = df
        return df.copy()

    # ------------------------------------------------------------------
    # Live quote (polled; upgraded to streaming when keys are added)
    # ------------------------------------------------------------------
    def get_latest_price(self, symbol: str) -> float:
        """Return the most recent close/price for a symbol."""
        ticker = normalize_symbol(symbol)
        try:
            import yfinance as yf
            data = yf.Ticker(ticker).history(period="5d", interval="1d", auto_adjust=False)
            if data is not None and not data.empty:
                return float(data["Close"].iloc[-1])
        except Exception as exc:  # noqa: BLE001
            logger.warning("Latest-price fetch failed for %s: %s", ticker, exc)
        return 0.0

    def get_quotes(self, symbols: List[str]) -> Dict[str, float]:
        """Batch-fetch latest prices for many symbols."""
        import yfinance as yf
        tickers = [normalize_symbol(s) for s in symbols]
        quotes: Dict[str, float] = {}
        try:
            data = yf.download(tickers, period="5d", interval="1d",
                               group_by="ticker", auto_adjust=False, progress=False)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Batch quote fetch failed: %s", exc)
            return quotes

        for ticker in tickers:
            try:
                if len(tickers) == 1:
                    series = data["Close"]
                else:
                    series = data[ticker]["Close"]
                if series is not None and not series.dropna().empty:
                    quotes[ticker] = float(series.dropna().iloc[-1])
            except Exception:  # noqa: BLE001
                continue
        return quotes


_provider: Optional[MarketDataProvider] = None


def get_provider() -> MarketDataProvider:
    global _provider
    if _provider is None:
        _provider = MarketDataProvider()
    return _provider
