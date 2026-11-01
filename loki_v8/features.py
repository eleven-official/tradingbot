"""LOKI v8 — advanced feature engineering and regime-aware signals.

New factor families that extend the ensemble beyond the original 5 stacks:
- Cross-asset / market-structure factors (correlation, beta, flow)
- Microstructure / liquidity factors (spread, depth, toxicity)
- Alternative data proxies (funding rates, open interest, on-chain)
- Regime-specific factor gating (only activate factors in their regime)
- Non-linear interactions (factor × factor, factor × regime)

Also provides a feature importance tracker that learns which factors
actually drive P&L in each regime — feeding back into the trainer.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .config import LokiConfig
from . import indicators as ta
from .regime import regime_series, is_bullish, is_bearish, STATES

logger = logging.getLogger(__name__)

STATE_DIR = Path("state") / "features"
STATE_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Factor Registry — every factor knows its regime affinity
# ---------------------------------------------------------------------------

@dataclass
class FactorSpec:
    """Metadata for a factor: name, regime affinity, description."""
    name: str
    column: str                    # column name in the factor frame
    regime_affinity: Dict[str, float]  # regime -> weight multiplier (0-2)
    description: str
    category: str                  # "trend", "momentum", "flow", "squeeze", "vol", "cross", "micro", "alt"


# Core factor specs — each factor declares where it works best
FACTOR_SPECS: List[FactorSpec] = [
    # Original 5 stacks (preserved)
    FactorSpec("trend_ema", "f_trend", {"STRONG_BULL": 1.2, "BULL": 1.0, "RANGING": 0.5, "BEAR": 0.3, "CRISIS": 0.2},
               "EMA stack + supertrend + long-term trend", "trend"),
    FactorSpec("momentum_rsi_macd", "f_momentum", {"STRONG_BULL": 1.0, "BULL": 1.2, "RANGING": 0.8, "BEAR": 0.6, "CRISIS": 0.4},
               "RSI + MACD + stochastic + ROC", "momentum"),
    FactorSpec("volume_flow", "f_volume_flow", {"STRONG_BULL": 1.1, "BULL": 1.0, "RANGING": 0.9, "BEAR": 0.7, "CRISIS": 0.5},
               "OBV slope + CMF + VWAP bias", "flow"),
    FactorSpec("squeeze", "f_squeeze", {"STRONG_BULL": 1.3, "BULL": 1.1, "RANGING": 1.5, "BEAR": 0.8, "CRISIS": 0.6},
               "TTM Squeeze breakout momentum", "squeeze"),
    FactorSpec("volatility_structure", "f_volatility", {"STRONG_BULL": 0.8, "BULL": 0.9, "RANGING": 1.2, "BEAR": 1.0, "CRISIS": 1.3},
               "Bollinger %B mean reversion + ADX-gated DI", "vol"),

    # NEW: Cross-asset / market structure
    FactorSpec("market_beta", "f_beta", {"STRONG_BULL": 1.0, "BULL": 1.0, "RANGING": 0.5, "BEAR": 1.2, "CRISIS": 1.5},
               "Rolling beta vs SPY/BTC — risk-on/off filter", "cross"),
    FactorSpec("correlation_regime", "f_corr_regime", {"STRONG_BULL": 0.8, "BULL": 0.8, "RANGING": 0.6, "BEAR": 1.3, "CRISIS": 1.5},
               "Cross-asset correlation spike = regime shift", "cross"),
    FactorSpec("sector_rotation", "f_sector_rot", {"STRONG_BULL": 1.2, "BULL": 1.1, "RANGING": 0.7, "BEAR": 0.4, "CRISIS": 0.3},
               "Relative strength vs sector/industry peers", "cross"),
    FactorSpec("flow_divergence", "f_flow_div", {"STRONG_BULL": 1.0, "BULL": 1.0, "RANGING": 0.8, "BEAR": 0.9, "CRISIS": 0.6},
               "Price/volume divergence across correlated assets", "cross"),

    # NEW: Microstructure / liquidity
    FactorSpec("bid_ask_spread", "f_spread", {"STRONG_BULL": 0.7, "BULL": 0.8, "RANGING": 0.9, "BEAR": 1.1, "CRISIS": 1.4},
               "Relative spread — liquidity stress indicator", "micro"),
    FactorSpec("volume_profile", "f_vol_profile", {"STRONG_BULL": 1.0, "BULL": 1.0, "RANGING": 1.2, "BEAR": 0.8, "CRISIS": 0.6},
               "Volume at price — support/resistance from volume", "micro"),
    FactorSpec("order_flow_toxicity", "f_toxicity", {"STRONG_BULL": 0.6, "BULL": 0.7, "RANGING": 0.9, "BEAR": 1.2, "CRISIS": 1.5},
               "VPIN-like toxicity — informed trading probability", "micro"),

    # NEW: Alternative data proxies (from OHLCV only)
    FactorSpec("funding_rate_proxy", "f_funding", {"STRONG_BULL": 1.2, "BULL": 1.0, "RANGING": 0.5, "BEAR": 0.3, "CRISIS": 0.2},
               "Funding rate proxy from basis + OI change", "alt"),
    FactorSpec("open_interest_momentum", "f_oi_mom", {"STRONG_BULL": 1.1, "BULL": 1.0, "RANGING": 0.6, "BEAR": 0.8, "CRISIS": 0.5},
               "Open interest momentum — commitment gauge", "alt"),
    FactorSpec("liquidation_pressure", "f_liq_pressure", {"STRONG_BULL": 0.3, "BULL": 0.5, "RANGING": 0.7, "BEAR": 1.3, "CRISIS": 1.5},
               "Wick-based liquidation proxy — cascade risk", "alt"),
    FactorSpec("whale_accumulation", "f_whale_acc", {"STRONG_BULL": 1.0, "BULL": 1.2, "RANGING": 0.8, "BEAR": 0.5, "CRISIS": 0.3},
               "Large trade proxy — volume clusters at key levels", "alt"),
]


def compute_cross_asset_factors(df: pd.DataFrame, benchmark: pd.DataFrame) -> pd.DataFrame:
    """Compute cross-asset factors using a benchmark (SPY for equities, BTC for crypto)."""
    df = df.copy()
    c = df["close"]
    bc = benchmark["close"].reindex(df.index).ffill().bfill()

    # Rolling beta (60-day)
    ret = np.log(c / c.shift(1))
    b_ret = np.log(bc / bc.shift(1))
    cov = ret.rolling(60).cov(b_ret)
    var = b_ret.rolling(60).var()
    df["f_beta"] = (cov / var.replace(0, np.nan)).clip(-3, 3).fillna(1.0)

    # Rolling correlation (60-day)
    df["f_corr_regime"] = ret.rolling(60).corr(b_ret).fillna(0)

    # Relative strength (vs benchmark)
    df["f_sector_rot"] = np.sign((c / c.shift(20)) / (bc / bc.shift(20)) - 1).fillna(0)

    # Flow divergence: our volume trend vs benchmark volume trend
    our_vol_trend = np.sign(df["volume"].rolling(20).apply(lambda x: np.polyfit(range(len(x)), x, 1)[0] if len(x) == 20 else 0))
    bench_vol = benchmark["volume"].reindex(df.index).ffill().bfill()
    bench_vol_trend = np.sign(bench_vol.rolling(20).apply(lambda x: np.polyfit(range(len(x)), x, 1)[0] if len(x) == 20 else 0))
    df["f_flow_div"] = (our_vol_trend - bench_vol_trend).fillna(0)

    return df


def compute_microstructure_factors(df: pd.DataFrame) -> pd.DataFrame:
    """Compute microstructure/liquidity factors from OHLCV."""
    df = df.copy()
    c, h, l, v = df["close"], df["high"], df["low"], df["volume"]

    # Relative spread proxy: (high - low) / close ≈ spread + volatility
    # In crypto 24/7, this is mostly volatility; in equities it's spread + vol
    df["f_spread"] = ((h - l) / c.replace(0, np.nan)).rolling(20).mean().fillna(0)

    # Volume profile: volume-weighted average price vs close
    typical = (h + l + c) / 3
    vwap = (typical * v).rolling(20).sum() / v.rolling(20).sum().replace(0, np.nan)
    df["f_vol_profile"] = np.sign(c - vwap).fillna(0)

    # VPIN-like toxicity: volume imbalance at price extremes
    # High volume on up-ticks vs down-ticks within the bar
    up_vol = v * np.where(c > df["open"], 1, 0)
    down_vol = v * np.where(c < df["open"], 1, 0)
    vol_imbalance = (up_vol - down_vol) / (up_vol + down_vol).replace(0, np.nan)
    df["f_toxicity"] = vol_imbalance.rolling(20).std().fillna(0)

    return df


def compute_alt_data_proxies(df: pd.DataFrame) -> pd.DataFrame:
    """Compute alternative data proxies from OHLCV only (no external feeds needed)."""
    df = df.copy()
    c, h, l, o, v = df["close"], df["high"], df["low"], df["open"], df["volume"]

    # Funding rate proxy: annualized basis from futures vs spot
    # For crypto: approximate from the premium/discount in the term structure
    # Here: use (high - low) / close as a volatility proxy, and volume trend
    # In real use, this would come from exchange API; this is a structural proxy
    df["f_funding"] = (ta.rolling_slope(c, 20) * 252).clip(-1, 1).fillna(0)  # annualized trend as funding proxy

    # Open interest momentum proxy: volume trend * price trend
    vol_trend = ta.rolling_slope(v, 20)
    price_trend = ta.rolling_slope(c, 20)
    df["f_oi_mom"] = np.sign(vol_trend * price_trend).fillna(0)

    # Liquidation pressure: long lower wicks (long liquidations) or upper wicks (short liquidations)
    lower_wick = (c - l) / (h - l).replace(0, np.nan)  # where close is, relative to range
    upper_wick = (h - c) / (h - l).replace(0, np.nan)
    # High lower wick + high volume = long liquidations (bearish)
    # High upper wick + high volume = short liquidations (bullish)
    liq_signal = (lower_wick - upper_wick) * (v / v.rolling(20).mean().replace(0, np.nan))
    df["f_liq_pressure"] = liq_signal.rolling(10).mean().fillna(0)

    # Whale accumulation: volume clusters at price levels (simplified)
    # High volume bars where price barely moved = absorption
    price_change = (c / c.shift(1) - 1).abs()
    vol_ratio = v / v.rolling(20).mean().replace(0, np.nan)
    absorption = (vol_ratio > 1.5) & (price_change < 0.01)
    df["f_whale_acc"] = absorption.rolling(20).sum().fillna(0) / 20.0  # fraction of absorption bars

    return df


def compute_all_advanced_factors(
    df: pd.DataFrame,
    benchmark: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Compute ALL advanced factors and append to frame."""
    df = df.copy()

    # Need base indicators first
    df = ta.add_all_indicators(df)

    # Cross-asset factors (need benchmark)
    if benchmark is not None and not benchmark.empty:
        df = compute_cross_asset_factors(df, benchmark)

    # Microstructure factors
    df = compute_microstructure_factors(df)

    # Alternative data proxies
    df = compute_alt_data_proxies(df)

    return df


# ---------------------------------------------------------------------------
# Regime-Gated Factor Weighting
# ---------------------------------------------------------------------------

def regime_gated_weights(
    base_weights: Dict[str, float],
    regime: str,
    factor_specs: Optional[List[FactorSpec]] = None,
) -> Dict[str, float]:
    """Adjust factor weights based on current regime affinity.

    Factors that don't work in the current regime get downweighted.
    """
    specs = factor_specs or FACTOR_SPECS
    weights = dict(base_weights)

    for spec in specs:
        if spec.name in weights:
            affinity = spec.regime_affinity.get(regime, 1.0)
            weights[spec.name] *= affinity

    # Renormalize
    total = sum(max(0, v) for v in weights.values())
    if total > 0:
        weights = {k: max(0, v) / total for k, v in weights.items()}

    return weights


def compute_regime_gated_score(
    df: pd.DataFrame,
    base_weights: Dict[str, float],
    factor_specs: Optional[List[FactorSpec]] = None,
) -> pd.DataFrame:
    """Compute a regime-aware composite score that changes weights per bar."""
    specs = factor_specs or FACTOR_SPECS
    df = df.copy()

    # Get regime series
    regimes = regime_series(df)

    # Build factor columns if missing
    factor_cols = [s.column for s in specs if s.column in df.columns]
    if not factor_cols:
        return df

    # Compute per-bar weights
    score = pd.Series(0.0, index=df.index)
    for i, (idx, regime) in enumerate(regimes.items()):
        w = regime_gated_weights(base_weights, regime, specs)
        row_score = 0.0
        for spec in specs:
            if spec.column in df.columns and spec.name in w:
                row_score += w[spec.name] * df[spec.column].iloc[i]
        score.iloc[i] = np.clip(row_score, -1, 1) * 100

    df["score_regime_gated"] = score
    return df


# ---------------------------------------------------------------------------
# Factor Interaction Terms (non-linear)
# ---------------------------------------------------------------------------

def add_factor_interactions(df: pd.DataFrame) -> pd.DataFrame:
    """Add non-linear interaction terms between factors."""
    df = df.copy()

    # Trend × Momentum: trend-following momentum works better
    if "f_trend" in df.columns and "f_momentum" in df.columns:
        df["f_trend_x_momentum"] = df["f_trend"] * df["f_momentum"]

    # Squeeze × Volume: squeeze breakout with volume confirmation
    if "f_squeeze" in df.columns and "f_volume_flow" in df.columns:
        df["f_squeeze_x_volume"] = df["f_squeeze"] * df["f_volume_flow"]

    # Volatility × Trend: mean reversion in ranging, trend in trending
    if "f_volatility" in df.columns and "f_trend" in df.columns:
        df["f_vol_x_trend"] = df["f_volatility"] * df["f_trend"]

    # Cross-asset beta × local momentum
    if "f_beta" in df.columns and "f_momentum" in df.columns:
        df["f_beta_x_momentum"] = df["f_beta"] * df["f_momentum"]

    # Liquidity × Squeeze: squeeze in illiquid conditions = fakeout risk
    if "f_spread" in df.columns and "f_squeeze" in df.columns:
        df["f_spread_x_squeeze"] = -df["f_spread"] * df["f_squeeze"]  # negative = bad

    # Funding proxy × trend: funding in direction of trend = fuel
    if "f_funding" in df.columns and "f_trend" in df.columns:
        df["f_funding_x_trend"] = df["f_funding"] * df["f_trend"]

    # Liquidation pressure × volatility structure
    if "f_liq_pressure" in df.columns and "f_volatility" in df.columns:
        df["f_liq_x_vol"] = df["f_liq_pressure"] * df["f_volatility"]

    return df


# ---------------------------------------------------------------------------
# Feature Importance Learner (online, regime-conditioned)
# ---------------------------------------------------------------------------

@dataclass
class FactorImportanceState:
    """Tracks factor effectiveness per regime over time."""
    regime: str
    factor_returns: Dict[str, List[float]] = field(default_factory=dict)
    factor_hit_rates: Dict[str, List[bool]] = field(default_factory=dict)
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def update(self, factor_values: Dict[str, float], forward_return: float) -> None:
        """Update with one observation."""
        for fname, fval in factor_values.items():
            if fname not in self.factor_returns:
                self.factor_returns[fname] = []
                self.factor_hit_rates[fname] = []
            self.factor_returns[fname].append(fval * forward_return)
            self.factor_hit_rates[fname].append((fval > 0) == (forward_return > 0))

    def get_importance(self) -> Dict[str, Dict[str, float]]:
        """Compute importance metrics per factor."""
        out = {}
        for fname in self.factor_returns:
            rets = self.factor_returns[fname]
            hits = self.factor_hit_rates[fname]
            if len(rets) < 10:
                continue
            out[fname] = {
                "mean_contribution": float(np.mean(rets)),
                "hit_rate": float(np.mean(hits)),
                "n_obs": len(rets),
                "sharpe": float(np.mean(rets) / (np.std(rets) + 1e-9)),
            }
        return out


class RegimeFeatureLearner:
    """Online learner that tracks which factors work in which regimes."""

    def __init__(self):
        self.states: Dict[str, FactorImportanceState] = {}

    def observe(
        self,
        regime: str,
        factor_values: Dict[str, float],
        forward_return: float,
    ) -> None:
        if regime not in self.states:
            self.states[regime] = FactorImportanceState(regime=regime)
        self.states[regime].update(factor_values, forward_return)
        self.states[regime].last_updated = datetime.now().isoformat(timespec="seconds")

    def get_regime_importance(self, regime: str) -> Dict[str, Dict[str, float]]:
        if regime in self.states:
            return self.states[regime].get_importance()
        return {}

    def get_best_factors(self, regime: str, top_n: int = 5) -> List[str]:
        imp = self.get_regime_importance(regime)
        if not imp:
            return []
        sorted_factors = sorted(imp.items(), key=lambda x: x[1]["sharpe"], reverse=True)
        return [f for f, _ in sorted_factors[:top_n]]

    def save(self, path: Optional[Path] = None) -> Path:
        if path is None:
            path = STATE_DIR / f"feature_learner_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
        data = {
            regime: {
                "factor_returns": {k: list(v) for k, v in state.factor_returns.items()},
                "factor_hit_rates": {k: list(v) for k, v in state.factor_hit_rates.items()},
                "last_updated": state.last_updated,
            }
            for regime, state in self.states.items()
        }
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> "RegimeFeatureLearner":
        data = json.loads(path.read_text(encoding="utf-8"))
        learner = cls()
        for regime, state_data in data.items():
            state = FactorImportanceState(regime=regime)
            state.factor_returns = {k: list(v) for k, v in state_data.get("factor_returns", {}).items()}
            state.factor_hit_rates = {k: list(v) for k, v in state_data.get("factor_hit_rates", {}).items()}
            state.last_updated = state_data.get("last_updated", "")
            learner.states[regime] = state
        return learner


# ---------------------------------------------------------------------------
# Feature Pipeline Integration
# ---------------------------------------------------------------------------

def build_feature_frame(
    df: pd.DataFrame,
    benchmark: Optional[pd.DataFrame] = None,
    include_interactions: bool = True,
    include_regime_gated: bool = True,
    base_weights: Optional[Dict[str, float]] = None,
) -> pd.DataFrame:
    """Full feature engineering pipeline."""
    df = compute_all_advanced_factors(df, benchmark)

    if include_interactions:
        df = add_factor_interactions(df)

    if include_regime_gated and base_weights:
        df = compute_regime_gated_score(df, base_weights)

    return df


def get_factor_columns(df: pd.DataFrame) -> List[str]:
    """Get all factor columns (f_*)."""
    return [c for c in df.columns if c.startswith("f_")]


def print_factor_importance(importance: Dict[str, Dict[str, float]]) -> None:
    """Pretty-print factor importance."""
    print(f"\n{'='*70}")
    print("FACTOR IMPORTANCE (regime-conditioned)")
    print(f"{'='*70}")
    print(f"{'Factor':<30} {'Mean Contr.':>12} {'Hit Rate':>10} {'Sharpe':>10} {'N':>6}")
    print(f"{'-'*70}")
    for fname, metrics in sorted(importance.items(), key=lambda x: -x[1]["sharpe"]):
        print(f"{fname:<30} {metrics['mean_contribution']:>12.6f} "
              f"{metrics['hit_rate']*100:>9.1f}% {metrics['sharpe']:>10.3f} {metrics['n_obs']:>6}")


# ---------------------------------------------------------------------------
# CLI for testing
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Test advanced feature engineering")
    parser.add_argument("--symbol", default="BTC-USD")
    parser.add_argument("--period", default="1y")
    parser.add_argument("--benchmark", default="SPY")
    args = parser.parse_args()

    from .data import get_provider
    provider = get_provider()

    history = provider.fetch_history(args.symbol, args.period, "1d")
    benchmark = provider.fetch_history(args.benchmark, args.period, "1d")

    if history is None or history.empty:
        print(f"No data for {args.symbol}")
        return

    frame = build_feature_frame(history, benchmark)
    factor_cols = get_factor_columns(frame)
    print(f"Computed {len(factor_cols)} factor columns:")
    for c in factor_cols:
        print(f"  {c}")

    print(f"\nLatest factor values:")
    for c in factor_cols:
        print(f"  {c}: {frame[c].iloc[-1]:.4f}")


if __name__ == "__main__":
    main()