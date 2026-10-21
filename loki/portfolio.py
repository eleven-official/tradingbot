"""Stateless, read-only portfolio reporting primitives.

This module provides valuation and concentration metrics from positions and
prices supplied by the caller. It does not fetch prices, place orders, or make
investment recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable, cast


class PortfolioInputError(ValueError):
    """Raised when a portfolio input cannot be valued safely."""


@dataclass(frozen=True, slots=True)
class Position:
    """A long holding with its quantity, cost basis, and current price."""

    symbol: str
    quantity: float
    average_cost: float
    current_price: float

    def __post_init__(self) -> None:
        symbol = self.symbol.strip().upper()
        if not symbol:
            raise PortfolioInputError("Position symbol must not be empty.")
        object.__setattr__(self, "symbol", symbol)

        for name, value in (
            ("quantity", self.quantity),
            ("average_cost", self.average_cost),
            ("current_price", self.current_price),
        ):
            if not isfinite(value) or value < 0:
                raise PortfolioInputError(f"{name} must be a finite non-negative number.")

    @property
    def cost_basis(self) -> float:
        """Total amount paid for this position before fees and taxes."""
        return self.quantity * self.average_cost

    @property
    def market_value(self) -> float:
        """Current market value using the caller-supplied price."""
        return self.quantity * self.current_price

    @property
    def unrealized_gain_loss(self) -> float:
        """Unrealised gain or loss before fees and taxes."""
        return self.market_value - self.cost_basis


def build_portfolio_summary(
    positions: Iterable[Position],
    *,
    cash: float = 0.0,
    currency: str = "AUD",
) -> dict[str, object]:
    """Build a deterministic, read-only portfolio summary.

    Prices are inputs rather than live quotes so callers can choose their own
    trusted data source and timestamp. All allocations are descriptive; no
    rebalance or trade instruction is produced.
    """
    if not isfinite(cash) or cash < 0:
        raise PortfolioInputError("cash must be a finite non-negative number.")

    normalized_currency = currency.strip().upper()
    if len(normalized_currency) != 3 or not normalized_currency.isalpha():
        raise PortfolioInputError("currency must be a three-letter code.")

    holdings = list(positions)
    symbols = [position.symbol for position in holdings]
    if len(symbols) != len(set(symbols)):
        raise PortfolioInputError("Each symbol may appear only once.")

    invested_value = sum(position.market_value for position in holdings)
    cost_basis = sum(position.cost_basis for position in holdings)
    total_value = cash + invested_value
    unrealized_gain_loss = invested_value - cost_basis
    position_weight_denominator = total_value if total_value else 1.0

    serialized_positions: list[dict[str, float | str | None]] = []
    for position in sorted(holdings, key=lambda item: item.market_value, reverse=True):
        gain_loss_percentage = (
            position.unrealized_gain_loss / position.cost_basis * 100
            if position.cost_basis
            else None
        )
        serialized_positions.append(
            {
                "symbol": position.symbol,
                "quantity": position.quantity,
                "average_cost": position.average_cost,
                "current_price": position.current_price,
                "cost_basis": position.cost_basis,
                "market_value": position.market_value,
                "unrealized_gain_loss": position.unrealized_gain_loss,
                "unrealized_gain_loss_percentage": gain_loss_percentage,
                "portfolio_weight": position.market_value / position_weight_denominator,
            }
        )

    weights: list[float] = [cast(float, item["portfolio_weight"]) for item in serialized_positions]
    concentration_hhi = sum(weight**2 for weight in weights)
    effective_positions = 1 / concentration_hhi if concentration_hhi else 0.0
    largest_position_weight = max(weights, default=0.0)

    risk_flags = []
    if largest_position_weight > 0.5:
        risk_flags.append("A single holding represents more than half of portfolio value.")
    if cash / position_weight_denominator > 0.8 and total_value:
        risk_flags.append("Cash represents more than 80% of portfolio value.")

    return {
        "currency": normalized_currency,
        "cash": cash,
        "invested_value": invested_value,
        "total_cost_basis": cost_basis,
        "total_value": total_value,
        "unrealized_gain_loss": unrealized_gain_loss,
        "unrealized_gain_loss_percentage": (
            unrealized_gain_loss / cost_basis * 100 if cost_basis else None
        ),
        "cash_weight": cash / position_weight_denominator,
        "largest_position_weight": largest_position_weight,
        "concentration_hhi": concentration_hhi,
        "effective_positions": effective_positions,
        "diversification_score": (1 - concentration_hhi) * 100 if weights else 0.0,
        "risk_flags": risk_flags,
        "positions": serialized_positions,
        "disclaimer": (
            "Portfolio metrics are informational only and do not constitute "
            "investment advice or an instruction to trade."
        ),
    }
