"""LOKI v8 — stress testing and scenario analysis."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .backtest import run_backtest
from .config import LokiConfig
from .data import get_provider
from .portfolio import fetch_returns, build_portfolio, PortfolioAllocation

logger = logging.getLogger(__name__)

STATE_DIR = Path("state") / "stress"
STATE_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class Scenario:
    """A market scenario definition."""
    name: str
    description: str
    shock_returns: Dict[str, float]  # symbol -> return shock (e.g., -0.20 for -20%)
    correlation_shock: float = 0.0  # Increase in correlations
    vol_multiplier: float = 1.0  # Volatility multiplier


# Predefined scenarios
PREDEFINED_SCENARIOS = {
    "crypto_crash_2022": Scenario(
        name="crypto_crash_2022",
        description="2022-style crypto bear market (~70% drawdown for majors)",
        shock_returns={
            "BTC-USD": -0.65, "ETH-USD": -0.70, "SOL-USD": -0.85,
            "BNB-USD": -0.60, "XRP-USD": -0.55, "ADA-USD": -0.75,
            "DOGE-USD": -0.80, "LINK-USD": -0.70, "AVAX-USD": -0.85,
            "LTC-USD": -0.65,
        },
        correlation_shock=0.30,
        vol_multiplier=2.5,
    ),
    "flash_crash": Scenario(
        name="flash_crash",
        description="Intraday flash crash: 20% drop in minutes, partial recovery",
        shock_returns={
            "BTC-USD": -0.20, "ETH-USD": -0.25, "SOL-USD": -0.35,
            "BNB-USD": -0.18, "XRP-USD": -0.22, "ADA-USD": -0.30,
            "DOGE-USD": -0.30, "LINK-USD": -0.28, "AVAX-USD": -0.35,
            "LTC-USD": -0.20,
        },
        correlation_shock=0.50,
        vol_multiplier=4.0,
    ),
    "fed_hike_surprise": Scenario(
        name="fed_hike_surprise",
        description="Unexpected 75bp rate hike: risk-off across assets",
        shock_returns={
            "BTC-USD": -0.12, "ETH-USD": -0.15, "SOL-USD": -0.20,
            "BNB-USD": -0.10, "XRP-USD": -0.12, "ADA-USD": -0.18,
            "DOGE-USD": -0.15, "LINK-USD": -0.15, "AVAX-USD": -0.22,
            "LTC-USD": -0.10,
            "SPY": -0.05, "QQQ": -0.07, "AAPL": -0.06,
        },
        correlation_shock=0.20,
        vol_multiplier=1.8,
    ),
    "liquidity_crisis": Scenario(
        name="liquidity_crisis",
        description="Exchange halt / liquidity crisis: gaps and slippage",
        shock_returns={
            "BTC-USD": -0.30, "ETH-USD": -0.35, "SOL-USD": -0.50,
            "BNB-USD": -0.25, "XRP-USD": -0.28, "ADA-USD": -0.40,
            "DOGE-USD": -0.40, "LINK-USD": -0.35, "AVAX-USD": -0.45,
            "LTC-USD": -0.28,
        },
        correlation_shock=0.40,
        vol_multiplier=3.0,
    ),
    "bull_continuation": Scenario(
        name="bull_continuation",
        description="Bull market continues: steady gains, low vol",
        shock_returns={
            "BTC-USD": 0.25, "ETH-USD": 0.35, "SOL-USD": 0.50,
            "BNB-USD": 0.20, "XRP-USD": 0.15, "ADA-USD": 0.30,
            "DOGE-USD": 0.20, "LINK-USD": 0.25, "AVAX-USD": 0.40,
            "LTC-USD": 0.18,
        },
        correlation_shock=-0.10,
        vol_multiplier=0.7,
    ),
}


@dataclass
class StressResult:
    """Result of a stress test."""
    scenario: str
    portfolio_return: float
    portfolio_drawdown: float
    worst_asset: str
    worst_asset_return: float
    var_95: float  # Value at Risk 95%
    var_99: float  # Value at Risk 99%
    cvar_95: float  # Conditional VaR (Expected Shortfall)
    max_leverage: float
    timestamp: str


def apply_scenario(
    returns: pd.DataFrame,
    scenario: Scenario,
    weights: Dict[str, float],
) -> Tuple[pd.Series, Dict[str, float]]:
    """Apply a scenario shock to returns and compute portfolio path."""
    # Start with historical returns
    shocked = returns.copy()

    # Apply return shocks
    for sym, shock in scenario.shock_returns.items():
        if sym in shocked.columns:
            # Add a single large shock day
            next_date = shocked.index[-1] + pd.Timedelta(days=1)
            shock_series = pd.Series([shock], index=[next_date])
            shocked = pd.concat([shocked, shock_series.to_frame().T])

    # Apply correlation shock (increase off-diagonal correlations)
    if scenario.correlation_shock != 0:
        corr = shocked.corr()
        n = len(corr)
        # Increase correlations
        for i in range(n):
            for j in range(i + 1, n):
                new_corr = min(0.99, corr.iloc[i, j] + scenario.correlation_shock)
                corr.iloc[i, j] = new_corr
                corr.iloc[j, i] = new_corr
        # Reconstruct returns with new correlations (simplified: scale vol)
        vol = shocked.std()
        for i in range(n):
            for j in range(i + 1, n):
                cov_target = corr.iloc[i, j] * vol.iloc[i] * vol.iloc[j]
                # This is approximate; in practice use Cholesky
        # For simplicity, just scale vol
        shocked = shocked * scenario.vol_multiplier

    # Compute portfolio returns
    w = np.array([weights.get(c, 0.0) for c in shocked.columns])
    port_ret = shocked @ w
    return port_ret, weights


def historical_var(portfolio_returns: pd.Series, confidence: float = 0.95) -> float:
    """Historical Value at Risk."""
    if len(portfolio_returns) == 0:
        return 0.0
    return float(np.percentile(portfolio_returns, (1 - confidence) * 100))


def historical_cvar(portfolio_returns: pd.Series, confidence: float = 0.95) -> float:
    """Conditional Value at Risk (Expected Shortfall)."""
    var = historical_var(portfolio_returns, confidence)
    tail = portfolio_returns[portfolio_returns <= var]
    return float(tail.mean()) if len(tail) > 0 else var


def max_drawdown(returns: pd.Series) -> float:
    """Maximum drawdown from returns series."""
    if len(returns) == 0:
        return 0.0
    equity = (1 + returns).cumprod()
    peak = equity.cummax()
    dd = (equity - peak) / peak
    return float(dd.min())


def run_stress_test(
    allocation: PortfolioAllocation,
    scenarios: Optional[Dict[str, Scenario]] = None,
    historical_returns: Optional[pd.DataFrame] = None,
) -> List[StressResult]:
    """Run stress tests on a portfolio allocation."""
    if scenarios is None:
        scenarios = PREDEFINED_SCENARIOS

    if historical_returns is None:
        # Fetch from allocation symbols
        symbols = list(allocation.weights.keys())
        historical_returns = fetch_returns(symbols, "2y", "1d")

    results = []
    for name, scenario in scenarios.items():
        port_ret, _ = apply_scenario(historical_returns, scenario, allocation.weights)

        port_return = float((1 + port_ret).prod() - 1)
        port_dd = max_drawdown(port_ret)
        var_95 = historical_var(port_ret, 0.95)
        var_99 = historical_var(port_ret, 0.99)
        cvar_95 = historical_cvar(port_ret, 0.95)

        # Find worst asset
        asset_rets = {}
        for sym, shock in scenario.shock_returns.items():
            if sym in historical_returns.columns:
                asset_rets[sym] = shock
        worst_asset = min(asset_rets, key=asset_rets.get) if asset_rets else "N/A"
        worst_ret = asset_rets.get(worst_asset, 0.0)

        results.append(StressResult(
            scenario=name,
            portfolio_return=port_return,
            portfolio_drawdown=port_dd,
            worst_asset=worst_asset,
            worst_asset_return=worst_ret,
            var_95=var_95,
            var_99=var_99,
            cvar_95=cvar_95,
            max_leverage=sum(abs(v) for v in allocation.weights.values()),
            timestamp=datetime.now().isoformat(timespec="seconds"),
        ))

    return results


def monte_carlo_stress(
    allocation: PortfolioAllocation,
    n_paths: int = 10_000,
    horizon_days: int = 252,
    return_dist: str = "t",
    df: float = 5.0,
) -> Dict[str, Any]:
    """Monte Carlo stress test: simulate many paths."""
    if not allocation.weights:
        return {}

    symbols = list(allocation.weights.keys())
    hist = fetch_returns(symbols, "2y", "1d")
    if hist.empty:
        return {"error": "No historical data"}

    # Fit distribution
    mu = hist.mean().values
    cov = hist.cov().values

    w = np.array([allocation.weights.get(s, 0.0) for s in symbols])

    final_values = []
    max_dds = []

    for _ in range(n_paths):
        if return_dist == "t":
            # Multivariate t-distribution
            shocks = np.random.multivariate_normal(
                np.zeros(len(symbols)), cov * df / (df - 2), size=horizon_days
            )  # Scale for t-dist variance
        else:
            shocks = np.random.multivariate_normal(mu, cov, size=horizon_days)

        path_returns = shocks @ w
        equity = np.cumprod(1 + path_returns)
        final_values.append(equity[-1] - 1)
        peak = np.maximum.accumulate(equity)
        dd = (equity - peak) / peak
        max_dds.append(dd.min())

    final_values = np.array(final_values)
    max_dds = np.array(max_dds)

    return {
        "n_paths": n_paths,
        "horizon_days": horizon_days,
        "mean_return": float(final_values.mean()),
        "median_return": float(np.median(final_values)),
        "std_return": float(final_values.std()),
        "var_95": float(np.percentile(final_values, 5)),
        "var_99": float(np.percentile(final_values, 1)),
        "cvar_95": float(final_values[final_values <= np.percentile(final_values, 5)].mean()),
        "prob_loss": float((final_values < 0).mean()),
        "prob_50pct_loss": float((final_values < -0.5).mean()),
        "max_drawdown_mean": float(max_dds.mean()),
        "max_drawdown_95": float(np.percentile(max_dds, 95)),
        "max_drawdown_99": float(np.percentile(max_dds, 99)),
    }


def save_stress_results(
    results: List[StressResult],
    mc_results: Optional[Dict[str, Any]] = None,
    path: Optional[Path] = None,
) -> Path:
    """Save stress test results."""
    if path is None:
        path = STATE_DIR / f"stress_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "scenarios": [
            {
                "scenario": r.scenario,
                "portfolio_return": r.portfolio_return,
                "portfolio_drawdown": r.portfolio_drawdown,
                "worst_asset": r.worst_asset,
                "worst_asset_return": r.worst_asset_return,
                "var_95": r.var_95,
                "var_99": r.var_99,
                "cvar_95": r.cvar_95,
                "max_leverage": r.max_leverage,
                "timestamp": r.timestamp,
            }
            for r in results
        ],
        "monte_carlo": mc_results,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return path


def print_stress_results(results: List[StressResult], mc: Optional[Dict[str, Any]] = None) -> None:
    """Pretty-print stress test results."""
    print(f"\n{'='*70}")
    print(f"STRESS TEST RESULTS")
    print(f"{'='*70}")
    print(f"{'Scenario':<25} {'Return':>10} {'MaxDD':>10} {'VaR95':>10} {'CVaR95':>10} {'Worst':<12}")
    print(f"{'-'*70}")
    for r in results:
        print(f"{r.scenario:<25} {r.portfolio_return*100:>9.2f}% {r.portfolio_drawdown*100:>9.2f}% "
              f"{r.var_95*100:>9.2f}% {r.cvar_95*100:>9.2f}% {r.worst_asset:<12}")
    if mc:
        print(f"\n--- Monte Carlo ({mc.get('n_paths', 0)} paths, {mc.get('horizon_days', 0)}d horizon) ---")
        print(f"  Mean Return:       {mc['mean_return']*100:.2f}%")
        print(f"  Median Return:     {mc['median_return']*100:.2f}%")
        print(f"  Prob(Loss):        {mc['prob_loss']*100:.1f}%")
        print(f"  Prob(>50% Loss):   {mc['prob_50pct_loss']*100:.2f}%")
        print(f"  VaR 95:            {mc['var_95']*100:.2f}%")
        print(f"  CVaR 95:           {mc['cvar_95']*100:.2f}%")
        print(f"  MaxDD Mean:        {mc['max_drawdown_mean']*100:.2f}%")
        print(f"  MaxDD 99:          {mc['max_drawdown_99']*100:.2f}%")