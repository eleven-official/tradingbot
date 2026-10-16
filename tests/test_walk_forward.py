"""Tests for leakage-aware validation and replay input guards."""
import asyncio
import unittest

import numpy as np
import pandas as pd
from datetime import datetime

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


class WalkForwardTests(unittest.TestCase):
    def test_purged_walk_forward_has_gap_and_future_only_test_windows(self):
        validator = PurgedWalkForwardValidator(n_splits=3, test_size=20, gap=5, min_train_size=30)
        folds = list(validator.split(100))
        self.assertEqual(len(folds), 3)
        for fold in folds:
            self.assertEqual(fold.train_end + 5, fold.test_start)
            self.assertLessEqual(fold.train_end, fold.test_start)


    def test_walk_forward_evaluation_reports_out_of_sample_robustness(self):
        validator = PurgedWalkForwardValidator(n_splits=3, test_size=20, gap=2, min_train_size=20)
        report = validator.evaluate(
            sample_data(90),
            lambda train, test, fold: {"total_return": 0.02 if fold != 1 else -0.01, "sharpe_ratio": 0.5},
        )
        self.assertFalse(report.robust)
        self.assertIn("too few positive out-of-sample folds", report.rejection_reasons)
        self.assertAlmostEqual(report.summary["positive_return_fraction"], 2 / 3)


    def test_replay_rejects_missing_columns_and_non_monotonic_data(self):
        engine = HistoricalReplayEngine({})
        with self.assertRaisesRegex(ValueError, "missing columns"):
            asyncio.run(engine.replay(sample_data(10).drop(columns=["volume"]), "momentum", "BTCUSDT"))
        reversed_data = sample_data(10).iloc[::-1]
        with self.assertRaisesRegex(ValueError, "sorted"):
            asyncio.run(engine.replay(reversed_data, "momentum", "BTCUSDT"))


    def test_replay_executes_signal_on_next_bar_open_not_signal_close(self):
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
        self.assertTrue(result.trades)
        self.assertGreater(result.trades[0].entry_price, 150.0)


    def test_performance_stats_use_compounded_annualization_and_annualized_sortino(self):
        returns = pd.Series([0.01, -0.005, 0.01, 0.0] * 30)
        metrics = PerformanceStats(returns).calculate_metrics()
        self.assertGreater(metrics["annualized_return"], returns.mean() * 252)
        self.assertTrue(np.isfinite(metrics["sortino_ratio"]))


    def test_execution_simulation_is_reproducible_and_stressable(self):
        order = Order("BTCUSDT", OrderSide.BUY, OrderType.MARKET, 1.0)
        market = {"close": 100.0, "volume": 10000.0, "volatility": 0.02}
        normal = RealisticExecutionSimulator(TransactionCostModel(random_seed=7))
        repeat = RealisticExecutionSimulator(TransactionCostModel(random_seed=7))
        stressed = RealisticExecutionSimulator(TransactionCostModel(random_seed=7, stress_multiplier=3.0))
        first = normal.simulate_execution(order, market)
        second = repeat.simulate_execution(order, market)
        harsh = stressed.simulate_execution(order, market)
        self.assertEqual(first.fill_price, second.fill_price)
        self.assertGreater(harsh.slippage_bps, first.slippage_bps)


    def test_execution_simulation_rejects_invalid_quote(self):
        order = Order("BTCUSDT", OrderSide.BUY, OrderType.MARKET, 1.0)
        with self.assertRaisesRegex(ValueError, "positive market price"):
            RealisticExecutionSimulator().simulate_execution(order, {"close": 0.0})


    def test_research_harness_records_trials_compares_baseline_and_runs_stress(self):
        harness = ResearchHarness("sample-data-v1", random_seed=11)
        harness.record_trial("momentum", "params-a", "first candidate")
        self.assertEqual(harness.trial_ledger()[0]["data_id"], "sample-data-v1")
        prices = pd.Series([100, 101, 100, 103], index=pd.date_range("2026-01-01", periods=4))
        baseline = harness.baseline_returns(prices)
        comparison = harness.compare_to_baseline(baseline, baseline)
        self.assertAlmostEqual(comparison["excess_total_return"], 0.0)
        scenarios = harness.run_cost_stress(lambda multiplier, seed: {"multiplier": multiplier, "seed": seed})
        self.assertEqual([scenario.multiplier for scenario in scenarios], [1.0, 1.5, 2.0, 3.0])


    @unittest.skipUnless(SCIPY_AVAILABLE, "scipy is optional")
    def test_outperformance_uses_paired_observations(self):
        strategy = pd.Series([0.01, 0.02, -0.01, 0.03])
        benchmark = pd.Series([0.005, 0.01, -0.005, 0.01])
        result = StatisticalValidator().test_outperformance(strategy, benchmark)
        self.assertIn("t_test", result)
        self.assertTrue(np.isfinite(result["t_test"]["statistic"]))

