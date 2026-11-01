from copy import deepcopy

import pytest

from core.fusion import paper_evidence, paper_models


@pytest.fixture
def candidate():
    return {"artifact": {"version": paper_models.MODEL_VERSION, "threshold": 0.6},
            "test": {"closed_trades": 20, "net_return": 0.01, "expectancy_usd": 5.0, "max_drawdown": 0.01},
            "cost_stress": {"multiple": 2, "net_return": 0.005}}


def test_paper_candidate_never_claims_future_profit(candidate):
    result = paper_evidence.assess(candidate)
    assert result["entry_allowed"] and result["can_start"]
    assert result["future_profitability_proven"] is False


@pytest.mark.parametrize("field,value", [("net_return", -0.01), ("net_return", float("nan")),
    ("expectancy_usd", 0), ("closed_trades", 1), ("closed_trades", True), ("max_drawdown", 0.10)])
def test_bad_later_performance_blocks_entry(candidate, field, value):
    candidate["test"][field] = value
    result = paper_evidence.assess(candidate)
    assert not result["entry_allowed"] and not result["can_start"]
    assert result["reasons"]


def test_missing_or_negative_cost_stress_blocks_entry(candidate):
    negative = deepcopy(candidate)
    negative["cost_stress"]["net_return"] = -0.001
    assert not paper_evidence.assess(negative)["can_start"]
    del candidate["cost_stress"]
    assert not paper_evidence.assess(candidate)["can_start"]


def test_cash_monitoring_does_not_manufacture_profit(candidate):
    candidate["artifact"]["threshold"] = None
    candidate["test"] = {}
    candidate.pop("cost_stress")
    result = paper_evidence.assess(candidate)
    assert result["can_start"] and not result["entry_allowed"]
    assert result["cash_only"] and result["status"] == "cash_only"
