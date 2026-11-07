"""LOKI v8 — Portfolio AI: the verified strategy on every market at once.

One trend strategy on one symbol is bumpy. The same verified rules run on
many weakly-related markets (stocks, ETFs, gold, bonds, crypto) and then
combined smooth each other out. This module:

1. replays each market's universal profile with ``run_backtest`` (a
   "sleeve"), giving its daily return after costs and its daily exposure;
2. gives every active sleeve an equal share of capital, then scales the
   whole book toward a target annual volatility — capped every day so total
   holdings never exceed 100% of the account (no leverage, ever);
3. for live use, reports what that exact portfolio holds at the latest
   completed bar, so the paper autopilot holds what was tested.

Scale changes are charged ``COST_BPS`` per side on the traded notional.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .backtest import run_backtest
from .config import LokiConfig
from .data import is_crypto
from .strategy import EnsembleStrategy

VOL_WINDOW = 63  # trading days of portfolio returns for realised volatility
ANNUAL = 260  # union calendar mixes 252 equity and 365 crypto days
MAX_SCALE = 4.0  # sleeves at 1/N each; the 100% gross cap binds far earlier
COST_BPS = 15.0  # fees + slippage per side on scale-driven rebalancing
FEE_BPS = 10.0  # per side on sleeve fills, on top of slippage in fills


def config_for(params: Dict[str, Any]) -> LokiConfig:
    base = {k: v for k, v in params.items() if k in LokiConfig.__dataclass_fields__ and k != "factor_weights"}
    return replace(LokiConfig(initial_cash=100_000.0), **base, factor_weights=dict(params.get("factor_weights") or {}))


def run_sleeve(df: pd.DataFrame, params: Dict[str, Any], symbol: str) -> Dict[str, Any]:
    """Replay one market: daily net returns, daily exposure, latest state."""
    cfg = config_for(params)
    bpy = 365 if is_crypto(symbol) else 252
    frame = EnsembleStrategy(cfg).score_frame(df)
    res = run_backtest(df, cfg, symbol=symbol, bars_per_year=bpy, frame=frame)
    equity = res.equity_curve
    if equity.empty:
        return {"symbol": symbol, "returns": pd.Series(dtype=float), "exposure": pd.Series(dtype=float), "state": None}
    idx = equity.index
    fees = pd.Series(0.0, index=idx)
    held = pd.Series(0.0, index=idx)
    open_trade = None
    for t in res.trades:
        for stamp, px in ((t.entry_time, t.entry_price), (t.exit_time, t.exit_price)):
            pos = idx.searchsorted(pd.Timestamp(stamp))
            if pos < len(fees):
                fees.iloc[pos] += px * t.qty * FEE_BPS / 10_000.0
        mask = (idx >= t.entry_time) & (idx < t.exit_time)
        held[mask] += t.qty
        if t.exit_reason == "end":
            open_trade = t
    net = equity - fees.cumsum()
    close = df["close"].reindex(idx).astype(float)
    exposure = (held * close / net).clip(lower=0.0).fillna(0.0)
    if open_trade is not None:
        # The replay force-closes at the end; for live use it is still open.
        exposure.iloc[-1] = float(open_trade.qty * close.iloc[-1] / net.iloc[-1]) if net.iloc[-1] > 0 else 0.0
    returns = net.pct_change().fillna(0.0)
    norm = pd.DatetimeIndex(idx)
    if norm.tz is not None:
        norm = norm.tz_localize(None)
    returns.index = exposure.index = norm.normalize()
    state = None
    if open_trade is not None:
        state = {
            "in_position": True,
            "entry_date": str(pd.Timestamp(open_trade.entry_time).date()),
            "entry_price": round(float(open_trade.entry_price), 6),
            "unrealized_pct": round((float(close.iloc[-1]) / float(open_trade.entry_price) - 1) * 100, 2),
        }
    else:
        state = {"in_position": False}
    state["last_close"] = round(float(close.iloc[-1]), 6)
    state["as_of"] = str(norm[-1].date())
    return {"symbol": symbol, "returns": returns, "exposure": exposure, "state": state}


def combine(sleeves: Dict[str, Dict[str, Any]], target_vol_pct: float, warmup: int = 300) -> Dict[str, Any]:
    """Equal-capital sleeves, vol-targeted, gross exposure capped at 100%."""
    R = pd.DataFrame({s: v["returns"] for s, v in sleeves.items()}).sort_index()
    E = pd.DataFrame({s: v["exposure"] for s, v in sleeves.items()}).reindex(R.index).ffill().fillna(0.0)
    active = pd.DataFrame(
        {s: R.index >= (v["returns"].index[min(warmup, len(v["returns"]) - 1)] if len(v["returns"]) else R.index[-1])
         for s, v in sleeves.items()},
        index=R.index,
    )
    R = R.fillna(0.0)
    n = active.sum(axis=1).clip(lower=1)
    ew = (R * active).sum(axis=1) / n
    gross_ew = (E * active).sum(axis=1) / n
    vol = ew.rolling(VOL_WINDOW, min_periods=20).std().shift(1) * math.sqrt(ANNUAL)
    target = (target_vol_pct / 100.0 / vol).fillna(1.0)
    weekly = target.resample("W-FRI").last().reindex(ew.index, method="ffill").fillna(1.0)
    # Same-day cap: a sleeve's holdings for day t are decided at that day's
    # open from day t-1's signal, so the book can size around them exactly.
    cap = (1.0 / gross_ew.replace(0.0, np.nan)).fillna(MAX_SCALE)
    scale = np.minimum(weekly, cap).clip(lower=0.0, upper=MAX_SCALE)
    cost = scale.diff().abs().fillna(0.0) * gross_ew * COST_BPS / 10_000.0
    returns = ew * scale - cost
    return {"returns": returns, "scale": scale, "gross": gross_ew * scale, "active": active, "exposure": E,
            "n_active": n, "base_returns": ew}


def window_stats(returns: pd.Series, start: str, end: str) -> Dict[str, Any]:
    x = returns[(returns.index >= start) & (returns.index <= end)]
    if len(x) < 30:
        return {}
    eq = (1 + x).cumprod()
    years = len(x) / ANNUAL
    cagr = eq.iloc[-1] ** (1 / years) - 1 if eq.iloc[-1] > 0 else -1.0
    sd = x.std()
    return {
        "cagr_pct": round(float(cagr * 100), 2),
        "sharpe": round(float(x.mean() / sd * math.sqrt(ANNUAL)), 3) if sd > 0 else 0.0,
        "max_dd_pct": round(float((eq / eq.cummax() - 1).min() * 100), 2),
        "profitable_months_pct": round(float((x.resample("ME").apply(lambda m: (1 + m).prod() - 1) > 0).mean() * 100), 1),
    }


def buy_hold_returns(frames: Dict[str, pd.DataFrame], index: pd.DatetimeIndex, active: pd.DataFrame) -> pd.Series:
    cols = {}
    for s, df in frames.items():
        c = df["close"].astype(float)
        idx = pd.DatetimeIndex(c.index)
        if idx.tz is not None:
            idx = idx.tz_localize(None)
        c.index = idx.normalize()
        cols[s] = c.pct_change()
    bh = pd.DataFrame(cols).reindex(index).fillna(0.0)
    n = active.sum(axis=1).clip(lower=1)
    return (bh * active).sum(axis=1) / n


def allocation(sleeves: Dict[str, Dict[str, Any]], book: Dict[str, Any], prices: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """What the tested portfolio holds now: per-market target weights (sum ≤ 1)."""
    scale_now = float(book["scale"].iloc[-1])
    active_now = book["active"].iloc[-1]
    n = max(1, int(active_now.sum()))
    rows: List[Dict[str, Any]] = []
    for s, v in sleeves.items():
        state = v.get("state") or {}
        expo = float(v["exposure"].iloc[-1]) if len(v["exposure"]) else 0.0
        weight = scale_now / n * expo if bool(active_now.get(s, False)) else 0.0
        rows.append({"symbol": s, "weight": weight, "sleeve_exposure": round(expo, 4), **state,
                     "price": (prices or {}).get(s) or state.get("last_close")})
    gross = sum(r["weight"] for r in rows)
    if gross > 1.0:  # exact daily cap for live use
        for r in rows:
            r["weight"] /= gross
        gross = 1.0
    for r in rows:
        r["weight"] = round(r["weight"], 5)
    rows.sort(key=lambda r: r["weight"], reverse=True)
    return {"scale": round(scale_now, 4), "gross": round(gross, 4), "cash": round(1.0 - gross, 4),
            "active_markets": n, "positions": rows}


def select_target_vol(sleeves: Dict[str, Dict[str, Any]], windows: Dict[str, Tuple[str, str]],
                      candidates: Tuple[float, ...] = (10.0, 15.0, 20.0, 25.0)) -> Tuple[float, List[Dict[str, Any]]]:
    """Pick the vol target with the best WORSE of development/validation Sharpe."""
    trials = []
    for tv in candidates:
        book = combine(sleeves, tv)
        dev = window_stats(book["returns"], *windows["development"])
        val = window_stats(book["returns"], *windows["validation"])
        trials.append({"target_vol_pct": tv, "development": dev, "validation": val,
                       "rank": round(min(dev.get("sharpe", -9), val.get("sharpe", -9)), 3)})
    best = max(trials, key=lambda t: (t["rank"], -t["target_vol_pct"]))
    return best["target_vol_pct"], trials

