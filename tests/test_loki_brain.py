"""Loki's brain: real conversations, grounded in the AI engine and real quotes."""

import pytest
from fastapi.testclient import TestClient

from loki.api import loki_brain
from loki.api.server import app
from loki_v8.config import LokiConfig

client = TestClient(app)


def fake_read(allowed=False):
    gates = [
        {"name": "signal", "passed": allowed, "detail": "score"},
        {"name": "volatility_cap", "passed": True, "detail": "ok"},
        {"name": "trend_filter", "passed": allowed, "detail": "x"},
        {"name": "regime_filter", "passed": True, "detail": "y"},
    ]
    plan = {"ready": True, "action": "BUY" if allowed else "HOLD", "allowed": allowed, "score": 41.0 if allowed else 3.0,
            "threshold": 30.0, "ann_vol": 0.2, "gates": gates, "win_probability": 0.52}
    cfg = LokiConfig(sizing_mode="vol_target", target_vol_pct=20.0, exit_mode="trend", stop_loss_atr=10.0)
    return lambda symbol: {"analysis": {"price": 512.4, "regime": "STRONG_BULL", "plan": plan}, "cfg": cfg,
                           "source": "universal_long_history"}


class TestDetection:
    @pytest.mark.parametrize("text,expected", [
        ("should I buy SPY?", ["SPY"]),
        ("what about bitcoin", ["BTC-USD"]),
        ("ETH/USD pulse", ["ETH-USD"]),
        ("tell me about apple and tesla", ["AAPL", "TSLA"]),
        ("$NVDA looks hot", ["NVDA"]),
        ("what is a stop loss?", []),
        ("I think AI is cool", []),
    ])
    def test_symbols(self, text, expected):
        assert loki_brain.detect_symbols(text) == expected


class TestIntents:
    def test_greeting_thanks_help_identity(self):
        assert loki_brain.answer("hey", "Sam")["intent"] == "greeting"
        assert "Sam" in loki_brain.answer("hello", "Sam")["text"]
        assert loki_brain.answer("thanks!")["intent"] == "thanks"
        assert "ticker" in loki_brain.answer("what can you do?")["text"]
        assert loki_brain.answer("who are you?")["intent"] == "identity"

    def test_glossary_answers_in_plain_english(self):
        reply = loki_brain.answer("what is a stop loss?")
        assert reply["intent"] == "glossary" and "exit price" in reply["text"]
        assert "Average True Range" in loki_brain.answer("explain ATR")["text"]
        assert "peak" in loki_brain.answer("what does drawdown mean")["text"]

    def test_track_record_and_how_it_works_use_the_shipped_report(self):
        record = loki_brain.answer("how did the AI do historically?")
        assert record["intent"] == "track_record" and "2023" in record["text"] and "a year" in record["text"]
        how = loki_brain.answer("how does the AI learn from mistakes?")
        assert how["intent"] == "how_ai" and "200-day" in how["text"]

    def test_orders_fall_through_to_the_refusal_path(self):
        assert loki_brain.answer("buy 10 BTC now") is None
        assert client.post("/api/copilot", json={"message": "buy 10 BTC now"}).json()["intent"] == "action"

    def test_unknown_chatter_falls_back(self):
        assert loki_brain.answer("the weather is purple and my cat sings") is None


@pytest.mark.brain_data
class TestLiveReads:
    def test_symbol_read_explains_every_check(self, monkeypatch):
        monkeypatch.setattr(loki_brain, "_ai_read", fake_read(allowed=False))
        monkeypatch.setattr(loki_brain, "_universal", lambda: {})
        reply = loki_brain.answer("should I buy SPY?", "Sam")
        assert reply["intent"] == "symbol" and reply["symbols"] == ["SPY"]
        text = reply["text"]
        assert "can't tell you what to do" in text
        assert "WAIT" in text and "below its 200-day average" in text and "52%" in text
        assert "never places orders" in text

    def test_buy_setup_reports_size_and_exit_rule(self, monkeypatch):
        monkeypatch.setattr(loki_brain, "_ai_read", fake_read(allowed=True))
        text = loki_brain.answer("what about QQQ?")["text"]
        assert "BUY setup" in text and "100% of a paper account" in text and "200-day" in text

    def test_market_overview_and_unreachable_feeds(self, monkeypatch):
        rows = [{"ok": True, "symbol": "SPY", "label": "S&P 500", "price": 700.0, "change_pct": -1.2},
                {"ok": True, "symbol": "^VIX", "label": "VIX (fear gauge)", "price": 27.0, "change_pct": 9.0}]
        monkeypatch.setattr(loki_brain, "_quotes", lambda symbols: rows)
        text = loki_brain.answer("how's the market today?")["text"]
        assert "S&P 500 700.00 (-1.2%)" in text and "Fear is elevated" in text
        monkeypatch.setattr(loki_brain, "_quotes", lambda symbols: [])
        assert "aren't answering" in loki_brain.answer("how's the market today?")["text"]

    def test_both_chats_use_the_brain(self, monkeypatch):
        monkeypatch.setattr(loki_brain, "_ai_read", fake_read(allowed=False))
        copilot = client.post("/api/copilot", json={"message": "what does the AI think of NVDA?"}).json()
        assert copilot["intent"] == "brain:symbol" and "NVDA" in copilot["text"]
        room = TestClient(app)
        room.post("/api/ai/chat/access", json={"name": "Sam", "code": ""})
        reply = room.post("/api/ai/chat/message", json={"text": "what is a stop loss?"}).json()
        assert "exit price" in reply["text"]


def test_portfolio_question_uses_the_shipped_record():
    reply = loki_brain.answer("what is the portfolio AI?")
    assert reply["intent"] == "portfolio" and "21 markets" in reply["text"] and "a year" in reply["text"]


@pytest.mark.brain_data
def test_portfolio_answer_lists_current_holdings(monkeypatch):
    monkeypatch.setattr(loki_brain, "_portfolio", lambda: {"as_of": "2026-11-06", "cash": 0.6, "positions": [
        {"symbol": "SPY", "weight": 0.07}, {"symbol": "BTC-USD", "weight": 0.0}]})
    text = loki_brain.answer("what is the AI holding right now?")["text"]
    assert "SPY 7.0%" in text and "60% in cash" in text


def test_workspace_routes_portfolio_ai_questions_to_the_brain():
    reply = client.post("/api/copilot", json={"message": "What is the Portfolio AI holding?"}).json()
    assert reply["intent"] == "brain:portfolio"
    mine = client.post("/api/copilot", json={"message": "how is my portfolio doing?"}).json()
    assert not mine["intent"].startswith("brain:")
