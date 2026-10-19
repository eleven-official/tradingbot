"""Conservative daily paper-risk budgeting from browser journal aggregates."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


class DailyRiskError(ValueError):
    """Raised when daily paper-risk inputs are invalid."""


@dataclass(frozen=True)
class DailyRiskSummary:
    """A user-configured paper loss cap compared with tracked journal risk."""

    status: str
    limit_amount: float
    realized_pnl: float
    realized_loss: float
    open_planned_risk: float
    committed_loss: float
    remaining_amount: float
    utilization_percent: float
    closed_today: int
    open_positions: int


def _finite_number(name: str, value: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise DailyRiskError(f"{name} must be a number") from error
    if not isfinite(number):
        raise DailyRiskError(f"{name} must be finite")
    return number


def build_daily_risk_summary(
    *,
    capital: float,
    loss_limit_percent: float,
    realized_pnl: float,
    realized_loss: float,
    open_planned_risk: float,
    closed_today: int = 0,
    open_positions: int = 0,
) -> DailyRiskSummary:
    """Compare today's manual outcomes and planned open risk with a chosen cap.

    Profits never increase the remaining risk budget. Open risk uses the
    original planned loss at the stop and does not model mark-to-market moves.
    """
    account_capital = _finite_number("capital", capital)
    limit_percent = _finite_number("loss_limit_percent", loss_limit_percent)
    daily_pnl = _finite_number("realized_pnl", realized_pnl)
    gross_realized_loss = _finite_number("realized_loss", realized_loss)
    open_risk = _finite_number("open_planned_risk", open_planned_risk)
    if account_capital <= 0:
        raise DailyRiskError("capital must be greater than zero")
    if not 0 < limit_percent <= 100:
        raise DailyRiskError("loss_limit_percent must be greater than zero and at most 100")
    if gross_realized_loss < 0:
        raise DailyRiskError("realized_loss cannot be negative")
    if open_risk < 0:
        raise DailyRiskError("open_planned_risk cannot be negative")
    if closed_today < 0 or open_positions < 0:
        raise DailyRiskError("journal position counts cannot be negative")

    limit_amount = account_capital * limit_percent / 100
    committed_loss = gross_realized_loss + open_risk
    remaining_amount = max(0.0, limit_amount - committed_loss)
    utilization_percent = committed_loss / limit_amount * 100

    if committed_loss >= limit_amount:
        status = "PAUSE"
    elif committed_loss >= limit_amount * 0.75:
        status = "WATCH"
    else:
        status = "WITHIN_LIMIT"

    return DailyRiskSummary(
        status=status,
        limit_amount=limit_amount,
        realized_pnl=daily_pnl,
        realized_loss=gross_realized_loss,
        open_planned_risk=open_risk,
        committed_loss=committed_loss,
        remaining_amount=remaining_amount,
        utilization_percent=utilization_percent,
        closed_today=closed_today,
        open_positions=open_positions,
    )
