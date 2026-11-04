"""The Proof Engine: plain English in, falsification battery out, no promises.

Every test here pins honesty, not vibes: unknown words are surfaced, rules
are spelled out before any replay, verdicts are deterministic on the same
inputs, declared values in words actually control the replay, fingerprints
depend on the full dataset, and rejection reasons are listed rather than
hidden. The adapter's pagination and the abuse protection are exercised
directly instead of being trusted.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import loki.api.binance_market_data as binance_market_data
import loki.api.proof_engine as proof_engine
import loki.api.server as server
from loki.api.proof_engine import ProofError

client = TestClient(server.app)


@pytest.fixture(autouse=True)
def _fresh_proof_limiter():
    """Route tests share one identity, so each test starts with a clean quota."""
    proof_engine.reset_rate_limiter()
    yield
    proof_engine.reset_rate_limiter()


def breakout_candles(count=800):
    """Staircase series with repeated volume-confirmed breakouts.

    Deterministic and synthetic: on 800 bars the holdout window carries
    16 closed trades for the trend family — enough to cross the 15-trade
    bar a supported verdict demands — and the edge still dies at 3x costs,
    which is exactly what the report should state, no more.
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
    # Nothing declared -> the un-declared knobs are named, never silently defaulted.
    joined = "; ".join(spec_bare["not_modelled"])
    assert "any drawdown limit" in joined
    assert "per-trade risk" in joined and "none was declared" in joined
    assert "starting capital" in joined


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
    runs = proof_engine.run_battery(breakout_candles(), "trend_following", 10_000.0, 1.0, 20)
    assert [run["run"] for run in runs] == ["base", "harsher", "harshest"]
    fees = [run["fee_bps"] for run in runs]
    slippage = [run["slippage_bps"] for run in runs]
    assert fees == [10.0, 20.0, 30.0]
    assert slippage == [5.0, 10.0, 15.0]
    base_holdout = runs[0]["holdout"]
    assert base_holdout["trade_count"] >= 12  # the staircase pays out enough triggers


def test_holdout_sample_crosses_the_fifteen_trade_supported_bar():
    """800 staircase bars -> 16 holdout trades, so sample-size passes the new bar."""
    report = proof_engine.safe_assess(
        breakout_candles(800),
        "test momentum breakouts with macd confirmation and short bursts",
        symbol="BTCUSDT",
        interval="1h",
    )
    statuses = {check["check"]: check["status"] for check in report["checks"]}
    assert statuses["holdout_sample_size"] == "pass"
    trades = next(c for c in report["checks"] if c["check"] == "holdout_sample_size")
    assert "closed holdout trades" in trades["detail"]
    # A 700-bar series lands at 14 trades: readable, but flagged as watch.
    thinner = proof_engine.safe_assess(
        breakout_candles(700),
        "test momentum breakouts with macd confirmation and short bursts",
        symbol="BTCUSDT",
        interval="1h",
    )
    thin_status = next(c for c in thinner["checks"] if c["check"] == "holdout_sample_size")
    assert thin_status["status"] == "watch"
    assert "enough to read, not enough" in thin_status["detail"]


def test_candle_level_report_rejects_the_cost_frangible_idea_and_pins_every_find():
    report = proof_engine.safe_assess(
        breakout_candles(800),
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


def test_report_is_reproducible_and_sensitive_to_every_input():
    description = "test momentum breakouts with macd confirmation and short bursts"
    same = proof_engine.safe_assess(
        breakout_candles(800), description, symbol="BTCUSDT", interval="1h"
    )["fingerprint"]["value"]
    repeated = proof_engine.safe_assess(
        breakout_candles(800), description, symbol="BTCUSDT", interval="1h"
    )["fingerprint"]["value"]
    assert same == repeated
    different_words = proof_engine.safe_assess(
        breakout_candles(800), "test volume-confirmed breakouts", symbol="BTCUSDT", interval="1h"
    )["fingerprint"]["value"]
    assert different_words != same
    different_symbol = proof_engine.safe_assess(
        breakout_candles(800), description, symbol="ETHUSDT", interval="1h"
    )["fingerprint"]["value"]
    assert different_symbol != same
    different_interval = proof_engine.safe_assess(
        breakout_candles(800), description, symbol="BTCUSDT", interval="4h"
    )["fingerprint"]["value"]
    assert different_interval != same
    different_declared = proof_engine.safe_assess(
        breakout_candles(800), description + ", risk 2% per trade", symbol="BTCUSDT", interval="1h"
    )["fingerprint"]["value"]
    assert different_declared != same


def test_fingerprint_marks_two_datasets_apart_even_with_matching_endpoints():
    """Same length, same window endpoints, one minted verb magnet changed in a series."""
    rows = breakout_candles(800)
    report_a = proof_engine.safe_assess(
        rows, "test momentum breakouts", symbol="BTCUSDT", interval="1h"
    )
    report_b = proof_engine.safe_assess(
        rows, "test momentum breakouts", symbol="BTCUSDT", interval="1h"
    )
    assert report_a["fingerprint"]["value"] == report_b["fingerprint"]["value"]

    mutated = [dict(row) for row in rows]
    mutated[400]["close"] += 0.05  # mid-gap valid: open <= close <= high holds
    report_c = proof_engine.safe_assess(
        mutated, "test momentum breakouts", symbol="BTCUSDT", interval="1h"
    )
    assert report_c["fingerprint"]["value"] != report_a["fingerprint"]["value"]

    stamp_a = report_a["repro"]
    stamp_c = report_c["repro"]
    assert stamp_a["dataset_rows"] == stamp_c["dataset_rows"]
    assert stamp_a["first_time"] == stamp_c["first_time"]
    assert stamp_a["last_time"] == stamp_c["last_time"]
    assert stamp_a["dataset_sha256"] != stamp_c["dataset_sha256"]


def test_dataset_digest_is_canonical_over_every_candle_value():
    rows = breakout_candles(600)
    digest_a = proof_engine.dataset_digest(rows)
    assert digest_a == proof_engine.dataset_digest(rows)
    same_values_different_float_type = proof_engine.dataset_digest(
        [{**row, "volume": float(row["volume"])} for row in rows]
    )
    assert same_values_different_float_type == digest_a
    for field in ("open", "high", "low", "close", "volume", "time"):
        mutated = [dict(row) for row in rows]
        mutated[17][field] += 0.003 / 10 if field != "time" else 3600.0
        # Allow the candle-sanity fields to stay valid by nudging within tolerance
        if field in ("high",):
            mutated[17][field] += 0.001
        assert proof_engine.dataset_digest(mutated) != digest_a, field


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
    watch_only = [
        {"check": "a", "status": "pass", "detail": "1"},
        {"check": "b", "status": "watch", "detail": "2"},
    ]
    verdict = proof_engine.verdict_for(watch_only)
    assert verdict["status"].startswith("provisional support")
    assert "provisional" in verdict["headline"]
    all_pass = [
        {"check": "a", "status": "pass", "detail": "1"},
        {"check": "b", "status": "pass", "detail": "2"},
    ]
    verdict = proof_engine.verdict_for(all_pass)
    assert verdict["status"].startswith("tested-supported")
    assert "not independent validation" in verdict["headline"]
    fail = [
        {"check": "a", "status": "pass", "detail": "1"},
        {"check": "b", "status": "fail", "detail": "the edge dies"},
    ]
    verdict = proof_engine.verdict_for(fail)
    assert verdict["status"] == "rejected"
    assert "the edge dies" in verdict["reasons"][0]
    assert proof_engine.verdict_for([])["status"] == "insufficient evidence"
    insufficient = [{"check": "a", "status": "insufficient", "detail": "too few"}]
    assert proof_engine.verdict_for(insufficient)["status"] == "insufficient evidence"


def test_declared_risk_and_capital_in_words_control_the_replay():
    report = proof_engine.safe_assess(
        breakout_candles(800),
        "momentum idea, risk 2% per trade, starting capital 25000 dollars",
        symbol="BTCUSDT",
        interval="1h",
    )
    spec = report["spec"]
    assert spec["declared_risk_percent"] == 2.0
    assert spec["applied_risk_percent"] == 2.0
    assert spec["declared_capital"] == 25000.0
    assert spec["applied_starting_capital"] == 25000.0
    # Once a value is declared it is modelled, so the un-declared note points elsewhere.
    joined = "; ".join(spec["not_modelled"])
    assert "per-trade risk" not in joined


def test_dollar_sign_capital_declared_with_commas_parses():
    spec = proof_engine.compile_spec("momentum idea with $12,345 starting capital")
    assert spec["declared_capital"] == 12345.0


def test_declared_risk_is_clamped_into_the_replay_band_and_named():
    report = proof_engine.safe_assess(
        breakout_candles(800),
        "momentum idea, risk 12% per trade",
        symbol="BTCUSDT",
        interval="1h",
    )
    spec = report["spec"]
    assert spec["declared_risk_percent"] == 12.0
    assert spec["applied_risk_percent"] == 5.0  # the band ceiling
    joined = "; ".join(spec["not_modelled"])
    assert "0.05%-5%" in joined
    below_floor = proof_engine.safe_assess(
        breakout_candles(800), "momentum idea, risk 0.01%", interval="1h"
    )
    assert below_floor["spec"]["applied_risk_percent"] == 0.05


def test_kwargs_override_words_and_defaults_fill_the_silence():
    rows = breakout_candles(800)
    explicit = proof_engine.safe_assess(
        rows,
        "momentum idea, risk 2%, capital 50000 dollars",
        symbol="BTCUSDT",
        interval="1h",
        risk_percent=0.5,
        starting_capital=1234.0,
    )
    assert explicit["spec"]["applied_risk_percent"] == 0.5
    assert explicit["spec"]["applied_starting_capital"] == 1234.0

    defaults = proof_engine.safe_assess(rows, "momentum idea", symbol="BTCUSDT", interval="1h")
    spec = defaults["spec"]
    assert spec["applied_risk_percent"] == 1.0
    assert spec["applied_starting_capital"] == 10_000.0
    joined = "; ".join(spec["not_modelled"])
    assert "none was declared in words" in joined


def test_wording_never_promises_income():
    report = proof_engine.safe_assess(
        breakout_candles(800),
        "test momentum breakouts with macd confirmation and short bursts",
        interval="1h",
    )
    blob = (report["verdict"]["headline"] + " " + report["disclaimer"]).lower()
    assert "not advice" in blob
    assert "does not promise" in blob or "never promises income" in blob or "no income" in blob
    joined = " ".join(report["limitations"]).lower()
    assert "not forecasts" in joined
    assert "does not repeat on command" in joined


def test_rate_limiter_is_a_windowed_quota_per_identity():
    limiter = proof_engine
    limiter.reset_rate_limiter()
    base_now = 1000.0
    assert [limiter.rate_limited("key-a", now=base_now + i * 0.1) for i in range(8)] == [False] * 8
    assert limiter.rate_limited("key-a", now=base_now + 0.9) is True
    assert limiter.rate_limited("key-b", now=base_now + 0.9) is False
    assert limiter.rate_limited("key-a", now=base_now + 59.9) is True
    assert limiter.rate_limited("key-a", now=base_now + 60.1) is False
    limiter.reset_rate_limiter()
    assert limiter.rate_limited("key-a", now=base_now) is False


def test_api_accepts_a_description_and_returns_the_report(monkeypatch):
    monkeypatch.setattr(
        binance_market_data,
        "get_binance_spot_history",
        lambda symbol, interval, limit: breakout_candles(min(limit, 800)),
    )
    response = client.post(
        "/api/proof/assess",
        json={
            "description": "test momentum breakouts with macd confirmation and short bursts",
            "symbol": "BTCUSDT",
            "interval": "1h",
            "bars": 800,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "evidence-report"
    assert body["engine"] == "loki-proof-engine"
    assert body["verdict"]["status"] in {
        "rejected",
        "insufficient evidence",
        "provisional support (paper research, not advice)",
        "tested-supported (paper research, not advice)",
    }
    assert body["spec"]["family"] in proof_engine.__dict__["_FAMILY_WORDS"].keys()
    assert body["bar_count"] == 800
    assert body["fingerprint"]["algorithm"] == "sha256"
    assert "full canonical candle values" in body["fingerprint"]["inputs"]


def test_api_surfaces_compilation_and_feed_errors_honestly(monkeypatch):
    response = client.post("/api/proof/assess", json={"description": "make me rich by friday"})
    assert response.status_code == 422
    assert "momentum / trend" in response.json()["detail"]


def test_a_bad_description_is_a_text_error_even_when_the_feed_is_down(monkeypatch):
    def unavailable(*args, **kwargs):
        raise binance_market_data.MarketDataError("public market data unavailable")

    monkeypatch.setattr(binance_market_data, "get_binance_spot_history", unavailable)
    response = client.post("/api/proof/assess", json={"description": "make me rich by friday"})
    assert response.status_code == 422
    assert "momentum / trend" in response.json()["detail"]


def test_api_maps_market_data_outage_to_gateway_error(monkeypatch):
    def unavailable(*args, **kwargs):
        raise binance_market_data.MarketDataError("public market data unavailable")

    monkeypatch.setattr(binance_market_data, "get_binance_spot_history", unavailable)
    response = client.post("/api/proof/assess", json={"description": "breakout idea"})
    assert response.status_code == 502
    assert response.json()["detail"] == "public market data unavailable"


def test_api_rate_limits_the_ninth_run_in_a_window(monkeypatch):
    monkeypatch.setattr(
        binance_market_data,
        "get_binance_spot_history",
        lambda *args: breakout_candles(min(args[-1], 300)),
    )
    for _ in range(8):
        response = client.post(
            "/api/proof/assess",
            json={
                "description": "momentum idea",
                "symbol": "BTCUSDT",
                "interval": "1h",
                "bars": 300,
            },
        )
        assert response.status_code == 200
    ninth = client.post(
        "/api/proof/assess",
        json={"description": "momentum idea", "symbol": "BTCUSDT", "interval": "1h", "bars": 300},
    )
    assert ninth.status_code == 429
    assert "rate limited" in ninth.json()["detail"]


def test_api_times_out_a_stalled_feed_with_a_readable_error(monkeypatch):
    import threading

    stuck = threading.Event()

    def hang(*args, **kwargs):
        stuck.wait(2.0)
        return breakout_candles(300)

    monkeypatch.setattr(binance_market_data, "get_binance_spot_history", hang)
    monkeypatch.setattr(server, "_PROOF_RUN_TIMEOUT_SECONDS", 0.05)
    response = client.post(
        "/api/proof/assess",
        json={"description": "momentum idea", "symbol": "BTCUSDT", "interval": "1h", "bars": 300},
    )
    stuck.set()
    assert response.status_code == 503
    assert "timed out" in response.json()["detail"]


def test_api_accepts_the_three_thousand_candle_paginated_depth(monkeypatch):
    monkeypatch.setattr(
        binance_market_data,
        "get_binance_spot_history",
        lambda symbol, interval, limit: breakout_candles(min(limit, 3000)),
    )
    response = client.post(
        "/api/proof/assess",
        json={"description": "momentum idea", "symbol": "BTCUSDT", "interval": "1h", "bars": 3000},
    )
    assert response.status_code == 200
    assert response.json()["bar_count"] == 3000


def test_history_shorter_the_replay_minimum_is_a_readable_error(monkeypatch):
    monkeypatch.setattr(
        binance_market_data,
        "get_binance_spot_history",
        lambda *args: breakout_candles(40),
    )
    response = client.post("/api/proof/assess", json={"description": "breakout idea", "bars": 600})
    assert response.status_code == 422
    assert "candles" in response.json()["detail"]


def _paged_stamps(count):
    return [1_700_000_000_000 + i * 3_600_000 for i in range(count)]


def _row_for(stamp_ms):
    price = 100.0 + (stamp_ms - 1_700_000_000_000) / 3_600_000 * 0.01
    return [stamp_ms, price, price + 0.1, price - 0.1, price + 0.05, 1.0, stamp_ms + 3_599_000]


def _serve_newest(stamps, limit, end_ms):
    """Provider window: all stamps <=endTime inclusive, newest-first slice kept ascending."""
    capped = [stamp for stamp in stamps if end_ms is None or stamp <= end_ms]
    return [_row_for(stamp) for stamp in capped[-limit:]]


def test_history_pagination_stitches_ascending_across_three_pages():
    calls = []
    stamps = _paged_stamps(2300)
    request = 2500

    def provider(_path, params):
        calls.append(dict(params))
        return _serve_newest(stamps, int(params["limit"]), params.get("endTime"))

    previous = binance_market_data._fetch_json
    binance_market_data._fetch_json = provider
    try:
        candles = binance_market_data.get_binance_spot_history("BTCUSDT", "1h", request)
    finally:
        binance_market_data._fetch_json = previous

    assert len(candles) == 2300  # every stamp in the table, nothing padded
    assert len(calls) == 3  # 1000 + 1000 + 300 with the limit shrinking
    times = [candle["time"] for candle in candles]
    assert times == sorted(times)
    assert all(b - a == 3_600.0 for a, b in zip(times, times[1:]))
    assert calls[0].get("endTime") is None
    passed_ends = [call.get("endTime") for call in calls[1:]]
    assert all(end is not None for end in passed_ends)
    assert passed_ends == sorted(passed_ends, reverse=True)


def test_history_within_one_page_makes_exactly_one_request():
    calls = []
    stamps = _paged_stamps(2300)

    def provider(_path, params):
        calls.append(dict(params))
        return _serve_newest(stamps, int(params["limit"]), params.get("endTime"))

    previous = binance_market_data._fetch_json
    binance_market_data._fetch_json = provider
    try:
        candles = binance_market_data.get_binance_spot_history("BTCUSDT", "1h", 120)
    finally:
        binance_market_data._fetch_json = previous
    assert len(candles) == 120
    assert len(calls) == 1


def test_history_refuses_depth_outside_the_bounded_band():
    for bad in (119, 3001, 0, -5, 12.5, True, "600"):
        with pytest.raises(binance_market_data.MarketDataError):
            binance_market_data.get_binance_spot_history("BTCUSDT", "1h", bad)  # type: ignore[arg-type]


def test_history_deduplicates_a_candle_delivered_on_two_pages():
    """A provider that overlaps page boundaries must not yield a repeated candle."""
    calls = []
    stamps = _paged_stamps(2100)
    request = 2000

    def overlapping_provider(_path, params):
        calls.append(dict(params))
        limit = int(params["limit"])
        end = params.get("endTime")
        capped = [stamp for stamp in stamps if end is None or stamp <= end]
        window = capped[-limit:]
        if end is not None:
            # Misbehaving feed: the candle one step past the boundary (the page
            # stroke already collected) is served again.
            window = sorted(window + [end + 1])
        return [_row_for(stamp) for stamp in window]

    previous = binance_market_data._fetch_json
    binance_market_data._fetch_json = overlapping_provider
    try:
        candles = binance_market_data.get_binance_spot_history("BTCUSDT", "1h", request)
    finally:
        binance_market_data._fetch_json = previous

    times = [candle["time"] for candle in candles]
    assert times == sorted(times)
    assert len(times) == len(set(times))  # the boundary duplicate is served exactly once
    assert len(candles) == request  # the demanded depth, not the misbehaved wider body
    stamp_set = {float(stamp) / 1000 for stamp in stamps}
    assert set(times) <= stamp_set  # nothing invented beyond the table


def test_history_refuses_a_provider_that_ignores_the_time_window():
    """Same payload every time means circular paging -> refused, no infinite loop."""

    def deaf_provider(_path, params):
        stamp = 1_700_000_000_000
        price = 100.0
        return [
            [
                stamp + i * 3_600_000,
                price,
                price + 0.1,
                price - 0.1,
                price + 0.05,
                1.0,
                stamp + i * 3_600_000 + 3_599_000,
            ]
            for i in range(10)
        ]

    previous = binance_market_data._fetch_json
    binance_market_data._fetch_json = deaf_provider
    try:
        with pytest.raises(binance_market_data.MarketDataError):
            binance_market_data.get_binance_spot_history("BTCUSDT", "1h", 2500)
    finally:
        binance_market_data._fetch_json = previous


def test_history_calls_out_a_feed_that_returns_too_little():
    def skimpy(_path, params):
        return _make_two_rows()

    def _make_two_rows():
        stamp = 1_700_000_000_000
        return [[stamp, 100.0, 100.1, 99.9, 100.05, 1.0, stamp + 3_599_000]]

    previous = binance_market_data._fetch_json
    binance_market_data._fetch_json = skimpy
    try:
        with pytest.raises(binance_market_data.MarketDataError) as thrown:
            binance_market_data.get_binance_spot_history("BTCUSDT", "1h", 120)
    finally:
        binance_market_data._fetch_json = previous
    assert "too few" in str(thrown.value)


def test_ui_renders_costs_in_basis_points_not_percent():
    """Audit fix 4 contract: fee/slippage cells use the bps formatter.

    The backend ships basis points; a percent formatter reading them
    overstates costs a hundredfold. The served file must carry the
    dedicated formatter and wire it into the battery row.
    """
    js = (Path(__file__).resolve().parents[1] / "static" / "js" / "proof_engine.js").read_text(
        encoding="utf-8"
    )
    assert "function proofBps(" in js
    assert "function proofDollars(" in js
    assert "${proofBps(run.fee_bps)}" in js
    assert "${proofBps(run.slippage_bps)}" in js
    assert not any(f"proofPercent(run.{field})" in js for field in ("fee_bps", "slippage_bps"))
    # The report footer states the applied risk and capital in their own units
    assert "proofPercent(data.spec.applied_risk_percent)" in js
    assert "proofDollars(data.spec.applied_starting_capital)" in js
    # The provisional verdict band has its own tint, declared values are shown
    assert "proof-verdict-provisional" in js
    assert "declared starting capital" in js
    assert "declared per-trade risk" in js
    # The compiled-rules block tells visitors the words are editable
    assert "These compiled rules are exactly what ran" in js


def test_ui_offers_the_paginated_three_thousand_depth():
    html = (Path(__file__).resolve().parents[1] / "templates" / "index.html").read_text(
        encoding="utf-8"
    )
    bars_index = html.index('id="proof-bars"')
    select = html[html.rindex("<select", 0, bars_index) : html.index("</select>", bars_index)]
    for offered in ("600", "1000", "2000", "3000"):
        assert f'value="{offered}"' in select
    css = (Path(__file__).resolve().parents[1] / "static" / "css" / "style.css").read_text(
        encoding="utf-8"
    )
    assert ".proof-verdict-provisional" in css
