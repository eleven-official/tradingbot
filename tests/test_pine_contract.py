"""Static Pine regression contracts, NOT a TradingView compiler/runtime test.

These guard previously observed source defects and publication integrity.
TradingView compilation and Bar Replay remain separate acceptance checks.
"""

import hashlib
from html import unescape
from pathlib import Path
import re

from fastapi.testclient import TestClient

from loki.api.server import app


SOURCE = (Path(__file__).resolve().parents[1] / "templates" / "loki_nq.pine").read_text(encoding="utf-8")


def test_candle_input_does_not_pass_title_twice():
    call = SOURCE.split("paintModel = input.string(", 1)[1].split("\ntrailGlow", 1)[0]
    assert '"market", "Candle ghosting"' in call
    assert "title=" not in call


def test_cash_session_is_weekdays_in_new_york():
    assert 'sessDef + ":23456", "America/New_York"' in SOURCE
    assert "123456789" not in SOURCE


def test_training_labels_use_exact_horizon_before_append():
    assert "idx = array.size(sampleL) - horizon" in SOURCE
    assert "bar_index - array.get(sampleB, idx) == horizon" in SOURCE
    assert SOURCE.index("array.set(sampleL, idx, dir)") < SOURCE.index("array.push(sampleL, 0)")
    assert "array.shift(sampleB)" in SOURCE


def test_lorentz_distance_matches_documentation():
    assert "d += math.log(1.0 + math.abs(" in SOURCE


def test_v5_array_guards_do_not_depend_on_short_circuit():
    assert "while slot > 0\n" in SOURCE
    assert "while array.size(auditDir) > 0\n" in SOURCE
    assert "while slot > 0 and" not in SOURCE
    assert "while array.size(auditDir) > 0 and" not in SOURCE


def test_audit_caps_resolved_results_and_counts_flat_outcomes():
    assert "array.size(auditResults) > statLen" in SOURCE
    assert "array.shift(auditResults)" in SOURCE
    assert "auditW := array.sum(auditResults)" in SOURCE
    assert "if moved != 0" not in SOURCE
    assert '"Horizon hit-rate"' in SOURCE


def test_bracket_resolution_precedes_new_entry_and_excludes_entry_bar():
    assert "if bracketLive and bar_index > entryBar" in SOURCE
    assert SOURCE.index("ambiguousHit := tpHit and slHit") < SOURCE.index("entryBar := bar_index")
    assert "BOTH touched; intrabar order unknown" in SOURCE
    for handle in ("tpLine", "slLine", "enLine"):
        assert f"line.delete({handle})" in SOURCE
    assert "math.round_to_mintick" in SOURCE


def test_hud_and_levels_commit_only_at_confirmed_boundaries():
    assert "barstate.islastconfirmedhistory or (barstate.islast and barstate.isconfirmed)" in SOURCE
    assert "srClosed = barstate.isconfirmed and time_close == time_close(srTF)" in SOURCE
    assert "if srClosed and not na(srHigh)" in SOURCE
    assert "if srClosed and not na(srLow)" in SOURCE
    assert "barmerge.lookahead_on" not in SOURCE


def test_vote_shaping_inputs_and_weighted_polls_exist():
    assert 'useWeights= input.bool(true, "Closest neighbor counts double+"' in SOURCE
    assert "1.0 / (0.5 + dNei)" in SOURCE
    assert "decayHalf = input.int(90" in SOURCE
    assert "wNei *= age > 0 ? math.pow(0.5, age / decayHalf) : 1.0" in SOURCE
    assert "[closedUp, closedDown, closedWUp, closedWDn, closedD] = scoreBar()" in SOURCE
    # every recorded neighbor keeps a library index so the decay age is exact
    assert "bestI = array.new_int(knn, -1)" in SOURCE
    assert "array.set(bestI, slot, i)" in SOURCE


def test_margin_gate_blocks_tied_vote_pools():
    assert "margin = wTotal > 0 ? 100.0 * math.abs(wUpN - wDnN) / wTotal : 0.0" in SOURCE
    assert "margin >= marginMin" in SOURCE
    assert '"VOTE POOL TIED"' in SOURCE
    assert '"Margin"' in SOURCE


def test_entries_align_with_structure_and_pay_to_fade():
    assert "alignsLong  = not alignGate or structUp or conf >= confMin + ctBump" in SOURCE
    assert "alignsShort = not alignGate or structDn or conf >= confMin + ctBump" in SOURCE
    assert "ctBump    = input.float(10.0" in SOURCE
    assert "quietUntil := bar_index + coolBars" in SOURCE
    assert "cooling = bar_index < quietUntil" in SOURCE


def test_audit_reports_atr_expectancy():
    assert "array.push(auditExp, (dirF > 0 ? 1.0 : -1.0) * moved / atrSafe)" in SOURCE
    assert "expMean = array.size(auditExp) > 0 ? array.avg(auditExp) : na" in SOURCE
    assert '"Expectancy"' in SOURCE
    assert "expMean > 0 ? C_BULL : C_BEAR" in SOURCE


def test_published_source_and_hash_match_file(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setenv("LOKI_SITE_GATE", "0")
    with TestClient(app) as browser:
        response = browser.get("/indicator")
    assert response.status_code == 200
    match = re.search(r'<pre id="pine-source">(.*?)</pre>', response.text, re.S)
    assert match is not None
    assert unescape(match.group(1)) == SOURCE
    assert hashlib.sha256(SOURCE.encode()).hexdigest()[:24] in response.text
