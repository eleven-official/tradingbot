"""Offline regression coverage for desktop evidence and risk form rules."""

import unittest

from core.desktop_presenter import (
    performance_evidence, quote_is_fresh, risk_sized_quantity, validate_risk_settings,
)


class EvidenceTests(unittest.TestCase):
    def test_no_outcomes_are_not_reported_as_zero_success(self):
        self.assertIn("awaiting", performance_evidence(0, 0))
        self.assertNotIn("0.0%", performance_evidence(0, 0))

    def test_observed_rate_includes_sample_and_uncertainty(self):
        text = performance_evidence(7, 10)
        self.assertIn("70.0% (7/10)", text)
        self.assertIn("95% interval: 40%–89%", text)

    def test_all_winners_still_have_uncertainty(self):
        self.assertIn("21%–100%", performance_evidence(1, 1))

    def test_invalid_counts_rejected(self):
        with self.assertRaises(ValueError):
            performance_evidence(3, 2)


class RiskFormTests(unittest.TestCase):
    def setUp(self):
        self.form = dict(risk_per_trade_pct="1", stop_loss_pct="3", take_profit_pct="6",
                         trailing_stop_pct="2", daily_loss_pct="4", max_drawdown_pct="12",
                         min_confidence="70")

    def test_percentages_convert_once_and_input_is_unchanged(self):
        result = validate_risk_settings(self.form)
        self.assertEqual(result["risk_per_trade_pct"], 0.01)
        self.assertEqual(result["min_confidence"], 0.70)
        self.assertEqual(self.form["min_confidence"], "70")

    def test_nonfinite_and_out_of_range_settings_rejected(self):
        for value in ("nan", "inf", "-1", "0", "101", "hello"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_risk_settings({**self.form, "min_confidence": value})

    def test_overlarge_per_trade_risk_rejected(self):
        with self.assertRaises(ValueError):
            validate_risk_settings({**self.form, "risk_per_trade_pct": "6"})

    def test_missing_field_rejected(self):
        del self.form["stop_loss_pct"]
        with self.assertRaises(ValueError):
            validate_risk_settings(self.form)


class RiskSizingTests(unittest.TestCase):
    def test_quantity_is_based_on_stop_distance(self):
        tight = risk_sized_quantity(10000, 25000, 100, 98, .01)
        wide = risk_sized_quantity(10000, 25000, 100, 96, .01)
        self.assertLess(tight, 50)
        self.assertLess(wide, 25)
        self.assertGreater(tight, wide)
        risk_per_unit = 100 * 1.0001 * 1.0005 - 98 * .9999 * .9995
        self.assertAlmostEqual(tight * risk_per_unit, 100)

    def test_quantity_is_capped_at_cash_including_costs(self):
        quantity = risk_sized_quantity(10000, 500, 100, 99, .01)
        self.assertLess(quantity, 5)
        self.assertAlmostEqual(quantity * 100 * 1.0001 * 1.0005, 500)

    def test_invalid_stops_and_nonfinite_values_rejected(self):
        for stop in (0, 100, 101, float("nan")):
            with self.subTest(stop=stop), self.assertRaises(ValueError):
                risk_sized_quantity(10000, 500, 100, stop, .01)


class SourceFreshnessTests(unittest.TestCase):
    def test_missing_stale_future_and_nonfinite_quotes_are_rejected(self):
        for updated in (None, 1, 101, float("nan"), float("inf")):
            with self.subTest(updated=updated):
                self.assertFalse(quote_is_fresh(updated, 100))

    def test_freshness_boundary(self):
        self.assertTrue(quote_is_fresh(40, 100))
        self.assertFalse(quote_is_fresh(39.9, 100))


if __name__ == "__main__":
    unittest.main()
