"""Rank IC and quantile equity adapted from Vibe-Trading factor_analysis_core.

Copyright (c) 2026 Vibe-Trading Contributors. MIT; see LICENSE.
Original retained in upstream/factor_analysis_core.py. Dict panels replace
pandas; paired-observation ranking, the five-name IC minimum and equal weights
are preserved. Equal-size quantiles use deterministic symbol tie-breaking.
Inputs to this module are mathematical panels, not orders or predictions.
"""
from __future__ import annotations

import math
import statistics
from collections.abc import Mapping

Panel = Mapping[str, Mapping[str, float | None]]


def _valid(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    result = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        rank = (start + 1 + end) / 2
        for index in order[start:end]:
            result[index] = rank
        start = end
    return result


def _shared(factors: Mapping[str, float | None], returns: Mapping[str, float | None]) -> list[str]:
    return sorted(symbol for symbol in factors.keys() & returns.keys()
                  if _valid(factors[symbol]) and _valid(returns[symbol]))


def compute_ic_series(factor_panel: Panel, return_panel: Panel) -> list[dict[str, float | str | int]]:
    """Spearman IC on paired observations, requiring at least five assets/date."""
    output = []
    for date in sorted(factor_panel.keys() & return_panel.keys()):
        factors, returns = factor_panel[date], return_panel[date]
        shared = _shared(factors, returns)
        if len(shared) < 5:
            continue
        factor_ranks = _ranks([factors[symbol] for symbol in shared])
        return_ranks = _ranks([returns[symbol] for symbol in shared])
        if len(set(factor_ranks)) < 2 or len(set(return_ranks)) < 2:
            continue
        correlation = statistics.correlation(factor_ranks, return_ranks)
        output.append({"timestamp": date, "ic": max(-1.0, min(1.0, correlation)), "assets": len(shared)})
    return output


def compute_group_equity(factor_panel: Panel, return_panel: Panel, n_groups: int = 5) -> list[dict[str, object]]:
    """Equal-weight rank groups; caller supplies correctly aligned forward returns.

    These are gross factor diagnostics. Overlapping forward horizons must not be
    interpreted as investable compounded portfolio returns.
    """
    if isinstance(n_groups, bool) or not isinstance(n_groups, int) or not 1 <= n_groups <= 20:
        raise ValueError("n_groups must be between 1 and 20")
    equity = [1.0] * n_groups
    output = []
    for date in sorted(factor_panel.keys() & return_panel.keys()):
        factors, returns = factor_panel[date], return_panel[date]
        shared = _shared(factors, returns)
        if len(shared) < n_groups:
            continue
        shared.sort(key=lambda symbol: (factors[symbol], symbol))
        groups: list[list[str]] = [[] for _ in range(n_groups)]
        for index, symbol in enumerate(shared):
            groups[min(n_groups - 1, index * n_groups // len(shared))].append(symbol)
        group_returns = [statistics.mean(returns[symbol] for symbol in group) for group in groups]
        if any(value < -1 for value in group_returns):
            raise ValueError("unlevered forward returns cannot be less than -1")
        equity = [previous * (1 + value) for previous, value in zip(equity, group_returns)]
        if not all(math.isfinite(value) for value in equity):
            raise ValueError("factor equity overflow; input magnitudes are too extreme")
        output.append({"timestamp": date, "groups": {f"Group_{index + 1}": value for index, value in enumerate(equity)},
                       "returns": {f"Group_{index + 1}": value for index, value in enumerate(group_returns)}})
    return output
