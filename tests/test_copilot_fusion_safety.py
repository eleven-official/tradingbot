"""Fusion chat preserves the units of each explicitly supplied result."""

from core.copilot import LokiCopilot


def test_scenario_quote_currency_is_not_relabelled_as_current_account_currency():
    context = {
        "portfolio": {"currency": "USDT"},
        "scenario": {
            "mode": "hypothetical_stress",
            "quote_currency": "EUR",
            "effective_shock_pct": -10,
            "baseline_equity": 1000,
            "stressed_equity": 950,
            "pnl": -50,
            "return_pct": -5,
        },
    }
    reply = LokiCopilot().respond("Explain the stress scenario", context)
    assert "EUR -50.00" in reply.text
    assert "EUR 1,000.00" in reply.text
    assert "USDT -50.00" not in reply.text


def test_unknown_scenario_currency_does_not_invent_dollar_units():
    reply = LokiCopilot().respond(
        "Explain the stress scenario",
        {
            "scenario": {
                "mode": "hypothetical_stress",
                "effective_shock_pct": -10,
                "baseline_equity": 1000,
                "stressed_equity": 950,
                "pnl": -50,
                "return_pct": -5,
            },
        },
    )
    assert "quote currency was not supplied" in reply.text
    assert "$" not in reply.text


def test_overflowing_supplied_quantities_do_not_produce_infinite_risk_percentages():
    reply = LokiCopilot().respond(
        "Explain exposure risk",
        {
            "metrics": {"equity": 10000},
            "positions": {"BTC/USD": {"quantity": 1e308}},
            "current_prices": {"BTC/USD": 1e308},
        },
    )
    assert "inf%" not in reply.text
    assert "Exposure is incomplete" in reply.text


def test_overflowing_fraction_remains_unknown_instead_of_infinite_percent():
    reply = LokiCopilot().respond(
        "Explain the factors",
        {
            "factor_analysis": {"symbol": "BTC/USD", "signal": {"stance": "cash", "score": 1e308}},
        },
    )
    assert "Rule-agreement score: unknown" in reply.text
    assert "inf%" not in reply.text
