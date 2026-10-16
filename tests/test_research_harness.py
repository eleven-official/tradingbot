"""Tests for the reproducible strategy research helpers."""
import math
import unittest

import numpy as np
import pandas as pd

from core_engine.research_harness import ResearchHarness
from core_engine.walk_forward import PurgedWalkForwardValidator


class ResearchHarnessTests(unittest.TestCase):
    def test_folds_are_chronological_and_respect_embargo_gap(self):
        validator = PurgedWalkForwardValidator(n_splits=3, test_size=20, gap=5, min_train_size=30)
        folds = list(validator.split(100))
        self.assertEqual(len(folds), 3)
        for fold in folds:
            self.assertEqual(fold.train_end + 5, fold.test_start)
            self.assertLessEqual(fold.train_end, fold.test_start)
            self.assertLess(fold.test_start, fold.test_end)

    def test_walk_forward_uses_untouched_future_folds_and_reports_robustness(self):
        validator = PurgedWalkForwardValidator(
            n_splits=3, test_size=20, gap=2, min_train_size=20, min_positive_folds=3,
        )
        data = pd.DataFrame({"close": np.linspace(100.0, 150.0, 90)})
        report = validator.evaluate(
            data,
            lambda train, test, fold: {
                "total_return": 0.02 if fold != 1 else -0.01,
                "sharpe_ratio": 0.5,
            },
        )
        self.assertFalse(report.robust)
        self.assertIn("too few positive out-of-sample folds", report.rejection_reasons)
        self.assertTrue(math.isclose(report.summary["positive_return_fraction"], 2 / 3))

    def test_trial_ledger_tracks_dataset_and_parameter_choices(self):
        harness = ResearchHarness("sample-data-v1", random_seed=11)
        harness.record_trial("momentum", "params-a", "first candidate")
        record = harness.trial_ledger()[0]
        self.assertEqual(record["data_id"], "sample-data-v1")
        self.assertEqual(record["parameter_hash"], "params-a")

    def test_baseline_comparison_aligns_periods_and_reports_excess(self):
        index = pd.date_range("2026-01-01", periods=5)
        strategy = pd.Series([0.01, 0.0, 0.02, -0.01], index=index[1:])
        baseline = pd.Series([0.0, 0.0, 0.0, 0.0], index=index[1:])
        comparison = ResearchHarness.compare_to_baseline(strategy, baseline)
        self.assertEqual(comparison["aligned_observations"], 4)
        self.assertGreater(comparison["excess_total_return"], 0.0)

    def test_cost_stress_runs_requested_scenarios_with_fixed_seed(self):
        harness = ResearchHarness("sample-data-v1", random_seed=17)
        results = harness.run_cost_stress(
            lambda multiplier, seed: {"multiplier": multiplier, "seed": seed},
            multipliers=(1.0, 2.0, 3.0),
        )
        self.assertEqual([item.multiplier for item in results], [1.0, 2.0, 3.0])
        self.assertTrue(all(item.result["seed"] == 17 for item in results))

    def test_baseline_rejects_non_positive_prices(self):
        with self.assertRaisesRegex(ValueError, "finite and positive"):
            ResearchHarness.baseline_returns(pd.Series([100.0, 0.0, 101.0]))


    def test_baseline_returns_match_close_to_close_changes(self):
        prices = pd.Series([100.0, 110.0, 99.0])
        returns = ResearchHarness.baseline_returns(prices)
        np.testing.assert_allclose(returns.to_numpy(), [0.10, -0.10])

    def test_summary_handles_flat_series_without_infinite_ratios(self):
        metrics = ResearchHarness.summary(pd.Series([0.0, 0.0, 0.0]))
        self.assertEqual(metrics["total_return"], 0.0)
        self.assertEqual(metrics["sharpe_ratio"], 0.0)
        self.assertEqual(metrics["sortino_ratio"], 0.0)
        self.assertEqual(metrics["max_drawdown"], 0.0)
        self.assertTrue(all(math.isfinite(value) for value in metrics.values()))

    def test_summary_rejects_empty_and_non_finite_return_series(self):
        for returns in (pd.Series(dtype=float), pd.Series([float("inf")])):
            with self.subTest(returns=returns.tolist()):
                with self.assertRaisesRegex(ValueError, "finite observations"):
                    ResearchHarness.summary(returns)

    def test_harness_requires_a_dataset_identity(self):
        for data_id in ("", "  "):
            with self.subTest(data_id=data_id):
                with self.assertRaisesRegex(ValueError, "data_id is required"):
                    ResearchHarness(data_id)

    def test_cost_stress_rejects_empty_non_positive_and_non_finite_scenarios(self):
        harness = ResearchHarness("sample-data-v1")
        for multipliers in ((), (0.0,), (-1.0,), (float("nan"),)):
            with self.subTest(multipliers=multipliers):
                with self.assertRaisesRegex(ValueError, "finite and positive"):
                    harness.run_cost_stress(lambda multiplier, seed: {}, multipliers)

    def test_baseline_comparison_rejects_disjoint_observation_windows(self):
        left = pd.Series([0.01], index=["day-1"])
        right = pd.Series([0.02], index=["day-2"])
        with self.assertRaisesRegex(ValueError, "no aligned observations"):
            ResearchHarness.compare_to_baseline(left, right)

    def test_walk_forward_configuration_rejects_invalid_sizes(self):
        invalid = (
            {"n_splits": 1}, {"n_splits": 2.5}, {"test_size": 0},
            {"gap": -1}, {"min_positive_folds": 0},
            {"min_median_sharpe": float("nan")},
        )
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    PurgedWalkForwardValidator(**kwargs)

    def test_walk_forward_rejects_unsorted_input_before_splitting(self):
        validator = PurgedWalkForwardValidator(n_splits=2, test_size=10,
                                                gap=0, min_train_size=10)
        data = pd.DataFrame({"close": range(30)}, index=list(range(15, -15, -1)))
        with self.assertRaisesRegex(ValueError, "sorted chronologically"):
            validator.evaluate(data, lambda train, test, fold: {"total_return": 0.1})


if __name__ == "__main__":
    unittest.main()

