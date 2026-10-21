"""Trading desk: five deterministic agents, hard risk rules, honest abstains.

Every unit matches the published words on the panel: fixed weights,
renormalized whenever an agent abstains, a hold when nobody sees data, and
hard vetoes in code. The endpoint must never place an order itself — the
trace arrives from public data, execution is the browser's click alone.
"""

import re
from pathlib import Path

from fastapi.testclient import TestClient

import loki.api.trading_desk as module
from loki.api.server import app

ROOT = Path(__file__).resolve().parents[1]

client = TestClient(app)


def gate():
    opened = client.post("/api/gate", json={"code": "flathead"})
    assert opened.status_code == 200


# --------------------------------------------------------------------------
# pure units
# --------------------------------------------------------------------------
class TestLexicon:
    def test_positive_words_accumulate(self):
        assert module._lexicon_score("Nvidia beats record quarter, soars") == 1.0

    def test_negative_words_accumulate_and_clamp(self):
        assert module._lexicon_score("Lawsuit plunges amid layoffs, fraud probe") == -1.0

    def test_plain_headline_is_neutral(self):
        assert module._lexicon_score("Stock closes flat on quiet news") == 0.0

    def test_word_boundaries_keep_neighbour_words_out(self):
        # "beat" must not match "wheat"; "miss" must not match "mission".
        assert module._lexicon_score("Wheat mission continues") == 0.0


class TestTechnicals:
    def test_sma_takes_the_last_window(self):
        closes = list(range(1, 31))
        assert module.sma(closes, 25) == sum(range(6, 31)) / 25

    def test_sma_needs_enough_bars(self):
        assert module.sma([1.0, 2.0], 25) is None

    def test_rsi_rising_market_pins_hundred(self):
        closes = [float(value) for value in range(10, 40)]
        assert module.rsi14(closes) == 100.0

    def test_rsi_flat_market_reads_fifty(self):
        closes = [5.0] * 30
        assert module.rsi14(closes) == 50.0

    def test_published_score_formula(self):
        # above-average trend, confirmed slope, neutral RSI
        assert module.technical_score(110, 105, 100, 50) == 0.5
        # below-average, slope agrees, stretched RSI pulls further
        assert module.technical_score(90, 95, 100, 80) == -0.7
        # washed-out RSI bends the verdict back toward sensible
        assert module.technical_score(90, 95, 100, 20) == -0.3


# --------------------------------------------------------------------------
# agent + strategist + risk units
# --------------------------------------------------------------------------
NEWS_OK = {
    "agent": "news",
    "status": "ok",
    "score": 0.5,
    "headlines_read": 10,
    "top": [{"title": "beats record", "publisher": "Wire", "score": 0.6}],
    "method": "lexicon",
}
NEWS_ABSTAIN = {
    "agent": "news",
    "status": "abstain",
    "score": None,
    "error": "the public headlines feed answered no usable items",
}
TECH_OK_BULL = {
    "agent": "technical",
    "status": "ok",
    "score": 0.5,
    "facts": {"last": 100.0, "sma10": 99.0, "sma25": 98.0, "rsi14": 50.0},
    "bars_used": 200,
    "method": "code",
}
TECH_OK_BEAR = {
    "agent": "technical",
    "status": "ok",
    "score": -0.9,
    "facts": {"last": 90.0, "sma10": 95.0, "sma25": 98.0, "rsi14": 80.0},
    "bars_used": 200,
    "method": "code",
}
TECH_ABSTAIN = {
    "agent": "technical",
    "status": "abstain",
    "score": None,
    "error": "only 3 usable 5-minute closes right now",
}
FUND_OK_CHEAP = {
    "agent": "fundamentals",
    "status": "ok",
    "score": 0.5,
    "facts": {"trailing_pe": 10.5},
    "verdict": "cheap band",
}
FUND_ABSTAIN = {
    "agent": "fundamentals",
    "status": "abstain",
    "score": None,
    "reason": "no trailing earnings multiple",
}


class TestStrategist:
    def test_every_agent_down_stands_down(self):
        proposal = module.strategist(NEWS_ABSTAIN, TECH_ABSTAIN, FUND_ABSTAIN)
        assert proposal["side"] == "hold"
        assert proposal["qty"] == 0
        assert proposal["status"] == "stand_down"
        assert "stands down" in " ".join(proposal["reasons"])

    def test_weights_renormalize_over_the_present_agents_only(self):
        proposal = module.strategist(NEWS_OK, TECH_OK_BULL, FUND_ABSTAIN)
        # news .25 / technical .55 of the .8 present total — full precision,
        # so the renormalization visibly sums to one.
        assert abs(proposal["weights_used"]["news"] - 0.25 / 0.8) < 1e-12
        assert abs(proposal["weights_used"]["technical"] - 0.55 / 0.8) < 1e-12
        expected = (0.25 * 0.5 + 0.55 * 0.5) / 0.8
        assert abs(proposal["score"] - expected) < 1e-12

    def test_strong_bullish_composite_proposes_buy(self):
        big_tech = dict(TECH_OK_BULL, score=0.9)
        proposal = module.strategist(NEWS_OK, big_tech, FUND_OK_CHEAP)
        assert proposal["side"] == "buy"
        assert proposal["qty"] == 2  # the composite passes the strong band

    def test_bearish_composite_proposes_sell(self):
        proposal = module.strategist(NEWS_ABSTAIN, TECH_OK_BEAR, FUND_OK_CHEAP)
        assert proposal["side"] == "sell"
        assert proposal["qty"] in (1, 2)  # float edge decides the size band

    def test_mild_composite_means_hold(self):
        proposal = module.strategist(NEWS_OK, dict(TECH_OK_BULL, score=0.1), FUND_ABSTAIN)
        expected = (0.25 * 0.5 + 0.55 * 0.1) / 0.8
        assert expected < 0.25  # sanity: this sits below the buy threshold
        assert abs(proposal["score"] - expected) < 1e-12
        assert proposal["side"] == "hold"
        assert proposal["qty"] == 0


class TestRisk:
    def test_no_price_means_no_approval(self):
        proposal = module.strategist(NEWS_OK, TECH_OK_BEAR, FUND_OK_CHEAP)
        # the proposal is real but the technical log went dark: no price, no deal
        verdict = module.risk_manager(proposal, TECH_ABSTAIN)
        assert verdict["approved"] is False
        assert verdict["verdict"] == "veto"
        gates = {check["gate"]: check["passed"] for check in verdict["checks"]}
        assert gates["price_known"] is False

    def test_notional_cap_vetoes_oversized_tickets(self):
        proposal = {"side": "buy", "qty": module.DESK_QTY_MAX, "score": 0.8, "status": "ok"}
        priced = dict(TECH_OK_BULL, facts={"last": 10_000.0})
        verdict = module.risk_manager(proposal, priced)
        gates = {check["gate"]: check["passed"] for check in verdict["checks"]}
        assert gates["notional_cap"] is False
        assert verdict["approved"] is False

    def test_hold_proposals_need_no_defence(self):
        verdict = module.risk_manager(
            {"side": "hold", "qty": 0, "score": 0.1, "status": "hold"}, TECH_OK_BULL
        )
        assert verdict["verdict"] == "no_action"
        assert verdict["approved"] is False
        assert "nothing to defend" in verdict["reason"]

    def test_stand_down_is_reflected_verbatim(self):
        verdict = module.risk_manager(
            {"agent": "strategy", "status": "stand_down", "side": "hold", "qty": 0, "score": None},
            TECH_ABSTAIN,
        )
        assert verdict["verdict"] == "veto"
        assert "stood down" in verdict["reason"]

    def test_clean_bullish_proposal_is_approved(self):
        proposal = module.strategist(NEWS_OK, TECH_OK_BULL, FUND_OK_CHEAP)
        verdict = module.risk_manager(proposal, TECH_OK_BULL)
        assert verdict["approved"] is True
        assert verdict["verdict"] == "approved"
        assert all(check["passed"] for check in verdict["checks"])
        assert verdict["notional_estimate"] is not None


# --------------------------------------------------------------------------
# endpoint
# --------------------------------------------------------------------------
class TestEndpoint:
    def test_desk_requires_the_access_door(self):
        fresh = TestClient(app)
        answer = fresh.post("/api/desk/run", json={"symbol": "AAPL"})
        assert answer.status_code == 403
        assert "door" in answer.json()["detail"].lower()

    def test_bad_symbols_answer_the_human_422(self):
        gate()
        answer = client.post("/api/desk/run", json={"symbol": "AAPL DROP"})
        assert answer.status_code == 422

    def test_extra_fields_are_refused(self):
        gate()
        answer = client.post("/api/desk/run", json={"symbol": "AAPL", "qty": 100})
        assert answer.status_code == 422

    def test_happy_path_returns_the_whole_trace_and_no_order(self, monkeypatch):
        gate()
        monkeypatch.setattr(module, "news_agent", lambda symbol: dict(NEWS_OK))
        monkeypatch.setattr(module, "technical_agent", lambda symbol: dict(TECH_OK_BULL))
        monkeypatch.setattr(module, "fundamentals_agent", lambda symbol: dict(FUND_OK_CHEAP))

        def no_network(*args, **kwargs):  # pragma: no cover - must never run
            raise AssertionError("the desk endpoint must not reach the network when agents are patched")

        monkeypatch.setattr(module, "_http_json", no_network)

        answer = client.post("/api/desk/run", json={"symbol": "aapl"})
        assert answer.status_code == 200
        run = answer.json()
        assert run["mode"] == "trading-desk"
        assert run["symbol"] == "AAPL"
        assert [row["agent"] for row in run["trace"]] == [
            "news",
            "technical",
            "fundamentals",
            "strategy",
            "risk",
        ]
        assert run["proposal"]["side"] == "buy"
        assert run["verdict"]["approved"] is True
        assert "never advice" in run["note"]
        # The payload carries no order identity: nothing was executed here.
        blob = str(run).lower()
        assert "order_id" not in blob and "order id" not in blob
        # Execution channel is the browser rail; keys required; server silent.
        assert run["execution"]["requires_armed_paper_keys"] is True
        assert "rail" in run["execution"]["channel"].lower()

    def test_every_agent_down_is_an_honest_200_stand_down(self, monkeypatch):
        gate()
        monkeypatch.setattr(module, "news_agent", lambda symbol: dict(NEWS_ABSTAIN))
        monkeypatch.setattr(module, "technical_agent", lambda symbol: dict(TECH_ABSTAIN))
        monkeypatch.setattr(module, "fundamentals_agent", lambda symbol: dict(FUND_ABSTAIN))
        answer = client.post("/api/desk/run", json={"symbol": "AAPL"})
        assert answer.status_code == 200
        run = answer.json()
        risk_row = run["trace"][-1]
        assert risk_row["verdict"] == "veto"
        assert "stood down" in risk_row["reason"]
        assert run["proposal"]["side"] == "hold"


# --------------------------------------------------------------------------
# panel wiring
# --------------------------------------------------------------------------
class TestPanelWiring:
    def test_index_wires_the_desk_before_the_game_and_game_stays_last(self):
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        nav = re.findall(r'data-view="([a-z-]+)"', html)
        assert "trading-desk" in nav
        assert nav[-1] == "game"
        for needed in (
            "desk-form",
            "desk-symbol",
            "desk-run",
            "desk-status",
            "desk-pipeline",
            "desk-proposal",
            "desk-exec-wrap",
            "desk-exec",
            "desk-exec-message",
            "desk-log",
            "desk-count",
        ):
            assert needed in html, f"index.html is missing the {needed} id"

    def test_desk_script_is_included(self):
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        assert "static/js/desk.js?v={{ version }}" in html
