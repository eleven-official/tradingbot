"""Deterministic, paper-only position planning.

The planner deliberately has no broker or network dependency.  It turns a
proposed entry, stop and target into a bounded plan that callers can inspect
before deciding whether to submit anything to a separate execution system.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import floor, isfinite


class RiskPlanError(ValueError):
    """Raised when a proposed trade cannot be evaluated safely."""


@dataclass(frozen=True)
class RiskPlanInput:
    """Inputs required to build a position plan."""

    side: str
    capital: float
    risk_percent: float
    entry_price: float
    stop_price: float
    target_price: float
    max_notional_percent: float = 10.0
    minimum_reward_risk: float = 1.5


@dataclass(frozen=True)
class RiskPlan:
    """A transparent sizing result; it is not an execution instruction."""

    side: str
    approved: bool
    reason: str
    quantity: float
    risk_budget: float
    risk_per_unit: float
    reward_per_unit: float
    reward_risk_ratio: float
    notional: float
    estimated_loss: float
    projected_profit: float


_QUANTITY_PRECISION = 8
_QUANTITY_SCALE = 10 ** _QUANTITY_PRECISION


def _floor_quantity(value: float) -> float:
    """Round a positive paper quantity down to the supported precision."""
    scaled = value * _QUANTITY_SCALE
    if not isfinite(scaled):
        raise RiskPlanError("The calculated quantity is too large to represent safely")
    return floor(scaled) / _QUANTITY_SCALE


def _positive_number(name: str, value: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise RiskPlanError(f"{name} must be a number") from error
    if not isfinite(number) or number <= 0:
        raise RiskPlanError(f"{name} must be a finite value greater than zero")
    return number


def build_risk_plan(request: RiskPlanInput) -> RiskPlan:
    """Build a position plan using the tighter risk and notional limits.

    The result is approved only when a supported paper quantity fits inside
    both configured limits and the target meets the requested reward/risk ratio.
    Quantities are rounded down to eight decimal places; venue lot sizes are
    not modeled.
    It intentionally performs no market-data lookup and cannot place an order.
    """
    side = str(request.side).upper().strip()
    if side not in {"BUY", "SELL"}:
        raise RiskPlanError("side must be BUY or SELL")

    capital = _positive_number("capital", request.capital)
    risk_percent = _positive_number("risk_percent", request.risk_percent)
    entry_price = _positive_number("entry_price", request.entry_price)
    stop_price = _positive_number("stop_price", request.stop_price)
    target_price = _positive_number("target_price", request.target_price)
    max_notional_percent = _positive_number(
        "max_notional_percent", request.max_notional_percent
    )
    minimum_reward_risk = _positive_number(
        "minimum_reward_risk", request.minimum_reward_risk
    )

    if risk_percent > 100 or max_notional_percent > 100:
        raise RiskPlanError("risk_percent and max_notional_percent cannot exceed 100")

    if side == "BUY":
        risk_per_unit = entry_price - stop_price
        reward_per_unit = target_price - entry_price
    else:
        risk_per_unit = stop_price - entry_price
        reward_per_unit = entry_price - target_price

    if risk_per_unit <= 0:
        raise RiskPlanError(f"{side} stop must be on the loss side of entry")
    if reward_per_unit <= 0:
        raise RiskPlanError(f"{side} target must be on the profit side of entry")

    risk_budget = capital * (risk_percent / 100)
    max_notional = capital * (max_notional_percent / 100)
    reward_risk_ratio = reward_per_unit / risk_per_unit
    if not all(
        isfinite(value) for value in (risk_budget, max_notional, reward_risk_ratio)
    ):
        raise RiskPlanError(
            "The calculated risk values are outside the safe numeric range"
        )

    risk_quantity = risk_budget / risk_per_unit
    notional_quantity = max_notional / entry_price
    if not all(isfinite(value) for value in (risk_quantity, notional_quantity)):
        raise RiskPlanError("The calculated quantity is outside the safe numeric range")
    quantity = min(_floor_quantity(risk_quantity), _floor_quantity(notional_quantity))

    if quantity <= 0:
        return RiskPlan(
            side=side,
            approved=False,
            reason=(
                "The configured limits cannot fund the minimum supported paper quantity "
                "(0.00000001 units)."
            ),
            quantity=0.0,
            risk_budget=risk_budget,
            risk_per_unit=risk_per_unit,
            reward_per_unit=reward_per_unit,
            reward_risk_ratio=reward_risk_ratio,
            notional=0.0,
            estimated_loss=0.0,
            projected_profit=0.0,
        )

    notional = quantity * entry_price
    estimated_loss = quantity * risk_per_unit
    projected_profit = quantity * reward_per_unit
    if not all(isfinite(value) for value in (notional, estimated_loss, projected_profit)):
        raise RiskPlanError("The calculated plan is outside the safe numeric range")
    approved = reward_risk_ratio >= minimum_reward_risk
    reason = (
        "Paper plan passes the configured risk and reward/risk checks."
        if approved
        else "Target reward/risk is below the configured minimum."
    )
    return RiskPlan(
        side=side,
        approved=approved,
        reason=reason,
        quantity=quantity,
        risk_budget=risk_budget,
        risk_per_unit=risk_per_unit,
        reward_per_unit=reward_per_unit,
        reward_risk_ratio=reward_risk_ratio,
        notional=notional,
        estimated_loss=estimated_loss,
        projected_profit=projected_profit,
    )

