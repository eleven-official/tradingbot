"""Mode and native-scenario explanations retain their actual evidence limits."""

from core.copilot import LokiCopilot


def test_practice_chat_uses_only_practice_metrics_and_does_not_claim_a_trade_edge():
    answer = LokiCopilot().respond(
        "Explain my simulated market",
        {
            "simulated_market": {
                "synthetic": True,
                "step": 10,
                "scenario": "volatile",
                "metrics": {"equity": 9990, "cash": 9000, "total_pnl": -10},
            }
        },
    )
    assert "sim_market" in answer.topics
    assert "$9,990.00" in answer.text
    assert "synthetic outcomes" in answer.text
    assert "cannot establish 70%" in answer.text


def test_real_mode_chat_explains_manual_confirmation_without_implying_autonomous_execution():
    answer = LokiCopilot().respond("How does real mode work?")
    assert "sim_market" in answer.topics
    assert "typed confirmation" in answer.text
    assert "Automatic bot execution is disabled" in answer.text


def test_explicit_practice_balance_does_not_use_the_main_paper_account():
    answer = LokiCopilot().respond(
        "What is my practice balance?",
        {
            "metrics": {"equity": 20000, "cash": 15000},
            "simulated_market": {
                "synthetic": True,
                "step": 4,
                "scenario": "range",
                "metrics": {"equity": 9990, "cash": 9000},
            },
        },
    )
    assert "sim_market" in answer.topics
    assert "portfolio" not in answer.topics
    assert "$9,990.00" in answer.text
    assert "$20,000.00" not in answer.text


def test_council_chat_explains_native_mirofish_source_and_scenario_limit():
    answer = LokiCopilot().respond(
        "Explain the council",
        {
            "council": {
                "director": {"decision": "wait", "summary": "Needs forward evidence."},
                "miro_research": {
                    "report": {
                        "report_id": "report_fixture",
                        "outline": {"summary": "A hypothetical liquidity shock."},
                    }
                },
            }
        },
    )
    assert "retained ReportManager" in answer.text
    assert "cannot validate a strategy" in answer.text
