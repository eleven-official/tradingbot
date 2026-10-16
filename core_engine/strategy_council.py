"""Transparent, advisory council for explaining the bot's current setup.

The council reads evidence already produced by the trading loop. It does not
fetch extra market data, change strategy signals, or place orders. Its verdict
is an audit aid; the bot's existing risk and execution gates remain authoritative.
"""
from __future__ import annotations

from datetime import datetime
from math import isfinite
from typing import Any, Iterable, Mapping, Sequence


def _text(value: Any, limit: int = 240) -> str:
    if value is None:
        return ""
    return str(value).strip()[:limit]


def _direction(value: Any) -> str:
    text = _text(value).upper()
    if text in {"BUY", "BULLISH", "VERY BULLISH", "CE"} or "BULL" in text:
        return "BUY"
    if text in {"SELL", "BEARISH", "VERY BEARISH", "PE"} or "BEAR" in text:
        return "SELL"
    return "NEUTRAL"


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def build_strategy_council(
    *,
    strategy: str | None,
    signal: str | None,
    sentiment: str | None,
    regime: str | None,
    regime_reason: str | None = None,
    trend_composite: Any = None,
    trend_summary: str | None = None,
    trend_components: Mapping[str, Any] | None = None,
    conditions: Iterable[Any] = (),
    conviction: str | None = None,
    setup_score: Any = None,
    strategy_status: str | None = None,
    news_headlines: Sequence[Mapping[str, Any]] = (),
    recent_blockers: Iterable[Any] = (),
    active_trade: bool = False,
) -> dict[str, Any]:
    """Build role-based opinions and a cautious, explainable recommendation."""
    action = _text(signal, 24).upper()
    action = action if action in {"BUY", "SELL"} else "HOLD"
    sentiment_direction = _direction(sentiment)
    trend_score = _number(trend_composite)
    trend_direction = (
        "BUY" if trend_score is not None and trend_score > 0.15 else
        "SELL" if trend_score is not None and trend_score < -0.15 else
        "NEUTRAL"
    )

    headlines = []
    for item in list(news_headlines or ())[:3]:
        if not isinstance(item, Mapping):
            continue
        title = _text(item.get("title"), 180)
        if not title:
            continue
        polarity = _number(item.get("polarity"))
        headlines.append({
            "title": title,
            "source": _text(item.get("source"), 80),
            "published_at": _text(item.get("published_at"), 40),
            "polarity": polarity,
        })

    blockers = [_text(item, 180) for item in recent_blockers if _text(item, 180)]
    disagreements = []
    if action in {"BUY", "SELL"}:
        if sentiment_direction not in {"NEUTRAL", action}:
            disagreements.append(
                f"{action} signal disagrees with {sentiment or 'neutral'} sentiment."
            )
        if trend_direction not in {"NEUTRAL", action}:
            disagreements.append(
                f"{action} signal disagrees with the market trend composite."
            )
    disagreements.extend(blockers[:3])

    catalyst_reason = (
        f"{sentiment or 'No sentiment read'} from {len(headlines)} recent headline(s). "
        "Headlines provide context; they do not prove what caused a price move."
        if headlines else
        f"Sentiment read: {sentiment or 'unavailable'}. No headline evidence was attached to this snapshot."
    )
    market_facts = []
    if regime:
        market_facts.append(f"Regime: {_text(regime, 60)}")
    if trend_score is not None:
        market_facts.append(f"Trend composite: {trend_score:+.2f}")
    for condition in list(conditions or ())[:5]:
        condition_text = _text(condition, 60)
        if condition_text:
            market_facts.append(condition_text)
    market_reason = _text(trend_summary) or _text(regime_reason) or "; ".join(market_facts)
    if not market_reason:
        market_reason = "No fresh regime or trend explanation is available."

    strategy_facts = [part for part in (
        f"{_text(strategy, 100)} returned {action}" if strategy else f"Latest strategy signal: {action}",
        _text(strategy_status),
        f"Best setup score: {float(_number(setup_score)):.1f}" if _number(setup_score) is not None else "",
        f"Conviction: {_text(conviction, 40)}" if conviction else "",
    ) if part]

    if active_trade:
        decision = "MANAGE_OPEN_POSITION"
        decision_reason = "An open position exists; the council will not propose another entry."
    elif action == "HOLD":
        decision = "WAIT"
        decision_reason = "The strategy has not produced a current BUY or SELL candidate."
    elif disagreements:
        decision = "REVIEW"
        decision_reason = "The candidate has dissenting evidence that should be reviewed against the bot's existing gates."
    else:
        decision = "CANDIDATE"
        decision_reason = "Evidence is aligned in this snapshot; the bot's existing risk and execution gates still decide whether an order is allowed."

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "decision": decision,
        "decision_reason": decision_reason,
        "signal": action,
        "members": [
            {
                "name": "Catalyst analyst",
                "stance": _text(sentiment, 40) or "UNKNOWN",
                "reason": catalyst_reason,
                "evidence": headlines,
            },
            {
                "name": "Market watcher",
                "stance": trend_direction,
                "reason": market_reason,
                "evidence": market_facts[:6],
            },
            {
                "name": "Strategy analyst",
                "stance": action,
                "reason": "; ".join(strategy_facts) or "No strategy detail is available.",
                "evidence": [],
            },
            {
                "name": "Skeptic",
                "stance": "DISSENT" if disagreements else "NO_DISSENT_RECORDED",
                "reason": "; ".join(disagreements[:4]) or
                          "No disagreement was recorded. Missing evidence is still unknown, not a safety signal.",
                "evidence": disagreements[:4],
            },
        ],
        "authority_note": "Advisory only. Existing strategy, risk limits, and execution checks remain authoritative; this council never places orders.",
    }

