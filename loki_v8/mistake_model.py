"""LOKI v8 — learning from mistakes: a filter trained on the AI's own trades.

Every entry the strategy takes leaves a record: the market conditions at the
signal bar and whether the trade ended in profit after costs. Replaying the
strategy over many years produces hundreds of those records — wins and,
crucially, losses. This module fits a small, regularised logistic model on
them (meta-labelling): given today's conditions, how often did setups like
this end as a loss? Entries whose estimated win probability falls below a
threshold are skipped.

Honesty rules, enforced by ``train_long_history.py``:

* features use only the completed signal bar (causal, same as the strategy);
* a model is trained only on trades that had already CLOSED before the
  window it is judged on (no label leakage);
* it ships only if it improves the validation window and does not hurt the
  untouched holdout — otherwise the live AI runs without it.

The fitted model is plain numbers (means, scales, weights) stored in the
training snapshot; no pickles, no external ML library.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

FEATURES: tuple = (
    "score",
    "atr_pct",
    "dist_sma200",
    "roc_20",
    "roc_60",
    "adx",
    "rsi",
    "realized_vol",
    "drawdown_60",
    "vol_rank",
    "f_trend",
    "f_momentum",
    "f_volume_flow",
    "f_squeeze",
    "f_volatility",
)


def feature_frame(frame: pd.DataFrame, bars_per_year: int = 252) -> pd.DataFrame:
    """Causal per-bar features from a scored strategy frame."""
    close = frame["close"].astype(float)
    out = pd.DataFrame(index=frame.index)
    out["score"] = frame["score"] / 100.0
    out["atr_pct"] = frame["atr_pct"]
    out["dist_sma200"] = close / frame["sma_200"] - 1.0
    out["roc_20"] = frame["roc_20"] / 100.0
    out["roc_60"] = frame["roc_60"] / 100.0
    out["adx"] = frame["adx"] / 50.0
    out["rsi"] = frame["rsi"] / 100.0
    rets = np.log(close).diff()
    out["realized_vol"] = rets.rolling(20, min_periods=10).std() * math.sqrt(bars_per_year)
    out["drawdown_60"] = close / close.rolling(60, min_periods=20).max() - 1.0
    out["vol_rank"] = frame["atr_pct"].rolling(252, min_periods=60).rank(pct=True)
    for name in ("f_trend", "f_momentum", "f_volume_flow", "f_squeeze", "f_volatility"):
        out[name] = frame[name] if name in frame.columns else 0.0
    return out[list(FEATURES)]


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return np.asarray(1.0 / (1.0 + np.exp(-np.clip(z, -30, 30))))


def fit(X: np.ndarray, y: np.ndarray, l2: float = 1.0, steps: int = 3000, lr: float = 0.1) -> Dict[str, Any]:
    """L2-regularised logistic regression by gradient descent (standardised)."""
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    mean = np.nanmean(X, axis=0)
    scale = np.nanstd(X, axis=0)
    scale[~np.isfinite(scale) | (scale < 1e-9)] = 1.0
    mean[~np.isfinite(mean)] = 0.0
    Z = np.nan_to_num((X - mean) / scale)
    n, k = Z.shape
    w = np.zeros(k)
    b = math.log((y.mean() + 1e-6) / (1 - y.mean() + 1e-6)) if 0 < y.mean() < 1 else 0.0
    for _ in range(steps):
        p = _sigmoid(Z @ w + b)
        grad_w = Z.T @ (p - y) / n + l2 * w / n
        grad_b = float(np.mean(p - y))
        w -= lr * grad_w
        b -= lr * grad_b
    return {
        "features": list(FEATURES),
        "mean": [round(float(v), 8) for v in mean],
        "scale": [round(float(v), 8) for v in scale],
        "weights": [round(float(v), 8) for v in w],
        "bias": round(float(b), 8),
        "samples": int(n),
        "base_win_rate": round(float(y.mean()), 4) if n else None,
    }


def predict_row(model: Dict[str, Any], row: Dict[str, Any] | pd.Series) -> Optional[float]:
    """Win probability for one feature row, or None when features are missing."""
    try:
        values = np.array([float(row[name]) for name in model["features"]], dtype=float)
    except (KeyError, TypeError, ValueError):
        return None
    if not np.all(np.isfinite(values)):
        return None
    z = (values - np.asarray(model["mean"])) / np.asarray(model["scale"])
    return float(_sigmoid(np.array([z @ np.asarray(model["weights"]) + model["bias"]]))[0])


def predict_frame(model: Dict[str, Any], features: pd.DataFrame) -> pd.Series:
    """Vectorised win probability per bar (NaN where features are missing)."""
    X = features[model["features"]].to_numpy(dtype=float)
    Z = (X - np.asarray(model["mean"])) / np.asarray(model["scale"])
    p = _sigmoid(Z @ np.asarray(model["weights"]) + model["bias"])
    p[~np.all(np.isfinite(X), axis=1)] = np.nan
    return pd.Series(p, index=features.index)


def allows(meta: Optional[Dict[str, Any]], probability: Optional[float]) -> bool:
    """Gate decision: no filter, or a probability at/above its threshold.

    A missing probability (warm-up features) never blocks: the filter can
    only remove entries it has an opinion about.
    """
    if not meta or not meta.get("model"):
        return True
    if probability is None or not math.isfinite(probability):
        return True
    return probability >= float(meta.get("threshold", 0.0))


def training_rows(frames: Sequence[pd.DataFrame], trades_by_frame: Sequence[List[Any]], bars_per_year: int,
                  closed_before: Optional[str] = None, entered_before: Optional[str] = None):
    """(X, y) from trades: features at the bar before entry, label = profit."""
    X: List[List[float]] = []
    y: List[int] = []
    for frame, trades in zip(frames, trades_by_frame):
        feats = feature_frame(frame, bars_per_year)
        index = feats.index
        for t in trades:
            if getattr(t, "exit_reason", "") == "scale_out":
                continue
            if closed_before and str(pd.Timestamp(t.exit_time).date()) >= closed_before:
                continue
            if entered_before and str(pd.Timestamp(t.entry_time).date()) >= entered_before:
                continue
            pos = index.get_indexer([pd.Timestamp(t.entry_time)])[0]
            if pos <= 0:
                continue
            row = feats.iloc[pos - 1].to_numpy(dtype=float)
            if not np.all(np.isfinite(row)):
                continue
            X.append(list(row))
            y.append(1 if t.pnl > 0 else 0)
    return np.array(X), np.array(y)
