import math
import unittest

from loki.api.risk_planner import RiskPlanError, RiskPlanInput, build_risk_plan


class RiskPlannerTests(unittest.TestCase):
    def test_buy_plan_uses_the_tighter_notional_limit(self):
        plan = build_risk_plan(
            RiskPlanInput(
                side="buy",
                capital=10_000,
                risk_percent=1,
                entry_price=100,
                stop_price=98,
                target_price=106,
                max_notional_percent=10,
            )
        )

        self.assertTrue(plan.approved)
        self.assertEqual(plan.quantity, 10)
        self.assertEqual(plan.risk_budget, 100)
        self.assertEqual(plan.estimated_loss, 20)
        self.assertEqual(plan.projected_profit, 60)
        self.assertEqual(plan.reward_risk_ratio, 3)

    def test_sell_plan_uses_inverse_price_geometry(self):
        plan = build_risk_plan(
            RiskPlanInput(
                side="SELL",
                capital=5_000,
                risk_percent=2,
                entry_price=50,
                stop_price=52,
                target_price=44,
                max_notional_percent=50,
            )
        )

        self.assertTrue(plan.approved)
        self.assertEqual(plan.quantity, 50)
        self.assertEqual(plan.reward_risk_ratio, 3)

    def test_plan_rejects_reward_risk_below_the_user_threshold(self):
        plan = build_risk_plan(
            RiskPlanInput(
                side="BUY",
                capital=10_000,
                risk_percent=1,
                entry_price=100,
                stop_price=98,
                target_price=102,
                minimum_reward_risk=1.5,
            )
        )

        self.assertFalse(plan.approved)
        self.assertIn("below", plan.reason)

    def test_plan_uses_fractional_units_when_no_whole_unit_fits(self):
        plan = build_risk_plan(
            RiskPlanInput(
                side="BUY",
                capital=50,
                risk_percent=1,
                entry_price=100,
                stop_price=99,
                target_price=102,
            )
        )

        self.assertTrue(plan.approved)
        self.assertEqual(plan.quantity, 0.05)
        self.assertEqual(plan.estimated_loss, 0.05)

    def test_btc_plan_uses_fractional_units_within_both_limits(self):
        plan = build_risk_plan(
            RiskPlanInput(
                side="BUY",
                capital=10_000,
                risk_percent=1,
                entry_price=80_000,
                stop_price=79_000,
                target_price=82_000,
                max_notional_percent=10,
            )
        )

        self.assertTrue(plan.approved)
        self.assertEqual(plan.quantity, 0.0125)
        self.assertEqual(plan.notional, 1_000)
        self.assertEqual(plan.estimated_loss, 12.5)
        self.assertEqual(plan.projected_profit, 25)

    def test_extreme_derived_quantity_is_rejected(self):
        with self.assertRaisesRegex(RiskPlanError, "safe numeric range"):
            build_risk_plan(
                RiskPlanInput(
                    side="BUY",
                    capital=1e308,
                    risk_percent=100,
                    entry_price=1,
                    stop_price=0.5,
                    target_price=2,
                    max_notional_percent=100,
                )
            )

    def test_invalid_stop_geometry_is_rejected(self):
        with self.assertRaisesRegex(RiskPlanError, "loss side"):
            build_risk_plan(
                RiskPlanInput(
                    side="BUY",
                    capital=10_000,
                    risk_percent=1,
                    entry_price=100,
                    stop_price=101,
                    target_price=104,
                )
            )

    def test_non_finite_values_are_rejected(self):
        with self.assertRaises(RiskPlanError):
            build_risk_plan(
                RiskPlanInput(
                    side="BUY",
                    capital=math.inf,
                    risk_percent=1,
                    entry_price=100,
                    stop_price=99,
                    target_price=102,
                )
            )


if __name__ == "__main__":
    unittest.main()

