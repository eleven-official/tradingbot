"""Tests for leakage-aware validation and replay input guards."""
import asyncio

import numpy as np
import pandas as pd
import pytest
from datetime import datetime
from types import SimpleNamespace

from core_engine.historical_replay import HistoricalReplayEngine
from core_engine.walk_forward import PurgedWalkForwardValidator
from core_engine.strategy_validator import PerformanceStats, StatisticalValidator, SCIPY_AVAILABLE
from core_engine.academic_strategies import StrategySignal
from core_engine.execution_cost_model import (
    Order, OrderSide, OrderType, RealisticExecutionSimulator, TransactionCostModel,
)
from core_engine.research_harness import ResearchHarness


def sample_data(n=120):
    index = pd.date_range("2024-01-01", periods=n, freq="D")
    close = np.linspace(100.0, 150.0, n)
    return pd.DataFrame({
        "open": close,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "volume": 1000.0,
    }, index=index)


def test_purged_walk_forward_has_gap_and_future_only_test_windows():
    validator = PurgedWalkForwardValidator(n_splits=3, test_size=20, gap=5, min_train_size=30)
    folds = list(validator.split(100))
    assert len(folds) == 3
    for fold in folds:
        assert fold.train_end + 5 == fold.test_start
        assert fold.train_end <= fold.test_start


def test_walk_forward_evaluation_reports_out_of_sample_robustness():
    validator = PurgedWalkForwardValidator(n_splits=3, test_size=20, gap=2, min_train_size=20)
    report = validator.evaluate(
        sample_data(90),
        lambda train, test, fold: {"total_return": 0.02 if fold != 1 else -0.01, "sharpe_ratio": 0.5},
    )
    assert report.robust is False
    assert "too few positive out-of-sample folds" in report.rejection_reasons
    assert report.summary["positive_return_fraction"] == pytest.approx(2 / 3)


def test_replay_rejects_missing_columns_and_non_monotonic_data():
    engine = HistoricalReplayEngine({})
    with pytest.raises(ValueError, match="missing columns"):
        asyncio.run(engine.replay(sample_data(10).drop(columns=["volume"]), "momentum", "BTCUSDT"))
    reversed_data = sample_data(10).iloc[::-1]
    with pytest.raises(ValueError, match="sorted"):
        asyncio.run(engine.replay(reversed_data, "momentum", "BTCUSDT"))


def test_replay_executes_signal_on_next_bar_open_not_signal_close():
    data = sample_data(6)
    data["open"] = [100, 100, 200, 200, 200, 200]
    data["close"] = [100, 100, 200, 200, 200, 200]
    engine = HistoricalReplayEngine({"initial_balance": 100000.0})

    class FakeStrategy:
        params = {"lookback_period": 1}
        def generate_signals(self, frame):
            return [StrategySignal("BTCUSDT", "BUY", 1.0, 100.0, 1.0, 1000.0, 1.0, datetime.now())]

    engine.strategy_library.get_strategy = lambda _name: FakeStrategy()
    result = asyncio.run(engine.replay(data, "fake", "BTCUSDT"))
    assert result.trades
    assert result.trades[0].entry_price > 150.0


def test_performance_stats_use_compounded_annualization_and_annualized_sortino():
    returns = pd.Series([0.01, -0.005, 0.01, 0.0] * 30)
    metrics = PerformanceStats(returns).calculate_metrics()
    assert metrics["annualized_return"] > returns.mean() * 252
    assert np.isfinite(metrics["sortino_ratio"])


def test_execution_simulation_is_reproducible_and_stressable():
    order = Order("BTCUSDT", OrderSide.BUY, OrderType.MARKET, 1.0)
    market = {"close": 100.0, "volume": 10000.0, "volatility": 0.02}
    normal = RealisticExecutionSimulator(TransactionCostModel(random_seed=7))
    repeat = RealisticExecutionSimulator(TransactionCostModel(random_seed=7))
    stressed = RealisticExecutionSimulator(TransactionCostModel(random_seed=7, stress_multiplier=3.0))
    first = normal.simulate_execution(order, market)
    second = repeat.simulate_execution(order, market)
    harsh = stressed.simulate_execution(order, market)
    assert first.fill_price == second.fill_price
    assert harsh.slippage_bps > first.slippage_bps


def test_execution_simulation_rejects_invalid_quote():
    order = Order("BTCUSDT", OrderSide.BUY, OrderType.MARKET, 1.0)
    with pytest.raises(ValueError, match="positive market price"):
        RealisticExecutionSimulator().simulate_execution(order, {"close": 0.0})


def test_research_harness_records_trials_compares_baseline_and_runs_stress():
    harness = ResearchHarness("sample-data-v1", random_seed=11)
    harness.record_trial("momentum", "params-a", "first candidate")
    assert harness.trial_ledger()[0]["data_id"] == "sample-data-v1"
    prices = pd.Series([100, 101, 100, 103], index=pd.date_range("2026-01-01", periods=4))
    baseline = harness.baseline_returns(prices)
    comparison = harness.compare_to_baseline(baseline, baseline)
    assert comparison["excess_total_return"] == pytest.approx(0.0)
    scenarios = harness.run_cost_stress(lambda multiplier, seed: {"multiplier": multiplier, "seed": seed})
    assert [scenario.multiplier for scenario in scenarios] == [1.0, 1.5, 2.0, 3.0]


@pytest.mark.skipif(not SCIPY_AVAILABLE, reason="scipy is optional")
def test_outperformance_uses_paired_observations():
    strategy = pd.Series([0.01, 0.02, -0.01, 0.03])
    benchmark = pd.Series([0.005, 0.01, -0.005, 0.01])
    result = StatisticalValidator().test_outperformance(strategy, benchmark)
    assert "t_test" in result
    assert np.isfinite(result["t_test"]["statistic"])
