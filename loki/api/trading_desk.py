"""The multi-agent trading desk: one public pipeline, five roles, two clicks.

The desk runs the shape of a small trading firm as a pure function of
public data. Five deterministic agents hand structured JSON to the next
stage — no language model sits anywhere in the loop (the site holds no
provider keys, and the published best practice already says raw indicators
and sizes must be computed in code, not invented in prose):

1. News agent     — public headlines for the symbol, scored by an
                   open lexicon of finance words (transparent keyword
                   weights, not an AI model).
2. Technical agent— public intraday closes; SMA10/SMA25/RSI14 like the
                   autopilot's published rule, computed in code.
3. Fundamentals   — one public earnings multiple read, banded honestly,
                   abstaining by design on crypto (no quarterly reports).
4. Strategy lead  — fixed, published weights (news 25 / technical 55 /
                   fundamentals 20), renormalized over whichever agents
                   actually returned; emits a structured proposal.
5. Risk manager   — hard rules in Python with veto power: quantity cap,
                   notional cap, price known, side known, score sane.

Nothing here places an order. An approved proposal becomes executable
only in the browser through the existing Alpaca PAPER rail (keys stay
browser-held, the user clicks, two-step confirm). Every number is
information, never advice; every agent that cannot see its data says
"abstain" instead of guessing.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any, Dict, List, Sequence, Tuple

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

import loki.api.site_access as site_access
from loki.api.market_feed import (
    MarketFeedError,
    YAHOO_CHART_URL,
    _http_json,
    classify_symbol,
    fetch_headlines,
    normalize_symbol,
)

router = APIRouter(prefix="/api/desk", tags=["Trading desk"])

# The desk's hard caps. They are guards, not advice — and they are far
# below the rail's own ceiling, because the risk manager exists to say no.
DESK_QTY_MAX = 5
DESK_NOTIONAL_MAX = 2_500.0
DESK_SCORE_MAX_SHARES = 2  # strategist asks for 2 shares only at |score| >= 0.60

# Fixed, published weights. When an agent abstains, the remaining weights
# are renormalized — the proposal never silently treats silence as zero vote.
AGENT_WEIGHTS = {"news": 0.25, "technical": 0.55, "fundamentals": 0.20}
BUY_THRESHOLD = 0.25
SELL_THRESHOLD = -0.25
STRONG_SCORE = 0.60

NEWS_LIMIT = 10
MIN_CLOSES = 26  # 25 for the SMA plus one more for the RSI deltas
CLOSES_MAX = 400

# Open lexicon, weights in (-1, 1]; matched word-boundary case-insensitive
# like the news desk's visible signal chips. Kept short and readable.
_LEXICON: Tuple[Tuple[str, float], ...] = (
    ("beats", 0.6), ("beat", 0.5), ("record", 0.4), ("surge", 0.6),
    ("soars", 0.6), ("rally", 0.5), ("upside", 0.4), ("upgrade", 0.5),
    ("raises guidance", 0.55), ("outperform", 0.45), ("buybacks", 0.35),
    ("stock split", 0.3), ("dividend increase", 0.35), ("winner", 0.3),
    ("misses", -0.6), ("miss", -0.5), ("plunge", -0.65), ("plunges", -0.65),
    ("lawsuit", -0.45), ("recall", -0.5), ("downgrade", -0.55),
    ("probe", -0.4), ("fraud", -0.7), ("layoffs", -0.4), ("cuts guidance", -0.55),
    ("underperform", -0.45), ("short seller", -0.5), ("downturn", -0.5),
    ("selloff", -0.55), ("warns", -0.4), (" bankruptcy", -0.75),
)
_LEXICON_WORDS: Tuple[Tuple[re.Pattern[str], float], ...] = tuple(
    (re.compile(rf"\b{re.escape(word.strip())}\b", re.IGNORECASE), weight) for word, weight in _LEXICON
)


def _clamp(score: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, score))


def _lexicon_score(title: str) -> float:
    """One headline's lexicon score: the sum of the words it matched."""
    return _clamp(sum(weight for pattern, weight in _LEXICON_WORDS if pattern.search(title)))


def _round(value: Any, digits: int = 2) -> float | None:
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------
# Agent 1 — news
# --------------------------------------------------------------------------
def news_agent(symbol: str) -> Dict[str, Any]:
    """Public headlines for one symbol, scored with the open lexicon."""
    try:
        payload = fetch_headlines(symbol, NEWS_LIMIT)
        items = payload.get("items") or []
    except Exception as error:  # noqa: BLE001 - abstain, never crash the desk
        return {
            "agent": "news",
            "status": "abstain",
            "score": None,
            "error": str(error)[:160],
            "method": "public headlines + word-by-word lexicon weights; without headlines this agent raises its hand, not a guess",
        }
    scored: List[tuple[float, Dict[str, Any]]] = []
    for item in items:
        title = str(item.get("title") or "")
        if not title:
            continue
        value = round(_lexicon_score(title), 2)
        scored.append(
            (
                value,
                {
                    "title": title,
                    "publisher": str(item.get("publisher") or ""),
                    "score": value,
                },
            )
        )
    if not scored:
        return {
            "agent": "news",
            "status": "abstain",
            "score": None,
            "error": "the public headlines feed answered no usable items",
            "method": "public headlines + word-by-word lexicon weights",
        }
    scores = [value for value, _ in scored]
    # Headline mean, clamped, plus a small breadth term: many agreeing
    # headlines move the read a little past a single loud one.
    mean = sum(scores) / len(scores)
    breadth = (len(scored) / NEWS_LIMIT) * 0.05 * (1 if mean >= 0 else -1)
    score = _clamp(mean * 0.95 + breadth)
    strongest = [row for _, row in sorted(scored, key=lambda pair: abs(pair[0]), reverse=True)[:3]]
    return {
        "agent": "news",
        "status": "ok",
        "score": _round(score, 3),
        "headlines_read": len(scored),
        "top": strongest,
        "method": (
            "matched words carry fixed weights (beats +0.6, lawsuit -0.45, ...); "
            "the score is their clamped mean — plain string matching, not a model"
        ),
    }


# --------------------------------------------------------------------------
# Agent 2 — technical
# --------------------------------------------------------------------------
def sma(closes: Sequence[float], window: int) -> float | None:
    if len(closes) < window:
        return None
    return sum(closes[-window:]) / window


def rsi14(closes: Sequence[float]) -> float | None:
    if len(closes) < 15:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(len(closes) - 14, len(closes))]
    gains = sum(max(delta, 0.0) for delta in deltas) / 14
    losses = sum(max(-delta, 0.0) for delta in deltas) / 14
    if gains == 0 and losses == 0:
        return 50.0
    if losses == 0:
        return 100.0
    rs = gains / losses
    return 100.0 - 100.0 / (1.0 + rs)


def technical_score(last: float, fast: float, slow: float, rsi: float) -> float:
    """The published formula: trend base ± trend agreement ± RSI stretch.

    price above the 25-bar average leans positive (+0.35 below), a confirmed
    fast-over-slow slope adds ±0.15 more, and RSI extremes pull ±0.20 back
    toward sensible (stretched markets get discounted). Clamped to [-1, 1].
    """
    score = 0.35 if last > slow else -0.35
    score += 0.15 if fast > slow else -0.15
    if rsi < 30:
        score += 0.20
    elif rsi > 70:
        score -= 0.20
    return _clamp(score)


def _yahoo_closes(symbol: str) -> List[float]:
    """Public 5-minute closes for one equity-style symbol (range 2d)."""
    from urllib.parse import quote, urlencode

    url = (
        f"{YAHOO_CHART_URL}/{quote(symbol, safe='')}?"
        f"{urlencode({'range': '2d', 'interval': '5m', 'includePrePost': 'false'})}"
    )
    payload = _http_json(url)
    try:
        result = payload["chart"]["result"]
        if isinstance(result, list):
            result = result[0]
        raw = result["indicators"]["quote"][0].get("close") or []
        closes = [float(value) for value in raw if value is not None]
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise MarketFeedError(f"no usable public closes for {symbol}") from error
    if len(closes) < MIN_CLOSES:
        raise MarketFeedError(
            f"only {len(closes)} usable 5-minute closes right now — not enough for the desk's averages"
        )
    return closes[-CLOSES_MAX:]


def _binance_closes(pair: str) -> List[float]:
    """Public 5-minute closes for one crypto pair via the site's adapter."""
    from loki.api.binance_market_data import MarketDataError, get_binance_spot_snapshot

    try:
        snapshot = get_binance_spot_snapshot(pair.replace("/", ""), "5m")
    except MarketDataError as error:
        raise MarketFeedError(str(error)) from error
    closes = [float(candle["close"]) for candle in snapshot.candles if "close" in candle]
    if len(closes) < MIN_CLOSES:
        raise MarketFeedError(
            f"only {len(closes)} usable 5-minute closes right now — not enough for the desk's averages"
        )
    return closes[-CLOSES_MAX:]


def technical_agent(symbol: str) -> Dict[str, Any]:
    """Intraday technicals computed in code from public closes."""
    provider = classify_symbol(symbol)
    try:
        if provider == "binance":
            closes = _binance_closes(symbol)
            provider_name = "Binance Spot public API (5m)"
        else:
            closes = _yahoo_closes(symbol)
            provider_name = "Yahoo Finance public chart (5m, 2d)"
    except MarketFeedError as error:
        return {
            "agent": "technical",
            "status": "abstain",
            "score": None,
            "error": str(error)[:160],
            "provider": provider_name if provider else None,
            "method": "SMA10/SMA25/RSI14 computed in code on completed 5-minute bars",
        }
    last = closes[-1]
    fast = sma(closes, 10)
    slow = sma(closes, 25)
    rsi = rsi14(closes)
    if fast is None or slow is None or rsi is None:
        return {
            "agent": "technical",
            "status": "abstain",
            "score": None,
            "error": "bars arrived but not enough to compute the desk's averages",
            "provider": provider_name,
        }
    return {
        "agent": "technical",
        "status": "ok",
        "score": _round(technical_score(last, fast, slow, rsi), 3),
        "facts": {"last": _round(last, 4), "sma10": _round(fast, 4), "sma25": _round(slow, 4), "rsi14": _round(rsi)},
        "bars_used": len(closes),
        "provider": provider_name,
        "method": (
            "score = price-over-SMA25 base ± fast-slow slope ±0.15, RSI<30 pulls +0.20, RSI>70 pulls -0.20; "
            "the same trend vocabulary as the autopilot's published rule, computed in code"
        ),
    }


# --------------------------------------------------------------------------
# Agent 3 — fundamentals
# --------------------------------------------------------------------------
def fundamentals_agent(symbol: str) -> Dict[str, Any]:
    """One public earnings multiple, banded honestly; abstains on crypto."""
    if classify_symbol(symbol) == "binance":
        return {
            "agent": "fundamentals",
            "status": "abstain",
            "score": None,
            "reason": "crypto rails settle in code, not quarterly reports — there is no earnings multiple to read",
        }
    try:
        import yfinance  # lazy: the site imports it at request time only
    except Exception as error:  # noqa: BLE001 - the dependency itself may be absent
        return {
            "agent": "fundamentals",
            "status": "abstain",
            "score": None,
            "error": f"the fundamentals library is unavailable here: {error}"[:160],
        }
    try:
        ticker = yfinance.Ticker(symbol)
        info = ticker.info
    except Exception as error:  # noqa: BLE001 - yfinance raises arbitrarily; the desk abstains
        return {
            "agent": "fundamentals",
            "status": "abstain",
            "score": None,
            "error": f"the public fundamentals feed did not answer useably: {error}"[:160],
        }
    pe = _round(info.get("trailing_pe"), 2)
    if pe is None or pe <= 0:
        return {
            "agent": "fundamentals",
            "status": "abstain",
            "score": None,
            "reason": "no trailing earnings multiple was reported for this symbol",
            "facts": {
                "market_cap": _round(info.get("market_cap"), 0),
                "price_to_book": _round(info.get("price_to_book"), 2),
            },
        }
    if pe <= 12:
        score, verdict = 0.5, "trades below the usual earnings multiple — reads cheap next to common income (heuristic band)"
    elif pe >= 40:
        score, verdict = -0.5, "earnings multiple is stretched against common bands — reads expensive-looking (heuristic band)"
    else:
        score, verdict = 0.0, "earnings multiple sits inside the middle band — no edge declared"
    return {
        "agent": "fundamentals",
        "status": "ok",
        "score": score,
        "facts": {
            "trailing_pe": pe,
            "forward_pe": _round(info.get("forward_pe"), 2),
            "market_cap": _round(info.get("market_cap"), 0),
            "price_to_book": _round(info.get("price_to_book"), 2),
        },
        "verdict": verdict,
        "method": "one declared banding of the trailing P/E; not valuation research and never advice",
    }


# --------------------------------------------------------------------------
# Agent 4 — strategy lead
# --------------------------------------------------------------------------
def strategist(news: Dict[str, Any], technical: Dict[str, Any], fundamentals: Dict[str, Any]) -> Dict[str, Any]:
    """Fixed published weights, renormalized over the agents that answered."""
    votes = {
        "news": news.get("score"),
        "technical": technical.get("score"),
        "fundamentals": fundamentals.get("score"),
    }
    present = {name: value for name, value in votes.items() if isinstance(value, (int, float))}
    missing = [name for name, value in votes.items() if name not in present]
    if not present:
        return {
            "agent": "strategy",
            "status": "stand_down",
            "side": "hold",
            "qty": 0,
            "score": None,
            "weights_used": {},
            "missing": missing,
            "reasons": ["not one agent had data — the desk stands down honestly rather than guess"],
        }
    total_weight = sum(AGENT_WEIGHTS[name] for name in present)
    # Full precision on purpose: rounded shares stop summing to one, and a
    # renormalization that doesn't visibly sum to one would be the lie.
    weights_used = {name: AGENT_WEIGHTS[name] / total_weight for name in present}
    composite = sum(AGENT_WEIGHTS[name] * value for name, value in present.items()) / total_weight
    composite = _clamp(composite)
    if composite >= BUY_THRESHOLD:
        side = "buy"
    elif composite <= SELL_THRESHOLD:
        side = "sell"
    else:
        side = "hold"
    qty = (1 if abs(composite) < STRONG_SCORE else 2) if side != "hold" else 0
    reasons: List[str] = []
    news_row = news if news.get("status") == "ok" else None
    tech_row = technical if technical.get("status") == "ok" else None
    fund_row = fundamentals if fundamentals.get("status") == "ok" else None
    if news_row and isinstance(votes["news"], (int, float)):
        reasons.append(f"news read {votes['news']:+.2f} over {news_row.get('headlines_read')} public headlines")
    if tech_row and isinstance(votes["technical"], (int, float)):
        facts = tech_row.get("facts") or {}
        reasons.append(
            f"technicals {votes['technical']:+.2f} (last {facts.get('last')} vs SMA25 {facts.get('sma25')}, RSI {facts.get('rsi14')})"
        )
    if fund_row and isinstance(votes["fundamentals"], (int, float)):
        reasons.append(f"fundamentals {votes['fundamentals']:+.2f} ({fund_row.get('verdict')})")
    reasons.append("weights are fixed and published; each abstaining agent's weight was renormalized over the rest")
    return {
        "agent": "strategy",
        "status": "ok" if side != "hold" else "hold",
        "side": side,
        "qty": qty,
        "score": _round(composite, 3),
        "weights_used": weights_used,
        "missing": missing,
        "reasons": reasons,
    }


# --------------------------------------------------------------------------
# Agent 5 — risk manager
# --------------------------------------------------------------------------
def risk_manager(proposal: Dict[str, Any], technical: Dict[str, Any]) -> Dict[str, Any]:
    """Hard rules in code; one veto ends it.

    Order of the gates matters and is published: sanity, then price, then
    side, then the caps. The desk refuses to act blind — without a trusted
    last price there is no notional check, so there is no approval.
    """
    checks: List[Dict[str, Any]] = []

    def gate(name: str, passed: bool, detail: str) -> bool:
        checks.append({"gate": name, "passed": passed, "detail": detail})
        return passed

    score = proposal.get("score")
    side = proposal.get("side")
    qty = proposal.get("qty")
    price = (technical.get("facts") or {}).get("last") if technical.get("status") == "ok" else None

    gate("score_sanity", score is None or -1.0 <= float(score) <= 1.0, "the composite score stayed inside its declared band")
    gate("price_known", isinstance(price, (int, float)) and float(price) > 0,
         "a trusted public last price is required before any sizing check can happen")
    gate("side_known", side in ("buy", "sell"),
         "the strategist proposed a held position or no proposal — nothing to execute")
    gate("quantity_cap", isinstance(qty, int) and 1 <= (qty or 0) <= DESK_QTY_MAX,
         f"ticket size capped at {DESK_QTY_MAX} shares")
    notional = None
    if isinstance(price, (int, float)) and isinstance(qty, int):
        notional = float(price) * qty
        gate("notional_cap", notional <= DESK_NOTIONAL_MAX,
             f"ticket notional {round(notional, 2)} vs cap {DESK_NOTIONAL_MAX}")

    if proposal.get("status") == "stand_down":
        return {
            "agent": "risk",
            "approved": False,
            "verdict": "veto",
            "reason": "the desk stood down — not one agent had data, so there is no proposal to defend",
            "checks": checks,
        }
    approved = all(gate["passed"] for gate in checks)
    failed = [gate["gate"] for gate in checks if not gate["passed"]]
    if approved:
        verdict = "approved"
    elif not side or side == "hold":
        verdict = "no_action"
    else:
        verdict = "veto"
    reason_map = {
        "approved": "every hard gate passed — the proposal may be executed by your click through the paper rail",
        "no_action": "the strategist proposed no trade; the risk manager has nothing to defend or veto",
        "veto": f"hard rule refused this proposal: {', '.join(failed)}" if failed else "a hard rule refused this proposal",
    }
    return {
        "agent": "risk",
        "approved": approved,
        "verdict": verdict,
        "reason": reason_map[verdict],
        "checks": checks,
        "notional_estimate": _round(notional, 2) if notional is not None else None,
        "caps": {"qty": DESK_QTY_MAX, "notional": DESK_NOTIONAL_MAX},
    }


# --------------------------------------------------------------------------
# Endpoint
# --------------------------------------------------------------------------
class DeskRequest(BaseModel):
    """One desk run: symbol, nothing else (the data basket is public)."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=15, pattern=r"^[A-Za-z][A-Za-z0-9./]{0,14}$")


def _require_gate(request: Request) -> None:
    """The desk serves people who already passed the workspace's door."""
    cookie = request.cookies.get(site_access.GATE_COOKIE)
    if not site_access.verify_gate_cookie_value(cookie or ""):
        raise HTTPException(403, "Open the workspace through its access door first.")


@router.post("/run", include_in_schema=False)
async def run_desk(request: Request, body: DeskRequest) -> Dict[str, Any]:
    """One public-data pipeline: news → technicals → fundamentals → proposal → risk."""

    _require_gate(request)
    try:
        normalized = normalize_symbol(body.symbol)
    except MarketFeedError as error:
        raise HTTPException(422, str(error)) from error

    news, technical, fundamentals = await asyncio.gather(
        run_in_threadpool(news_agent, normalized),
        run_in_threadpool(technical_agent, normalized),
        run_in_threadpool(fundamentals_agent, normalized),
    )
    proposal = strategist(news, technical, fundamentals)
    verdict = risk_manager(proposal, technical)

    return {
        "mode": "trading-desk",
        "symbol": normalized,
        "trace": [news, technical, fundamentals, proposal, verdict],
        "proposal": {"side": proposal.get("side"), "qty": proposal.get("qty"), "score": proposal.get("score")},
        "verdict": {"approved": verdict["approved"], "reason": verdict["reason"]},
        "execution": {
            "channel": "the browser-held Alpaca PAPER rail — nothing is sent from the server",
            "requires_armed_paper_keys": True,
        },
        "note": (
            "Five deterministic agents over public data; every handoff is the JSON you can read below. "
            "No language model, no hidden weight, no persistence. The proposal is information, never advice, "
            "and execution only ever happens on your click through your own paper keys."
        ),
    }
