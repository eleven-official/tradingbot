"""LOKI v8 — market-regime detection.

Classifies the market as BULL / BEAR / RANGING from causal indicators, so the
Director agent can set its posture (long / flat / short) and the backtester
can avoid buying into falling markets.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import indicators as ta


@dataclass
class Regime:
    state: str            # "BULL" | "BEAR" | "RANGING"
    confidence: float     # 0-100
    trend_score: float    # -3 .. +3
    volatility_pct: float # daily ATR%
    adx: float


def detect_regime(df: pd.DataFrame) -> Regime:
    """Return the regime for the latest bar of `df`."""
    if df is None or len(df) < 210:
        return Regime("RANGING", 0.0, 0.0, 0.0, 0.0)

    frame = ta.add_all_indicators(df)
    last = frame.iloc[-1]
    price = float(last["close"])
    sma50 = float(last["sma_50"])
    sma200 = float(last["sma_200"])
    adx = float(last["adx"])
    atr_pct = float(last["atr_pct"])
    slope200 = float(frame["sma_200"].diff(20).iloc[-1])

    trend_score = 0.0
    trend_score += 1.0 if price > sma200 else -1.0
    trend_score += 1.0 if sma50 > sma200 else -1.0
    trend_score += 1.0 if slope200 > 0 else -1.0

    if trend_score >= 2 and adx >= 20:
        state = "BULL"
    elif trend_score <= -2:
        state = "BEAR"
    else:
        state = "RANGING"

    confidence = min(95.0, 50.0 + abs(trend_score) / 3.0 * 40.0)
    return Regime(state, confidence, trend_score, atr_pct, adx)


def regime_series(frame: pd.DataFrame) -> pd.Series:
    """Vectorized, causal regime label for every bar of an indicator frame."""
    c = frame["close"]
    sma50 = frame["sma_50"]
    sma200 = frame["sma_200"]
    slope200 = sma200.diff(20)
    adx = frame["adx"]

    bull = (c > sma200) & (sma50 > sma200) & (slope200 > 0) & (adx >= 20)
    bear = (c < sma200) & (sma50 < sma200) & (slope200 < 0)

    state = np.where(bull, "BULL", np.where(bear, "BEAR", "RANGING"))
    return pd.Series(state, index=frame.index)
