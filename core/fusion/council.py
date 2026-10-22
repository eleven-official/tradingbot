"""Evidence-first research council adapted from AutoHedge's role architecture.

This is an explicit deterministic pipeline, not a group of independently
reasoning LLM agents. All decisions are inspectable; every proposal is inert.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from typing import Any

from core.fusion.quant import ShadowConfig, _bars, _symbol, analyze_factors
from core.risk_preview import preview_position
from third_party.autohedge.role_contracts import ROLE_CONTRACTS, role_packet

STRATEGY_ID = "loki_fusion_fixed_factor_v1"
AUTOHEDGE_PROVENANCE = {
    "project": "AutoHedge",
    "license": "MIT",
    "archive_sha256": "e998228572869b754f2aba3ee61016bf427ebc1159ad04421d945dc5e6f3767b",
    "modules": ["autohedge/workers.py", "autohedge/prompts.py"],
    "adaptation": "Director, quant, sentiment, risk and execution role contracts adapted to deterministic local evidence.",
}


@dataclass(frozen=True)
class CouncilConfig(ShadowConfig):
    max_portfolio_exposure: float = 0.60
    require_research_evidence: bool = True

    def __post_init__(self) -> None:
        # ShadowConfig validates its own fields only; its fields(self) would also
        # see this class's boolean flag, so validate a base instance explicitly.
        ShadowConfig(**{item.name: getattr(self, item.name) for item in fields(ShadowConfig)})
        if (
            isinstance(self.max_portfolio_exposure, bool)
            or not isinstance(self.max_portfolio_exposure, (int, float))
            or not math.isfinite(self.max_portfolio_exposure)
            or not 0 < self.max_portfolio_exposure <= 1
        ):
            raise ValueError("max_portfolio_exposure must be a fraction in (0, 1]")
        if not isinstance(self.require_research_evidence, bool):
            raise ValueError("require_research_evidence must be true or false")
        if self.max_exposure > self.max_portfolio_exposure:
            raise ValueError("The single-asset exposure cap cannot exceed the portfolio cap")


def _config(value: Mapping[str, Any] | CouncilConfig | None) -> CouncilConfig:
    if value is None:
        return CouncilConfig()
    if isinstance(value, CouncilConfig):
        return value
    if not isinstance(value, Mapping):
        raise ValueError("config must contain council settings")
    try:
        return CouncilConfig(**value)
    except TypeError as exc:
        raise ValueError("Unknown council settings") from exc


def _number(value: Any, name: str, *, positive: bool = False) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
        or value > 1e15
        or (positive and value == 0)
    ):
        raise ValueError(
            f"{name} must be a finite {'positive' if positive else 'nonnegative'} number at most 1e15"
        )
    return float(value)


def _portfolio(
    value: Mapping[str, Any] | None, config: CouncilConfig, symbol: str
) -> dict[str, Any]:
    if value is None:
        return {
            "equity": config.initial_capital,
            "cash": config.initial_capital,
            "gross_exposure": 0.0,
            "symbol_exposure": 0.0,
            "currency": symbol.rsplit("/", 1)[1] if "/" in symbol else None,
            "basis": "hypothetical_starting_cash",
            "warnings": [
                "Sizing uses hypothetical starting cash; no account snapshot was supplied."
            ],
        }
    if not isinstance(value, Mapping):
        raise ValueError("portfolio must be a supplied snapshot")
    if "state" in value:
        value = value["state"]
    if not isinstance(value, Mapping):
        raise ValueError("portfolio state must be a mapping")
    if value.get("mode") == "paper_only" or "schema_version" in value:
        from core.fusion.portfolio import portfolio_metrics, validate_portfolio

        state = validate_portfolio(value)
        metrics = portfolio_metrics(state)
        return {
            "equity": metrics["equity"],
            "cash": metrics["cash"],
            "gross_exposure": metrics["gross_exposure"],
            "symbol_exposure": sum(
                position["quantity"] * position["mark_price"]
                for ticker, position in state["positions"].items()
                if ticker == symbol
            ),
            "currency": state["quote_currency"],
            "basis": "client_paper_ledger",
            "warnings": [
                "Paper marks are client supplied; freshness and quote currency need review."
            ],
        }
    equity, cash = _number(value.get("equity"), "equity", positive=True), _number(
        value.get("cash"), "cash"
    )
    positions = value.get("positions", [])
    if not isinstance(positions, (list, tuple)) or len(positions) > 100:
        raise ValueError("positions must be a list of at most 100 valued long positions")
    exposure = same_symbol = 0.0
    seen = set()
    for row in positions:
        if not isinstance(row, Mapping):
            raise ValueError("Each position needs symbol and market_value")
        ticker = _symbol(row.get("symbol"))
        if ticker in seen:
            raise ValueError("Aggregate duplicate position symbols before submitting a snapshot")
        seen.add(ticker)
        market_value = _number(row.get("market_value"), "position market_value")
        exposure += market_value
        if ticker == symbol:
            same_symbol += market_value
    if abs(cash + exposure - equity) > max(1e-6, equity * 1e-8):
        raise ValueError("Portfolio equity must equal cash plus all priced long positions")
    currency = value.get("currency", value.get("quote_currency"))
    if currency is not None and (not isinstance(currency, str) or not 2 <= len(currency) <= 12):
        raise ValueError("Portfolio currency must be an explicit currency code")
    return {
        "equity": equity,
        "cash": cash,
        "gross_exposure": exposure,
        "symbol_exposure": same_symbol,
        "currency": currency.upper() if currency else None,
        "basis": "supplied_long_snapshot",
        "warnings": [
            "Snapshot prices, completeness, currency and freshness are supplied by the caller."
        ],
    }


def _performance(
    research: Mapping[str, Any] | None, bars, symbol: str, target: float
) -> dict[str, Any]:
    if research is not None and not isinstance(research, Mapping):
        raise ValueError("research must be an existing structured research report")
    research = research or {}
    summary = research.get("summary", {})
    if not isinstance(summary, Mapping):
        raise ValueError("Research summary must be a mapping")
    count, rate, interval = (
        summary.get("total_trades", 0),
        summary.get("win_rate"),
        summary.get("win_rate_ci95"),
    )
    valid_count = isinstance(count, int) and not isinstance(count, bool) and count >= 0
    valid_rate = (
        isinstance(rate, (int, float))
        and not isinstance(rate, bool)
        and math.isfinite(rate)
        and 0 <= rate <= 1
    )
    lower = None
    if (
        isinstance(interval, (list, tuple))
        and len(interval) == 2
        and all(
            isinstance(item, (int, float)) and not isinstance(item, bool) and math.isfinite(item)
            for item in interval
        )
        and 0 <= interval[0] <= interval[1] <= 1
    ):
        lower = float(interval[0])
    fingerprint = hashlib.sha256(
        json.dumps(
            [
                [bar.timestamp.isoformat(), bar.open, bar.high, bar.low, bar.close, bar.volume]
                for bar in bars
            ],
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    linked = bool(research) and research.get("data_fingerprint") == fingerprint
    same_symbol = research.get("symbol", symbol) == symbol
    same_strategy = research.get("strategy_id") == STRATEGY_ID
    forward = research.get("validation_mode") == "chronological_forward_test"
    positives = all(
        isinstance(summary.get(key), (int, float))
        and not isinstance(summary.get(key), bool)
        and math.isfinite(summary[key])
        and summary[key] > 0
        for key in ("total_return", "expectancy")
    )
    supported = (
        valid_count
        and count >= 100
        and valid_rate
        and rate >= target
        and lower is not None
        and lower >= target
        and linked
        and same_symbol
        and same_strategy
        and forward
        and positives
    )
    reasons = []
    if not research:
        reasons.append("No forward-test report was supplied.")
    else:
        if not linked or not same_symbol:
            reasons.append("Research observations or instrument do not match this council input.")
        if not same_strategy:
            reasons.append(
                "The supplied report evaluates a different strategy; it does not validate the Fusion factor rule."
            )
        if not forward:
            reasons.append("A chronological forward-test identity for this rule is missing.")
        if not valid_count or count < 100:
            reasons.append(
                "At least 100 completed forward trades are required for the target evidence gate."
            )
        if not valid_rate or rate < target or lower is None or lower < target:
            reasons.append(
                "Observed wins and the descriptive 95% lower bound do not both meet the target."
            )
        if not positives:
            reasons.append(
                "Positive net return and positive net expectancy after costs are required."
            )
    return {
        "win_rate": target,
        "observed_win_rate": float(rate) if valid_rate and valid_count and count else None,
        "lower_confidence_bound": lower,
        "closed_trades": count if valid_count else 0,
        "meets_observed_target": bool(valid_rate and valid_count and count and rate >= target),
        "supported": bool(supported),
        "same_observations": linked,
        "same_strategy": same_strategy,
        "evidence_source": "caller_supplied_report",
        "reasons": reasons,
        "limitation": "Historical sample evidence cannot guarantee future wins; report authenticity and trade independence are not established.",
    }


def _analyst(
    role: str, status: str, summary: str, evidence: dict[str, Any], concerns: list[str], symbol: str
) -> dict[str, Any]:
    packet = role_packet(role, symbol=symbol, evidence=evidence)
    return {
        "role": role,
        "title": ROLE_CONTRACTS[role]["title"],
        "status": status,
        "summary": summary,
        "evidence": packet["evidence"],
        "contract": packet["contract"],
        "concerns": concerns,
    }


def _signed_score(value: Any, name: str) -> float:
    """A news mood or headline score: finite and within the published [-1, 1] band."""
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < -1.0
        or value > 1.0
    ):
        raise ValueError(f"{name} must be a finite number within [-1, 1]")
    return float(value)


def _news_evidence(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Bind the desk news agent's read for inspection — never for gating.

    The packet is the bounded JSON handoff the spec asks for: a clamped
    score, the count of headlines read, headline rows with per-headline
    scores and the method string. Anything else is an error, so no
    side channel ever smuggles undocumented claims into the sentiment seat.
    """
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("news_evidence must be the desk news agent's JSON packet")
    if value.get("status") != "ok":
        raise ValueError("news_evidence must be an ok packet; abstains stay abstains")
    score = _signed_score(value.get("score"), "news_evidence score")
    if not -1.0 <= score <= 1.0:
        raise ValueError("news_evidence score must be within [-1, 1]")
    headlines_read = value.get("headlines_read")
    if (
        isinstance(headlines_read, bool)
        or not isinstance(headlines_read, int)
        or not 1 <= headlines_read <= 50
    ):
        raise ValueError("news_evidence headlines_read must be an integer from 1 to 50")
    method = value.get("method")
    if not isinstance(method, str) or not 12 <= len(method.strip()) <= 300:
        raise ValueError("news_evidence method must be a 12..300 character description")
    top = value.get("top")
    if not isinstance(top, list) or not 1 <= len(top) <= 30:
        raise ValueError("news_evidence top must list 1..30 scored headlines")
    rows: list[dict[str, Any]] = []
    for row in top:
        if not isinstance(row, Mapping):
            raise ValueError("Each news_evidence headline must be a mapping")
        title = row.get("title")
        if not isinstance(title, str) or not 3 <= len(title.strip()) <= 200:
            raise ValueError("Each news_evidence headline needs a 3..200 character title")
        publisher = row.get("publisher", "")
        if not isinstance(publisher, str) or len(publisher) > 80:
            raise ValueError("news_evidence publisher must be at most 80 characters")
        per_score = _signed_score(row.get("score"), "news_evidence headline score")
        if not -1.0 <= per_score <= 1.0:
            raise ValueError("news_evidence headline scores must be within [-1, 1]")
        rows.append({"title": title, "publisher": publisher, "score": per_score})
    return {
        "status": "ok",
        "score": score,
        "headlines_read": headlines_read,
        "top": rows,
        "method": method.strip(),
    }


def build_council_report(
    data: Sequence[Mapping[str, Any]],
    *,
    symbol: str = "BTC/USDT",
    portfolio: Mapping[str, Any] | None = None,
    research: Mapping[str, Any] | None = None,
    config: Mapping[str, Any] | CouncilConfig | None = None,
    miro_research: Mapping[str, Any] | None = None,
    miro_reviewed: bool = False,
    news_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Quant -> sentiment -> risk -> execution -> director on supplied evidence.

    Returns an inert proposal with explicit blocked checks. No free-text agent
    output can bypass sizing, the account limits or the evidence gate.
    """
    symbol, config = _symbol(symbol), _config(config)
    bars = _bars(data, 21)
    quant = analyze_factors(data, symbol=symbol, periods_per_year=config.periods_per_year)
    snapshot = _portfolio(portfolio, config, symbol)
    performance = _performance(research, bars, symbol, config.min_win_rate)
    news_packet = _news_evidence(news_evidence)
    if type(miro_reviewed) is not bool:
        raise ValueError("MiroFish scenario review must be an explicit boolean")
    if miro_research is not None and news_packet is not None:
        raise ValueError(
            "The sentiment seat reads one bounded packet: pass MiroFish evidence or desk news context, not both"
        )
    if miro_research is not None:
        if (
            not isinstance(miro_research, Mapping)
            or miro_research.get("engine") != "bundled_mirofish_native"
            or miro_research.get("symbol") != symbol
            or not isinstance(miro_research.get("report"), Mapping)
            or miro_research["report"].get("status") != "completed"
        ):
            raise ValueError(
                "MiroFish evidence must be a completed native report bound to this council instrument"
            )
    equity, cash = snapshot["equity"], snapshot["cash"]
    asset_room = max(0.0, equity * config.max_exposure - snapshot["symbol_exposure"])
    portfolio_room = max(0.0, equity * config.max_portfolio_exposure - snapshot["gross_exposure"])
    currency = snapshot["currency"]
    quote_currency = symbol.rsplit("/", 1)[1] if "/" in symbol else None
    currency_matches = currency is not None and (
        quote_currency is None or currency == quote_currency
    )
    entry = bars[-1].close
    stop_fraction = min(0.15, max(0.02, config.stop_atr_multiple * quant["risk"]["atr14"] / entry))
    stop = entry * (1 - stop_fraction)
    target = entry + 2 * (entry - stop)
    sizing = (
        preview_position(
            equity,
            entry,
            stop,
            config.risk_per_trade * 100,
            config.max_exposure * 100,
            config.fee_bps,
            config.slippage_bps,
        )
        if equity > 0
        else None
    )
    fee, slip = config.fee_bps / 10_000, config.slippage_bps / 10_000
    unit_cash = entry * (1 + slip) * (1 + fee)
    available = min(cash, asset_room, portfolio_room)
    quantity = (
        min(sizing["quantity"], available / unit_cash, bars[-1].volume * 0.005) if sizing else 0.0
    )
    unit_risk = unit_cash - stop * (1 - slip) * (1 - fee)
    unit_reward = target * (1 - slip) * (1 - fee) - unit_cash
    reward_risk = unit_reward / unit_risk
    checks = [
        {
            "name": "Factor conditions agree",
            "passed": quant["signal"]["stance"] == "long_candidate",
            "detail": f"{sum(row['passed'] for row in quant['signal']['conditions'])}/5 fixed conditions met; score is not win probability.",
        },
        {
            "name": "Cash and existing exposure leave capacity",
            "passed": quantity > 0,
            "detail": "Sizing subtracts held asset exposure, total portfolio exposure and both-side trading costs.",
        },
        {
            "name": "Quote currency agrees",
            "passed": currency_matches,
            "detail": f"Account currency {currency or 'missing'}; instrument quote {quote_currency or 'caller must verify'}. No FX conversion is performed.",
        },
        {
            "name": "Net reward/risk at least 1.5",
            "passed": reward_risk >= 1.5,
            "detail": "Entry, stop and 2R target references include adverse slippage and fees on both sides.",
        },
        {
            "name": "Research target supported for this rule",
            "passed": performance["supported"] or not config.require_research_evidence,
            "detail": (
                "Matching forward-test evidence is required."
                if config.require_research_evidence
                else "Evidence gate explicitly disabled for hypothetical paper planning; no validation claim."
            ),
        },
    ]
    if miro_research is not None:
        checks.append(
            {
                "name": "MiroFish scenario reviewed",
                "passed": miro_reviewed,
                "detail": "Read the native report's assumptions and counterarguments. Acknowledging it never validates trade performance or overrides cash/risk gates.",
            }
        )
    blocked = [row["name"] for row in checks if not row["passed"]]
    proposal = None
    if quantity > 0:
        proposal = {
            "symbol": symbol,
            "side": "buy",
            "mode": "proposal_only",
            "quantity": quantity,
            "entry_reference": entry,
            "stop_reference": stop,
            "take_profit_reference": target,
            "cash_required": quantity * unit_cash,
            "planned_loss_at_stop": quantity * unit_risk,
            "reward_risk_after_costs": reward_risk,
            "time_in_force": "review_before_submission",
            "executable": False,
            "blocked_by": blocked,
            "strategy_id": STRATEGY_ID,
            "reference_timestamp": bars[-1].timestamp.isoformat(),
            "note": "Sizing is a snapshot draft; all references must be refreshed before any paper decision.",
        }
    sentiment = (
        _analyst(
            "sentiment",
            "news_context",
            (
                "Desk news context: clamped lexicon mean "
                f"{news_packet['score']:+.2f} over {news_packet['headlines_read']} "
                "public headlines; inspection evidence, never a gate."
            ),
            {
                "sentiment": None,
                "news_count": news_packet["headlines_read"],
                "themes": [],
                "critical_events": [],
                "news": news_packet,
            },
            [
                "The score is a fixed-word-weight mean over public headlines, not a calibrated probability of profit.",
                "No council gate consults news context; it can neither approve nor veto a check.",
                "Headlines are a point-in-time public feed scored in code, not verified research evidence.",
            ],
            symbol,
        )
        if news_packet is not None
        else _analyst(
            "sentiment",
            "missing_evidence",
            "No verified point-in-time news or social evidence was supplied.",
            {"sentiment": None, "news_count": 0, "themes": [], "critical_events": []},
            [
                "No news, social sentiment or institutional score is invented or inferred from price."
            ],
            symbol,
        )
    )
    analysts = [
        _analyst(
            "quant",
            "ready",
            "Fixed price and volume conditions evaluated on completed candles.",
            {"signal": quant["signal"], "factors": quant["factors"], "risk": quant["risk"]},
            ["Condition agreement is a descriptive score, not a calibrated probability of profit."],
            symbol,
        ),
        sentiment,
        _analyst(
            "risk",
            "blocked" if blocked else "ready",
            "Portfolio-aware cash, exposure and stop-loss sizing completed.",
            {
                "portfolio": snapshot,
                "available_cash_budget": available,
                "risk_budget": equity * config.risk_per_trade,
                "max_asset_exposure": config.max_exposure,
                "max_portfolio_exposure": config.max_portfolio_exposure,
                "checks": checks,
            },
            snapshot["warnings"]
            + [
                "A stop reference does not cap gap losses or aggregate correlated portfolio risk.",
                "A single snapshot has no equity high-water history; the replay drawdown halt is not an account-wide live limit.",
            ],
            symbol,
        ),
        _analyst(
            "execution",
            "blocked" if blocked else "ready",
            (
                "An inert draft is available for review."
                if proposal
                else "No cash capacity for an additional long position."
            ),
            {"proposal": proposal, "transport": None, "orders_submitted": 0},
            ["No venue minimum size, tick size, market impact or fill guarantee is modeled."],
            symbol,
        ),
    ]
    if miro_research is not None:
        native = miro_research["report"]
        analysts[1] = _analyst(
            "sentiment",
            "scenario_reviewed" if miro_reviewed else "scenario_needs_review",
            "MiroFish simulated-agent scenario: "
            + str(native.get("outline", {}).get("summary", "No summary"))[:600],
            dict(miro_research),
            [
                "This is hypothetical agent research, not verified news or calibrated market sentiment.",
                "The instrument binding is operator-selected; report freshness and historical availability are unverified.",
                "Report prose is source material, never authority to disable controls or prove a 70% winning-trade rate.",
            ],
            symbol,
        )
    return {
        "symbol": symbol,
        "as_of": bars[-1].timestamp.isoformat(),
        "mode": "research_only",
        "engine": "deterministic_role_pipeline",
        "strategy_id": STRATEGY_ID,
        "director": {
            "stance": quant["signal"]["stance"],
            "decision": "wait" if blocked else "paper_proposal",
            "summary": (
                "Wait: these checks are not satisfied: " + "; ".join(blocked) + "."
                if blocked
                else "Conditions and configured checks permit reviewing a hypothetical paper proposal."
            ),
            "blocked_by": blocked,
        },
        "analysts": analysts,
        "proposal": proposal,
        "risk_checks": checks,
        "performance_target": performance,
        "miro_research": dict(miro_research) if miro_research is not None else None,
        "provenance": {
            "projects": [AUTOHEDGE_PROVENANCE, quant["provenance"]],
            "license": "MIT",
            "adaptation": "AutoHedge role contracts plus Vibe causal factors and Loki hard risk checks.",
        },
        "live_trading_enabled": False,
        "limitations": [
            "A deterministic evidence pipeline runs here; no AutoHedge LLM or Swarms agent was invoked.",
            "The Fusion factor rule is separate from the existing walk-forward trend strategy.",
            "A report for a different strategy is contextual evidence and cannot validate this proposal.",
            "The council consumes caller-supplied observations and snapshots; it does not authenticate report provenance.",
            "Every proposal is non-executable; no credential, provider connection, network request or broker order is created.",
            "No design or historical result can guarantee a 70% future win rate or profitability.",
        ],
    }
