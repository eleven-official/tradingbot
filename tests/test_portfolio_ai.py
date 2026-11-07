"""Portfolio AI: verified sleeves combined without leverage; live plan mirrors the replay."""

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from loki.api import ai_paper
from loki.api.server import app
from loki_v8 import portfolio_ai
from tests.test_live_engine import _tape

PARAMS = {"signal_threshold": 8.0, "sizing_mode": "vol_target", "target_vol_pct": 20.0, "take_profit_atr": 0.0,
          "stop_loss_atr": 6.0, "exit_mode": "trend", "max_hold_bars": 0,
          "factor_weights": {"trend": 0.8, "momentum": 0.05, "volume_flow": 0.05, "squeeze": 0.05, "volatility": 0.05}}


@pytest.fixture(scope="module")
def sleeves():
    return {f"S{i}": portfolio_ai.run_sleeve(_tape(900, seed=i + 3), PARAMS, f"S{i}") for i in range(5)}


def test_sleeve_exposure_matches_positions(sleeves):
    for sleeve in sleeves.values():
        assert sleeve["exposure"].between(0, 1.05).all()
        assert len(sleeve["returns"]) == len(sleeve["exposure"])
        assert sleeve["state"]["as_of"]


def test_book_never_uses_leverage(sleeves):
    book = portfolio_ai.combine(sleeves, 25.0, warmup=260)
    assert (book["scale"] <= portfolio_ai.MAX_SCALE).all()
    assert book["gross"].max() <= 1.0 + 1e-9
    alloc = portfolio_ai.allocation(sleeves, book)
    assert sum(p["weight"] for p in alloc["positions"]) <= 1.0 + 1e-9
    assert alloc["cash"] == pytest.approx(1 - alloc["gross"], abs=1e-3)


def test_diversification_smooths_returns(sleeves):
    book = portfolio_ai.combine(sleeves, 10.0, warmup=260)
    port_vol = book["base_returns"].iloc[300:].std()
    single_vol = np.mean([s["returns"].iloc[300:].std() for s in sleeves.values()])
    assert port_vol < single_vol


def test_target_selection_uses_only_dev_and_validation(sleeves):
    idx = next(iter(sleeves.values()))["returns"].index
    windows = {"development": (str(idx[100].date()), str(idx[400].date())),
               "validation": (str(idx[401].date()), str(idx[600].date()))}
    target, trials = portfolio_ai.select_target_vol(sleeves, windows)
    assert target in (10.0, 15.0, 20.0, 25.0)
    assert all("holdout" not in t for t in trials)


def test_window_stats():
    r = pd.Series([0.01, -0.005] * 100, index=pd.bdate_range("2024-01-01", periods=200))
    s = portfolio_ai.window_stats(r, "2024-01-01", "2030-01-01")
    assert s["cagr_pct"] > 0 and s["sharpe"] > 0 and s["max_dd_pct"] <= 0


def test_portfolio_endpoint_caches_and_reports(monkeypatch):
    calls = []

    def fake_plan():
        calls.append(1)
        return {"target_vol_pct": 10.0, "positions": [{"symbol": "SPY", "weight": 0.1}], "gross": 0.1, "cash": 0.9}

    monkeypatch.setattr(ai_paper, "_portfolio_plan", fake_plan)
    monkeypatch.setattr(ai_paper, "_PORTFOLIO_CACHE", {})
    client = TestClient(app)
    first = client.get("/api/fusion/ai/portfolio").json()
    client.get("/api/fusion/ai/portfolio")
    assert first["positions"][0]["symbol"] == "SPY" and len(calls) == 1
    client.get("/api/fusion/ai/portfolio?refresh=true")
    assert len(calls) == 2


def test_shipped_portfolio_block_is_verified_and_unleveraged():
    from loki_v8.train import load_report

    block = load_report()["universal"]["portfolio"]
    assert block["verified"] and block["target_vol_pct"] in (10.0, 15.0, 20.0, 25.0)
    assert block["holdout"]["sharpe"] > 0.5
    assert 0 < block["average_gross_exposure"] <= 1.0
