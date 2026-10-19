"""Conversational and Fusion regressions on explicitly supplied observations."""
from copy import deepcopy

from core.copilot import LokiCopilot


def snapshot():
    return {
        "data_mode": "uploaded historical CSV (unverified)", "trading_mode": "paper research only",
        "as_of": "2026-10-17T00:00:00Z", "symbol": "TEST/USDT",
        "portfolio": {"equity": 10200, "cash": 8000, "currency": "USDT"},
        "positions": [{"symbol": "TEST/USDT", "quantity": 20, "average_price": 100,
                       "mark_price": 110, "stop_loss": 90}],
        "metrics": {"equity": 10200, "cash": 8000, "total_pnl": 200,
                    "total_return_pct": 2, "closed_trades": 0},
    }


def test_multi_topic_typo_question_uses_supplied_paper_ledger_and_currency():
    context = snapshot()
    before = deepcopy(context)
    reply = LokiCopilot().respond("Show my porfolio and explain exposure risk", context)
    assert set(reply.topics) == {"portfolio", "risk"}
    assert "USDT 10,200.00" in reply.text
    assert "average entry USDT 100.00" in reply.text
    assert "snapshot value USDT 2,200.00" in reply.text
    assert "21.6%" in reply.text
    assert context == before


def test_followup_retains_only_valid_topics_and_instrument_with_fresh_values():
    context = snapshot()
    first = LokiCopilot().respond("Show my positions for TEST/USDT", context).as_dict()
    assert set(first["conversation"]) == {"topics", "symbol"}
    context["conversation"] = first["conversation"]
    context["metrics"]["equity"] = 10100
    second = LokiCopilot().respond("why?", context)
    assert second.intent == "portfolio"
    assert "USDT 10,100.00" in second.text
    missing = LokiCopilot().respond("why?", {"conversation": first["conversation"]})
    assert "Equity unknown" in missing.text
    assert "10,200" not in missing.text


def test_overview_distinguishes_zero_closed_positions_from_fills():
    reply = LokiCopilot().respond("How am I doing?", snapshot())
    assert reply.intent == "overview"
    assert "No trades have completed" in reply.text
    assert "P&L USDT 200.00" in reply.text


def test_loss_review_uses_exit_records_and_does_not_invent_market_causation():
    context = snapshot()
    context["recent_trades"] = [
        {"symbol": "TEST/USDT", "side": "BUY", "pnl": -999},
        {"symbol": "TEST/USDT", "side": "SELL", "pnl": -20, "reason": "manual paper exit"},
    ]
    reply = LokiCopilot().respond("Why did we lose?", context)
    assert reply.intent == "diagnosis"
    assert "1 losing exits sum to USDT -20.00" in reply.text
    assert "manual paper exit" in reply.text
    assert "-999" not in reply.text
    assert "do not establish why the market moved" in reply.text


def test_council_wait_explains_mismatched_strategy_and_blocked_draft():
    context = snapshot()
    context["council"] = {
        "director": {"decision": "wait", "summary": "These checks failed.",
                     "blocked_by": ["Research target supported for this rule"]},
        "performance_target": {"closed_trades": 10, "observed_win_rate": .4,
                               "lower_confidence_bound": .2, "supported": False, "same_strategy": False},
        "proposal": {"symbol": "TEST/USDT", "quantity": 1, "cash_required": 100.15,
                     "planned_loss_at_stop": 5.3},
    }
    reply = LokiCopilot().respond("Why did the council wait?", context)
    assert reply.intent == "council"
    for phrase in ("wait", "40.00%", "20.00%", "different strategy", "blocked draft",
                   "No AutoHedge LLM was invoked", "no order was submitted"):
        assert phrase in reply.text


def test_factor_score_is_not_a_prediction_and_invalid_values_remain_unknown():
    context = snapshot()
    context["factor_analysis"] = {
        "symbol": "TEST/USDT", "signal": {"stance": "cash", "score": .8,
            "conditions": [{"name": "Momentum positive", "passed": False}]},
        "factors": [{"label": "Momentum", "value": .05, "unit": "fraction"},
                    {"label": "RSI", "value": float("nan"), "unit": "index_0_100"}],
    }
    reply = LokiCopilot().respond("Explain the factors", context)
    assert reply.intent == "factors"
    assert "80.00%" in reply.text and "not a probability" in reply.text
    assert "Momentum positive: not met" in reply.text
    assert "Momentum: 5.00%" in reply.text and "RSI: unknown" in reply.text


def test_stress_percentage_points_and_currency_are_kept_distinct_from_mirofish():
    context = snapshot()
    context["scenario"] = {"mode": "hypothetical_stress", "effective_shock_pct": -10,
        "baseline_equity": 10200, "stressed_equity": 9980, "pnl": -220,
        "return_pct": -220 / 10200 * 100, "positions": [{"symbol": "TEST/USDT"}]}
    reply = LokiCopilot().respond("Explain the stress scenario", context)
    assert reply.intent == "scenario"
    assert "shock is -10.00%" in reply.text
    assert "USDT -220.00 (-2.16%)" in reply.text
    assert "not a forecast" in reply.text and "MiroFish agent simulation" in reply.text
    assert "journal was not changed" in reply.text


def test_missing_fusion_context_does_not_invent_diagnostics():
    for question, phrase in [("Explain the council", "No council review"),
                             ("Explain factors", "No factor analysis"),
                             ("Explain stress scenario", "No hypothetical portfolio stress")]:
        reply = LokiCopilot().respond(question)
        assert phrase in reply.text


def test_changes_require_comparable_timestamped_snapshots():
    context = snapshot()
    reply = LokiCopilot().respond("What changed?", context)
    assert "only the current snapshot" in reply.text
    context["previous_snapshot"] = deepcopy(context)
    context["previous_snapshot"]["trading_mode"] = "live"
    reply = LokiCopilot().respond("What changed?", context)
    assert "not comparable" in reply.text


def test_explicit_action_still_takes_priority_over_fusion_topics():
    context = snapshot()
    before = deepcopy(context)
    reply = LokiCopilot().respond("Execute the council trade now", context)
    assert reply.intent == "action"
    assert "No action was taken" in reply.text
    assert context == before
