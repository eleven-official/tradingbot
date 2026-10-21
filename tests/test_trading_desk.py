"""Trading desk: five deterministic agents, hard risk rules, honest abstains.

Every unit matches the published words on the panel: fixed weights,
renormalized whenever an agent abstains, a hold when nobody sees data, and
hard vetoes in code. The endpoint must never place an order itself — the
trace arrives from public data, execution is the browser's click alone.
"""

import re
from pathlib import Path

import pytest
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


# --------------------------------------------------------------------------
# live evidence for the agent council
# --------------------------------------------------------------------------
from datetime import datetime, timedelta, timezone  # noqa: E402 - evidence helpers

EVIDENCE_START = datetime(2026, 10, 21, 15, 0, tzinfo=timezone.utc)


def _fake_bars(count: int, base: float = 100.0) -> list:
    """Clean ascending OHLCV rows in the council's exact bar contract."""
    rows = []
    for index in range(count):
        open_ = base + 0.1 * index
        rows.append(
            {
                "timestamp": (EVIDENCE_START + timedelta(minutes=5 * index)).isoformat(),
                "open": open_,
                "high": open_ + 1.0,
                "low": open_ - 0.25,
                "close": open_ + 0.4,
                "volume": 1000.0 + index,
            }
        )
    return rows


class TestBarRow:
    def test_valid_rows_pass_and_keep_the_contract_shape(self):
        row = module._bar_row(EVIDENCE_START.isoformat(), 10.0, 11.0, 9.5, 10.4, 500)
        assert row == {
            "timestamp": EVIDENCE_START.isoformat(),
            "open": 10.0,
            "high": 11.0,
            "low": 9.5,
            "close": 10.4,
            "volume": 500.0,
        }

    def test_inconsistent_candles_are_dropped_not_kept(self):
        assert module._bar_row(EVIDENCE_START.isoformat(), 10.0, 9.0, 9.5, 10.4, 500) is None

    def test_junk_values_are_dropped(self):
        assert module._bar_row(EVIDENCE_START.isoformat(), "n/a", 11.0, 9.5, 10.4, 500) is None

    def test_zero_prices_and_missing_volume_are_handled(self):
        assert module._bar_row(EVIDENCE_START.isoformat(), 0.0, 1.0, 0.5, 0.9, None) is None


class TestEvidenceEndpoint:
    def test_evidence_requires_the_access_door(self):
        fresh = TestClient(app)
        answer = fresh.post("/api/desk/evidence", json={"symbol": "AAPL"})
        assert answer.status_code == 403

    def test_bad_symbols_answer_the_human_422(self):
        gate()
        answer = client.post("/api/desk/evidence", json={"symbol": "A B C"})
        assert answer.status_code == 422

    def test_evidence_returns_bars_and_the_desk_read_from_one_fetch(self, monkeypatch):
        gate()
        fake = _fake_bars(70)
        monkeypatch.setattr(module, "_yahoo_bars", lambda symbol: list(fake))
        monkeypatch.setattr(module, "news_agent", lambda symbol: dict(NEWS_OK))
        monkeypatch.setattr(module, "fundamentals_agent", lambda symbol: dict(FUND_OK_CHEAP))

        answer = client.post("/api/desk/evidence", json={"symbol": "aapl"})
        assert answer.status_code == 200
        evidence = answer.json()
        assert evidence["mode"] == "desk-evidence"
        assert evidence["status"] == "ok"
        assert evidence["symbol"] == "AAPL"
        assert evidence["bars"] == fake
        assert "Yahoo Finance public chart" in evidence["bars_source"]
        assert evidence["periods_per_year"] == module.PERIODS_PER_YEAR_EQUITY
        # the technical read used the SAME bars, so its last price is the last close
        assert evidence["technical"]["status"] == "ok"
        assert abs(evidence["technical"]["facts"]["last"] - (fake[-1]["open"] + 0.4)) < 1e-9
        assert evidence["news"]["status"] == "ok"
        assert "never advice" in evidence["note"]

    def test_crypto_path_uses_the_crypto_clock(self, monkeypatch):
        gate()
        fake = _fake_bars(80)
        monkeypatch.setattr(module, "_binance_bars", lambda symbol: list(fake))
        answer = client.post("/api/desk/evidence", json={"symbol": "BTC/USDT"})
        assert answer.status_code == 200
        evidence = answer.json()
        assert evidence["periods_per_year"] == module.PERIODS_PER_YEAR_CRYPTO
        assert "Binance Spot public klines" in evidence["bars_source"]
        # no quarterly reports on crypto rails, exactly as published
        assert evidence["fundamentals"]["status"] == "abstain"

    def test_insufficient_bars_abstains_inside_a_200(self, monkeypatch):
        gate()
        monkeypatch.setattr(module, "news_agent", lambda symbol: dict(NEWS_OK))
        monkeypatch.setattr(module, "fundamentals_agent", lambda symbol: dict(FUND_ABSTAIN))

        def only_three(symbol):
            raise module.MarketFeedError("only 3 usable 5-minute bars right now — the council needs at least 61 clean bars")

        monkeypatch.setattr(module, "_yahoo_bars", only_three)
        answer = client.post("/api/desk/evidence", json={"symbol": "AAPL"})
        assert answer.status_code == 200
        evidence = answer.json()
        assert evidence["status"] == "abstain"
        assert "bars" not in evidence
        assert "only 3" in evidence["error"]
        assert "invented" in evidence["note"]
        assert evidence["technical"]["status"] == "abstain"

    def test_council_engine_reviews_the_public_bar_shape_offline(self):
        # The whole point of the upgrade, pinned: the desk's public bars are
        # shaped exactly like the council's dataset evidence — 61+ rows slot
        # straight into the deterministic role pipeline with no spare glue.
        bars = _fake_bars(90)
        answer = client.post(
            "/api/fusion/council",
            json={"bars": bars, "symbol": "FAKE/USDT", "config": {"periods_per_year": module.PERIODS_PER_YEAR_EQUITY}},
        )
        assert answer.status_code == 200
        report = answer.json()
        assert report["engine"] == "deterministic_role_pipeline"
        assert report["as_of"]
        assert report["director"]["decision"] in ("paper_proposal", "wait")
        assert [analyst["role"] for analyst in report["analysts"]]
        assert report["risk_checks"]


class TestCouncilPanelWiring:
    def test_index_wires_the_live_evidence_panel_before_the_bars_review(self):
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        for needed in ("live-evidence-symbol", "live-evidence-run", "live-evidence-message", "live-evidence-strip"):
            assert needed in html, f"index.html is missing {needed}"
        live_marker = html.index("LIVE EVIDENCE / ONE FETCH")
        reviewers_marker = html.index("RESEARCH / SIGNAL / RISK / EXECUTION")
        miro_marker = html.index("NATIVE MIROFISH CODE")
        assert miro_marker < live_marker < reviewers_marker

    def test_workspace_carries_the_live_evidence_path(self):
        js = (ROOT / "static" / "js" / "workspace.js").read_text(encoding="utf-8")
        for needed in (
            "runLiveEvidence",
            "renderEvidenceStrip",
            "/api/desk/evidence",
            "live-evidence-run",
            "periods_per_year:liveEvidence.periods_per_year",
        ):
            assert needed in js, f"workspace.js is missing {needed}"


# --------------------------------------------------------------------------
# features round two: watchlist sweep + council second opinion
# --------------------------------------------------------------------------
class TestSweepEndpoint:
    def test_sweep_requires_the_access_door(self):
        fresh = TestClient(app)
        answer = fresh.post("/api/desk/sweep", json={"symbols": ["AAPL"]})
        assert answer.status_code == 403

    def test_empty_watchlist_is_a_422(self):
        gate()
        answer = client.post("/api/desk/sweep", json={"symbols": []})
        assert answer.status_code == 422

    def test_seven_symbols_is_a_422(self):
        gate()
        answer = client.post("/api/desk/sweep", json={"symbols": ["AAPL", "MSFT", "KO", "PEP", "TSLA", "XOM", "JNJ"]})
        assert answer.status_code == 422

    def test_extra_fields_are_refused(self):
        gate()
        answer = client.post("/api/desk/sweep", json={"symbols": ["AAPL"], "side": "buy"})
        assert answer.status_code == 422

    def test_unreadable_symbols_become_honest_abstain_rows(self):
        gate()
        answer = client.post("/api/desk/sweep", json={"symbols": ["NOT A SYMBOL"]})
        assert answer.status_code == 200
        rows = answer.json()["rows"]
        assert len(rows) == 1
        assert rows[0]["status"] == "abstain"
        assert rows[0]["symbol"] == "NOT A SYMBOL"
        assert rows[0]["error"]

    def test_duplicates_are_skipped_and_said_so(self, monkeypatch):
        gate()
        monkeypatch.setattr(module, "_yahoo_bars", lambda symbol: list(_fake_bars(70)))
        monkeypatch.setattr(module, "news_agent", lambda symbol: dict(NEWS_OK))
        monkeypatch.setattr(module, "fundamentals_agent", lambda symbol: dict(FUND_OK_CHEAP))
        answer = client.post("/api/desk/sweep", json={"symbols": ["AAPL", "aapl"]})
        assert answer.status_code == 200
        rows = answer.json()["rows"]
        assert [row["status"] for row in rows] == ["ok", "skipped"]
        assert "once" in rows[1]["reason"]

    def test_rows_are_independent_when_one_feed_explodes(self, monkeypatch):
        gate()
        monkeypatch.setattr(module, "_yahoo_bars", lambda symbol: list(_fake_bars(70)))
        monkeypatch.setattr(module, "fundamentals_agent", lambda symbol: dict(FUND_OK_CHEAP))

        def exploding_news(symbol):
            if symbol == "MSFT":
                raise RuntimeError("feed exploded")
            return dict(NEWS_OK)

        monkeypatch.setattr(module, "news_agent", exploding_news)
        answer = client.post("/api/desk/sweep", json={"symbols": ["AAPL", "MSFT"]})
        assert answer.status_code == 200
        rows = answer.json()["rows"]
        assert rows[0]["status"] == "ok"
        assert rows[0]["symbol"] == "AAPL"
        assert rows[1]["status"] == "abstain"
        assert "feed exploded" in rows[1]["error"]

    def test_two_ok_rows_carry_proposals_with_the_same_gates(self, monkeypatch):
        gate()
        monkeypatch.setattr(module, "_yahoo_bars", lambda symbol: list(_fake_bars(70)))
        monkeypatch.setattr(module, "news_agent", lambda symbol: dict(NEWS_OK))
        monkeypatch.setattr(module, "fundamentals_agent", lambda symbol: dict(FUND_OK_CHEAP))
        answer = client.post("/api/desk/sweep", json={"symbols": ["AAPL", "MSFT"]})
        rows = answer.json()["rows"]
        for row in rows:
            assert row["status"] == "ok"
            assert set(row["agents"]) == {"news", "technical", "fundamentals"}
            assert row["proposal"]["side"] in ("buy", "sell", "hold")
            assert "approved" in row["verdict"]

    def test_the_note_says_what_a_sweep_is_not(self):
        gate()
        answer = client.post("/api/desk/sweep", json={"symbols": ["NOT A SYMBOL"]})
        assert answer.status_code == 200
        assert "never places an order" in answer.json()["note"]


class TestStrategistMatrix:
    """The published formula pinned across a grid — renormalization included."""

    @staticmethod
    def _agent(defn):
        if defn is None:
            return {"agent": "news", "status": "abstain", "score": None}
        status, score = defn
        return {"agent": "news", "status": status, "score": score}

    @pytest.mark.parametrize(
        "news_def,tech_def,fund_def",
        [
            (("ok", 0.9), ("ok", 0.3), ("ok", 0.1)),
            (("ok", -0.4), ("ok", -0.8), ("ok", -0.3)),
            (("ok", 0.0), ("ok", 0.0), ("ok", 0.0)),
            (("ok", 0.5), ("ok", 0.05), None),
            (("ok", 0.9), None, ("ok", -0.1)),
            (None, ("ok", 0.7), ("ok", 0.5)),
            (("ok", 0.1), ("ok", 0.9), None),
            (("abstain", None), ("ok", -0.6), ("ok", -0.2)),
            (("ok", 1.0), ("ok", 1.0), ("ok", 1.0)),
            (("ok", -1.0), ("ok", -1.0), ("ok", -1.0)),
        ],
    )
    def test_side_and_score_follow_the_published_formula(self, news_def, tech_def, fund_def):
        news = self._agent(news_def)
        tech = self._agent(tech_def)
        fund = self._agent(fund_def)
        # the test computes the expectation independently, from the base weights
        votes = {"news": news["score"], "technical": tech["score"], "fundamentals": fund["score"]}
        weights = module.AGENT_WEIGHTS
        present = {name: value for name, value in votes.items() if isinstance(value, (int, float))}
        expected_total = sum(weights[name] for name in present)
        expected_composite = module._clamp(
            sum(weights[name] * value for name, value in present.items()) / expected_total
        )
        expected_side = (
            "buy" if expected_composite >= module.BUY_THRESHOLD else
            "sell" if expected_composite <= module.SELL_THRESHOLD else
            "hold"
        )

        proposal = module.strategist(news, tech, fund)
        assert proposal["score"] == pytest.approx(round(expected_composite, 3), abs=1e-9)
        assert proposal["side"] == expected_side
        assert sum(proposal["weights_used"].values()) == pytest.approx(1.0, abs=1e-12)
        if expected_side == "hold":
            assert proposal["status"] == "hold"
        else:
            assert proposal["status"] == "ok"

    def test_every_agent_abstaining_stands_down(self):
        abstain = self._agent(None)
        proposal = module.strategist(abstain, abstain, abstain)
        assert proposal["status"] == "stand_down"
        assert proposal["side"] == "hold"
        assert proposal["score"] is None
        assert "stands down" in " ".join(proposal["reasons"])


class TestBarsFetchers:
    """Both public bar feeders, pinned offline against synthetic responses."""

    @staticmethod
    def _chart_payload(count, drop_close_at=None, invert_at=None):
        stamps, opens, highs, lows, closes, volumes = [], [], [], [], [], []
        for index in range(count):
            stamps.append(1_760_000_000 + 300 * index)
            opens.append(100.0 + index)
            highs.append(101.0 + index)
            lows.append(99.0 + index)
            closes.append(100.0 + index)
            volumes.append(1000 + index)
        if drop_close_at is not None:
            closes[drop_close_at] = None
        if invert_at is not None:
            highs[invert_at] = 0.5  # a high below open/close is not a candle
        return {
            "chart": {
                "result": [
                    {
                        "timestamp": stamps,
                        "indicators": {"quote": [{"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes}]},
                    }
                ]
            }
        }

    def test_yahoo_bars_drop_junk_rows_and_keep_order(self, monkeypatch):
        payload = self._chart_payload(70, drop_close_at=1, invert_at=3)
        monkeypatch.setattr(module, "_http_json", lambda url: payload)
        assert len(module._yahoo_bars("AAPL")) == 68
        # clear-eyed about what was offered: 68 usable bars of 70

    def test_yahoo_bars_refuse_a_window_thin_for_the_council(self, monkeypatch):
        payload = self._chart_payload(40)
        monkeypatch.setattr(module, "_http_json", lambda url: payload)
        with pytest.raises(module.MarketFeedError, match="council needs"):
            module._yahoo_bars("AAPL")

    def test_yahoo_bars_cap_at_four_hundred_and_convert_the_clock(self, monkeypatch):
        payload = self._chart_payload(430)
        monkeypatch.setattr(module, "_http_json", lambda url: payload)
        bars = module._yahoo_bars("AAPL")
        assert len(bars) == module.EVIDENCE_BARS_MAX
        stamps = [row["timestamp"] for row in bars]
        assert stamps == sorted(stamps) and len(set(stamps)) == len(stamps)
        assert stamps[0].endswith("+00:00")  # UTC, ISO 8601

    def test_yahoo_bars_missing_volume_becomes_zero(self, monkeypatch):
        payload = self._chart_payload(70)
        payload["chart"]["result"][0]["indicators"]["quote"][0]["volume"] = [None] * 70
        monkeypatch.setattr(module, "_http_json", lambda url: payload)
        bars = module._yahoo_bars("AAPL")
        assert all(row["volume"] == 0.0 for row in bars)

    def test_yahoo_bars_malformed_payload_is_an_honest_feed_error(self, monkeypatch):
        monkeypatch.setattr(module, "_http_json", lambda url: {"chart": {"result": []}})
        with pytest.raises(module.MarketFeedError, match="no usable public bars"):
            module._yahoo_bars("AAPL")

    def test_binance_bars_parse_kline_rows_and_skip_junk(self, monkeypatch):
        import loki.api.binance_market_data as binance

        valid = [
            [1_760_000_000_000 + 300_000 * i, "100", "101", "99", "100.5", "1000"] for i in range(63)
        ]
        klines = valid[:1] + [["not even a row"]] + valid[1:2] + [[1_760_000_030_000, "oops", "101", "99", "100.5", "1000"]] + valid[2:]
        monkeypatch.setattr(binance, "_fetch_json", lambda path, params: klines)
        bars = module._binance_bars("BTC/USDT")
        assert len(bars) == 63
        stamps = [row["timestamp"] for row in bars]
        assert stamps == sorted(stamps) and len(set(stamps)) == len(stamps)

    def test_binance_adapter_error_is_rewrapped_for_the_desk(self, monkeypatch):
        import loki.api.binance_market_data as binance

        def rate_limited(path, params):
            raise binance.MarketDataError("Binance rate limited this IP")

        monkeypatch.setattr(binance, "_fetch_json", rate_limited)
        with pytest.raises(module.MarketFeedError) as caught:
            module._binance_bars("BTC/USDT")
        assert "rate limited" in str(caught.value)

    def test_binance_short_window_refused_like_yahoo(self, monkeypatch):
        import loki.api.binance_market_data as binance

        monkeypatch.setattr(binance, "_fetch_json", lambda path, params: [[1_760_000_000_000, "1", "2", "1", "2", "5"]])
        with pytest.raises(module.MarketFeedError, match="council needs"):
            module._binance_bars("BTC/USDT")

    def test_evidence_bars_are_ascending_and_unique_end_to_end(self, monkeypatch):
        gate()
        monkeypatch.setattr(module, "_yahoo_bars", lambda symbol: list(_fake_bars(65)))
        monkeypatch.setattr(module, "news_agent", lambda symbol: dict(NEWS_OK))
        monkeypatch.setattr(module, "fundamentals_agent", lambda symbol: dict(FUND_ABSTAIN))
        evidence = client.post("/api/desk/evidence", json={"symbol": "AAPL"}).json()
        stamps = [row["timestamp"] for row in evidence["bars"]]
        assert stamps == sorted(stamps) and len(set(stamps)) == len(stamps)

    def test_council_rejects_a_sixty_bar_window_but_takes_sixty_one(self):
        for count, expected_status in ((60, 422), (61, 200)):
            answer = client.post(
                "/api/fusion/council",
                json={"bars": _fake_bars(count), "symbol": "FAKE/USDT", "config": {"periods_per_year": module.PERIODS_PER_YEAR_EQUITY}},
            )
            assert answer.status_code == expected_status


class TestDeskCouncilOpinionWiring:
    def test_index_wires_both_new_panels_inside_the_desk_before_the_game(self):
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        for needed in (
            "desk-council-run",
            "desk-council-message",
            "desk-council",
            "desk-sweep-form",
            "desk-sweep-symbols",
            "desk-sweep-run",
            "desk-sweep-message",
            "desk-sweep-results",
        ):
            assert needed in html, f"index.html is missing {needed}"
        assert html.index("desk-council-run") < html.index('id="game"')
        assert html.index("desk-sweep-run") < html.index('id="game"')

    def test_desk_script_carries_both_features(self):
        js = (ROOT / "static" / "js" / "desk.js").read_text(encoding="utf-8")
        for needed in (
            "runSweep",
            "askCouncil",
            "/api/desk/sweep",
            "/api/desk/evidence",
            "/api/fusion/council",
            "desk-sweep-run",
            "desk-council-run",
        ):
            assert needed in js, f"desk.js is missing {needed}"
