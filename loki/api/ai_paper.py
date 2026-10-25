"""Autonomous AI paper-trading decisions from the trained strategy book.

Public endpoint: runs the Director→Quant→Risk pipeline in review-only mode
(``execute=False`` — no orders, no engine state) on one symbol using that
symbol's trained profile from the shipped snapshot, and returns the
auditable decision trail. The browser performs the paper fills locally in
its own journal; the server never places orders and never holds positions.

The expensive part of a step is the history fetch + indicator scoring, so
the per-symbol analysis (regime, director posture, quant signal, price) is
cached briefly; the risk/execution legs are recomputed per request because
they depend on the caller's paper equity and open positions. Each step
builds its OWN RiskAgent aligned with the caller's browser ledger — the
cached pipeline is shared between every caller, so its risk manager is
never mutated (that would leak one browser's day baseline and loss streak
into another browser's decisions).

A read-only ``GET /bars`` endpoint serves the engine's cached history as
market candles for the AI trading view; it shares the provider cache,
so polling it dedupes against the step analysis fetch.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from loki.api.fusion import _private_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/fusion/ai", tags=["Loki Fusion"])

_ANALYSIS_TTL_SECONDS = 45.0
_ANALYSIS_LOCK = threading.Lock()
_ANALYSIS_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_PIPELINE_CACHE: Dict[str, Tuple[Any, Any, bool]] = {}
_PIPELINE_LOCK = threading.Lock()


class AiStepBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: str = Field(min_length=1, max_length=12)
    equity: float = Field(default=10_000.0, gt=0.0, le=100_000_000.0)
    open_positions: int = Field(default=0, ge=0, le=1_000)
    has_position: bool = False
    equity_start: float = Field(default=0.0, ge=0.0, le=100_000_000.0)
    consecutive_losses: int = Field(default=0, ge=0, le=100)


def _get_pipeline(symbol: str) -> Tuple[Any, Any, bool]:
    """Ephemeral pipeline with the symbol's trained profile applied (cached)."""
    with _PIPELINE_LOCK:
        cached = _PIPELINE_CACHE.get(symbol)
        if cached:
            return cached
    from loki_v8.agents import LokiAgentPipeline
    from loki_v8.broker import PaperBroker
    from loki_v8.config import LokiConfig
    from loki_v8.train import apply_best, load_report

    cfg = LokiConfig(period="1y")
    applied: Dict[str, Any] = {}
    try:
        report = load_report()
        if report:
            applied = apply_best(report, symbol, cfg) or {}
    except Exception as exc:  # noqa: BLE001 - degrade to default config
        logger.warning("trained profile unavailable for %s: %s", symbol, exc.__class__.__name__)
    pipeline = LokiAgentPipeline(cfg, broker=PaperBroker(cfg))
    entry = (pipeline, cfg, bool(applied))
    with _PIPELINE_LOCK:
        _PIPELINE_CACHE[symbol] = entry
    return entry


def _risk_agent_for(cfg: Any, payload: AiStepBody) -> Any:
    """Build a fresh RiskAgent aligned with the caller's browser paper ledger.

    The cached pipeline is shared between every caller of this endpoint, so
    its own risk manager must never be touched — a reset there would leak
    one browser's day baseline and loss streak into another browser's
    decisions. Instead, each step gets its own agent, seeded from the
    ledger the caller sent (``equity_start`` becomes the day baseline;
    ``consecutive_losses`` carries the streak), and shares nothing.
    """
    from loki_v8.agents import RiskAgent

    risk = RiskAgent(cfg)
    if payload.equity_start > 0:
        risk.risk.reset_day(payload.equity_start)
    risk.risk._consecutive_losses = payload.consecutive_losses
    return risk


def _analyze(symbol: str) -> Dict[str, Any]:
    """Cached per-symbol analysis: regime, director, quant signal, price."""
    from loki_v8.regime import detect_regime

    now = time.time()
    with _ANALYSIS_LOCK:
        cached = _ANALYSIS_CACHE.get(symbol)
        if cached and now - cached[0] < _ANALYSIS_TTL_SECONDS:
            return cached[1]

    pipeline, cfg, trained_applied = _get_pipeline(symbol)
    try:
        frame = pipeline.provider.fetch_history(symbol, cfg.period, cfg.timeframe)
        if frame is None or frame.empty:
            raise ValueError("no history")
        regime = detect_regime(frame)
        director = pipeline.director.run(symbol, regime)
        signal = pipeline.quant.run(symbol, frame)
        quotes = pipeline.provider.get_quotes([symbol])
        price = float(quotes.get(symbol) or 0.0)
        if price <= 0.0:
            price = float(frame["close"].iloc[-1])
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - surface a friendly retry
        logger.warning("AI analysis failed for %s: %s", symbol, exc.__class__.__name__)
        raise HTTPException(
            503,
            f"The AI engine could not pull fresh data for {symbol} right now; try again shortly.",
        ) from exc

    analysis = {
        "price": round(price, 6),
        "trained_profile_applied": trained_applied,
        "regime": getattr(regime, "state", None),
        "director": director,
        "quant": signal,
    }
    with _ANALYSIS_LOCK:
        _ANALYSIS_CACHE[symbol] = (time.time(), analysis)
    return analysis


@router.post("/step")
def ai_step(payload: AiStepBody, response: Response) -> Dict[str, Any]:
    symbol = payload.symbol.strip().upper()
    if not symbol:
        raise HTTPException(400, "Pick a symbol first.")
    _private_response(response)

    analysis = _analyze(symbol)
    cfg = _get_pipeline(symbol)[1]

    # The paper ledger lives in the browser; this step's risk agent is built
    # fresh from it. Nothing below mutates the cached pipeline.
    quant = analysis.get("quant")
    risk = _risk_agent_for(cfg, payload).run(
        analysis["director"]["posture"],
        quant,
        payload.equity,
        payload.open_positions,
        analysis["price"],
    )
    execution = {
        "executed": False,
        "reason": "paper_fill_by_browser",
        "approved": bool(risk.get("approved", False)),
    }
    trail = [
        {"agent": "director", **analysis["director"]},
        {"agent": "quant", **(quant or {"action": "HOLD"})},
        {"agent": "risk", **risk},
        {"agent": "execution", **execution},
    ]
    return {
        "symbol": symbol,
        "price": analysis["price"],
        "regime": analysis.get("regime"),
        "trained_profile_applied": analysis.get("trained_profile_applied", False),
        "trail": trail,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


@router.get("/bars")
def ai_bars(
    response: Response,
    symbol: str = Query(min_length=1, max_length=12, pattern=r"^[A-Za-z0-9.^=\-]+$"),
    limit: int = Query(default=60, ge=10, le=120),
    timeframe: Literal["1m", "5m", "15m", "1h", "1d"] = "1d",
) -> Dict[str, Any]:
    """Bounded provider candles, sorted oldest first; newest may be forming.

    Daily requests share the analysis provider cache. Intraday timeframes
    use bounded windows independently of the daily strategy configuration.
    """
    symbol = symbol.strip().upper()
    if not symbol:
        raise HTTPException(400, "Pick a symbol first.")
    _private_response(response)

    pipeline, cfg, _applied = _get_pipeline(symbol)
    period = {"1m": "5d", "5m": "1mo", "15m": "1mo", "1h": "3mo", "1d": cfg.period}[timeframe]
    try:
        frame = pipeline.provider.fetch_history(symbol, period, timeframe)
    except Exception as exc:  # noqa: BLE001 - provider/network outages surface as 503
        logger.warning("AI bars fetch failed for %s: %s", symbol, exc.__class__.__name__)
        raise HTTPException(
            503,
            f"Candle data for {symbol} is unavailable right now; try again shortly.",
        ) from exc

    candles: List[Dict[str, Any]] = []
    if frame is not None and not getattr(frame, "empty", True):
        frame = frame.sort_index()
        frame = frame[~frame.index.duplicated(keep="last")]
        for stamp, row in frame.tail(limit).iterrows():
            try:
                values = [
                    float(row[label])
                    for label in ("open", "high", "low", "close", "volume")
                ]
            except (KeyError, TypeError, ValueError):
                continue
            if not all(math.isfinite(value) for value in values):
                continue
            o, h, low, c, v = values
            if min(o, h, low, c) <= 0 or v < 0 or not low <= min(o, c) <= max(o, c) <= h:
                continue
            candles.append(
                {
                    "t": stamp.isoformat() if hasattr(stamp, "isoformat") else str(stamp),
                    "o": round(values[0], 6),
                    "h": round(values[1], 6),
                    "l": round(values[2], 6),
                    "c": round(values[3], 6),
                    "v": values[4],
                }
            )
    if not candles:
        raise HTTPException(
            503,
            f"Candle data for {symbol} is unavailable right now; try again shortly. "
            "The chart stays empty rather than inventing candles.",
        )
    return {
        "symbol": symbol,
        "period": period,
        "timeframe": timeframe,
        "count": len(candles),
        "kind": "provider_candles",
        "source": "Yahoo Finance",
        "as_of": candles[-1]["t"],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "latest_bar_may_be_incomplete": True,
        "note": (
            "Yahoo Finance market candles — potentially delayed, not a live quote. "
            "The newest candle may still be forming. Chart timeframe does not change the daily AI strategy. "
            "Futures charts are reference series, not a Lucid execution feed or a specific tradable contract."
        ),
        "candles": candles,
    }
