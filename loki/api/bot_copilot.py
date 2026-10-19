"""A deterministic, local-context coach for Loki's paper console.

The coach only summarizes context supplied with each browser request. It has no
external model dependency, does not predict returns, and cannot submit orders.
"""
from __future__ import annotations

import re
from typing import Any


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _fmt(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def _fmt_quantity(value: Any) -> str:
    try:
        return f"{float(value):,.8f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return "—"


def _decision_answer(context: dict[str, Any]) -> str:
    decision = _record(context.get("decision"))
    if not decision.get("action"):
        return "I don't have a council review on this screen yet. Load a market snapshot, set entry, stop and target, then run the Defence Council. I can explain its gates and the next step for each WAIT or SKIP."
    action = str(decision.get("action", "UNKNOWN")).upper()
    market = _record(context.get("market"))
    symbol = market.get("symbol") or "the selected market"
    interval = market.get("interval") or "current frame"
    rationale = str(decision.get("rationale") or "No council rationale was recorded.")
    blockers = [
        review for review in decision.get("reviews", [])
        if str(_record(review).get("verdict", "")).upper() in {"WAIT", "SKIP"}
    ]
    if action == "BUY":
        return (
            f"The paper council marked {symbol} ({interval}) BUY because all six gates passed. "
            "That is a checklist result, not a forecast or an order. Keep the planned stop and target visible and make any execution decision separately."
        )
    lines = [f"The council marked {symbol} ({interval}) {action}: {rationale}"]
    if blockers:
        lines.append("Items to resolve:")
        for review in blockers[:4]:
            item = _record(review)
            agent = str(item.get("agent") or "Council gate")
            reason = str(item.get("reason") or "The gate needs review.")
            next_step = str(item.get("next_step") or "Review the input and run the council again.")
            lines.append(f"• {agent}: {reason} Next: {next_step}")
    lines.append("Refresh the feed before rerunning so the review uses current context.")
    return "\n".join(lines)


def _risk_answer(context: dict[str, Any]) -> str:
    decision = _record(context.get("decision"))
    plan = _record(decision.get("plan"))
    if not plan:
        return "There is no calculated plan to summarize yet. Enter capital, risk budget, entry, stop and target, then run the council. Position size is constrained by the risk budget and notional cap."
    quantity = plan.get("quantity")
    loss = plan.get("estimated_loss")
    ratio = plan.get("reward_risk_ratio")
    notional = plan.get("notional")
    profit = plan.get("projected_profit")
    return (
        f"The current paper plan sizes {_fmt_quantity(quantity)} fractional paper units, "
        f"with an estimated loss of {_fmt(loss)} quote units and reward/risk of "
        f"{_fmt(ratio)}×. Notional is {_fmt(notional)}; projected target profit is "
        f"{_fmt(profit)} before real-world costs. "
        "Quantity is rounded down to eight decimals; venue lot sizes are not modeled. "
        "Actual losses can exceed the estimate because of gaps, slippage and fees; "
        "this calculation does not place an order."
    )


def _strategy_answer(context: dict[str, Any]) -> str:
    decision = _record(context.get("decision"))
    journal = _record(context.get("journal"))
    setup_name = str(decision.get("setup_name") or "")
    setups = [item for item in journal.get("setups", []) if isinstance(item, dict)]
    selected = next((item for item in setups if str(item.get("name", "")).casefold() == setup_name.casefold()), None)
    if not selected and setups:
        selected = max(setups, key=lambda item: int(item.get("closed", 0) or 0))
    if not selected:
        return (
            f"I don't have closed journal outcomes for {setup_name or 'a setup'} yet. "
            "Track paper entries and record manual exits to build a sample. Compare setups only after enough outcomes, and use the Strategy Lab holdout with fees and slippage before changing rules."
        )
    count = int(selected.get("closed", 0) or 0)
    wins = int(selected.get("wins", 0) or 0)
    win_rate = selected.get("win_rate_percent")
    if win_rate is None and count:
        win_rate = wins / count * 100
    if count < 5:
        sample_read = "This is a very small sample; treat it as a note, not evidence to change the rules."
    elif count < 20:
        sample_read = "This is an early sample; keep logging outcomes before treating the difference as repeatable."
    else:
        sample_read = "This is a larger journal sample to review, but it still does not establish a future edge."
    return (
        f"{selected.get('name', setup_name or 'Setup')}: {count} closed journal outcomes, "
        f"{_fmt(win_rate, 1)}% wins, average {_fmt(selected.get('average_r'))}R, "
        f"gross P&L {_fmt(selected.get('pnl'))} quote units. {sample_read} "
        "These browser-recorded results exclude costs unless you account for them. Prefer a predeclared holdout and realistic costs over tuning to this sample."
    )


def _market_answer(context: dict[str, Any]) -> str:
    market = _record(context.get("market"))
    if not market.get("symbol"):
        return "No market snapshot is attached to this message. Refresh the read-only market feed first; then I can summarize its price, regime, RSI, volume, spread and data age."
    age = market.get("data_age_seconds")
    freshness = ""
    try:
        if float(age) > 60:
            freshness = " The snapshot is older than the 60-second council limit; refresh it before reviewing a setup."
    except (TypeError, ValueError):
        pass
    return (
        f"{market.get('symbol')} ({market.get('interval', 'frame')}): price {_fmt(market.get('current_price'), 6)}, "
        f"regime {market.get('trend', 'unknown')}, RSI 14 {_fmt(market.get('rsi_14'), 1)}, "
        f"volume {_fmt(market.get('volume_ratio'))}× baseline, spread {_fmt(market.get('spread_percent'), 4)}%, "
        f"data age {_fmt(age, 0)}s.{freshness} These are descriptive readings, not a directional prediction."
    )


def _daily_risk_answer(context: dict[str, Any]) -> str:
    risk = _record(context.get("daily_risk"))
    if not risk:
        return (
            "The daily risk guard has no current reading yet. Set a valid capital amount "
            "and daily cap, "
            "then track paper entries and manual exits in the journal."
        )
    return (
        f"Daily paper-risk guard: {risk.get('status', 'UNKNOWN')}. "
        f"User cap {_fmt(risk.get('limit_amount'))} quote units; today's gross realized losses "
        f"{_fmt(risk.get('realized_loss'))}, realized P&L {_fmt(risk.get('realized_pnl'))}, "
        f"open planned risk {_fmt(risk.get('open_planned_risk'))}, and combined committed loss "
        f"{_fmt(risk.get('committed_loss'))}. Remaining cap {_fmt(risk.get('remaining_amount'))} "
        f"({_fmt(risk.get('utilization_percent'), 1)}% used). It covers "
        f"{risk.get('closed_today', 0)} closed and "
        f"{risk.get('open_positions', 0)} open journal entries. "
        "This is an advisory estimate from your browser's local day. "
        "It uses original planned risk, excludes mark-to-market, fees and slippage, "
        "and does not block plans or orders."
    )


def answer_bot_question(payload: dict[str, Any]) -> str:
    """Answer a bounded question from the market, council and journal context."""
    question = re.sub(r"\s+", " ", str(payload.get("question") or "")).strip()
    if not question:
        return "Ask about the council decision, risk plan, market snapshot or recorded setup outcomes."
    query = question.casefold()
    context = payload if isinstance(payload, dict) else {}

    is_daily_risk_question = (
        "daily" in query
        and any(word in query for word in ("risk", "loss", "cap", "limit", "budget"))
    ) or "loss cap" in query or "daily drawdown" in query
    if is_daily_risk_question:
        return _daily_risk_answer(context)
    if any(word in query for word in ("council", "decision", "wait", "skip", "buy", "gate", "why")):
        return _decision_answer(context)
    if any(word in query for word in ("risk", "size", "stop", "loss", "exposure", "position", "quantity", "reward")):
        return _risk_answer(context)
    if any(word in query for word in ("strategy", "setup", "performance", "journal", "outcome", "win rate", "expectancy")):
        return _strategy_answer(context)
    if any(word in query for word in ("market", "price", "trend", "rsi", "volume", "spread", "feed", "regime")):
        return _market_answer(context)
    return (
        "I can explain the current council decision and its next steps, summarize the paper risk plan, "
        "describe the read-only market snapshot, or review closed journal outcomes by setup. "
        "Try one of the suggested questions; I use only context sent from this screen."
    )
