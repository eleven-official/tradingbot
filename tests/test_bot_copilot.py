from loki.api.bot_copilot import answer_bot_question


def test_council_answer_explains_blockers_and_remediation():
    answer = answer_bot_question({
        "question": "Why is the council waiting?",
        "market": {"symbol": "BTCUSDT", "interval": "5m"},
        "decision": {
            "action": "WAIT",
            "rationale": "Trend is neutral.",
            "reviews": [{
                "agent": "Trend",
                "verdict": "WAIT",
                "reason": "Trend is neutral; wait for directional confirmation.",
                "next_step": "Wait for a confirmed bullish regime.",
            }],
        },
    })

    assert "BTCUSDT (5m) WAIT" in answer
    assert "Trend is neutral" in answer
    assert "Wait for a confirmed bullish regime" in answer


def test_risk_answer_uses_the_calculated_plan():
    answer = answer_bot_question({
        "question": "What is my position size and risk?",
        "decision": {
            "plan": {
                "quantity": 2,
                "estimated_loss": 20,
                "reward_risk_ratio": 2,
                "notional": 200,
                "projected_profit": 40,
            },
        },
    })

    assert "2.000000 units" in answer
    assert "20.00 quote units" in answer
    assert "2.00×" in answer
    assert "does not place an order" in answer


def test_setup_answer_labels_tiny_samples_and_avoids_edge_claims():
    answer = answer_bot_question({
        "question": "How is my strategy doing?",
        "decision": {"setup_name": "Trend continuation"},
        "journal": {
            "setups": [{
                "name": "Trend continuation",
                "closed": 3,
                "wins": 2,
                "win_rate_percent": 66.7,
                "average_r": 0.4,
                "pnl": 12,
            }],
        },
    })

    assert "3 closed journal outcomes" in answer
    assert "very small sample" in answer
    assert "does not establish a future edge" not in answer


def test_market_answer_warns_when_snapshot_is_stale():
    answer = answer_bot_question({
        "question": "Summarize the market feed",
        "market": {
            "symbol": "ETHUSDT",
            "interval": "1h",
            "current_price": 2500,
            "trend": "BULLISH",
            "rsi_14": 61.4,
            "volume_ratio": 1.2,
            "spread_percent": 0.1,
            "data_age_seconds": 90,
        },
    })

    assert "ETHUSDT (1h)" in answer
    assert "older than the 60-second council limit" in answer
    assert "not a directional prediction" in answer


def test_unknown_question_describes_coach_scope():
    answer = answer_bot_question({"question": "Tell me a joke"})

    assert "I can explain the current council decision" in answer
    assert "only context sent from this screen" in answer


def test_daily_risk_answer_uses_gross_loss_and_disclaims_scope():
    answer = answer_bot_question({
        "question": "How much of my daily loss cap remains?",
        "daily_risk": {
            "status": "WATCH",
            "limit_amount": 200,
            "realized_pnl": 100,
            "realized_loss": 75,
            "open_planned_risk": 100,
            "committed_loss": 175,
            "remaining_amount": 25,
            "utilization_percent": 87.5,
            "closed_today": 2,
            "open_positions": 1,
        },
    })

    assert "today's gross realized losses 75.00" in answer
    assert "Remaining cap 25.00" in answer
    assert "does not block plans or orders" in answer


def test_daily_risk_answer_handles_missing_summary():
    answer = answer_bot_question({"question": "Check my daily risk cap"})

    assert "has no current reading yet" in answer
    assert "track paper entries" in answer
