"""Regression tests of research integrity, not evidence of trading edge."""
from copy import deepcopy
import hashlib
import json

import pytest

from core.fusion import paper_models, paper_research, paper_rules
from core.strategy_lab import validate_bars
from test_paper_models import historical_fixture


@pytest.fixture(scope="module")
def baseline():
    rows = historical_fixture(5)
    report = paper_models.train_instrument(rows, "SPY", 5, source={"kind": "synthetic"})
    return rows, report


def test_ineligible_positive_result_never_bypasses_gates():
    trial = {"rule": "trend_50_200", "eligible": False,
             "stress": {"net_return": 1.0}, "closed_trades": 1}
    assert paper_research.choose([trial]) is None
    assert paper_research.choose([]) is None


def test_cash_fallback_is_valid_and_never_fabricates_profit(baseline, monkeypatch):
    rows, base = baseline
    monkeypatch.setattr(paper_research, "choose", lambda trials: None)
    report = paper_research.compare(base, rows)
    assert report["comparison"]["selection"] == "cash"
    assert report["artifact"]["threshold"] is None
    paper_rules.validate_artifact(report["artifact"])
    assert report["test"]["closed_trades"] == 0
    assert report["test"]["net_return"] == 0
    assert report["test"]["win_rate"] is None
    assert report["cost_stress"]["net_return"] == 0
    assert not paper_rules.decision(report["artifact"], validate_bars(rows))["enter"]


def test_later_prices_cannot_change_validation_choice(baseline):
    rows, base = baseline
    first = paper_research.compare(base, rows)
    changed = deepcopy(rows)
    for row in changed:
        if row["timestamp"] >= base["test"]["start"]:
            for field in ("open", "high", "low", "close"):
                row[field] *= 1.5
    altered_base = deepcopy(base)
    altered_base["data_sha256"] = hashlib.sha256(json.dumps(
        changed, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    second = paper_research.compare(altered_base, changed)
    assert first["artifact"] == second["artifact"]
    assert first["validation"] == second["validation"]


def test_rule_features_are_causal(baseline):
    rows, _ = baseline
    rule = paper_rules.RULES[0]
    bars = validate_bars(rows)
    assert paper_rules.signal_series(bars, rule)[:301] == paper_rules.signal_series(bars[:301], rule)


def test_old_bypass_report_cannot_authorize_execution():
    rule = paper_rules.RULES[0]
    artifact = {**paper_rules.frozen_rule(rule), "threshold": 1.0}
    report = {"artifact": artifact, "validation": {"trials": [
        {"rule": rule.name, "eligible": False, "stress": {"net_return": 0.1}, "closed_trades": 2}
    ]}}
    with pytest.raises(ValueError, match="did not pass validation"):
        paper_research.validate_execution_report(report)
    report["artifact"]["threshold"] = None
    paper_research.validate_execution_report(report)
