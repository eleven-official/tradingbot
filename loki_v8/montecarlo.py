"""LOKI v8 — Monte Carlo strategy simulation.

Answers the only question the backtest's single deterministic path cannot:
**how fragile is the strategy's edge?** The observed trade sequence is just
one draw from the strategy's return distribution (and its trade ORDER is
arbitrary luck). So we perform a sequential bootstrap: thousands of shuffled
replays of the same trades, each compounded as if every trade risks the same
fraction of the running equity.

Each simulated path therefore answers: "given this strategy's trade-quality
distribution but a different ordering/luck, where could the account end up,
and how deep could the drawdown spiral get before it recovers?"

Outputs (all numbers, no narrative):
  * percentile fan of equity at every trade step (chartable)
  * final-return distribution percentiles
  * max-drawdown distribution (median / p95 / worst)
  * probability of profit, probability of losing 20% / 50%+
  * Value-at-Risk (95%) and Conditional VaR of the final return
  * median equity after each round (fan medians)
  * worst losing streak

Deterministic for a given ``seed`` so tests are stable.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import numpy as np


def monte_carlo_simulation(
    trades: Sequence[Any],
    initial_equity: float = 100_000.0,
    n_sims: int = 2000,
    seed: Optional[int] = None,
    busted_threshold_pct: float = -50.0,
) -> Dict[str, Any]:
    """Bootstrap-replay the trade sequence and return a risk distribution.

    ``trades`` may be ``backtest.Trade`` objects or anything with ``pnl_pct``
    (percent return per trade, attributed to current equity). Replays shuffle
    the *order* of the same trades: same edge distribution, different luck.
    """
    pct = np.array([float(getattr(t, "pnl_pct")) for t in trades], dtype=float)
    out: Dict[str, Any] = {
        "n_trades": len(pct),
        "n_sims": int(n_sims) if pct.size else 0,
        "initial_equity": float(initial_equity),
    }
    if pct.size == 0:
        out.update(
            {
                "prob_profit_pct": 0.0,
                "mean_final_return_pct": 0.0,
                "final_return": {"p5": 0.0, "p25": 0.0, "p50": 0.0, "p75": 0.0, "p95": 0.0},
                "max_drawdown": {"p50": 0.0, "p95": 0.0, "worst": 0.0},
                "prob_dd_worse_20_pct": 0.0,
                "prob_dd_worse_50_pct": 0.0,
                "prob_bust_pct": 0.0,
                "var_95_pct": 0.0,
                "cvar_95_pct": 0.0,
                "median_worst_streak": 0.0,
                "fan": {},
                "verdict": "NO_TRADES",
            }
        )
        return out

    rng = np.random.default_rng(seed)
    pct = pct[np.isfinite(pct)]
    out["n_trades"] = len(pct)
    if pct.size == 0:  # can only happen if inputs were all-NaN
        return monte_carlo_simulation([], initial_equity, 0, seed, busted_threshold_pct)
    multipliers = 1.0 + pct / 100.0
    n = pct.size
    n_sims = int(n_sims)

    # Each path: n random trades (with replacement) in random order, seeded
    # at 1.0 so step 0 is the starting equity.
    picks = rng.integers(0, n, size=(n_sims, n))
    paths = np.ones((n_sims, n + 1))
    paths[:, 1:] = np.cumprod(multipliers[picks], axis=1)
    equity = paths * initial_equity

    returns_equity = equity / initial_equity - 1.0  # fraction per step

    # Running max and drawdown per path
    running_max = np.maximum.accumulate(equity, axis=1)
    dd = equity / running_max - 1.0  # fraction (<= 0)
    max_dd = dd.min(axis=1)  # worst drawdown per path (fraction)

    finals_pct = returns_equity[:, -1] * 100.0
    max_dd_pct = max_dd * 100.0

    # Equity fan percentiles per step (5 splines)
    fan_pcts = (5, 25, 50, 75, 95)
    fan = {
        f"p{p}": [round(float(v), 2) for v in np.percentile(equity, p, axis=0)] for p in fan_pcts
    }

    worst_streaks = _worst_losing_streaks(pct, picks)

    var_95 = float(np.percentile(finals_pct, 5.0))
    tail = finals_pct[finals_pct <= var_95]
    cvar_95 = float(tail.mean()) if tail.size else var_95

    prob_profit = float((finals_pct > 0.0).mean() * 100.0)
    prob_dd20 = float((max_dd_pct <= -20.0).mean() * 100.0)
    prob_dd50 = float((max_dd_pct <= -50.0).mean() * 100.0)
    bust = busted_threshold_pct
    prob_bust = float((finals_pct <= bust).mean() * 100.0)

    out.update(
        {
            "prob_profit_pct": round(prob_profit, 1),
            "mean_final_return_pct": round(float(finals_pct.mean()), 2),
            "final_return": {
                "p5": round(float(np.percentile(finals_pct, 5)), 2),
                "p25": round(float(np.percentile(finals_pct, 25)), 2),
                "p50": round(float(np.percentile(finals_pct, 50)), 2),
                "p75": round(float(np.percentile(finals_pct, 75)), 2),
                "p95": round(float(np.percentile(finals_pct, 95)), 2),
            },
            "max_drawdown": {
                "p50": round(float(np.percentile(max_dd_pct, 50)), 2),
                "p95": round(float(np.percentile(max_dd_pct, 95)), 2),
                "worst": round(float(max_dd_pct.min()), 2),
            },
            "prob_dd_worse_20_pct": round(prob_dd20, 1),
            "prob_dd_worse_50_pct": round(prob_dd50, 1),
            "prob_bust_pct": round(prob_bust, 1),
            "var_95_pct": round(var_95, 2),
            "cvar_95_pct": round(cvar_95, 2),
            "median_worst_streak": round(float(np.median(worst_streaks)), 1),
            "fan": fan,
            "verdict": classify(prob_profit, prob_dd20, float(np.percentile(max_dd_pct, 95))),
        }
    )
    return out


def _worst_losing_streaks(pct: np.ndarray, picks: np.ndarray) -> np.ndarray:
    """Longest consecutive losing run per path."""
    move = pct[picks] > 0  # win matrix (n_sims, n)
    streaks = np.zeros(move.shape[0], dtype=float)
    run = np.zeros(move.shape[0])
    for j in range(move.shape[1]):
        run = np.where(move[:, j], 0.0, run + 1.0)
        streaks = np.maximum(streaks, run)
    return streaks


def classify(prob_profit: float, prob_dd20: float, w95_dd: float) -> str:
    """Plain-language risk verdict bucket."""
    if prob_profit >= 70.0 and w95_dd > -25.0:
        return "ROBUST"
    if prob_profit >= 55.0 and w95_dd > -35.0:
        return "ACCEPTABLE"
    if prob_profit >= 40.0:
        return "FRAGILE"
    return "DANGEROUS"
