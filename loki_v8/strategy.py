"""LOKI v8 — consolidated ensemble strategy.

Fuses the best ideas already present in the codebase (Joshua's multi-factor
scoring: EMA/RSI/MACD/volume/S-R/ADX/ATR) with additional structure and
volatility filters into one causal score in [-100, 100].

Everything is computed with causal (rolling/ewm/shift) operators, so the
same scoring code drives both backtests and live trading without lookahead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .config import LokiConfig
from . import indicators as ta


@dataclass
class Signal:
    symbol: str
    action: str  # "BUY" | "SELL" | "HOLD"
    confidence: float  # 0-100
    entry_price: float
    stop_loss: float
    take_profit: float
    score: float
    target_2: float = 0.0
    risk_reward: float = 1.5
    squeeze_status: str = "OFF"
    reasons: List[str] = field(default_factory=list)


def _clip(v, lo=-1.0, hi=1.0):
    return np.clip(v, lo, hi)


FACTOR_KEYS = ("trend", "momentum", "volume_flow", "squeeze", "volatility")


def normalize_weights(weights: Optional[Dict[str, float]]) -> Dict[str, float]:
    """Return per-factor weights normalized to sum to 1.0 (missing -> 0).

    Defaults preserve the original fixed-weight ensemble when called with
    ``None`` or an empty dict.
    """
    defaults: Dict[str, float] = {
        "trend": 0.25,
        "momentum": 0.20,
        "volume_flow": 0.20,
        "squeeze": 0.20,
        "volatility": 0.15,
    }
    w: Dict[str, float] = {}
    for k in FACTOR_KEYS:
        try:
            w[k] = max(0.0, float((weights or {}).get(k, 0.0)))
        except (TypeError, ValueError):
            w[k] = 0.0
    if sum(w.values()) <= 1e-12:  # all zero -> fall back to the classic mix
        return dict(defaults)
    total = sum(w.values())
    return {k: v / total for k, v in w.items()}


class EnsembleStrategy:
    """Institutional Trend + Squeeze + Flow + Momentum + Volatility Ensemble."""

    def __init__(self, cfg: LokiConfig):
        self.cfg = cfg

    # ------------------------------------------------------------------
    # Causal scoring
    # ------------------------------------------------------------------
    def compute_factors(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return `df` with indicators plus one raw factor column per stack.

        Each ``f_*`` column is a causal score in [-1, 1] (positive = bullish).
        The composite score is a weighted sum of these columns, so any factor
        weighting can be evaluated without recomputing indicators.
        """
        df = ta.add_all_indicators(df)
        c = df["close"]

        # 1) Trend: EMA stack + supertrend + long-term trend
        df["f_trend"] = (
            0.30 * np.sign(c - df["ema_50"])
            + 0.20 * np.sign(df["ema_21"] - df["ema_50"])
            + 0.20 * np.sign(df["ema_9"] - df["ema_21"])
            + 0.20 * np.sign(df["supertrend"])
            + 0.10 * np.sign(c - df["sma_200"])
        )

        # 2) Momentum: RSI + MACD + stochastic + ROC
        df["f_momentum"] = (
            0.20 * _clip(df["rsi"] / 50.0 - 1.0)
            + 0.20 * np.sign(df["macd_hist"])
            + 0.15 * np.sign(df["macd"] - df["macd_signal"])
            + 0.15 * np.sign(df["stoch_k"] - df["stoch_d"])
            + 0.30 * (0.5 * np.sign(df["roc_20"]) + 0.5 * np.sign(df["roc_60"]))
        )

        # 3) Institutional Volume & Money Flow: OBV slope + CMF + VWAP
        obv_slope = np.sign(df["obv"].diff(5))
        cmf_val = _clip(df["cmf"] * 4.0)  # CMF > 0.25 is very bullish
        vwap_bias = np.sign(c - df["vwap"])
        df["f_volume_flow"] = 0.40 * cmf_val + 0.30 * obv_slope + 0.30 * vwap_bias

        # 4) TTM Squeeze Volatility Breakout:
        # Squeeze firing in momentum direction gives an explosive boost
        squeeze_mom_bias = np.sign(df["squeeze_mom"])
        squeeze_release = (~df["squeeze_on"]) & (df["squeeze_on"].shift(1).fillna(False))
        squeeze_factor = np.where(squeeze_release, squeeze_mom_bias * 1.5, squeeze_mom_bias * 0.5)
        df["f_squeeze"] = _clip(pd.Series(squeeze_factor, index=df.index))

        # 5) Volatility / Structure: Bollinger %B + ADX-gated DI
        pct_b = (c - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"]).replace(0.0, np.nan)
        mean_rev = 0.5 * _clip(0.5 - pct_b)
        di_spread = np.sign(df["plus_di"] - df["minus_di"])
        adx_gate = np.where(df["adx"] > 20.0, di_spread, 0.0)
        df["f_volatility"] = 0.5 * mean_rev + 0.5 * adx_gate

        return df

    def score_from_factors(
        self, factors: pd.DataFrame, weights: Optional[Dict[str, float]] = None
    ) -> pd.DataFrame:
        """Return a copy of a factor frame with a weighted composite `score`."""
        w = normalize_weights(weights if weights is not None else self.cfg.factor_weights)
        frame = factors.copy()
        raw = pd.Series(0.0, index=frame.index)
        for k in FACTOR_KEYS:
            raw = raw + w[k] * frame["f_" + k]
        frame["score"] = _clip(raw.fillna(0.0), -1.0, 1.0) * 100.0
        return frame

    def score_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return a copy of `df` with a causal `score` column in [-100, 100]."""
        return self.score_from_factors(self.compute_factors(df))

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
        confidence = min(98.0, 50.0 + abs(score) * 0.65)

        reasons: List[str] = []
        if action == "BUY":
            stop = entry - self.cfg.stop_loss_atr * atr
            target = entry + self.cfg.take_profit_atr * atr
            target2 = entry + (self.cfg.take_profit_atr * 1.6) * atr
            if last["ema_9"] > last["ema_21"]:
                reasons.append("Bullish EMA ribbon stack (EMA9 > EMA21)")
            if last["supertrend"] > 0:
                reasons.append("Supertrend green / long regime")
            if last["cmf"] > 0.05:
                reasons.append(f"Institutional accumulation (CMF {last['cmf']:+.2f})")
            if entry > last["vwap"]:
                reasons.append("Price trading above institutional VWAP")
            if bool(last["squeeze_on"]):
                reasons.append("TTM Squeeze coiled — breakout impending")
            elif float(last["squeeze_mom"]) > 0:
                reasons.append("TTM Squeeze released positive momentum")
        else:
            stop = entry + self.cfg.stop_loss_atr * atr
            target = entry - self.cfg.take_profit_atr * atr
            target2 = entry - (self.cfg.take_profit_atr * 1.6) * atr
            if last["ema_9"] < last["ema_21"]:
                reasons.append("Bearish EMA breakdown (EMA9 < EMA21)")
            if last["supertrend"] < 0:
                reasons.append("Supertrend red / short regime")
            if last["cmf"] < -0.05:
                reasons.append(f"Institutional distribution (CMF {last['cmf']:+.2f})")
            if entry < last["vwap"]:
                reasons.append("Price trading below VWAP")
            if bool(last["squeeze_on"]):
                reasons.append("TTM Squeeze active with downward bias")
            elif float(last["squeeze_mom"]) < 0:
                reasons.append("TTM Squeeze expanding downward")

        squeeze_status = (
            "ON"
            if bool(last["squeeze_on"])
            else ("FIRING_LONG" if float(last["squeeze_mom"]) > 0 else "FIRING_SHORT")
        )

        risk_dist = abs(entry - stop)
        reward_dist = abs(target - entry)
        rr = round(reward_dist / risk_dist, 2) if risk_dist > 0 else 1.5

        return Signal(
            symbol=symbol,
            action=action,
            confidence=confidence,
            entry_price=entry,
            stop_loss=stop,
            take_profit=target,
            target_2=target2,
            risk_reward=rr,
            squeeze_status=squeeze_status,
            score=score,
            reasons=reasons,
        )
