"""Public read-only watchtower endpoints: tracked quotes, market floor, headlines.

Every answer is an honest report about public market data. A symbol the
provider cannot serve comes back as a failed item with a reason — the
endpoint never invents a number, hides a degraded card, or pretends a
cache is live. None of this sends orders or holds credentials.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response

from loki.api.market_feed import (
    MAX_NEWS_ITEMS,
    MAX_WATCH_SYMBOLS,
    MarketFeedError,
    fetch_headlines,
    normalize_symbol,
    quote_or_failure,
)

router = APIRouter(prefix="/api", tags=["Watchtower"])

# The market floor is a fixed, public, pre-declared basket: any visitor sees
# the same honest context, and no request body can change the definition.
MARKET_FLOOR: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    ("Crypto majors", (
        ("BTC/USDT", "Bitcoin"),
        ("ETH/USDT", "Ethereum"),
        ("SOL/USDT", "Solana"),
    )),
    ("Mega-cap tech", (
        ("AAPL", "Apple"),
        ("MSFT", "Microsoft"),
        ("NVDA", "Nvidia"),
    )),
    ("US indices", (
        ("^GSPC", "S&P 500"),
        ("^IXIC", "Nasdaq"),
        ("^DJI", "Dow Jones"),
    )),
    ("Commodities", (
        ("GC=F", "Gold futures"),
        ("CL=F", "Oil (WTI)"),
    )),
    ("FX & havens", (
        ("EURUSD=X", "EUR/USD"),
        ("DX-Y.NYB", "Dollar index"),
    )),
)


def _clean_symbol_list(raw: str) -> list[str]:
    """Uppercase, de-duplicate, and cap a comma-separated symbol list."""
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if not parts:
        raise HTTPException(status_code=422, detail="Add at least one instrument symbol.")
    normalized: list[str] = []
    for part in parts:
        try:
            symbol = normalize_symbol(part)
        except MarketFeedError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if symbol not in normalized:
            normalized.append(symbol)
    if len(normalized) > MAX_WATCH_SYMBOLS:
        raise HTTPException(
            status_code=422,
            detail=f"Keep the watchtower at {MAX_WATCH_SYMBOLS} instruments or fewer.",
        )
    return normalized


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.get("/watch-quotes")
def watch_quotes(response: Response, symbols: str = Query(default="", max_length=240)) -> dict[str, Any]:
    """Live public quotes for the visitor's tracked symbols, failures included."""
    wanted = _clean_symbol_list(symbols)
    items = []
    for symbol in wanted:
        item = quote_or_failure(symbol)
        item.pop("label", None)
        items.append(item)
    degraded = sum(1 for item in items if not item["ok"])
    _no_store(response)
    return {
        "mode": "public-market-quotes",
        "count": len(items),
        "degraded": degraded,
        "items": items,
        "note": (
            "Live public quotes: crypto pairs via Binance Spot's public API, other "
            "instruments via Yahoo Finance's public chart feed, cached briefly per "
            "symbol. Read-only market context — it never sends orders and is not advice."
        ),
    }


@router.get("/watch-heatmap")
def watch_heatmap(response: Response) -> dict[str, Any]:
    """Fixed public baskets fetched in parallel; nothing here is curated advice."""
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            symbol: pool.submit(quote_or_failure, symbol, label)
            for _, members in MARKET_FLOOR
            for symbol, label in members
        }
    categories: list[dict[str, Any]] = []
    for category_label, members in MARKET_FLOOR:
        items = []
        for symbol, label in members:
            try:
                items.append(futures[symbol].result())
            except Exception as error:  # pragma: no cover - defensive only
                items.append(
                    {
                        "symbol": symbol,
                        "label": label,
                        "ok": False,
                        "error": f"quote assembly failed: {error}",
                        "provider": None,
                    }
                )
        categories.append({"label": category_label, "items": items})
    _no_store(response)
    return {
        "mode": "public-market-heatmap",
        "categories": categories,
        "note": (
            "The market floor is a fixed public basket (crypto majors, mega-cap tech, "
            "US indices, commodities, FX) served by Binance Spot and Yahoo Finance, "
            "cached briefly per symbol. It shows what the market DID last — it is "
            "context, never advice, and individual symbols can be unavailable."
        ),
    }


@router.get("/signal-feed")
def signal_feed(
    response: Response,
    symbol: str = Query(default="AAPL", max_length=16),
    limit: int = Query(default=6, ge=1, le=MAX_NEWS_ITEMS),
) -> dict[str, Any]:
    """Public headlines for one instrument; honesty over availability."""
    try:
        normalized = normalize_symbol(symbol)
        payload = fetch_headlines(normalized, limit)
    except MarketFeedError as error:
        _no_store(response)
        return {
            "mode": "public-headlines-degraded",
            "symbol": str(symbol).strip().upper(),
            "items": [],
            "error": str(error),
            "note": "Public headline feed is unavailable right now — nothing was invented to fill in.",
        }
    _no_store(response)
    return {
        "mode": "public-headlines",
        "symbol": normalized,
        "items": payload["items"],
        "note": (
            "Public headlines via Yahoo Finance's public search feed, cached about "
            "ten minutes. Headlines are information, never advice."
        ),
    }
