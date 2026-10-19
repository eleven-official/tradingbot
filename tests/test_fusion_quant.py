"""Mathematical and causal regressions for the local MIT research integration."""
import json
import math
import unittest
from datetime import datetime, timedelta, timezone

from core.fusion.quant import ShadowConfig, analyze_factors, evaluate_factor_panel, run_shadow_replay
from third_party.vibe_trading.indicators import compute_rsi


def sample_bars(count=240, flat=False):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    rows, previous = [], 100.0
    for index in range(count):
        close = 100.0 if flat else 100 * math.exp(.0009 * index + .06 * math.sin(index / 8))
        rows.append({"timestamp": (start + timedelta(days=index)).isoformat(),
                     "open": previous, "high": max(previous, close) * 1.007,
                     "low": min(previous, close) * .993, "close": close, "volume": 100_000.0})
        previous = close
    return rows


class VibeMathTests(unittest.TestCase):
    def test_wilder_rsi_matches_published_hand_calculation_and_preserves_warmup(self):
        close = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42,
                 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00]
        result = compute_rsi(close)
        self.assertEqual(result[:14], [None] * 14)
        self.assertAlmostEqual(result[14], 70.4641350211, places=8)
        self.assertAlmostEqual(result[15], 66.2496185536, places=8)

    def test_flat_missing_and_one_direction_rsi_are_explicit(self):
        self.assertEqual(compute_rsi([10.0] * 20), [None] * 20)
        self.assertEqual(compute_rsi(list(range(20)))[14:], [100.0] * 6)
        self.assertEqual(compute_rsi(list(range(20, 0, -1)))[14:], [0.0] * 6)
        self.assertIsNone(compute_rsi([1, 2, None, 3, 4], period=2)[3])
        with self.assertRaises(ValueError):
            compute_rsi([1, float("nan")])

    def test_factor_panel_uses_paired_ranks_and_minimum_five_assets(self):
        factors = {"2024-01-01": dict(zip("ABCDEF", [1, 1, 2, 3, 4, None])),
                   "2024-01-02": dict(zip("ABCD", [1, 2, 3, 4]))}
        returns = {"2024-01-01": dict(zip("ABCDEF", [.01, .01, .02, .03, .04, .99])),
                   "2024-01-02": dict(zip("ABCD", [.01, .02, .03, .04]))}
        result = evaluate_factor_panel(factors, returns, n_groups=5)
        self.assertEqual(result["observations"], 1)
        self.assertAlmostEqual(result["mean_ic"], 1.0)
        self.assertEqual(result["ic_series"][0]["assets"], 5)
        self.assertIsNone(result["ic_information_ratio"])
        self.assertAlmostEqual(result["group_equity"][0]["groups"]["Group_5"], 1.04)

    def test_constant_factor_is_missing_evidence_and_groups_are_not_advertised_net(self):
        factors = {"2024-01-01": dict.fromkeys("ABCDE", 1)}
        returns = {"2024-01-01": dict(zip("ABCDE", [.01, .02, .03, .04, .05]))}
        result = evaluate_factor_panel(factors, returns)
        self.assertIsNone(result["mean_ic"])
        self.assertTrue(any("gross" in item for item in result["limitations"]))

    def test_unlevered_forward_loss_cannot_be_hidden_by_group_averaging(self):
        factors = {"2024-01-01": dict(zip("ABCDE", [1, 2, 3, 4, 5]))}
        returns = {"2024-01-01": dict(zip("ABCDE", [-2, 2, .01, .02, .03]))}
        with self.assertRaises(ValueError):
            evaluate_factor_panel(factors, returns, n_groups=1)


class FusionReplayTests(unittest.TestCase):
    def test_report_reproducible_json_safe_and_target_not_certified(self):
        bars = sample_bars()
        first = run_shadow_replay(bars)
        self.assertEqual(first, run_shadow_replay(bars))
        json.dumps(first, allow_nan=False)
        self.assertFalse(first["live_trading_enabled"])
        self.assertFalse(first["target"]["supported"])
        self.assertEqual(first["summary"]["final_capital"], first["equity_curve"][-1]["equity"])
        self.assertGreater(first["summary"]["total_trades"], 0)
        self.assertAlmostEqual(first["summary"]["final_capital"] - first["summary"]["initial_capital"],
                               sum(trade["pnl"] for trade in first["trades"]))
        self.assertGreater(first["summary"]["total_fees"], 0)

    def test_wins_count_net_after_both_side_costs(self):
        report = run_shadow_replay(sample_bars(), {"fee_bps": 100, "slippage_bps": 100})
        summary = report["summary"]
        wins = sum(trade["pnl"] > 0 for trade in report["trades"])
        self.assertEqual(summary["winning_trades"], wins)
        self.assertEqual(summary["win_rate"], wins / summary["total_trades"])
        self.assertAlmostEqual(summary["total_fees"], sum(trade["fees"] for trade in report["trades"]))

    def test_future_data_does_not_change_prior_signal_or_replay_equity(self):
        bars = sample_bars()
        old = run_shadow_replay(bars)
        changed = [dict(row) for row in bars]
        for row in changed[180:]:
            for name in ("open", "high", "low", "close"):
                row[name] *= .8
        new = run_shadow_replay(changed)
        cutoff = bars[180]["timestamp"]
        for left, right in zip(old["equity_curve"], new["equity_curve"]):
            if left["timestamp"] < cutoff:
                self.assertEqual(left, right)
        self.assertEqual(analyze_factors(bars[:180]), analyze_factors(changed[:180]))

    def test_entry_is_after_prior_completed_signal_and_uses_next_open(self):
        bars = sample_bars()
        report = run_shadow_replay(bars)
        first = report["trades"][0]
        index = next(i for i, row in enumerate(bars) if row["timestamp"] == first["entry_timestamp"])
        self.assertEqual(analyze_factors(bars[:index])["signal"]["stance"], "long_candidate")
        self.assertAlmostEqual(first["entry_price"], bars[index]["open"] * 1.0005)
        self.assertLessEqual(first["quantity"], bars[index - 1]["volume"] * .005)

    def test_unknown_current_bar_volume_cannot_prevent_its_opening_fill(self):
        bars = sample_bars()
        report = run_shadow_replay(bars)
        timestamp = report["trades"][0]["entry_timestamp"]
        index = next(i for i, row in enumerate(bars) if row["timestamp"] == timestamp)
        changed = [dict(row) for row in bars]
        changed[index]["volume"] = 0
        rerun = run_shadow_replay(changed)
        self.assertEqual(rerun["trades"][0]["entry_timestamp"], timestamp)
        self.assertEqual(rerun["trades"][0]["quantity"], report["trades"][0]["quantity"])

    def test_flat_prices_hold_cash_and_do_not_invent_a_win_rate(self):
        report = run_shadow_replay(sample_bars(flat=True))
        self.assertEqual(report["trades"], [])
        self.assertIsNone(report["summary"]["win_rate"])
        self.assertIsNone(report["summary"]["win_rate_ci95"])
        self.assertEqual(report["summary"]["total_return"], 0)
        self.assertLess(report["benchmark"]["total_return"], 0)
        self.assertEqual(analyze_factors(sample_bars(flat=True))["signal"]["stance"], "cash")

    def test_inputs_and_settings_fail_closed(self):
        for config in ({"periods_per_year": True}, {"risk_per_trade": .1}, {"max_exposure": 2},
                       {"initial_capital": float("inf")}, {"unknown": 3}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                run_shadow_replay(sample_bars(), config)
        with self.assertRaises(ValueError):
            analyze_factors(sample_bars(20))
        with self.assertRaises(ValueError):
            run_shadow_replay(sample_bars(60))
        with self.assertRaises(ValueError):
            analyze_factors(sample_bars(), symbol="x\n<script>")


if __name__ == "__main__":
    unittest.main()
