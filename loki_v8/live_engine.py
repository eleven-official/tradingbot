"""LOKI v8 — live decisions that follow the verified backtest rules.

The trained profiles in ``training_report_snapshot.json`` were verified by
``loki_v8.backtest.run_backtest``. That loop decides on bar ``i`` using only
what bar ``i-1`` (the last *completed* bar) knew, and it applies more than
the raw ensemble score:

* entry gates   — 200-bar trend filter, bear-regime filter, ATR% ceiling
* sizing        — risk-per-trade, then conviction / regime / vol-target
                  multipliers, clamped to what the account can afford
* management    — stop, target, opposite signal, one partial scale-out,
                  time stop (``max_hold_bars``), breakeven lock and an
                  (optionally armed) ATR trailing ratchet on closes

A live decision that skips any of those is trading a different strategy
from the one that was verified. This module is the single place the live
paper engine gets those rules from, written to match the backtest bar for
bar (``tests/test_live_engine.py`` replays a backtest and checks every
entry decision agrees).

Nothing here places orders. Inputs are plain frames and dicts so the API
and the browser journal can share one contract.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .config import LokiConfig
from .regime import is_bearish, regime_series
from .risk import RiskManager
from .strategy import EnsembleStrategy

# Equity daily bars are complete once the regular session has closed. A
# short grace window lets the provider publish the final print.
_EQUITY_CLOSE_MINUTES = 16 * 60 + 15


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _bar_date(stamp: Any, tz: str) -> Optional[Any]:
    try:
        ts = pd.Timestamp(stamp)
    except (TypeError, ValueError):
        return None
    if ts.tzinfo is not None:
        ts = ts.tz_convert(tz)
    return ts.date()


def drop_forming_bar(
    df: pd.DataFrame,
    *,
    crypto: bool,
    timeframe: str = "1d",
    now: Optional[datetime] = None,
) -> Tuple[pd.DataFrame, bool]:
    """Return ``(completed_bars, dropped)`` for a daily frame.

    The provider's newest daily candle is usually today's, still moving.
    Scoring it would let a signal appear at 10:00 and vanish by 11:00 —
    the backtest never saw that bar until it closed. Crypto days close at
    00:00 UTC; equity days close after the New York session.
    """
    if df is None or len(df) == 0 or timeframe != "1d":
        return df, False
    tz = "UTC" if crypto else "America/New_York"
    current = pd.Timestamp(now or datetime.now(timezone.utc))
    if current.tzinfo is None:
        current = current.tz_localize("UTC")
    local_now = current.tz_convert(tz)
    last_date = _bar_date(df.index[-1], tz)
    if last_date is None or last_date < local_now.date():
        return df, False
    if not crypto and local_now.hour * 60 + local_now.minute >= _EQUITY_CLOSE_MINUTES:
        return df, False
    return df.iloc[:-1], True


def effective_threshold(cfg: LokiConfig, atr_pct: float, atr_med: float) -> float:
    """The entry bar ``EnsembleStrategy.action_for`` applies (adaptive aware)."""
    thr = float(cfg.signal_threshold)
    if cfg.adaptive_threshold and atr_pct > 0 and atr_med > 0:
        thr *= min(1.6, max(0.8, atr_pct / atr_med))
    return thr


def size_multiplier(cfg: LokiConfig, score: float, regime: str, atr_pct: float, atr_med: float) -> float:
    """Conviction / regime / vol-target multiplier, exactly as the backtest."""
    mult = 1.0
    if cfg.conviction_sizing and cfg.signal_threshold > 0:
        strength = abs(score) / cfg.signal_threshold
        mult *= min(1.25, max(0.6, strength))
    if cfg.regime_sizing and regime == "RANGING":
        mult *= 0.5
    if cfg.vol_target_sizing and atr_pct > 0 and atr_med > 0:
        mult *= min(1.2, atr_med / atr_pct)
    return mult


def score_completed(df: pd.DataFrame, cfg: LokiConfig) -> pd.DataFrame:
    """Indicator + factor + composite score frame for completed bars."""
    return EnsembleStrategy(cfg).score_frame(df)


def plan_entry(frame: pd.DataFrame, cfg: LokiConfig) -> Dict[str, Any]:
    """Entry decision for the *next* bar from a scored frame of completed bars.

    Mirrors the backtest's entry block: action from the last completed
    score, then the volatility, trend and regime gates. ``allowed`` is true
    only when the action is BUY and every gate passes (the paper engine is
    long-only unless ``allow_short``).
    """
    warmup = max(cfg.lookback_bars, 60)
    if frame is None or len(frame) < warmup + 1:
        return {
            "ready": False,
            "action": "HOLD",
            "allowed": False,
            "reason": "warming_up",
            "bars": 0 if frame is None else int(len(frame)),
            "bars_needed": warmup + 1,
            "gates": [],
        }

    last = frame.iloc[-1]
    score = _finite(last.get("score"))
    atr = _finite(last.get("atr"))
    atr_pct = _finite(last.get("atr_pct"))
    med_series = frame["atr_pct"].rolling(60, min_periods=20).median()
    atr_med = _finite(med_series.iloc[-1])
    close = _finite(last.get("close"))
    sma200 = _finite(last.get("sma_200"), default=float("nan"))
    regime = str(regime_series(frame).iloc[-1])

    strategy = EnsembleStrategy(cfg)
    action = strategy.action_for(score, atr_pct, atr_med)
    threshold = effective_threshold(cfg, atr_pct, atr_med)

    above_ma = bool(close > sma200) if math.isfinite(sma200) else False
    bear = is_bearish(regime)
    vol_ok = not (cfg.max_atr_pct > 0 and atr_pct > cfg.max_atr_pct)

    gates: List[Dict[str, Any]] = [
        {
            "name": "signal",
            "passed": action == "BUY",
            "detail": f"score {score:+.1f} vs entry bar ±{threshold:.1f}",
        },
        {
            "name": "volatility_cap",
            "passed": vol_ok,
            "detail": (
                f"ATR {atr_pct:.2f}% ≤ cap {cfg.max_atr_pct:.2f}%"
                if cfg.max_atr_pct > 0
                else "no ATR cap in this profile"
            ),
        },
        {
            "name": "trend_filter",
            "passed": (not cfg.require_trend_filter) or above_ma,
            "detail": (
                ("close above" if above_ma else "close below") + " the 200-bar average"
                if cfg.require_trend_filter
                else "trend filter off in this profile"
            ),
        },
        {
            "name": "regime_filter",
            "passed": (not cfg.regime_filter) or (not bear),
            "detail": f"regime {regime}" + (" blocks new longs" if bear and cfg.regime_filter else ""),
        },
    ]
    allowed = all(g["passed"] for g in gates)
    failed = next((g["name"] for g in gates if not g["passed"]), None)
    stamp = frame.index[-1]
    return {
        "ready": True,
        "action": action,
        "allowed": allowed,
        "reason": "ok" if allowed else (failed or "hold"),
        "score": round(score, 2),
        "threshold": round(threshold, 2),
        "atr": atr,
        "atr_pct": round(atr_pct, 4),
        "atr_pct_median": round(atr_med, 4),
        "regime": regime,
        "above_sma200": above_ma,
        "size_multiplier": round(size_multiplier(cfg, score, regime, atr_pct, atr_med), 4),
        "stop_atr": float(cfg.stop_loss_atr),
        "target_atr": float(cfg.take_profit_atr),
        "partial_tp_atr": float(cfg.partial_tp_atr),
        "max_hold_bars": int(cfg.max_hold_bars),
        "signal_bar": stamp.isoformat() if hasattr(stamp, "isoformat") else str(stamp),
        "gates": gates,
    }


def size_entry(
    cfg: LokiConfig, plan: Dict[str, Any], price: float, equity: float, cash: float
) -> Dict[str, Any]:
    """Stop, target and quantity for a live entry at ``price``.

    Risk-per-trade sizing from the stop distance, scaled by the plan's
    multiplier, then clamped to cash — the backtest refuses an entry it
    cannot pay for; the live engine buys what it can afford instead.
    """
    atr = _finite(plan.get("atr"))
    if price <= 0 or atr <= 0:
        return {"qty": 0.0, "stop": 0.0, "target": 0.0, "reason": "no_price_or_atr"}
    stop = price - cfg.stop_loss_atr * atr
    target = price + cfg.take_profit_atr * atr
    if stop <= 0:
        return {"qty": 0.0, "stop": 0.0, "target": target, "reason": "stop_below_zero"}
    qty = RiskManager(cfg).position_size(equity, price, stop) * _finite(plan.get("size_multiplier"), 1.0)
    affordable = max(0.0, cash) / price
    capped = qty > affordable
    qty = max(0.0, min(qty, affordable))
    risk_amount = qty * (price - stop)
    return {
        "qty": qty,
        "stop": stop,
        "target": target,
        "partial": (
            price + cfg.partial_tp_atr * atr
            if 0 < cfg.partial_tp_atr < cfg.take_profit_atr
            else 0.0
        ),
        "atr": atr,
        "risk_amount": risk_amount,
        "risk_pct_of_equity": (risk_amount / equity * 100.0) if equity > 0 else 0.0,
        "capped_by_cash": capped,
        "reason": "ok" if qty > 0 else "no_size",
    }


def manage_position(
    frame: pd.DataFrame,
    cfg: LokiConfig,
    position: Dict[str, Any],
    price: float,
    signal_action: str,
) -> Dict[str, Any]:
    """Exit / scale-out / stop-ratchet decision for an open long position.

    ``position`` carries ``entry``, ``stop``, ``target``, ``atr`` (ATR used
    at entry), ``signal_bar`` (ISO stamp of the completed bar the entry was
    decided on), optional ``opened_at`` and ``leg1_done``.

    Order matches the backtest: ratchet from completed bars since entry →
    stop → target → opposite signal → partial scale-out → time stop. The
    ratchet is recomputed from the bars each time (monotone, so idempotent),
    never loosened below the caller's stop.
    """
    entry = _finite(position.get("entry"))
    stop = _finite(position.get("stop"))
    target = _finite(position.get("target"))
    atr_entry = _finite(position.get("atr"))
    leg1_done = bool(position.get("leg1_done"))
    result: Dict[str, Any] = {
        "exit": False,
        "reason": None,
        "scale_out": 0.0,
        "stop": stop,
        "target": target,
        "bars_held": 0,
        "max_hold_bars": int(cfg.max_hold_bars),
        "breakeven_armed": False,
        "trailing_armed": False,
    }
    if entry <= 0 or price <= 0:
        return result

    held = _bars_since(frame, position)
    result["bars_held"] = int(len(held))

    # Close-based ratchet: each completed bar since entry may lift the stop.
    for _, row in held.iterrows():
        close = _finite(row.get("close"))
        atr_now = _finite(row.get("atr"))
        if atr_now <= 0 or close <= 0:
            continue
        gain = (close - entry) / atr_now
        if cfg.breakeven_atr > 0 and gain >= cfg.breakeven_atr:
            be_stop = entry + 0.05 * atr_now
            if be_stop > stop:
                stop = be_stop
                result["breakeven_armed"] = True
        if cfg.trailing_stop_atr > 0 and (cfg.arm_trailing_atr <= 0 or gain >= cfg.arm_trailing_atr):
            trail = close - cfg.trailing_stop_atr * atr_now
            if trail > stop:
                stop = trail
                result["trailing_armed"] = True
    result["stop"] = stop

    if stop > 0 and price <= stop:
        result.update(exit=True, reason="stop")
        return result
    if target > 0 and price >= target:
        result.update(exit=True, reason="target")
        return result
    if str(signal_action).upper() == "SELL":
        result.update(exit=True, reason="signal")
        return result
    if not leg1_done and cfg.partial_tp_atr > 0 and atr_entry > 0:
        level = entry + atr_entry * cfg.partial_tp_atr
        if price >= level:
            fraction = min(0.9, max(0.1, cfg.partial_fraction))
            result.update(scale_out=fraction, reason="scale_out", partial_level=level)
            if price > stop:
                result["stop"] = max(stop, price)
            return result
    if cfg.max_hold_bars > 0 and result["bars_held"] >= cfg.max_hold_bars:
        result.update(exit=True, reason="time")
    return result


def _bars_since(frame: pd.DataFrame, position: Dict[str, Any]) -> pd.DataFrame:
    """Completed bars after the entry's signal bar (or from the open date)."""
    if frame is None or len(frame) == 0:
        return frame.iloc[0:0] if frame is not None else pd.DataFrame()
    index = pd.DatetimeIndex(frame.index)
    marker = position.get("signal_bar")
    strict = True
    if not marker:
        marker = position.get("opened_at")
        strict = False
    if not marker:
        return frame.iloc[0:0]
    try:
        ts = pd.Timestamp(marker)
    except (TypeError, ValueError):
        return frame.iloc[0:0]
    if index.tz is not None:
        ts = ts.tz_localize(index.tz) if ts.tzinfo is None else ts.tz_convert(index.tz)
    elif ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    if not strict:
        # Opened during a bar: that bar (by calendar day) counts as held.
        ts = ts.normalize()
        mask = index >= ts
    else:
        mask = index > ts
    return frame.loc[np.asarray(mask)]
