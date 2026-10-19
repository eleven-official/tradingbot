"""Offline research regressions. Fixtures are synthetic, never profit evidence."""
import json
import math
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.strategy_lab import LabConfig, TrendParameters, _metrics, _signal, _simulate, analyze_trend, evaluate_strategy, validate_bars


def sample_bars(count=220, pattern="trend"):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    rows = []
    previous = 100.0
    for index in range(count):
        if pattern == "flat":
            close = 100.0
        elif pattern == "fall":
            close = 100.0 * 0.995 ** index
        else:
            close = 100.0 * math.exp(index * 0.001 + 0.08 * math.sin(index / 12))
        rows.append({
            "timestamp": (start + timedelta(days=index)).isoformat(),
            "open": previous, "high": max(previous, close) * 1.01,
            "low": min(previous, close) * 0.99, "close": close, "volume": 10000,
        })
        previous = close
    return rows


class StrategyLabTests(unittest.TestCase):
    def test_report_is_reproducible_and_json_safe(self):
        rows = sample_bars()
        first = evaluate_strategy(rows)
        second = evaluate_strategy(rows)
        self.assertEqual(first, second)
        json.dumps(first, allow_nan=False)
        self.assertFalse(first["live_trading_enabled"])
        self.assertIn(first["status"], ("paper_candidate", "needs_more_evidence"))
        self.assertEqual(first["trial_count"], len(first["trial_ledger"]))
        self.assertEqual(first["trial_count"], 9)
        self.assertEqual(first["summary"]["observations"], len(first["equity_curve"]))
        self.assertEqual(first["summary"]["final_capital"], first["equity_curve"][-1]["equity"])
        self.assertEqual(first["cost_stress"][0]["total_return"], first["summary"]["total_return"])

    def test_cash_and_insufficient_evidence_are_explicit(self):
        report = evaluate_strategy(sample_bars(pattern="flat"))
        self.assertEqual(report["summary"]["total_trades"], 0)
        self.assertIsNone(report["summary"]["win_rate"])
        self.assertIsNone(report["summary"]["win_rate_ci95"])
        self.assertIsNone(report["summary"]["profit_factor"])
        self.assertEqual(report["summary"]["total_return"], 0)
        self.assertTrue(all(fold["parameters"] == {"mode": "cash"} for fold in report["folds"]))
        self.assertEqual(report["status"], "needs_more_evidence")
        self.assertLess(report["benchmark"]["total_return"], 0)
        self.assertGreater(report["benchmark"]["total_fees"], 0)

    def test_execution_uses_next_open_and_completed_volume(self):
        rows = sample_bars(23)
        # Strong completed-bar uptrend creates the signal; execution gaps up.
        for index, row in enumerate(rows):
            price = 100.0 + index
            row.update(open=price, close=price, high=price + 1, low=price - 1)
        rows[20].update(open=200, close=150, high=201, low=149, volume=0)
        rows[21].update(open=150, close=150, high=151, low=149)
        bars = validate_bars(rows)
        result = _simulate(bars, 20, 22, TrendParameters(5, 20), LabConfig(), 1000)
        trade = result["trades"][0]
        self.assertEqual(trade["entry_timestamp"], bars[20].timestamp.isoformat())
        self.assertAlmostEqual(trade["entry_price"], 200.1)
        # Execution-bar total volume is future information and must not
        # suppress a fill, while previous completed-bar volume can.
        rows[19]["volume"] = 0
        guarded = _simulate(validate_bars(rows), 20, 21, TrendParameters(5, 20), LabConfig(), 1000)
        self.assertEqual(guarded["trades"], [])

    def test_both_sides_costs_and_final_liquidation_match_cash(self):
        bars = validate_bars(sample_bars(3, "flat"))
        config = LabConfig(fee_bps=10, slippage_bps=5)
        result = _simulate(bars, 1, 3, None, config, 1000, benchmark=True)
        expected = 1000 / (100 * 1.0005 * 1.001) * (100 * 0.9995) * 0.999
        self.assertAlmostEqual(result["metrics"]["final_capital"], expected)
        self.assertAlmostEqual(result["trades"][0]["pnl"], expected - 1000)
        self.assertEqual(result["trades"][0]["exit_reason"], "window_end")
        self.assertGreater(result["metrics"]["total_fees"], 1.9)
        self.assertGreater(result["metrics"]["total_slippage"], 0.9)
        stress = _simulate(bars, 1, 3, None, config, 1000, multiplier=3, benchmark=True)
        self.assertLess(stress["metrics"]["total_return"], result["metrics"]["total_return"])

    def test_drawdown_includes_initial_equity(self):
        metrics = _metrics(1000, [900, 950], [], LabConfig())
        self.assertAlmostEqual(metrics["max_drawdown"], -0.1)

    def test_complete_loss_is_json_safe(self):
        metrics = _metrics(1000, [0, 0], [], LabConfig())
        self.assertEqual(metrics["total_return"], -1)
        self.assertEqual(metrics["annualized_return"], -1)
        self.assertEqual(metrics["max_drawdown"], -1)
        json.dumps(metrics, allow_nan=False)

    def test_future_data_cannot_change_earlier_fold_selection_or_equity(self):
        rows = sample_bars(280)
        first = evaluate_strategy(rows)
        changed = [dict(row) for row in rows]
        # Changes start strictly inside the last forward window.
        cutoff = datetime.fromisoformat(first["folds"][-1]["test_start"])
        for row in changed:
            if datetime.fromisoformat(row["timestamp"]) >= cutoff:
                for key in ("open", "high", "low", "close"):
                    row[key] *= 0.5
        second = evaluate_strategy(changed)
        self.assertEqual(first["folds"][0], second["folds"][0])
        self.assertEqual(first["folds"][1], second["folds"][1])
        self.assertEqual(first["folds"][-1]["parameters"], second["folds"][-1]["parameters"])
        for left, right in zip(first["equity_curve"], second["equity_curve"]):
            if datetime.fromisoformat(left["timestamp"]) < cutoff:
                self.assertEqual(left, right)
        self.assertNotEqual(first["data_fingerprint"], second["data_fingerprint"])

    def test_fold_boundaries_have_purge_and_disjoint_forward_windows(self):
        report = evaluate_strategy(sample_bars())
        previous_end = None
        for fold in report["folds"]:
            train_end = datetime.fromisoformat(fold["train_end"])
            test_start = datetime.fromisoformat(fold["test_start"])
            test_end = datetime.fromisoformat(fold["test_end"])
            self.assertEqual((test_start - train_end).days, 2)
            if previous_end:
                self.assertGreater(test_start, previous_end)
            previous_end = test_end

    def test_win_interval_conveys_small_sample_uncertainty(self):
        metrics = _metrics(1000, [1010], [{"pnl": 10, "fees": 0, "slippage": 0}], LabConfig())
        self.assertEqual(metrics["win_rate"], 1.0)
        self.assertLess(metrics["win_rate_ci95"][0], 0.7)
        self.assertLessEqual(metrics["win_rate_ci95"][1], 1.0)

    def test_requested_win_rate_is_an_explicit_evidence_gate(self):
        report = evaluate_strategy(sample_bars())
        self.assertEqual(report["win_rate_target"], 0.7)
        observed = report["summary"]["win_rate"]
        supported = report["summary"]["win_rate_ci95"]
        self.assertEqual(report["win_rate_target_met"], observed is not None and observed >= 0.7)
        self.assertEqual(report["win_rate_target_supported"], supported is not None and supported[0] >= 0.7)
        if not report["win_rate_target_supported"]:
            self.assertEqual(report["status"], "needs_more_evidence")
            self.assertTrue(any("win rate" in reason or "win-rate" in reason for reason in report["rejection_reasons"]))

    def test_public_signal_matches_frozen_research_on_closed_candles(self):
        rows = sample_bars(70)
        parameters = TrendParameters(10, 40)
        config = LabConfig()
        signal = analyze_trend(rows, parameters, config)
        self.assertEqual(signal["target_allocation"], _signal(validate_bars(rows), len(rows), parameters, config))
        self.assertEqual(signal["timestamp"], rows[-1]["timestamp"])
        self.assertEqual(signal["latest_close"], rows[-1]["close"])
        self.assertAlmostEqual(signal["suggested_stop"], rows[-1]["close"] * 0.92)
        self.assertEqual(signal, analyze_trend(rows, {"fast": 10, "slow": 40}, {}))
        self.assertEqual(analyze_trend(rows[:20], parameters)["target_allocation"], 0)
        for invalid in ({"fast": 40, "slow": 10}, {"fast": True, "slow": 20},
                        {"fast": 10, "slow": 40, "target": 1}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                analyze_trend(rows, invalid)

    def test_malformed_input_fails_closed(self):
        for alter in (
            lambda rows: rows.reverse(),
            lambda rows: rows[1].update(timestamp=rows[0]["timestamp"]),
            lambda rows: rows[1].update(high=1),
            lambda rows: rows[1].update(close=float("nan")),
            lambda rows: rows[1].update(volume=-1),
            lambda rows: rows[1].update(close=True),
            lambda rows: rows[1].update(timestamp="not-a-date"),
        ):
            rows = sample_bars()
            alter(rows)
            with self.subTest(alter=alter), self.assertRaises(ValueError):
                evaluate_strategy(rows)
        with self.assertRaisesRegex(ValueError, "at least 161"):
            evaluate_strategy(sample_bars(100))

    def test_bad_config_rejected(self):
        for config in ({"gap_bars": 0}, {"n_splits": 1}, {"fee_bps": -1},
                       {"periods_per_year": True}, {"max_exposure": 2},
                       {"target_volatility": float("inf")}, {"guaranteed_profit": True}, {"min_win_rate": 1.1}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                evaluate_strategy(sample_bars(), config)

    def test_cli_produces_reviewable_report_and_rejects_invalid_data(self):
        script = Path(__file__).resolve().parents[1] / "run_strategy_lab.py"
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "bars.json"
            output_path = Path(directory) / "report.json"
            input_path.write_text(json.dumps(sample_bars()), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(script), str(input_path), "--output", str(output_path), "--fee-bps", "12"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(report["config"]["fee_bps"], 12)
            self.assertFalse(report["live_trading_enabled"])
            self.assertIn("Historical research cannot guarantee", result.stdout)
            overwrite = subprocess.run(
                [sys.executable, str(script), str(input_path), "--output", str(input_path)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(overwrite.returncode, 2)
            self.assertIsInstance(json.loads(input_path.read_text(encoding="utf-8")), list)
            input_path.write_text("[]", encoding="utf-8")
            failed_output = Path(directory) / "invalid-report.json"
            failed = subprocess.run(
                [sys.executable, str(script), str(input_path), "--output", str(failed_output)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(failed.returncode, 2)
            self.assertIn("Research failed", failed.stderr)
            self.assertFalse(failed_output.exists())


if __name__ == "__main__":
    unittest.main()
