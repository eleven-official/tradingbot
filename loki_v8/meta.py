"""LOKI v8 — meta-learning ensemble (learning which factors work when).

The core insight: different factor combinations work in different regimes.
Instead of a single static ensemble, we learn a mapping:
    regime + market_state → optimal factor weights

This is trained on historical performance per regime, and can be updated
online as new trades complete. The meta-learner sits above the base
ensemble and dynamically reweights factors based on:
1. Current regime (from regime.py)
2. Recent factor performance in this regime
3. Volatility environment
4. Market breadth / correlation regime

The meta-model is simple, interpretable, and fully auditable.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .config import LokiConfig
from .regime import Regime, detect_regime, regime_series, STATES, is_bullish, is_bearish
from .strategy import EnsembleStrategy, FACTOR_KEYS
from .features import RegimeFeatureLearner, FACTOR_SPECS

logger = logging.getLogger(__name__)

STATE_DIR = Path("state") / "meta"
STATE_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Meta-Model: Regime-Conditioned Factor Weights
# ---------------------------------------------------------------------------

@dataclass
class MetaModel:
    """Learned factor weights per regime."""
    # regime -> factor_name -> weight
    regime_weights: Dict[str, Dict[str, float]] = field(default_factory=dict)
    # regime -> factor_name -> performance stats
    regime_performance: Dict[str, Dict[str, Dict[str, float]]] = field(default_factory=dict)
    # Global fallback weights
    global_weights: Dict[str, float] = field(default_factory=dict)
    # Meta-parameters
    min_observations: int = 20
    decay_factor: float = 0.99  # exponential decay for older observations
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def get_weights(self, regime: str) -> Dict[str, float]:
        """Get weights for a regime, falling back to global."""
        if regime in self.regime_weights and self.regime_weights[regime]:
            return self.regime_weights[regime]
        return self.global_weights or {k: 1.0 for k in FACTOR_KEYS}

    def update_from_learner(self, learner: RegimeFeatureLearner) -> None:
        """Update meta-model from the regime feature learner."""
        for regime in STATES:
            importance = learner.get_regime_importance(regime)
            if not importance:
                continue

            # Convert importance to weights (softmax of sharpe)
            sharpes = {k: v["sharpe"] for k, v in importance.items() if v["n_obs"] >= self.min_observations}
            if not sharpes:
                continue

            # Softmax with temperature
            temp = 1.0
            max_sharpe = max(sharpes.values())
            exp_sharpes = {k: math.exp((v - max_sharpe) / temp) for k, v in sharpes.items()}
            total = sum(exp_sharpes.values())
            weights = {k: v / total for k, v in exp_sharpes.items()}

            self.regime_weights[regime] = weights
            self.regime_performance[regime] = importance

        # Update global as average across regimes
        all_factors = set()
        for w in self.regime_weights.values():
            all_factors.update(w.keys())
        if all_factors:
            global_w = {}
            for f in all_factors:
                vals = [w.get(f, 0) for w in self.regime_weights.values() if f in w]
                if vals:
                    global_w[f] = np.mean(vals)
            self.global_weights = global_w

        self.updated_at = datetime.now().isoformat(timespec="seconds")

    def save(self, path: Optional[Path] = None) -> Path:
        if path is None:
            path = STATE_DIR / f"meta_model_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
        data = {
            "regime_weights": self.regime_weights,
            "regime_performance": self.regime_performance,
            "global_weights": self.global_weights,
            "min_observations": self.min_observations,
            "decay_factor": self.decay_factor,
            "updated_at": self.updated_at,
        }
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> "MetaModel":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            regime_weights=data.get("regime_weights", {}),
            regime_performance=data.get("regime_performance", {}),
            global_weights=data.get("global_weights", {}),
            min_observations=data.get("min_observations", 20),
            decay_factor=data.get("decay_factor", 0.99),
            updated_at=data.get("updated_at", ""),
        )


# ---------------------------------------------------------------------------
# Online Meta-Learner (updates after each trade)
# ---------------------------------------------------------------------------

class OnlineMetaLearner:
    """Updates meta-model online as trades complete."""

    def __init__(self, model: Optional[MetaModel] = None):
        self.model = model or MetaModel()
        self.learner = RegimeFeatureLearner()
        self.pending_trades: List[Dict] = []

    def observe_trade(
        self,
        regime: str,
        factor_values: Dict[str, float],
        forward_return: float,
        trade_pnl: float,
    ) -> None:
        """Call after a trade closes to update the meta-model."""
        self.learner.observe(regime, factor_values, forward_return)
        self.pending_trades.append({
            "regime": regime,
            "factor_values": factor_values,
            "return": forward_return,
            "pnl": trade_pnl,
        })

        # Rebuild model periodically
        if len(self.pending_trades) >= 10:
            self.rebuild()

    def rebuild(self) -> None:
        """Rebuild meta-model from accumulated observations."""
        self.model.update_from_learner(self.learner)
        self.pending_trades.clear()
        logger.info("Meta-model rebuilt: %d regimes with data", len(self.model.regime_weights))

    def get_current_weights(self, regime: str) -> Dict[str, float]:
        return self.model.get_weights(regime)


# ---------------------------------------------------------------------------
# Meta-Ensemble Strategy (drops into existing pipeline)
# ---------------------------------------------------------------------------

class MetaEnsembleStrategy:
    """Ensemble strategy that uses meta-learned weights per regime."""

    def __init__(self, cfg: LokiConfig, meta_model: Optional[MetaModel] = None):
        self.cfg = cfg
        self.base_strategy = EnsembleStrategy(cfg)
        self.meta_model = meta_model or MetaModel()
        self.online_learner = OnlineMetaLearner(self.meta_model)

    def compute_factors(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute base factors + regime series."""
        df = self.base_strategy.compute_factors(df)
        df["regime"] = regime_series(df)
        return df

    def score_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        """Score using meta-learned regime-conditioned weights."""
        df = self.compute_factors(df)

        # Get factor columns
        factor_cols = [f"f_{k}" for k in FACTOR_KEYS if f"f_{k}" in df.columns]

        # Score per bar with regime-specific weights
        scores = pd.Series(0.0, index=df.index)
        regimes = df["regime"]

        for i, (idx, regime) in enumerate(regimes.items()):
            weights = self.meta_model.get_weights(regime)
            row_score = 0.0
            total_w = 0.0
            for k in FACTOR_KEYS:
                col = f"f_{k}"
                if col in df.columns and k in weights:
                    w = weights[k]
                    row_score += w * df[col].iloc[i]
                    total_w += w
            if total_w > 0:
                scores.iloc[i] = np.clip(row_score / total_w, -1, 1) * 100
            else:
                scores.iloc[i] = 0.0

        df["score"] = scores
        df["meta_weights"] = regimes.map(lambda r: str(self.meta_model.get_weights(r)))
        return df

    def update_from_trade(
        self,
        regime: str,
        factor_values: Dict[str, float],
        forward_return: float,
        trade_pnl: float,
    ) -> None:
        """Update meta-model after a trade."""
        self.online_learner.observe_trade(regime, factor_values, forward_return, trade_pnl)


# ---------------------------------------------------------------------------
# Meta-Learning Trainer (offline training from history)
# ---------------------------------------------------------------------------

def train_meta_model(
    symbols: Sequence[str],
    period: str = "3y",
    timeframe: str = "1d",
    min_trades_per_regime: int = 20,
) -> MetaModel:
    """Train meta-model from historical data across symbols."""
    from .data import get_provider
    from .backtest import run_backtest

    provider = get_provider()
    learner = RegimeFeatureLearner()

    for symbol in symbols:
        try:
            history = provider.fetch_history(symbol, period, timeframe)
            if history is None or history.empty or len(history) < 500:
                continue

            cfg = LokiConfig(period=period, timeframe=timeframe)
            strategy = EnsembleStrategy(cfg)

            # Score the whole history
            frame = strategy.score_frame(history)

            # Get regime series
            regimes = regime_series(frame)

            # Simulate trades and collect factor values at entry + forward returns
            # Use the backtester's logic but collect factor values
            warmup = max(cfg.lookback_bars, 60)
            for i in range(warmup + 1, len(history) - 20):  # leave 20 bars for forward return
                score = float(frame["score"].iloc[i - 1])
                regime = str(regimes.iloc[i - 1])

                # Get factor values at this bar
                factor_values = {}
                for k in FACTOR_KEYS:
                    col = f"f_{k}"
                    if col in frame.columns:
                        factor_values[k] = float(frame[col].iloc[i - 1])

                # Forward return over next 20 bars (approx holding period)
                entry_price = float(history["close"].iloc[i])
                exit_price = float(history["close"].iloc[min(i + 20, len(history) - 1)])
                forward_return = (exit_price - entry_price) / entry_price

                # Only learn from bars where signal was strong enough
                if abs(score) >= cfg.signal_threshold:
                    learner.observe(regime, factor_values, forward_return)

        except Exception as e:
            logger.warning("Meta-training failed for %s: %s", symbol, e)

    # Build meta-model
    model = MetaModel(min_observations=min_trades_per_regime)
    model.update_from_learner(learner)

    # Save
    path = model.save()
    logger.info("Meta-model trained and saved to %s", path)

    return model


# ---------------------------------------------------------------------------
# Regime Transition Detector (anticipate regime changes)
# ---------------------------------------------------------------------------

@dataclass
class RegimeTransition:
    from_regime: str
    to_regime: str
    at_bar: int
    confidence: float
    description: str


def detect_regime_transitions(df: pd.DataFrame, lookback: int = 20) -> List[RegimeTransition]:
    """Detect regime transitions in historical data."""
    regimes = regime_series(df)
    transitions = []

    for i in range(lookback, len(regimes)):
        current = regimes.iloc[i]
        prev = regimes.iloc[i - lookback:i].mode()[0]  # dominant regime in lookback

        if current != prev:
            # Check if this is a real transition (not noise)
            recent = regimes.iloc[max(0, i - 5):i + 1]
            if (recent == current).sum() >= 3:  # new regime persists
                transitions.append(RegimeTransition(
                    from_regime=prev,
                    to_regime=current,
                    at_bar=i,
                    confidence=0.8,  # placeholder
                    description=f"{prev} → {current} at bar {i}"
                ))

    return transitions


def predict_regime_transition(df: pd.DataFrame) -> Optional[RegimeTransition]:
    """Predict imminent regime transition from current indicators."""
    if len(df) < 100:
        return None

    frame = ta.add_all_indicators(df)
    current = detect_regime(frame)

    # Check for regime change signals
    # 1. ADX collapsing in trending regime
    # 2. Volatility percentile spiking
    # 3. Price crossing SMA200
    # 4. Volume divergence

    adx = frame["adx"].iloc[-1]
    atr_pct = frame["atr_pct"].iloc[-1]
    atr_pct_rank = frame["atr_pct"].rolling(252).rank(pct=True).iloc[-1]
    close = frame["close"].iloc[-1]
    sma200 = frame["sma_200"].iloc[-1]
    sma50 = frame["sma_50"].iloc[-1]

    signals = []

    if current.state in {"STRONG_BULL", "BULL"} and adx < 20:
        signals.append(("BULL → RANGING", 0.7, "ADX collapsing in uptrend"))
    elif current.state in {"BEAR", "CRISIS"} and adx < 20:
        signals.append(("BEAR → RANGING", 0.7, "ADX collapsing in downtrend"))
    elif current.state == "RANGING" and adx > 25:
        if close > sma200 and sma50 > sma200:
            signals.append(("RANGING → BULL", 0.7, "ADX rising above SMA200"))
        elif close < sma200 and sma50 < sma200:
            signals.append(("RANGING → BEAR", 0.7, "ADX rising below SMA200"))

    if atr_pct_rank > 0.9 and current.state not in {"CRISIS"}:
        signals.append((f"{current.state} → CRISIS", 0.8, "Volatility spike (90th pctl)"))

    if (close > sma200) != (frame["close"].iloc[-2] > frame["sma_200"].iloc[-2]):
        signals.append(("SMA200 cross", 0.6, "Price crossed 200-day SMA"))

    if signals:
        best = max(signals, key=lambda x: x[1])
        return RegimeTransition(
            from_regime=current.state,
            to_regime=best[0].split("→")[1].strip(),
            at_bar=len(df) - 1,
            confidence=best[1],
            description=best[2],
        )

    return None


# ---------------------------------------------------------------------------
# Integration: Apply meta-weights to config
# ---------------------------------------------------------------------------

def apply_meta_weights(cfg: LokiConfig, meta_model: MetaModel, regime: str) -> LokiConfig:
    """Apply meta-learned weights to a config for a specific regime."""
    weights = meta_model.get_weights(regime)
    # Map factor names to config factor_weights keys
    factor_map = {
        "trend_ema": "trend",
        "momentum_rsi_macd": "momentum",
        "volume_flow": "volume_flow",
        "squeeze": "squeeze",
        "volatility_structure": "volatility",
    }
    new_weights = {}
    for meta_key, cfg_key in factor_map.items():
        if meta_key in weights:
            new_weights[cfg_key] = weights[meta_key]
    if new_weights:
        cfg = LokiConfig(**{**cfg.to_dict(), "factor_weights": new_weights})
    return cfg


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Train meta-learning ensemble")
    parser.add_argument("--symbols", default="BTC-USD,ETH-USD,SOL-USD,BNB-USD,XRP-USD")
    parser.add_argument("--period", default="3y")
    parser.add_argument("--timeframe", default="1d")
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",")]
    model = train_meta_model(symbols, args.period, args.timeframe)

    print("\nMeta-model trained:")
    for regime, weights in model.regime_weights.items():
        print(f"\n  {regime}:")
        for f, w in sorted(weights.items(), key=lambda x: -x[1]):
            print(f"    {f}: {w:.3f}")

    if model.global_weights:
        print("\n  GLOBAL:")
        for f, w in sorted(model.global_weights.items(), key=lambda x: -x[1]):
            print(f"    {f}: {w:.3f}")


if __name__ == "__main__":
    import loki_v8.features as ta  # for ta import in predict_regime_transition
    main()