"""LOKI v8 — consolidated ensemble strategy.

Fuses the best ideas already present in the codebase (Joshua's multi-factor
scoring: EMA/RSI/MACD/volume/S-R/ADX/ATR) with additional structure and
volatility filters into one causal score in [-100, 100].

Everything is computed with causal (rolling/ewm/shift) operators, so the
same scoring code drives both backtests and live trading without lookahead.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pandas as pd

from .config import LokiConfig
from . import indicators as ta


@dataclass
class Signal:
    symbol: str
    action: str            # "BUY" | "SELL" | "HOLD"
    confidence: float      # 0-100
    entry_price: float
    stop_loss: float
    take_profit: float
    score: float
    reasons: List[str] = field(default_factory=list)


def _clip(v, lo=-1.0, hi=1.0):
    return np.clip(v, lo, hi)


class EnsembleStrategy:
    """Trend + momentum + volume + volatility + structure ensemble."""

    def __init__(self, cfg: LokiConfig):
        self.cfg = cfg

    # ------------------------------------------------------------------
    # Causal scoring
    # ------------------------------------------------------------------
    def score_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return a copy of `df` with a causal `score` column in [-100, 100]."""
        df = ta.add_all_indicators(df)
        c = df["close"]

        # 1) Trend (weight 0.30): EMA stack + supertrend + long-term trend
        trend = (
            0.30 * np.sign(c - df["ema_50"])
            + 0.20 * np.sign(df["ema_21"] - df["ema_50"])
            + 0.20 * np.sign(df["ema_9"] - df["ema_21"])
            + 0.20 * np.sign(df["supertrend"])
            + 0.10 * np.sign(c - df["sma_200"])
        )

        # 2) Momentum (weight 0.25): RSI + MACD + stochastic + ROC
        momentum = (
            0.20 * _clip(df["rsi"] / 50.0 - 1.0)
            + 0.20 * np.sign(df["macd_hist"])
            + 0.15 * np.sign(df["macd"] - df["macd_signal"])
            + 0.15 * np.sign(df["stoch_k"] - df["stoch_d"])
            + 0.30 * (0.5 * np.sign(df["roc_20"]) + 0.5 * np.sign(df["roc_60"]))
        )

        # 3) Volume (weight 0.15): OBV slope + participation
        obv_slope = np.sign(df["obv"].diff(5))
        participation = np.sign(df["volume"] - df["volume"].rolling(20).mean())
        volume = 0.5 * obv_slope + 0.5 * participation

        # 4) Volatility / mean-reversion (weight 0.15): Bollinger %B + ATR regime
        pct_b = (c - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"]).replace(0.0, np.nan)
        mean_rev = 0.6 * _clip(0.5 - pct_b) - 0.4 * np.sign(
            df["atr_pct"] - df["atr_pct"].rolling(50).mean()
        )

        # 5) Structure / regime (weight 0.15): DI spread, ADX-gated trend, SMA50
        di_spread = np.sign(df["plus_di"] - df["minus_di"])
        structure = (
            0.40 * di_spread
            + 0.30 * np.sign(df["adx"] - 20.0) * di_spread
            + 0.30 * np.sign(c - df["sma_50"])
        )

        raw = (
            0.30 * trend
            + 0.25 * momentum
            + 0.15 * volume
            + 0.15 * mean_rev
            + 0.15 * structure
        )
        df["score"] = _clip(raw.fillna(0.0), -1.0, 1.0) * 100.0
        return df

    # ------------------------------------------------------------------
    # Action / signal
    # ------------------------------------------------------------------
    def action_for(self, score: float) -> str:
        thr = self.cfg.signal_threshold
        if score >= thr:
            return "BUY"
        if score <= -thr:
            return "SELL"
        return "HOLD"

    def generate_signal(self, df: pd.DataFrame, symbol: str = "SYMBOL") -> Optional[Signal]:
        """Return the current signal for the latest bar, or None when flat."""
        min_bars = max(self.cfg.lookback_bars, 60)
        if df is None or len(df) < min_bars:
            return None

        frame = self.score_frame(df)
        last = frame.iloc[-1]
        score = float(last["score"])
        action = self.action_for(score)
        if action == "HOLD":
            return None

        entry = float(last["close"])
        atr = float(last["atr"]) if np.isfinite(last["atr"]) else entry * 0.02
        atr = max(atr, entry * 0.001)
        confidence = min(95.0, 50.0 + abs(score) * 0.7)

        if action == "BUY":
            stop = entry - self.cfg.stop_loss_atr * atr
            target = entry + self.cfg.take_profit_atr * atr
        else:
            stop = entry + self.cfg.stop_loss_atr * atr
            target = entry - self.cfg.take_profit_atr * atr

        return Signal(
            symbol=symbol,
            action=action,
            confidence=confidence,
            entry_price=entry,
            stop_loss=stop,
            take_profit=target,
            score=score,
        )
