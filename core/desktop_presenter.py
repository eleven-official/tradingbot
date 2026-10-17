"""Small, dependency-free rules shared by the desktop terminal and its tests."""

import math
from datetime import datetime, timezone
from statistics import NormalDist
from typing import Any, Mapping


def performance_evidence(wins: int, closed: int) -> str:
    """Describe observed outcomes with a Wilson interval, never a prediction."""
    if closed <= 0:
        return "Win rate: awaiting closed paper trades"
    if wins < 0 or wins > closed:
        raise ValueError("Winning trades must be between zero and closed trades.")
    p = wins / closed
    z = NormalDist().inv_cdf(0.975)
    denominator = 1 + z * z / closed
    center = (p + z * z / (2 * closed)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * closed)) / closed) / denominator
    return (
        f"Observed wins: {p:.1%} ({wins}/{closed}) | "
        f"95% interval: {max(0.0, center - margin):.0%}–{min(1.0, center + margin):.0%}"
    )


def validate_risk_settings(values: Mapping[str, Any]) -> dict[str, float]:
    """Validate the entire form before changing any running risk controls."""
    limits = {
        "risk_per_trade_pct": (0.01, 5.0),
        "stop_loss_pct": (0.01, 50.0),
        "take_profit_pct": (0.01, 100.0),
        "trailing_stop_pct": (0.01, 50.0),
        "daily_loss_pct": (0.01, 50.0),
        "max_drawdown_pct": (0.01, 90.0),
        "min_confidence": (1.0, 100.0),
    }
    result = {}
    for name, (minimum, maximum) in limits.items():
        try:
            value = float(values[name])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"{name.replace('_', ' ')} needs a numeric percentage.") from None
        if not math.isfinite(value) or not minimum <= value <= maximum:
            raise ValueError(
                f"{name.replace('_', ' ')} must be between {minimum:g}% and {maximum:g}%."
            )
        result[name] = value / 100
    return result


def risk_sized_quantity(equity: float, cash: float, price: float, stop: float,
                        risk_fraction: float, fee_fraction: float = 0.0005,
                        slippage_fraction: float = 0.0001) -> float:
    """Budget entry/stop fills including costs; gaps can still exceed planned risk."""
    values = (equity, cash, price, stop, risk_fraction, fee_fraction, slippage_fraction)
    if not all(math.isfinite(v) for v in values):
        raise ValueError("Sizing inputs must be finite.")
    if equity <= 0 or cash <= 0 or price <= 0 or not 0 < stop < price:
        raise ValueError("Use a positive price, cash and equity, with a stop below entry.")
    if not 0 < risk_fraction <= 0.05 or not 0 <= fee_fraction < 1 or not 0 <= slippage_fraction < 1:
        raise ValueError("Risk must be above 0% and at most 5%.")
    entry_cost = price * (1 + slippage_fraction) * (1 + fee_fraction)
    stop_proceeds = stop * (1 - slippage_fraction) * (1 - fee_fraction)
    return max(0.0, min(equity * risk_fraction / (entry_cost - stop_proceeds),
                        cash / entry_cost))


def quote_is_fresh(updated_at: float | None, now: float, max_age: float = 60.0) -> bool:
    """Reject missing, nonfinite, future-dated and stale source timestamps."""
    return (updated_at is not None and math.isfinite(updated_at) and math.isfinite(now)
            and 0 <= now - updated_at <= max_age)


def candle_is_current(timestamp: Any, now: float, interval_seconds: int) -> bool:
    """A recent HTTP response is not evidence that its exchange candle is recent."""
    try:
        parsed = timestamp if isinstance(timestamp, datetime) else datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        age = now - parsed.timestamp()
        return math.isfinite(age) and -30 <= age <= interval_seconds * 2 + 30
    except (ValueError, TypeError, OverflowError, OSError):
        return False
