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
from loki_v8 import live_engine, memory_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/fusion/ai", tags=["Loki Fusion"])

_ANALYSIS_TTL_SECONDS = 45.0
_ANALYSIS_LOCK = threading.Lock()
_ANALYSIS_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_PIPELINE_CACHE: Dict[str, Tuple[Any, Any, bool]] = {}
_PIPELINE_LOCK = threading.Lock()
_PROFILE_SOURCE: Dict[str, str] = {}


class AiPositionBody(BaseModel):
    """The browser journal's open position, so the server can manage it."""

    model_config = ConfigDict(extra="ignore")
    entry: float = Field(gt=0.0, le=1e12)
    stop: float = Field(default=0.0, ge=0.0, le=1e12)
    target: float = Field(default=0.0, ge=0.0, le=1e12)
    atr: float = Field(default=0.0, ge=0.0, le=1e12)
    signal_bar: Optional[str] = Field(default=None, max_length=40)
    opened_at: Optional[str] = Field(default=None, max_length=40)
    leg1_done: bool = False


class AiStepBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: str = Field(min_length=1, max_length=12, pattern=r"^[A-Za-z0-9.^=\-]+$")
    equity: float = Field(default=10_000.0, gt=0.0, le=100_000_000.0)
    open_positions: int = Field(default=0, ge=0, le=1_000)
    has_position: bool = False
    equity_start: float = Field(default=0.0, ge=0.0, le=100_000_000.0)
    consecutive_losses: int = Field(default=0, ge=0, le=100)
    cash: Optional[float] = Field(default=None, ge=0.0, le=100_000_000.0)
    position: Optional[AiPositionBody] = None


def _get_pipeline(symbol: str) -> Tuple[Any, Any, bool]:
    """Ephemeral pipeline with the symbol's trained profile applied (cached)."""
    with _PIPELINE_LOCK:
        cached = _PIPELINE_CACHE.get(symbol)
        if cached:
            return cached
    from loki_v8.agents import LokiAgentPipeline
    from loki_v8.broker import PaperBroker
    from loki_v8.config import LokiConfig
    from loki_v8.data import is_crypto
    from loki_v8.train import apply_best, apply_crypto_consensus, apply_universal, load_report

    # The strategy refuses to signal below ``lookback_bars`` (250). A 1y daily
    # window is 365 crypto bars or ~250 equity bars — no slack at all, and a
    # single missing session leaves the symbol permanently HOLD. Two years of
    # equity tape and three of crypto keep the warmup clear of the edge.
    crypto = is_crypto(symbol)
    cfg = LokiConfig(period="3y" if crypto else "2y")
    applied: Dict[str, Any] = {}
    source = "default"
    try:
        report = load_report()
        if report:
            # Prefer the 10-20 year universal profile when it passed its
            # untouched holdout; fall back to the older per-symbol book.
            applied = apply_universal(report, symbol, cfg) or {}
            if applied:
                source = "universal_long_history"
            else:
                applied = apply_best(report, symbol, cfg) or {}
                source = "per_symbol" if applied else "default"
            if not applied and crypto:
                # No verified per-symbol profile: trade the crypto consensus
                # rather than the shipped defaults. ``applied`` stays empty so
                # the response still reports trained_profile_applied=False —
                # consensus is not a per-symbol verification.
                apply_crypto_consensus(report, cfg)
    except Exception as exc:  # noqa: BLE001 - degrade to default config
        logger.warning("trained profile unavailable for %s: %s", symbol, exc.__class__.__name__)
    pipeline = LokiAgentPipeline(cfg, broker=PaperBroker(cfg))
    _PROFILE_SOURCE[symbol] = source
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
    risk.risk.reset_day(payload.equity_start if payload.equity_start > 0 else payload.equity)
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
        raw = pipeline.provider.fetch_history(symbol, cfg.period, cfg.timeframe)
        if raw is None or raw.empty:
            raise ValueError("no history")
        # Decide on completed bars only, exactly like the verified backtest:
        # the forming daily candle can flip a signal intraday.
        from loki_v8.data import is_crypto

        frame, dropped_forming = live_engine.drop_forming_bar(
            raw, crypto=is_crypto(symbol), timeframe=cfg.timeframe
        )
        regime = detect_regime(frame)
        # The memory agent reviews past postures on the same fetched frame
        # BEFORE the Director runs, so the thesis can carry the self-review.
        memory = memory_agent.reflect(frame, horizon=memory_agent.HORIZON)
        director = pipeline.director.run(symbol, regime, memory_agent.director_notes(memory))
        signal = pipeline.quant.run(symbol, frame)
        quotes = pipeline.provider.get_quotes([symbol])
        price = float(quotes.get(symbol) or 0.0)
        if not math.isfinite(price) or price <= 0.0:
            price = float(raw["close"].iloc[-1])
        if not math.isfinite(price) or price <= 0.0:
            raise ValueError("No finite positive market price")
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
        "memory": memory,
        "director": director,
        "quant": signal,
    }
    try:
        scored = live_engine.score_completed(frame, cfg)
        analysis["plan"] = live_engine.plan_entry(
            scored, cfg, bars_per_year=365 if is_crypto(symbol) else 252
        )
        analysis["plan"]["forming_bar_excluded"] = bool(dropped_forming)
        analysis["managed_frame"] = scored[["close", "atr"]].tail(max(cfg.max_hold_bars, 30) + 10)
    except Exception as exc:  # noqa: BLE001 - plan is additive; keep the trail
        logger.warning("live plan unavailable for %s: %s", symbol, exc.__class__.__name__)
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
    if quant and quant.get("action") == "SELL":
        # Entry limits must not prevent reducing an existing long position.
        risk = {
            "approved": payload.has_position,
            "action": "SELL",
            "qty": 0.0,
            "reason": "close_existing_position" if payload.has_position else "no_position_to_close",
        }
    elif quant and quant.get("action") == "BUY" and payload.has_position:
        risk = {"approved": False, "action": "BUY", "reason": "position_already_open"}
    plan = analysis.get("plan")
    if plan and risk.get("approved") and risk.get("action") == "BUY":
        risk = _apply_plan(cfg, plan, risk, analysis["price"], payload)
    manage = None
    if payload.position is not None and analysis.get("managed_frame") is not None:
        manage = live_engine.manage_position(
            analysis["managed_frame"],
            cfg,
            payload.position.model_dump(),
            analysis["price"],
            live_engine.exit_signal(cfg, plan, (quant or {}).get("action", "HOLD")),
        )
    execution = {
        "executed": False,
        "reason": "paper_fill_by_browser",
        "approved": bool(risk.get("approved", False)),
    }
    trail = [
        {"agent": "memory", **analysis["memory"]},
        {"agent": "director", **analysis["director"]},
        {"agent": "quant", **(quant or {"action": "HOLD"})},
        {"agent": "risk", **risk},
        {"agent": "execution", **execution},
    ]
    body: Dict[str, Any] = {
        "symbol": symbol,
        "price": analysis["price"],
        "regime": analysis.get("regime"),
        "trained_profile_applied": analysis.get("trained_profile_applied", False),
        "trail": trail,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if plan:
        body["plan"] = plan
        body["profile"] = {**_profile_summary(cfg), "source": _PROFILE_SOURCE.get(symbol, "default")}
    if manage is not None:
        body["manage"] = manage
    return body


def _apply_plan(
    cfg: Any, plan: Dict[str, Any], risk: Dict[str, Any], price: float, payload: AiStepBody
) -> Dict[str, Any]:
    """Hold a risk-approved BUY to the verified backtest's gates and sizing."""
    if not plan.get("allowed"):
        return {
            "approved": False,
            "action": "BUY",
            "reason": f"entry_gate:{plan.get('reason', 'hold')}",
            "gates": plan.get("gates", []),
        }
    cash = payload.cash if payload.cash is not None else payload.equity
    sized = live_engine.size_entry(cfg, plan, price, payload.equity, cash)
    if sized["qty"] <= 0:
        return {"approved": False, "action": "BUY", "reason": sized["reason"]}
    return {
        **risk,
        "approved": True,
        "reason": "ok",
        "qty": sized["qty"],
        "stop": sized["stop"],
        "target": sized["target"],
        "partial": sized["partial"],
        "atr": sized["atr"],
        "signal_bar": plan.get("signal_bar"),
        "risk_pct_of_equity": round(sized["risk_pct_of_equity"], 3),
        "exposure_pct": round(sized["exposure_pct"], 2),
        "size_multiplier": plan.get("size_multiplier", 1.0),
        "capped_by_cash": sized["capped_by_cash"],
    }


def _profile_summary(cfg: Any) -> Dict[str, Any]:
    """The rules the live engine is applying, so the UI can show them."""
    return {
        "signal_threshold": cfg.signal_threshold,
        "stop_loss_atr": cfg.stop_loss_atr,
        "take_profit_atr": cfg.take_profit_atr,
        "max_hold_bars": cfg.max_hold_bars,
        "breakeven_atr": cfg.breakeven_atr,
        "trailing_stop_atr": cfg.trailing_stop_atr,
        "partial_tp_atr": cfg.partial_tp_atr,
        "require_trend_filter": cfg.require_trend_filter,
        "max_atr_pct": cfg.max_atr_pct,
        "risk_per_trade_pct": cfg.risk_per_trade_pct,
        "adaptive_threshold": cfg.adaptive_threshold,
        "conviction_sizing": cfg.conviction_sizing,
        "vol_target_sizing": cfg.vol_target_sizing,
        "sizing_mode": cfg.sizing_mode,
        "exit_mode": cfg.exit_mode,
        "target_vol_pct": cfg.target_vol_pct,
        "max_exposure_pct": cfg.max_exposure_pct,
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
                values = [float(row[label]) for label in ("open", "high", "low", "close", "volume")]
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


# --- Portfolio AI ---------------------------------------------------------------
_PORTFOLIO_TTL_SECONDS = 20 * 60.0
_PORTFOLIO_LOCK = threading.Lock()
_PORTFOLIO_CACHE: Dict[str, Any] = {}


def _portfolio_plan() -> Dict[str, Any]:
    """Replay every market's verified profile to the latest completed bar."""
    from concurrent.futures import ThreadPoolExecutor

    from loki_v8 import portfolio_ai
    from loki_v8.data import get_provider, is_crypto
    from loki_v8.train import load_report

    universal = (load_report() or {}).get("universal") or {}
    block = universal.get("portfolio") or {}
    if not block.get("verified") or not block.get("symbols"):
        raise HTTPException(503, "The Portfolio AI has no verified profile on this server yet.")
    provider = get_provider()

    def sleeve(symbol: str) -> Optional[Dict[str, Any]]:
        kind = "crypto" if is_crypto(symbol) else "equity"
        params = (universal.get(kind) or {}).get("params")
        if not params:
            return None
        try:
            raw = provider.fetch_history(symbol, "5y", "1d")
            if raw is None or raw.empty:
                return None
            frame, _ = live_engine.drop_forming_bar(raw, crypto=is_crypto(symbol))
            return portfolio_ai.run_sleeve(frame, params, symbol)
        except Exception as exc:  # noqa: BLE001 - one bad feed must not sink the book
            logger.warning("portfolio sleeve %s failed: %s", symbol, exc.__class__.__name__)
            return None

    symbols = list(block["symbols"])
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = dict(zip(symbols, pool.map(sleeve, symbols)))
    sleeves = {s: v for s, v in results.items() if v and len(v["returns"]) > 320}
    missing = [s for s in symbols if s not in sleeves]
    if len(sleeves) < max(5, len(symbols) // 2):
        raise HTTPException(503, "Not enough market data reached the Portfolio AI right now; try again shortly.")
    book = portfolio_ai.combine(sleeves, float(block["target_vol_pct"]), vol_window=block.get("vol_window"))
    try:
        quotes = provider.get_quotes(list(sleeves))
    except Exception:  # noqa: BLE001 - last closes are an honest fallback
        quotes = {}
    prices = {s: float(p) for s, p in (quotes or {}).items() if p and math.isfinite(float(p)) and float(p) > 0}
    alloc = portfolio_ai.allocation(sleeves, book, prices)
    recent = portfolio_ai.window_stats(book["returns"], str(book["returns"].index[-260].date()), "2100-01-01")
    health = portfolio_ai.health(book["returns"], block.get("expected_range") or {})
    changes = portfolio_ai.recent_changes(sleeves)
    return {
        "target_vol_pct": block["target_vol_pct"],
        "as_of": max((v["state"] or {}).get("as_of", "") for v in sleeves.values()),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **alloc,
        "missing_markets": missing,
        "replay_last_year": recent,
        "health": health,
        "changes": changes,
        "holdout_ci": block.get("holdout_ci"),
        "holdout": block.get("holdout"),
        "holdout_buy_hold": block.get("holdout_buy_hold"),
        "note": (
            "Weights are what the tested portfolio holds at the latest completed daily bar: every market runs "
            "its verified rules, capital is shared equally, and the book is scaled toward "
            f"{block['target_vol_pct']:g}% annual volatility with total holdings capped at 100% (no leverage). "
            "Paper money only — never advice."
        ),
    }


@router.get("/portfolio")
def ai_portfolio(response: Response, refresh: bool = False) -> Dict[str, Any]:
    _private_response(response)
    now = time.time()
    with _PORTFOLIO_LOCK:
        cached = _PORTFOLIO_CACHE.get("plan")
        if cached and not refresh and now - cached[0] < _PORTFOLIO_TTL_SECONDS:
            hit: Dict[str, Any] = cached[1]
            return hit
    plan = _portfolio_plan()
    with _PORTFOLIO_LOCK:
        _PORTFOLIO_CACHE["plan"] = (time.time(), plan)
    return plan
