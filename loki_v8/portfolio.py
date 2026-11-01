"""LOKI v8 — correlation-aware portfolio construction and regime-aware sizing."""

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
from .data import get_provider

logger = logging.getLogger(__name__)

STATE_DIR = Path("state") / "portfolio"
STATE_DIR.mkdir(parents=True, exist_ok=True)

# Default correlation thresholds
DEFAULT_MAX_CORRELATION = 0.70
DEFAULT_CLUSTER_THRESHOLD = 0.60
DEFAULT_MAX_CLUSTER_EXPOSURE = 0.40


@dataclass
class CorrelationCluster:
    """A cluster of highly correlated assets."""
    assets: List[str]
    avg_correlation: float
    representative: str


@dataclass
class PortfolioAllocation:
    """Complete portfolio allocation with risk metrics."""
    weights: Dict[str, float]
    cluster_exposures: Dict[str, float]
    expected_return: float
    expected_volatility: float
    sharpe: float
    max_drawdown_estimate: float
    correlation_matrix: pd.DataFrame
    clusters: List[CorrelationCluster]
    timestamp: str


def fetch_returns(
    symbols: List[str],
    period: str = "1y",
    timeframe: str = "1d",
) -> pd.DataFrame:
    """Fetch log returns for a list of symbols."""
    provider = get_provider()
    returns = {}
    for sym in symbols:
        try:
            hist = provider.fetch_history(sym, period, timeframe)
            if hist is not None and not hist.empty:
                close = hist["close"].astype(float)
                log_ret = np.log(close / close.shift(1)).dropna()
                returns[sym] = log_ret
        except Exception as e:
            logger.warning("Failed to fetch %s: %s", sym, e)
    if not returns:
        return pd.DataFrame()
    frame = pd.DataFrame(returns)
    frame = frame.dropna(how="all")
    return frame.ffill().dropna()


def compute_correlation_matrix(returns: pd.DataFrame) -> pd.DataFrame:
    """Compute Pearson correlation matrix."""
    return returns.corr()


def cluster_assets(
    corr_matrix: pd.DataFrame,
    threshold: float = DEFAULT_CLUSTER_THRESHOLD,
) -> List[CorrelationCluster]:
    """Group assets by correlation using simple hierarchical clustering."""
    assets = list(corr_matrix.index)
    if not assets:
        return []

    clusters: List[CorrelationCluster] = []
    assigned = set()

    for asset in assets:
        if asset in assigned:
            continue
        # Find all assets correlated above threshold with this one
        cluster = [asset]
        for other in assets:
            if other != asset and other not in assigned:
                if corr_matrix.loc[asset, other] >= threshold:
                    cluster.append(other)
        if len(cluster) > 1:
            # Compute average correlation within cluster
            sub = corr_matrix.loc[cluster, cluster]
            mask = np.triu(np.ones(sub.shape), k=1).astype(bool)
            avg_corr = float(sub.where(mask).stack().mean())
            clusters.append(CorrelationCluster(
                assets=cluster,
                avg_correlation=avg_corr,
                representative=cluster[0],
            ))
            assigned.update(cluster)

    # Singletons
    for asset in assets:
        if asset not in assigned:
            clusters.append(CorrelationCluster(
                assets=[asset],
                avg_correlation=1.0,
                representative=asset,
            ))

    return clusters


def optimize_weights(
    returns: pd.DataFrame,
    max_weight: float = 0.30,
    min_weight: float = 0.02,
    target_vol: Optional[float] = None,
    risk_free: float = 0.0,
    max_correlation: float = DEFAULT_MAX_CORRELATION,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Simple mean-variance optimization with correlation and weight constraints.

    Returns (weights, diagnostics).
    """
    n = len(returns.columns)
    if n == 0:
        return np.array([]), {}

    # Expected returns and covariance
    mu = returns.mean().values * 252  # Annualize
    cov = returns.cov().values * 252

    # Equal weight starting point
    w = np.ones(n) / n

    # Simple iterative optimization (gradient-free)
    best_sharpe = -np.inf
    best_w = w.copy()

    for _ in range(1000):
        # Random perturbation
        idx = np.random.choice(n, size=min(3, n), replace=False)
        delta = np.random.randn(len(idx)) * 0.02
        new_w = w.copy()
        new_w[idx] += delta
        new_w = np.clip(new_w, min_weight, max_weight)
        new_w = new_w / new_w.sum()

        # Check correlation constraint
        valid = True
        for i in range(n):
            if new_w[i] < min_weight:
                continue
            for j in range(i + 1, n):
                if new_w[j] < min_weight:
                    continue
                if returns.columns[i] in returns.columns and returns.columns[j] in returns.columns:
                    corr = returns.corr().iloc[i, j]
                    if abs(corr) > max_correlation:
                        valid = False
                        break
            if not valid:
                break

        if not valid:
            continue

        # Evaluate
        port_ret = float(new_w @ mu)
        port_vol = float(np.sqrt(new_w @ cov @ new_w))
        sharpe = (port_ret - risk_free) / port_vol if port_vol > 0 else -np.inf

        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_w = new_w.copy()
            w = new_w.copy()

    # Scale to target volatility if specified
    if target_vol is not None:
        port_vol = float(np.sqrt(best_w @ cov @ best_w))
        if port_vol > 0:
            scale = target_vol / port_vol
            best_w = np.clip(best_w * scale, 0, max_weight)
            best_w = best_w / best_w.sum() if best_w.sum() > 0 else best_w

    diagnostics = {
        "sharpe": best_sharpe,
        "expected_return": float(best_w @ mu),
        "expected_volatility": float(np.sqrt(best_w @ cov @ best_w)),
    }
    return best_w, diagnostics


def compute_cluster_exposures(
    weights: Dict[str, float],
    clusters: List[CorrelationCluster],
) -> Dict[str, float]:
    """Sum weights by correlation cluster."""
    exposures = {}
    for cluster in clusters:
        exposures[cluster.representative] = sum(
            weights.get(a, 0.0) for a in cluster.assets
        )
    return exposures


def apply_cluster_caps(
    weights: Dict[str, float],
    clusters: List[CorrelationCluster],
    max_cluster_exposure: float = DEFAULT_MAX_CLUSTER_EXPOSURE,
) -> Dict[str, float]:
    """Cap exposure per correlation cluster, redistribute excess."""
    exposures = compute_cluster_exposures(weights, clusters)
    capped = weights.copy()

    for cluster in clusters:
        total = exposures.get(cluster.representative, 0.0)
        if total > max_cluster_exposure:
            # Scale down all assets in cluster
            factor = max_cluster_exposure / total
            for asset in cluster.assets:
                if asset in capped:
                    capped[asset] *= factor

    # Renormalize
    total = sum(capped.values())
    if total > 0:
        capped = {k: v / total for k, v in capped.items()}
    return capped


def build_portfolio(
    symbols: List[str],
    period: str = "1y",
    timeframe: str = "1d",
    max_weight: float = 0.30,
    min_weight: float = 0.02,
    target_vol: Optional[float] = None,
    max_correlation: float = DEFAULT_MAX_CORRELATION,
    cluster_threshold: float = DEFAULT_CLUSTER_THRESHOLD,
    max_cluster_exposure: float = DEFAULT_MAX_CLUSTER_EXPOSURE,
) -> PortfolioAllocation:
    """End-to-end portfolio construction."""
    returns = fetch_returns(symbols, period, timeframe)
    if returns.empty:
        raise ValueError("No return data fetched")

    corr = compute_correlation_matrix(returns)
    clusters = cluster_assets(corr, cluster_threshold)

    weights_arr, diag = optimize_weights(
        returns, max_weight, min_weight, target_vol, max_correlation=max_correlation
    )
    weights = {sym: float(w) for sym, w in zip(returns.columns, weights_arr)}
    weights = apply_cluster_caps(weights, clusters, max_cluster_exposure)

    # Recompute diagnostics with final weights
    w_arr = np.array([weights.get(s, 0.0) for s in returns.columns])
    mu = returns.mean().values * 252
    cov = returns.cov().values * 252
    port_ret = float(w_arr @ mu)
    port_vol = float(np.sqrt(w_arr @ cov @ w_arr))

    # Estimate max drawdown from volatility (rough heuristic)
    max_dd_est = -port_vol * 1.5  # ~1.5x annual vol as rough max DD

    return PortfolioAllocation(
        weights=weights,
        cluster_exposures=compute_cluster_exposures(weights, clusters),
        expected_return=port_ret,
        expected_volatility=port_vol,
        sharpe=(port_ret / port_vol) if port_vol > 0 else 0.0,
        max_drawdown_estimate=max_dd_est,
        correlation_matrix=corr,
        clusters=clusters,
        timestamp=datetime.now().isoformat(timespec="seconds"),
    )


def save_allocation(allocation: PortfolioAllocation, path: Optional[Path] = None) -> Path:
    """Save allocation to JSON."""
    if path is None:
        path = STATE_DIR / f"allocation_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "weights": allocation.weights,
        "cluster_exposures": allocation.cluster_exposures,
        "expected_return": allocation.expected_return,
        "expected_volatility": allocation.expected_volatility,
        "sharpe": allocation.sharpe,
        "max_drawdown_estimate": allocation.max_drawdown_estimate,
        "correlation_matrix": allocation.correlation_matrix.to_dict(),
        "clusters": [
            {"assets": c.assets, "avg_correlation": c.avg_correlation, "representative": c.representative}
            for c in allocation.clusters
        ],
        "timestamp": allocation.timestamp,
    }
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return path


def load_allocation(path: Path) -> PortfolioAllocation:
    """Load allocation from JSON."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return PortfolioAllocation(
        weights=data["weights"],
        cluster_exposures=data["cluster_exposures"],
        expected_return=data["expected_return"],
        expected_volatility=data["expected_volatility"],
        sharpe=data["sharpe"],
        max_drawdown_estimate=data["max_drawdown_estimate"],
        correlation_matrix=pd.DataFrame(data["correlation_matrix"]),
        clusters=[
            CorrelationCluster(
                assets=c["assets"],
                avg_correlation=c["avg_correlation"],
                representative=c["representative"],
            )
            for c in data["clusters"]
        ],
        timestamp=data["timestamp"],
    )


def print_allocation(allocation: PortfolioAllocation) -> None:
    """Pretty-print portfolio allocation."""
    print(f"\n{'='*60}")
    print(f"PORTFOLIO ALLOCATION — {allocation.timestamp}")
    print(f"{'='*60}")
    print(f"Expected Return:  {allocation.expected_return*100:.2f}%")
    print(f"Expected Vol:     {allocation.expected_volatility*100:.2f}%")
    print(f"Sharpe:           {allocation.sharpe:.2f}")
    print(f"Est. Max DD:      {allocation.max_drawdown_estimate*100:.2f}%")
    print(f"\nWeights:")
    for sym, w in sorted(allocation.weights.items(), key=lambda x: -x[1]):
        print(f"  {sym:>10}: {w*100:>6.2f}%")
    print(f"\nCluster Exposures:")
    for rep, exp in allocation.cluster_exposures.items():
        print(f"  {rep:>10}: {exp*100:.2f}%")
    print(f"\nClusters:")
    for c in allocation.clusters:
        print(f"  {c.representative} ({len(c.assets)} assets, avg ρ={c.avg_correlation:.2f}): {', '.join(c.assets)}")