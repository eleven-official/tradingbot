"""Public market news desk: headlines from a fixed topic basket.

The basket is fixed, public and pre-declared ("what may move the tape"):
macro markets, the Fed, inflation, energy, semiconductors, Bitcoin. Every
headline comes from Yahoo Finance's public search feed — nothing invented,
nothing personalized, no order routing, no credentials. Partial failures are
reported term-by-term; an answer where every query failed says so instead of
serving an empty page as if the market stood still.

Theme and signal chips are plain keyword matches on the headline text, shown
so a reader skims faster. They are transparent string matching, not analysis,
and the endpoint says so in its note. Headlines are information, never advice.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, Query, Response

from loki.api.market_feed import MarketFeedError, latest_headlines_for_query

router = APIRouter(prefix="/api/news", tags=["News desk"])

# (search term, theme shown to the reader). Fixed basket — a request body
# never changes what the public gets.
NEWS_BASKET: Tuple[Tuple[str, str], ...] = (
    ("stock market", "markets"),
    ("Federal Reserve", "rates"),
    ("inflation", "inflation"),
    ("oil prices", "energy"),
    ("semiconductors", "chips"),
    ("Bitcoin", "crypto"),
)
PER_TERM_FETCH = 10
MAX_DESK_ITEMS = 24

# Plain keyword signals matched against each headline title. Case-insensitive
# substring matching on words — visible, deterministic, no model in the loop.
SIGNAL_PATTERNS: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    ("rates", re.compile(r"\b(fed|fomc|rate cut|rate hike|interest rate|yield|treasury)\w*", re.IGNORECASE)),
    ("inflation", re.compile(r"\b(cpi|inflation|ppi|pce|price index)\b", re.IGNORECASE)),
    ("jobs", re.compile(r"\b(jobs|payroll|unemployment|hiring)\b", re.IGNORECASE)),
    ("earnings", re.compile(r"\b(earnings|guidance|profit|revenue|quarterly)\b", re.IGNORECASE)),
    ("energy", re.compile(r"\b(oil|opec|crude|natural gas|gasoline)\w*", re.IGNORECASE)),
    ("chips", re.compile(r"\b(chip|chips|semiconductor|nvidia|amd|intel|taiwan)\w*", re.IGNORECASE)),
    ("crypto", re.compile(r"\b(bitcoin|crypto|ethereum|btc|etf)\w*", re.IGNORECASE)),
    ("tariffs", re.compile(r"\b(tariff|trade war|export control|sanction)\w*", re.IGNORECASE)),
)


def _signals_for_title(title: str) -> List[str]:
    hits = []
    for name, pattern in SIGNAL_PATTERNS:
        if pattern.search(title):
            hits.append(name)
    return hits


def _collect_basket() -> tuple[Dict[str, Dict[str, Any]], List[str]]:
    """Fetch every basket term in parallel; merge stories seen by two terms."""
    merged: Dict[str, Dict[str, Any]] = {}
    errors: List[str] = []
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="loki-news") as pool:
        results = list(
            pool.map(
                lambda entry: (entry, _safe_fetch(entry[0])),
                NEWS_BASKET,
            )
        )
    for (term, theme), payload in results:
        if isinstance(payload, MarketFeedError):
            errors.append(f"{term}: {payload}")
            continue
        for item in payload["items"]:
            link = item["link"]
            existing = merged.get(link)
            if existing is None:
                merged[link] = {
                    "title": item["title"],
                    "publisher": item["publisher"],
                    "link": link,
                    "published_at": item["published_at"],
                    "themes": [theme],
                    "signals": _signals_for_title(item["title"]),
                }
            elif theme not in existing["themes"]:
                existing["themes"].append(theme)
    return merged, errors


def _safe_fetch(term: str) -> Any:
    """A fetched item list, or the MarketFeedError itself — threads stay calm."""
    try:
        return latest_headlines_for_query(term, PER_TERM_FETCH)
    except MarketFeedError as error:
        return error


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.get("")
def news_desk(response: Response, limit: int = Query(default=MAX_DESK_ITEMS, ge=1, le=MAX_DESK_ITEMS)) -> dict[str, Any]:
    """Merged, deduplicated public headlines over the fixed topic basket."""
    merged, errors = _collect_basket()
    _no_store(response)
    if not merged:
        return {
            "mode": "news-desk-degraded",
            "items": [],
            "errors": errors,
            "note": (
                "Every public news query failed right now — nothing was invented "
                "to fill the page. Try again shortly."
            ),
        }
    items = sorted(merged.values(), key=lambda story: story["published_at"], reverse=True)[:limit]
    return {
        "mode": "news-desk",
        "items": items,
        "errors": errors,
        "note": (
            "Public headlines via Yahoo Finance's public search feed over a fixed "
            "topic basket, cached about ten minutes. Theme and signal chips are "
            "plain keyword matches, not analysis. Headlines are information, "
            "never advice."
        ),
    }
