"""LOKI v8 — market-regime detection (multi-factor trend & volatility engine).

Classifies every bar into one of five regimes from causal indicators only:

    STRONG_BULL  — uptrend confirmed with strong directional strength (ADX)
    BULL         — uptrend with weaker directional strength
    RANGING      — choppy / sideways, no dominant trend
    BEAR         — downtrend confirmed
    CRISIS       — downtrend with a volatility spike (crash conditions)

Volatility is scored as a percentile of the daily ATR% over a trailing
window (causal rolling rank), so "high vol" always refers to what the bar's
history already knew — never the future. The backtester blocks longs in
BEAR/CRISIS states, and the Director agent uses the same helpers for its
posture, keeping live trading and research consistent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np
import pandas as pd

from . import indicators as ta

STATES = ("STRONG_BULL", "BULL", "RANGING", "BEAR", "CRISIS")
BULLISH_STATES = frozenset({"STRONG_BULL", "BULL"})
BEARISH_STATES = frozenset({"BEAR", "CRISIS"})

# How many trailing bars the volatility percentile looks back on.
VOL_WINDOW = 252


def is_bullish(state: str) -> bool:
    return state in BULLISH_STATES


def is_bearish(state: str) -> bool:
    return state in BEARISH_STATES


@dataclass
class Regime:
    state: str = "RANGING"  # STRONG_BULL | BULL | RANGING | BEAR | CRISIS
    confidence: float = 0.0  # 0-100
    trend_score: float = 0.0  # -3 .. +3
    volatility_pct: float = 0.0  # daily ATR% (as a percent)
    adx: float = 0.0
    volatility_rank: float = 0.0  # percentile of current ATR% (0-1)
    description: str = ""

    def __post_init__(self):
        if not self.description:
            self.description = _default_description(self.state)


def _default_description(state: str) -> str:
    return {
        "STRONG_BULL": "Strong uptrend — directional momentum confirmed",
        "BULL": "Uptrend developing — cautiously bullish",
        "RANGING": "Sideways chop — mean-reversion conditions",
        "BEAR": "Downtrend — longs blocked, defensive posture",
        "CRISIS": "High-volatility crash regime — capital preserved",
    }.get(state, "Undetermined market structure")


def _trend_and_vol(frame: pd.DataFrame) -> dict:
    """Shared causal indicator extraction for both single-shot and series."""
    c = frame["close"]
    sma50 = frame["sma_50"]
    sma200 = frame["sma_200"]
    slope200 = sma200.diff(20)
    adx = frame["adx"]
    atr_pct = frame["atr_pct"]

    vol_rank = atr_pct.rolling(VOL_WINDOW, min_periods=60).rank(pct=True)

    bull_core = (c > sma200) & (sma50 > sma200) & (slope200 > 0)
    bear_core = (c < sma200) & (sma50 < sma200) & (slope200 < 0)

    strong_bull = bull_core & (adx >= 25)
    bull = bull_core & ~strong_bull
    crisis = bear_core & (vol_rank >= 0.90)
    bear = bear_core & ~(vol_rank >= 0.90)

    state = np.where(
        strong_bull,
        "STRONG_BULL",
        np.where(bull, "BULL", np.where(crisis, "CRISIS", np.where(bear, "BEAR", "RANGING"))),
    )

    trend_score = np.sign(c - sma200) + np.sign(sma50 - sma200) + np.sign(slope200)

    return {
        "state": state,
        "trend_score": trend_score,
        "atr_pct": atr_pct,
        "adx": adx,
        "vol_rank": vol_rank,
    }


def detect_regime(df: pd.DataFrame) -> Regime:
    """Return the regime for the latest bar of `df`."""
    if df is None or len(df) < 210:
        return Regime()

    frame = ta.add_all_indicators(df)
    parts = _trend_and_vol(frame)

    state = str(parts["state"][-1])
    score = float(parts["trend_score"].iloc[-1])
    adx = float(parts["adx"].iloc[-1]) if np.isfinite(parts["adx"].iloc[-1]) else 0.0
    atr_pct = float(parts["atr_pct"].iloc[-1]) if np.isfinite(parts["atr_pct"].iloc[-1]) else 0.0
    vol_rank = float(parts["vol_rank"].iloc[-1]) if np.isfinite(parts["vol_rank"].iloc[-1]) else 0.5

    if state == "STRONG_BULL":
        confidence = min(95.0, 60.0 + max(0.0, adx - 25.0) + 5.0 * score)
    elif state == "BULL":
        confidence = min(90.0, 55.0 + 10.0 * score)
    elif state == "BEAR":
        confidence = min(90.0, 55.0 + 10.0 * abs(score))
    elif state == "CRISIS":
        confidence = min(95.0, 60.0 + 35.0 * vol_rank)
    else:
        confidence = 50.0 + 5.0 * abs(score)

    description = _default_description(state)
    if state in BULLISH_STATES and atr_pct > 4.0:
        description += " · volatility elevated"
    elif state == "RANGING" and adx < 15:
        description += " · low directional strength"
    elif state == "BEAR" and vol_rank >= 0.75:
        description += " · vol building toward crisis"

    return Regime(
        state,
        round(confidence, 1),
        score,
        atr_pct,
        adx,
        volatility_rank=round(vol_rank, 2),
        description=description,
    )


def regime_series(frame: pd.DataFrame) -> pd.Series:
    """Vectorized, causal regime label for every bar of an indicator frame."""
    if frame is None or len(frame) == 0:
        return pd.Series(dtype=object)
    parts = _trend_and_vol(frame)
    return pd.Series(parts["state"], index=frame.index)


def regime_distribution(frame: pd.DataFrame) -> Dict[str, float]:
    """Fraction of bars spent in each regime (0-1), over the frame."""
    if frame is None or len(frame) == 0:
        return {}
    series = regime_series(frame)
    counts = series.value_counts(normalize=True)
    return {s: round(float(counts.get(s, 0.0)), 4) for s in STATES if counts.get(s, 0.0) > 0.0}
