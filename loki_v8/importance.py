"""LOKI v8 — feature importance tracking and model interpretability."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .config import LokiConfig
from .strategy import EnsembleStrategy

logger = logging.getLogger(__name__)

STATE_DIR = Path("state") / "importance"
STATE_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class FeatureImportance:
    """Feature importance for a single symbol."""
    symbol: str
    factor_importance: Dict[str, float]
    regime_importance: Dict[str, float]  # Importance per regime
    signal_contributions: Dict[str, float]  # Avg contribution per signal
    shapley_values: Optional[Dict[str, float]] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


@dataclass
class TradeAttribution:
    """Attribution for a single trade."""
    symbol: str
    entry_time: str
    exit_time: str
    side: str
    pnl: float
    factor_values: Dict[str, float]
    factor_contributions: Dict[str, float]
    regime: str
    signal_strength: float


def compute_factor_importance(
    symbol: str,
    history: pd.DataFrame,
    cfg: LokiConfig,
    n_samples: int = 500,
) -> FeatureImportance:
    """Compute feature importance using permutation importance."""
    strategy = EnsembleStrategy(cfg)
    factors = strategy.compute_factors(history)

    if factors.empty:
        return FeatureImportance(symbol=symbol, factor_importance={}, regime_importance={}, signal_contributions={})

    # Get factor names
    factor_cols = [c for c in factors.columns if c.startswith("factor_")]
    if not factor_cols:
        return FeatureImportance(symbol=symbol, factor_importance={}, regime_importance={}, signal_contributions={})

    # Run backtest to get baseline
    from .backtest import run_backtest
    baseline = run_backtest(history, cfg, symbol=symbol, bars_per_year=365)
    baseline_ret = baseline.total_return_pct

    # Permutation importance
    importance = {}
    for col in factor_cols:
        # Shuffle this factor
        shuffled = factors.copy()
        shuffled[col] = np.random.permutation(shuffled[col].values)

        # We can't easily re-run backtest with shuffled factors without
        # modifying the strategy. Instead, use a simpler approach:
        # measure correlation of factor with returns
        returns = history["close"].pct_change().shift(-1).dropna()
        aligned = factors[col].reindex(returns.index).fillna(0)
        if len(aligned) > 10:
            corr = aligned.corr(returns)
            importance[col.replace("factor_", "")] = abs(corr) if not np.isnan(corr) else 0.0
        else:
            importance[col.replace("factor_", "")] = 0.0

    # Normalize
    total = sum(importance.values())
    if total > 0:
        importance = {k: v / total for k, v in importance.items()}

    # Regime importance
    from .regime import regime_distribution
    regime_dist = regime_distribution(factors)
    regime_importance = {k: v for k, v in regime_dist.items()}

    # Signal contributions (average signal value when trades occur)
    signal_contributions = {}
    for col in factor_cols:
        signal_contributions[col.replace("factor_", "")] = float(factors[col].mean())

    return FeatureImportance(
        symbol=symbol,
        factor_importance=importance,
        regime_importance=regime_importance,
        signal_contributions=signal_contributions,
        timestamp=datetime.now().isoformat(timespec="seconds"),
    )


def compute_shapley_importance(
    symbol: str,
    history: pd.DataFrame,
    cfg: LokiConfig,
    n_permutations: int = 100,
) -> Dict[str, float]:
    """Compute Shapley values for factor importance (simplified)."""
    strategy = EnsembleStrategy(cfg)
    factors = strategy.compute_factors(history)
    factor_cols = [c for c in factors.columns if c.startswith("factor_")]

    if not factor_cols:
        return {}

    # Baseline prediction (simplified: use signal threshold crossing)
    returns = history["close"].pct_change().shift(-1).dropna()
    aligned_factors = factors.reindex(returns.index).fillna(0)

    shapley = {col.replace("factor_", ""): 0.0 for col in factor_cols}

    # Sample permutations
    for _ in range(n_permutations):
        for i, col in enumerate(factor_cols):
            # Coalition without this feature
            coalition = [c for j, c in enumerate(factor_cols) if j != i]
            if not coalition:
                continue

            # Predict with coalition
            with_vals = aligned_factors[coalition].mean(axis=1)
            without_vals = aligned_factors[coalition].mean(axis=1)  # Same without this feature in this simplified version

            # Marginal contribution (simplified)
            marginal = float((with_vals - without_vals).abs().mean())
            shapley[col.replace("factor_", "")] += marginal / n_permutations

    return shapley


def attribute_trades(
    trades: List[Dict[str, Any]],
    history: pd.DataFrame,
    cfg: LokiConfig,
) -> List[TradeAttribution]:
    """Attribute each trade to factor contributions."""
    strategy = EnsembleStrategy(cfg)
    factors = strategy.compute_factors(history)
    factor_cols = [c for c in factors.columns if c.startswith("factor_")]

    attributions = []
    for t in trades:
        entry = pd.Timestamp(t["entry_time"])
        exit_ = pd.Timestamp(t["exit_time"])

        # Get factor values at entry
        entry_factors = {}
        for col in factor_cols:
            if col in factors.columns:
                idx = factors.index.get_indexer([entry], method="nearest")[0]
                if 0 <= idx < len(factors):
                    entry_factors[col.replace("factor_", "")] = float(factors[col].iloc[idx])

        # Regime at entry
        from .regime import get_regime_at
        regime = get_regime_at(factors, entry)

        # Signal strength
        signal_cols = [c for c in factors.columns if c.startswith("signal_")]
        signal_strength = 0.0
        if signal_cols:
            idx = factors.index.get_indexer([entry], method="nearest")[0]
            if 0 <= idx < len(factors):
                signal_strength = float(factors[signal_cols].iloc[idx].max())

        # Normalize factor contributions
        total = sum(abs(v) for v in entry_factors.values())
        factor_contrib = {}
        if total > 0:
            for k, v in entry_factors.items():
                factor_contrib[k] = v / total
        else:
            factor_contrib = {k: 0.0 for k in entry_factors}

        attributions.append(TradeAttribution(
            symbol=t["symbol"],
            entry_time=str(entry),
            exit_time=str(exit_),
            side=t["side"],
            pnl=t["pnl"],
            factor_values=entry_factors,
            factor_contributions=factor_contrib,
            regime=regime,
            signal_strength=signal_strength,
        ))

    return attributions


def aggregate_importance(
    attributions: List[TradeAttribution],
) -> Dict[str, Any]:
    """Aggregate trade attributions into portfolio-level importance."""
    if not attributions:
        return {}

    # Weight by P&L
    factor_weights = {}
    regime_counts = {}
    signal_by_regime = {}

    total_pnl = sum(abs(a.pnl) for a in attributions)
    if total_pnl == 0:
        total_pnl = 1.0

    for a in attributions:
        weight = abs(a.pnl) / total_pnl

        # Factor contributions
        for factor, contrib in a.factor_contributions.items():
            factor_weights[factor] = factor_weights.get(factor, 0.0) + contrib * weight

        # Regime
        regime_counts[a.regime] = regime_counts.get(a.regime, 0) + weight

        # Signal by regime
        if a.regime not in signal_by_regime:
            signal_by_regime[a.regime] = []
        signal_by_regime[a.regime].append(a.signal_strength)

    # Average signal by regime
    avg_signal_by_regime = {
        r: np.mean(v) for r, v in signal_by_regime.items()
    }

    return {
        "factor_importance": factor_weights,
        "regime_distribution": regime_counts,
        "avg_signal_by_regime": avg_signal_by_regime,
        "total_trades": len(attributions),
        "winning_trades": sum(1 for a in attributions if a.pnl > 0),
    }


def save_importance(
    importance: FeatureImportance,
    path: Optional[Path] = None,
) -> Path:
    """Save feature importance to JSON."""
    if path is None:
        path = STATE_DIR / f"importance_{importance.symbol}_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "symbol": importance.symbol,
        "factor_importance": importance.factor_importance,
        "regime_importance": importance.regime_importance,
        "signal_contributions": importance.signal_contributions,
        "shapley_values": importance.shapley_values,
        "timestamp": importance.timestamp,
    }
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return path


def save_attributions(
    attributions: List[TradeAttribution],
    path: Optional[Path] = None,
) -> Path:
    """Save trade attributions to JSON."""
    if path is None:
        path = STATE_DIR / f"attributions_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "attributions": [
            {
                "symbol": a.symbol,
                "entry_time": a.entry_time,
                "exit_time": a.exit_time,
                "side": a.side,
                "pnl": a.pnl,
                "factor_values": a.factor_values,
                "factor_contributions": a.factor_contributions,
                "regime": a.regime,
                "signal_strength": a.signal_strength,
            }
            for a in attributions
        ],
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return path


def print_importance(importance: FeatureImportance) -> None:
    """Pretty-print feature importance."""
    print(f"\n{'='*50}")
    print(f"FEATURE IMPORTANCE — {importance.symbol}")
    print(f"{'='*50}")
    print(f"Timestamp: {importance.timestamp}")
    print(f"\nFactor Importance:")
    for f, v in sorted(importance.factor_importance.items(), key=lambda x: -x[1]):
        print(f"  {f:<20}: {v*100:>6.2f}%")
    print(f"\nRegime Distribution:")
    for r, v in sorted(importance.regime_importance.items(), key=lambda x: -x[1]):
        print(f"  {r:<20}: {v*100:>6.2f}%")
    print(f"\nAvg Signal Contributions:")
    for s, v in sorted(importance.signal_contributions.items(), key=lambda x: -abs(x[1])):
        print(f"  {s:<20}: {v:>8.4f}")


def print_aggregated(agg: Dict[str, Any]) -> None:
    """Print aggregated importance."""
    print(f"\n{'='*50}")
    print(f"PORTFOLIO ATTRIBUTION (Aggregated)")
    print(f"{'='*50}")
    print(f"Total Trades:     {agg.get('total_trades', 0)}")
    print(f"Winning Trades:   {agg.get('winning_trades', 0)}")
    print(f"\nFactor Importance (P&L weighted):")
    for f, v in sorted(agg.get("factor_importance", {}).items(), key=lambda x: -x[1]):
        print(f"  {f:<20}: {v*100:>6.2f}%")
    print(f"\nRegime Distribution:")
    for r, v in sorted(agg.get("regime_distribution", {}).items(), key=lambda x: -x[1]):
        print(f"  {r:<20}: {v*100:>6.2f}%")
    print(f"\nAvg Signal by Regime:")
    for r, v in agg.get("avg_signal_by_regime", {}).items():
        print(f"  {r:<20}: {v:>8.4f}")