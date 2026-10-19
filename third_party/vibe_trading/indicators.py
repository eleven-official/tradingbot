"""Wilder RSI adapted from Vibe-Trading's shadow_account/indicators.py.

Copyright (c) 2026 Vibe-Trading Contributors. MIT; see adjacent LICENSE.
The original is retained in upstream/indicators.py. This adaptation replaces
numpy/pandas with lists and None; warmup, Wilder seed, and missing-value state
semantics follow the original. Flat prices remain undefined, represented by None.
"""
from __future__ import annotations

import math
from collections.abc import Sequence


def _wilder_average(values: Sequence[float | None], period: int) -> list[float | None]:
    if isinstance(period, bool) or not isinstance(period, int) or period < 1:
        raise ValueError("period must be a positive integer")
    result: list[float | None] = [None] * len(values)
    seed: list[float] = []
    state: float | None = None
    for index, value in enumerate(values):
        if value is None:
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
            raise ValueError("indicator values must be finite numbers or None")
        if state is None:
            seed.append(float(value))
            if len(seed) == period:
                state = sum(seed) / period
                result[index] = state
        else:
            state = (state * (period - 1) + value) / period
            result[index] = state
    return result


def compute_rsi(close: Sequence[float | None], period: int = 14) -> list[float | None]:
    """SMA-seeded, causal Wilder RSI, aligned with the supplied closes."""
    if isinstance(period, bool) or not isinstance(period, int) or period < 1:
        raise ValueError("period must be a positive integer")
    for value in close:
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
            raise ValueError("close values must be finite numbers or None")
    delta = [None] + [None if previous is None or current is None else current - previous
                      for previous, current in zip(close, close[1:])] if close else []
    gains = _wilder_average([None if value is None else max(value, 0.0) for value in delta], period)
    losses = _wilder_average([None if value is None else max(-value, 0.0) for value in delta], period)
    result: list[float | None] = []
    for gain, loss in zip(gains, losses):
        result.append(None if gain is None or loss is None or gain + loss == 0
                      else 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss))
    return result
