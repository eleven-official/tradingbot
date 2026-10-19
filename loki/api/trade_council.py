"""Six independent, deterministic gates for paper-trade ideas.

The council is deliberately conservative.  It does not forecast returns,
connect to a broker, or make a loss-free promise.  Instead it records why a
proposed long trade is safe to study, needs more confirmation, or should be
skipped before any execution system sees it.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from loki.api.risk_planner import RiskPlan, RiskPlanError, RiskPlanInput, build_risk_plan


@dataclass(frozen=True)
class CouncilRequest:
    """Market and plan inputs consumed by the six independent reviews."""

    side: str
    capital: float
    risk_percent: float
    entry_price: float
    stop_price: float
    target_price: float
    current_price: float
    trend: str = "NEUTRAL"
    volatility_percent: float = 2.0
    volume_ratio: float = 0.0
    market_data_age_seconds: float = 61.0
    spread_percent: float = 0.1
    market_open: bool = False
    max_notional_percent: float = 10.0
    minimum_reward_risk: float = 1.5
    max_data_age_seconds: float = 60.0
    min_volume_ratio: float = 0.8
    max_volatility_percent: float = 5.0
    max_spread_percent: float = 0.5
    max_entry_deviation_percent: float = 0.5
    setup_name: str = ""
    setup_score: float | None = None
    min_setup_score: float = 80.0


@dataclass(frozen=True)
class AgentReview:
    """One explainable verdict from a named council role."""

    agent: str
    verdict: str
    reason: str
    next_step: str = ""


@dataclass(frozen=True)
class CouncilDecision:
    """The council's non-executable BUY, WAIT or SKIP decision."""

    action: str
    rationale: str
    reviews: tuple[AgentReview, ...]
    plan: RiskPlan


def _finite_nonnegative(name: str, value: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise RiskPlanError(f"{name} must be a number") from error
    if not isfinite(number) or number < 0:
        raise RiskPlanError(f"{name} must be finite and cannot be negative")
    return number


def _first_reason(reviews: list[AgentReview], verdict: str) -> str:
    return next(review.reason for review in reviews if review.verdict == verdict)



def _next_step(review: AgentReview, request: CouncilRequest) -> str:
    """Translate a gate result into a concrete, conservative follow-up."""
    if review.verdict == "PASS":
        return {
            "Scout": "Keep using a fresh feed and check participation again before a later review.",
            "Trend": "Keep the bullish regime and selected setup rules visible in your notes.",
            "Chart Guardian": "Preserve these entry, stop and target levels; do not chase a later price move.",
            "Risk Sentinel": "Keep the planned risk budget and exposure cap unchanged for this paper review.",
            "Volatility Guardian": "Recheck volatility before a later review; the regime can change.",
            "Execution Gate": "Recheck spread and session status before any separate decision.",
        }.get(review.agent, "Record this pass and recheck it with fresh data.")
    if review.agent == "Scout":
        if "seconds old" in review.reason.lower():
            return "Refresh the public feed and rerun only when data age is within the freshness limit."
        return "Wait for volume to reach the configured participation threshold, then refresh."
    if review.agent == "Trend":
        if "bearish" in review.reason.lower():
            return "Stand aside while the declared regime conflicts with a long; reassess only after a confirmed change."
        return "Wait for a confirmed bullish regime and, when selected, enough setup-rule confluence."
    if review.agent == "Chart Guardian":
        if "stop" in review.reason.lower():
            return "Treat the original thesis as invalidated. Build a new plan only from freshly chosen levels."
        return "Wait for the planned entry zone or remap entry, stop and target; do not chase."
    if review.agent == "Risk Sentinel":
        return "Rework the risk budget, exposure cap or reward-to-risk geometry. Do not move a stop closer just to force approval."
    if review.agent == "Volatility Guardian":
        return "Stand aside until volatility is within the chosen safety ceiling; do not raise the ceiling to force a pass."
    if review.agent == "Execution Gate":
        if not request.market_open:
            return "Wait for an open session, then refresh the feed and review the spread again."
        return "Wait for spread to return within the configured limit, then refresh."
    return "Review the flagged input and run the council again after it changes."



def _format_quantity(quantity: float) -> str:
    return f"{quantity:.8f}".rstrip("0").rstrip(".")


def evaluate_trade_council(request: CouncilRequest) -> CouncilDecision:
    """Run six gates and return an explainable, paper-only decision.

    `SKIP` is reserved for a broken plan or an outright safety conflict.
    `WAIT` means a valid plan needs fresh confirmation.  Only a clean pass by
    every role returns `BUY`; callers must still keep execution separate.
    """
    plan = build_risk_plan(
        RiskPlanInput(
            side=request.side,
            capital=request.capital,
            risk_percent=request.risk_percent,
            entry_price=request.entry_price,
            stop_price=request.stop_price,
            target_price=request.target_price,
            max_notional_percent=request.max_notional_percent,
            minimum_reward_risk=request.minimum_reward_risk,
        )
    )
    current_price = _finite_nonnegative("current_price", request.current_price)
    data_age = _finite_nonnegative("market_data_age_seconds", request.market_data_age_seconds)
    volatility = _finite_nonnegative("volatility_percent", request.volatility_percent)
    volume_ratio = _finite_nonnegative("volume_ratio", request.volume_ratio)
    spread = _finite_nonnegative("spread_percent", request.spread_percent)
    max_data_age = _finite_nonnegative("max_data_age_seconds", request.max_data_age_seconds)
    min_volume = _finite_nonnegative("min_volume_ratio", request.min_volume_ratio)
    max_volatility = _finite_nonnegative("max_volatility_percent", request.max_volatility_percent)
    max_spread = _finite_nonnegative("max_spread_percent", request.max_spread_percent)
    entry_tolerance = _finite_nonnegative(
        "max_entry_deviation_percent", request.max_entry_deviation_percent
    )
    min_setup_score = _finite_nonnegative("min_setup_score", request.min_setup_score)
    setup_name = str(request.setup_name).strip()
    setup_score = None
    if request.setup_score is not None:
        setup_score = _finite_nonnegative("setup_score", request.setup_score)
        if setup_score > 100:
            raise RiskPlanError("setup_score cannot exceed 100")
        if not setup_name:
            raise RiskPlanError("setup_name is required when setup_score is supplied")
    elif setup_name:
        raise RiskPlanError("setup_score is required when setup_name is supplied")

    reviews: list[AgentReview] = []

    # 1. Scout: makes sure the information is recent and liquid enough to use.
    if data_age > max_data_age:
        reviews.append(AgentReview("Scout", "SKIP", f"Market data is {data_age:.0f}s old; refresh before considering a trade."))
    elif volume_ratio < min_volume:
        reviews.append(AgentReview("Scout", "WAIT", f"Volume is {volume_ratio:.2f}× baseline, below the {min_volume:.2f}× participation threshold."))
    else:
        reviews.append(AgentReview("Scout", "PASS", f"Data is {data_age:.0f}s old and participation is {volume_ratio:.2f}× baseline."))

    # 2. Trend: avoids buying into a declared downtrend.
    trend = str(request.trend).upper().strip()
    if str(request.side).upper().strip() != "BUY":
        reviews.append(AgentReview("Trend", "SKIP", "This council currently approves only BUY, WAIT or SKIP decisions."))
    elif trend == "BEARISH":
        reviews.append(AgentReview("Trend", "SKIP", "The declared trend is bearish, which conflicts with a long entry."))
    elif trend == "NEUTRAL":
        reviews.append(AgentReview("Trend", "WAIT", "Trend is neutral; wait for directional confirmation."))
    elif trend != "BULLISH":
        reviews.append(AgentReview("Trend", "WAIT", "Trend classification is unknown; verify the market regime."))
    elif setup_score is not None and setup_score < min_setup_score:
        reviews.append(
            AgentReview(
                "Trend",
                "WAIT",
                f"{setup_name} matches {setup_score:.0f}/100 setup rules; {min_setup_score:.0f} are required. This score is rule confluence, not a win probability.",
            )
        )
    elif setup_score is not None:
        reviews.append(
            AgentReview(
                "Trend",
                "PASS",
                f"Bullish trend aligns with {setup_name} ({setup_score:.0f}/100 rule confluence; not a win probability).",
            )
        )
    else:
        reviews.append(AgentReview("Trend", "PASS", "The declared bullish trend supports the long thesis."))

    # 3. Chart guardian: preserves the entry / stop / target plan on the chart.
    entry_deviation = abs(current_price - request.entry_price) / request.entry_price * 100
    if current_price <= request.stop_price:
        reviews.append(
            AgentReview(
                "Chart Guardian",
                "SKIP",
                "Price is at or below the planned stop; the proposed long thesis is already invalidated.",
            )
        )
    elif current_price >= request.target_price:
        reviews.append(
            AgentReview(
                "Chart Guardian",
                "WAIT",
                "Price has reached or passed the target; re-map the trade instead of chasing the original setup.",
            )
        )
    elif entry_deviation > entry_tolerance:
        reviews.append(
            AgentReview(
                "Chart Guardian",
                "WAIT",
                f"Price is {entry_deviation:.2f}% from entry, beyond the {entry_tolerance:.2f}% zone; do not chase the setup.",
            )
        )
    else:
        reviews.append(
            AgentReview(
                "Chart Guardian",
                "PASS",
                "Entry, stop and target geometry is valid and price remains in the entry zone.",
            )
        )

    # 4. Risk sentinel: uses the deterministic position planner as a hard gate.
    if not plan.approved:
        reviews.append(AgentReview("Risk Sentinel", "SKIP", plan.reason))
    else:
        reviews.append(
            AgentReview(
                "Risk Sentinel",
                "PASS",
                f"Size {_format_quantity(plan.quantity)} fractional paper units; "
                f"estimated loss {plan.estimated_loss:.2f}, reward/risk "
                f"{plan.reward_risk_ratio:.2f}×, notional {plan.notional:.2f}. "
                "Quantity is rounded down to eight decimals; "
                "venue lot sizes are not modeled.",
            )
        )

    # 5. Volatility guardian: avoids entries in an explicitly excessive regime.
    if volatility > max_volatility:
        reviews.append(AgentReview("Volatility Guardian", "SKIP", f"Volatility is {volatility:.2f}%, above the {max_volatility:.2f}% safety ceiling."))
    else:
        reviews.append(AgentReview("Volatility Guardian", "PASS", f"Volatility is {volatility:.2f}%, within the {max_volatility:.2f}% ceiling."))

    # 6. Execution gate: blocks closed markets and pauses on a wide spread.
    if not request.market_open:
        reviews.append(AgentReview("Execution Gate", "SKIP", "The market is marked closed; no new plan should be acted on."))
    elif spread > max_spread:
        reviews.append(AgentReview("Execution Gate", "WAIT", f"Spread is {spread:.3f}%, above the {max_spread:.3f}% execution threshold."))
    else:
        reviews.append(AgentReview("Execution Gate", "PASS", f"Market is open and spread is {spread:.3f}%, within the {max_spread:.3f}% threshold."))

    reviews = [
        AgentReview(review.agent, review.verdict, review.reason, _next_step(review, request))
        for review in reviews
    ]

    if any(review.verdict == "SKIP" for review in reviews):
        return CouncilDecision("SKIP", _first_reason(reviews, "SKIP"), tuple(reviews), plan)
    if any(review.verdict == "WAIT" for review in reviews):
        return CouncilDecision("WAIT", _first_reason(reviews, "WAIT"), tuple(reviews), plan)
    return CouncilDecision(
        "BUY",
        "All six paper-trade gates passed. Keep the stop and target visible before any separate execution decision.",
        tuple(reviews),
        plan,
    )


