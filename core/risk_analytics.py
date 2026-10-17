"""
Enterprise Risk Analytics Module
Integrated from Vibe-Trading project
Provides comprehensive portfolio risk analysis
"""

import json
import math
from typing import Dict, List, Any, Optional
import numpy as np
import pandas as pd


def _finite(value: float | None) -> float | None:
    """Return value when finite, else None (strict-JSON safe)."""
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def compute_concentration(weights: np.ndarray) -> Dict[str, Any]:
    """Compute concentration metrics for portfolio weights."""
    hhi = float(np.sum(weights**2))
    order = np.argsort(weights)[::-1]
    return {
        "hhi": _finite(hhi),
        "effective_n": _finite(1.0 / hhi) if hhi > 0 else None,
        "top1_weight": _finite(float(weights[order[0]])) if len(order) else None,
        "top3_weight": _finite(float(weights[order[:3]].sum())) if len(order) else None,
    }


def compute_volatility(port_returns: pd.Series, periods_per_year: int = 252) -> Dict[str, Any]:
    """Compute volatility metrics for portfolio returns."""
    vol = float(port_returns.std(ddof=1)) if len(port_returns) > 1 else None
    
    # Downside deviation (Sortino ratio)
    downside_dev = (
        float(np.sqrt((port_returns.clip(upper=0.0) ** 2).mean())) if len(port_returns) > 0 else None
    )
    
    annualize = math.sqrt(periods_per_year)
    return {
        "daily_vol": _finite(vol),
        "annualized_vol": _finite(vol * annualize) if vol is not None else None,
        "downside_deviation_annualized": (
            _finite(downside_dev * annualize) if downside_dev is not None else None
        ),
    }


def compute_drawdown(port_returns: pd.Series) -> Dict[str, Any]:
    """Compute drawdown metrics for portfolio returns."""
    if port_returns.empty:
        return {"max_drawdown": None, "max_drawdown_start": None, "max_drawdown_trough": None}
    
    equity = (1.0 + port_returns).cumprod()
    peak = equity.cummax().clip(lower=1.0)
    dd = (equity - peak) / peak
    trough_idx = dd.idxmin()
    pre_trough = equity.loc[:trough_idx]
    start_idx = port_returns.index[0] if float(pre_trough.max()) < 1.0 else pre_trough.idxmax()
    
    return {
        "max_drawdown": _finite(float(dd.loc[trough_idx])),
        "max_drawdown_start": str(start_idx),
        "max_drawdown_trough": str(trough_idx),
    }


def compute_tail_risk(port_returns: pd.Series, levels: List[float] = [0.95, 0.99]) -> Dict[str, Any]:
    """Compute tail risk metrics (VaR and Expected Shortfall)."""
    out: Dict[str, Any] = {}
    losses = -port_returns.to_numpy(dtype=float)
    
    for level in levels:
        if len(losses) < 2:
            var = es = None
        else:
            var = float(np.quantile(losses, level))
            tail = losses[losses >= var]
            es = float(tail.mean()) if len(tail) else None
        
        key = f"{int(round(level * 100))}"
        out[f"var_{key}"] = _finite(var)
        out[f"expected_shortfall_{key}"] = _finite(es)
    
    out["method"] = "historical simulation (non-parametric)"
    return out


def compute_diversification(
    returns: pd.DataFrame, 
    weights: np.ndarray, 
    port_returns: pd.Series, 
    periods_per_year: int = 252
) -> Dict[str, Any]:
    """Compute diversification ratio."""
    if returns.shape[1] < 2:
        return {"diversification_ratio": None, "note": "needs at least 2 assets"}
    
    asset_vols = returns.std(ddof=1).to_numpy(dtype=float)
    port_vol = float(port_returns.std(ddof=1)) if len(port_returns) > 1 else 0.0
    
    if port_vol <= 0 or not math.isfinite(port_vol):
        return {"diversification_ratio": None, "note": "portfolio variance is zero"}
    
    ratio = float(np.dot(weights, asset_vols) / port_vol)
    return {"diversification_ratio": _finite(ratio)}


def compute_correlation(returns: pd.DataFrame, port_returns: pd.Series) -> Dict[str, Any]:
    """Compute correlation metrics."""
    if returns.shape[1] < 2:
        return {
            "avg_pairwise_abs": None,
            "max_pair": None,
            "beta_to_equal_weight": None,
            "note": "needs at least 2 assets",
        }
    
    corr = returns.corr().to_numpy(dtype=float)
    n = corr.shape[0]
    off_diag = [abs(corr[i, j]) for i in range(n) for j in range(i + 1, n)]
    avg_pairwise = float(np.mean(off_diag)) if off_diag else None
    
    max_pair = None
    if off_diag:
        i, j = max(
            ((i, j) for i in range(n) for j in range(i + 1, n)),
            key=lambda pair: abs(corr[pair[0], pair[1]]),
        )
        max_pair = {
            "symbols": [str(returns.columns[i]), str(returns.columns[j])],
            "corr": _finite(float(corr[i, j])),
        }
    
    market = returns.mean(axis=1)
    market_var = float(market.var(ddof=1)) if len(market) > 1 else 0.0
    if market_var > 0 and math.isfinite(market_var):
        beta = float(port_returns.cov(market) / market_var)
    else:
        beta = None
    
    return {
        "avg_pairwise_abs": _finite(avg_pairwise),
        "max_pair": max_pair,
        "beta_to_equal_weight": _finite(beta),
    }


def compute_comprehensive_risk_analysis(
    positions: Dict[str, float],
    price_history: Dict[str, pd.DataFrame],
    periods_per_year: int = 252
) -> Dict[str, Any]:
    """
    Compute comprehensive risk analysis for Loki's portfolio.
    
    Args:
        positions: Symbol -> quantity mapping
        price_history: Symbol -> OHLCV DataFrame
        periods_per_year: Annualization factor
    
    Returns:
        Comprehensive risk analysis dictionary
    """
    if not positions:
        return {"error": "No positions to analyze"}
    
    # Extract close prices and compute weights
    symbols = list(positions.keys())
    closes_dict = {}
    weights_dict = {}
    
    for sym in symbols:
        if sym in price_history and not price_history[sym].empty:
            closes_dict[sym] = price_history[sym]['close']
            # Use position value as weight
            last_price = closes_dict[sym].iloc[-1]
            weights_dict[sym] = positions[sym] * last_price
    
    if not closes_dict:
        return {"error": "No price data available"}
    
    # Create DataFrame
    closes = pd.DataFrame(closes_dict)
    
    # Normalize weights
    total = sum(weights_dict.values())
    if total <= 0:
        return {"error": "Total portfolio value is zero or negative"}
    
    weights = {sym: w / total for sym, w in weights_dict.items()}
    
    # Ensure all symbols in weights exist in closes
    valid_symbols = [sym for sym in weights if sym in closes.columns]
    weights = {sym: weights[sym] for sym in valid_symbols}
    closes = closes[valid_symbols]
    
    if len(valid_symbols) < 1:
        return {"error": "Not enough valid symbols for analysis"}
    
    # Compute returns
    returns = closes.pct_change(fill_method=None).dropna()
    if returns.empty:
        return {"error": "No overlapping return observations"}
    
    # Compute portfolio returns
    weights_array = np.array([weights[sym] for sym in valid_symbols])
    port_returns = returns.to_numpy(dtype=float) @ weights_array
    port_returns_series = pd.Series(port_returns, index=returns.index)
    
    # Compute all metrics
    result = {
        "concentration": compute_concentration(weights_array),
        "volatility": compute_volatility(port_returns_series, periods_per_year),
        "drawdown": compute_drawdown(port_returns_series),
        "tail_risk": compute_tail_risk(port_returns_series),
        "diversification": compute_diversification(returns, weights_array, port_returns_series, periods_per_year),
        "correlation": compute_correlation(returns, port_returns_series),
        "portfolio_value": total,
        "symbols": valid_symbols,
        "weights": {sym: round(weights[sym], 6) for sym in valid_symbols},
    }
    
    return result
