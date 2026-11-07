"""Live markets board: a wide public basket refreshed every few seconds.

Crypto pairs come from Binance Spot's public API (genuinely live); stocks,
indices, commodities and FX come from Yahoo Finance's public chart feed
(near-live, can lag by minutes). Every symbol is fetched in parallel and a
provider failure stays visible on its own tile — nothing is invented.

Market session chips are computed from the clock (regular hours only;
exchange holidays are not modelled and the copy says so).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Response

from loki.api.market_feed import MarketFeedError, normalize_symbol, quote_or_failure

router = APIRouter(prefix="/api/markets", tags=["Live markets"])

LIVE_MAX_AGE_SECONDS = 12.0
REFRESH_SECONDS = 15
MAX_CUSTOM_SYMBOLS = 20

LIVE_BOARD: Tuple[Tuple[str, str, Tuple[Tuple[str, str], ...]], ...] = (
    ("crypto", "Crypto", (
        ("BTC/USDT", "Bitcoin"),
        ("ETH/USDT", "Ethereum"),
        ("SOL/USDT", "Solana"),
        ("XRP/USDT", "XRP"),
        ("BNB/USDT", "BNB"),
        ("DOGE/USDT", "Dogecoin"),
        ("ADA/USDT", "Cardano"),
        ("AVAX/USDT", "Avalanche"),
    )),
    ("stocks", "US stocks", (
        ("AAPL", "Apple"),
        ("MSFT", "Microsoft"),
        ("NVDA", "Nvidia"),
        ("AMZN", "Amazon"),
        ("GOOGL", "Alphabet"),
        ("META", "Meta"),
        ("TSLA", "Tesla"),
        ("AMD", "AMD"),
    )),
    ("indices", "Indices & ETFs", (
        ("^GSPC", "S&P 500"),
        ("^IXIC", "Nasdaq"),
        ("^DJI", "Dow Jones"),
        ("^RUT", "Russell 2000"),
        ("^VIX", "VIX"),
        ("SPY", "SPY ETF"),
        ("QQQ", "QQQ ETF"),
    )),
    ("commodities", "Commodities", (
        ("GC=F", "Gold"),
        ("SI=F", "Silver"),
        ("CL=F", "Oil (WTI)"),
        ("NG=F", "Natural gas"),
    )),
    ("fx", "FX", (
        ("EURUSD=X", "EUR/USD"),
        ("GBPUSD=X", "GBP/USD"),
        ("USDJPY=X", "USD/JPY"),
        ("AUDUSD=X", "AUD/USD"),
        ("DX-Y.NYB", "Dollar index"),
    )),
)

_NY = ZoneInfo("America/New_York")


def market_sessions(now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Regular-hours session status for the markets on the board."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    ny = current.astimezone(_NY)
    minutes = ny.hour * 60 + ny.minute
    weekday = ny.weekday()  # Monday 0 .. Sunday 6

    if weekday >= 5:
        us_state, us_detail = "closed", "Weekend"
    elif 9 * 60 + 30 <= minutes < 16 * 60:
        us_state, us_detail = "open", "Regular session · closes 4:00 pm ET"
    elif 4 * 60 <= minutes < 9 * 60 + 30:
        us_state, us_detail = "pre", "Pre-market · opens 9:30 am ET"
    elif 16 * 60 <= minutes < 20 * 60:
        us_state, us_detail = "post", "After hours · closed for the day"
    else:
        us_state, us_detail = "closed", "Closed · opens 9:30 am ET"

    # Spot FX trades from Sunday 5 pm ET to Friday 5 pm ET.
    fx_open = not (
        weekday == 5
        or (weekday == 4 and minutes >= 17 * 60)
        or (weekday == 6 and minutes < 17 * 60)
    )
    return [
        {"market": "US stocks", "state": us_state, "detail": us_detail},
        {"market": "Crypto", "state": "open", "detail": "Trades 24/7"},
        {
            "market": "FX",
            "state": "open" if fx_open else "closed",
            "detail": "Sun 5 pm – Fri 5 pm ET" if fx_open else "Weekend · reopens Sun 5 pm ET",
        },
    ]


def _fetch_all(pairs: Sequence[Tuple[str, Optional[str]]]) -> List[Dict[str, Any]]:
    if not pairs:
        return []
    with ThreadPoolExecutor(max_workers=min(12, len(pairs))) as pool:
        futures = [pool.submit(quote_or_failure, sym, label, LIVE_MAX_AGE_SECONDS) for sym, label in pairs]
    items: List[Dict[str, Any]] = []
    for (sym, label), future in zip(pairs, futures):
        try:
            items.append(future.result())
        except Exception as error:  # pragma: no cover - defensive only
            items.append({"symbol": sym, "label": label, "ok": False, "error": str(error), "provider": None})
    return items


def movers(items: List[Dict[str, Any]], count: int = 3) -> Dict[str, List[Dict[str, Any]]]:
    """Biggest gainers and losers among tiles that answered with a change."""
    ranked = [
        item
        for item in items
        if item.get("ok") and isinstance(item.get("change_pct"), (int, float))
    ]
    ranked.sort(key=lambda item: item["change_pct"], reverse=True)
    gainers = [r for r in ranked if r["change_pct"] > 0][:count]
    losers = [r for r in reversed(ranked) if r["change_pct"] < 0][:count]
    return {"gainers": [_mover(r) for r in gainers], "losers": [_mover(r) for r in losers]}


def _mover(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "symbol": row["symbol"],
        "label": row.get("label"),
        "change_pct": row["change_pct"],
        "price": row.get("price"),
    }


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.get("/live")
def live_board(response: Response) -> Dict[str, Any]:
    pairs = [(sym, label) for _, _, members in LIVE_BOARD for sym, label in members]
    results = _fetch_all(pairs)
    by_symbol = {sym: item for (sym, _), item in zip(pairs, results)}
    categories = []
    for key, label, members in LIVE_BOARD:
        categories.append({"key": key, "label": label, "items": [by_symbol[sym] for sym, _ in members]})
    _no_store(response)
    return {
        "mode": "live-markets",
        "refresh_seconds": REFRESH_SECONDS,
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
        "sessions": market_sessions(),
        "categories": categories,
        "movers": movers(results),
        "degraded": sum(1 for item in results if not item.get("ok")),
        "note": (
            "Crypto via Binance Spot's public API (live). Stocks, indices, commodities and FX "
            "via Yahoo Finance's public chart feed (near-live; can lag by minutes). Session "
            "hours ignore exchange holidays. Market context only — never advice."
        ),
    }


@router.get("/quotes")
def live_quotes(response: Response, symbols: str = Query(default="", max_length=400)) -> Dict[str, Any]:
    wanted: List[str] = []
    for part in symbols.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            sym = normalize_symbol(part)
        except MarketFeedError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if sym not in wanted:
            wanted.append(sym)
    if len(wanted) > MAX_CUSTOM_SYMBOLS:
        raise HTTPException(status_code=422, detail=f"Keep a watchlist to {MAX_CUSTOM_SYMBOLS} symbols or fewer.")
    items = _fetch_all([(sym, None) for sym in wanted])
    _no_store(response)
    return {
        "mode": "live-quotes",
        "count": len(items),
        "items": items,
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
    }
