"""The Proof Engine: plain English in, falsification battery out, no promises.

Every test here pins honesty, not vibes: unknown words are surfaced, rules
are spelled out before any replay, verdicts are deterministic on the same
inputs, and rejection reasons are listed rather than hidden.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import loki.api.binance_market_data as binance_market_data
import loki.api.proof_engine as proof_engine
import loki.api.server as server
from loki.api.proof_engine import ProofError

client = TestClient(server.app)


def breakout_candles(count=600):
    """Staircase series with repeated volume-confirmed breakouts.

    Deterministic and synthetic: the purpose is a rule family that fires
    often enough for both windows to speak, then dies at 3x costs — which
    is exactly the result the report should state, no more.
    """
    rows = []
    price = 100.0
    for index in range(count):
        phase = index % 15
        if phase == 13:
            entry_open = price + 0.2
            rows.append(
                {
                    "time": 1_700_000_000.0 + index * 3600,
                    "open": entry_open,
                    "high": entry_open + 2.8,
                    "low": entry_open - 0.1,
                    "close": entry_open + 2.5,
                    "volume": 300.0,
                }
            )
            price = entry_open + 2.5
        else:
            rows.append(
                {
                    "time": 1_700_000_000.0 + index * 3600,
                    "open": price,
                    "high": price + 0.1,
                    "low": price - 0.1,
                    "close": price,
                    "volume": 100.0,
                }
            )
    return rows


def flat_candles(count=400):
    return [
        {
            "time": 1_700_000_000.0 + i * 3600,
            "open": 100.0,
            "high": 100.05,
            "low": 99.95,
            "close": 100.0,
            "volume": 100.0,
        }
        for i in range(count)
    ]


def compile_probe():
    return proof_engine.compile_spec(
        "test momentum breakouts with macd confirmation and short bursts, "
        "strict drawdown limit of 25%"
    )


def test_compile_maps_the_family_and_surfaces_what_it_will_not_model():
    spec = compile_probe()
    assert spec["family"] == "trend_following"  # "momentum" leads the word map
    assert spec["family_name"] == "EMA trend continuation"
    assert spec["declared_drawdown_limit"] == 25.0
    assert "short selling — this replay is long-only" in spec["not_modelled"]
    assert any("MACD" in item for item in spec["not_modelled"])
    assert "deterministic keyword classification" in spec["compiler"]


def test_compile_writes_the_rules_out_before_anything_runs():
    spec = compile_probe()
    assert "next candle open" in spec["entry_rule"]
    assert "1.5 ATR" in spec["exit_rule"] and "2-to-1" in spec["exit_rule"]
    assert "fixed-percent risk" in spec["sizing_rule"]
    spec_bare = proof_engine.compile_spec("a plain breakout idea")
    assert "declared_drawdown_limit" not in spec_bare


def test_gibberish_descriptions_fail_with_a_readable_how_to():
    with pytest.raises(ProofError) as thrown:
        proof_engine.compile_spec("make me rich by friday")
    message = str(thrown.value)
    assert "momentum / trend" in message and "pullback" in message
    with pytest.raises(ProofError, match="Describe the idea"):
        proof_engine.compile_spec("   ")
    with pytest.raises(ProofError, match="2000"):
        proof_engine.compile_spec("breakout " + "x" * 2100)


def test_battery_reruns_the_same_fixed_rules_at_higher_costs():
    runs = proof_engine.run_battery(breakout_candles(), "breakout", 10_000.0, 1.0, 20)
    assert [run["run"] for run in runs] == ["base", "harsher", "harshest"]
    fees = [run["fee_bps"] for run in runs]
    slippage = [run["slippage_bps"] for run in runs]
    assert fees == [10.0, 20.0, 30.0]
    assert slippage == [5.0, 10.0, 15.0]
    base_holdout = runs[0]["holdout"]
    assert base_holdout["trade_count"] >= 3  # the staircase pays out enough triggers


def test_candle_level_report_rejects_the_cost_frangible_idea_and_pins_every_find():
    report = proof_engine.safe_assess(
        breakout_candles(),
        "test momentum breakouts with macd confirmation and short bursts, "
        "strict drawdown limit of 25%",
        symbol="BTCUSDT",
        interval="1h",
    )
    statuses = {check["check"]: check["status"] for check in report["checks"]}
    assert statuses["holdout_sample_size"] == "pass"
    assert statuses["after_cost_edge"] == "pass"
    assert statuses["cost_robustness"] == "fail"  # expectancy flips at 3x costs
    assert statuses["declared_drawdown_respected"] == "pass"
    assert report["verdict"]["status"] == "rejected"
    assert any(
        "dies with costs" in reason or "fees" in reason.lower()
        for reason in report["verdict"]["reasons"]
    )
    roles = {reviewer["role"] for reviewer in report["reviewers"]}
    assert {"Quant reviewer", "Risk reviewer", "Execution reviewer", "Panel"} <= roles
    panel = next(r for r in report["reviewers"] if r["role"] == "Panel")
    assert panel["verdict"] == "fail"


def test_report_is_reproducible_and_sensitive_to_its_words():
    same = proof_engine.safe_assess(
        breakout_candles(),
        "test momentum breakouts with macd confirmation and short bursts",
        symbol="BTCUSDT",
        interval="1h",
    )["fingerprint"]["value"]
    repeated = proof_engine.safe_assess(
        breakout_candles(),
        "test momentum breakouts with macd confirmation and short bursts",
        symbol="BTCUSDT",
        interval="1h",
    )["fingerprint"]["value"]
    different_words = proof_engine.safe_assess(
        breakout_candles(),
        "test volume-confirmed breakouts",
        symbol="BTCUSDT",
        interval="1h",
    )["fingerprint"]["value"]
    assert same == repeated
    assert same != different_words
    thinner = proof_engine.safe_assess(
        breakout_candles()[:300],
        "test momentum breakouts with macd confirmation and short bursts",
        symbol="BTCUSDT",
        interval="1h",
    )["fingerprint"]["value"]
    assert thinner != same


def test_silent_market_reports_insufficient_evidence_not_a_number():
    report = proof_engine.safe_assess(
        flat_candles(),
        "hold until a small dip then watch the reclaim of the fast line",
        interval="1h",
    )
    assert report["verdict"]["status"] == "insufficient evidence"
    statuses = {check["check"]: check["status"] for check in report["checks"]}
    assert statuses["holdout_sample_size"] == "insufficient"
    for reviewer in report["reviewers"]:
        assert reviewer["verdict"] == "watch"
        if reviewer["role"] != "Panel":
            assert "may be unusable" in reviewer["reason"]


def test_verdict_band_is_total_over_the_check_sets():
    checks = [
        {"check": "a", "status": "pass", "detail": "1"},
        {"check": "b", "status": "watch", "detail": "2"},
    ]
    assert proof_engine.verdict_for(checks)["status"].startswith("tested-supported")
    fail = [
        {"check": "a", "status": "pass", "detail": "1"},
        {"check": "b", "status": "fail", "detail": "the edge dies"},
    ]
    verdict = proof_engine.verdict_for(fail)
    assert verdict["status"] == "rejected"
    assert "the edge dies" in verdict["reasons"][0]
    assert proof_engine.verdict_for([])["status"] == "insufficient evidence"


def test_wording_never_promises_income():
    report = proof_engine.safe_assess(
        breakout_candles(),
        "test momentum breakouts with macd confirmation and short bursts",
        interval="1h",
    )
    blob = (report["verdict"]["headline"] + " " + report["disclaimer"]).lower()
    assert "not advice" in blob
    assert "does not promise" in blob or "never promises income" in blob or "no income" in blob
    joined = " ".join(report["limitations"]).lower()
    assert "not forecasts" in joined
    assert "does not repeat on command" in joined


def test_api_accepts_a_description_and_returns_the_report(monkeypatch):
    monkeypatch.setattr(
        binance_market_data,
        "get_binance_spot_history",
        lambda symbol, interval, limit: breakout_candles(min(limit, 600)),
    )
    response = client.post(
        "/api/proof/assess",
        json={
            "description": "test momentum breakouts with macd confirmation and short bursts",
            "symbol": "BTCUSDT",
            "interval": "1h",
            "bars": 600,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "evidence-report"
    assert body["engine"] == "loki-proof-engine"
    assert body["verdict"]["status"] in {
        "rejected",
        "insufficient evidence",
        "tested-supported (paper research, not advice)",
    }
    assert body["spec"]["family"] in proof_engine.__dict__["_FAMILY_WORDS"].keys()
    assert body["bar_count"] == 600


def test_api_surfaces_compilation_and_feed_errors_honestly(monkeypatch):
    response = client.post("/api/proof/assess", json={"description": "make me rich by friday"})
    assert response.status_code == 422
    assert "momentum / trend" in response.json()["detail"]

    def unavailable(*args, **kwargs):
        raise binance_market_data.MarketDataError("public market data unavailable")

    monkeypatch.setattr(binance_market_data, "get_binance_spot_history", unavailable)
    response = client.post("/api/proof/assess", json={"description": "breakout idea"})
    assert response.status_code == 502
    assert response.json()["detail"] == "public market data unavailable"


def test_history_shorter_the_replay_minimum_is_a_readable_error(monkeypatch):
    monkeypatch.setattr(
        binance_market_data,
        "get_binance_spot_history",
        lambda *args: breakout_candles(40),
    )
    response = client.post("/api/proof/assess", json={"description": "breakout idea", "bars": 600})
    assert response.status_code == 422
    assert "candles" in response.json()["detail"]
