import unittest

from loki.api.daily_risk import DailyRiskError, build_daily_risk_summary


class TestDailyRisk(unittest.TestCase):
    def test_unused_cap_is_within_limit(self):
        result = build_daily_risk_summary(
            capital=10_000,
            loss_limit_percent=2,
            realized_pnl=0,
            realized_loss=0,
            open_planned_risk=50,
        )

        self.assertEqual(result.status, "WITHIN_LIMIT")
        self.assertEqual(result.limit_amount, 200)
        self.assertEqual(result.remaining_amount, 150)
        self.assertEqual(result.utilization_percent, 25)

    def test_nearby_cap_warns_without_counting_profit_as_more_budget(self):
        result = build_daily_risk_summary(
            capital=10_000,
            loss_limit_percent=2,
            realized_pnl=300,
            realized_loss=75,
            open_planned_risk=100,
            closed_today=2,
            open_positions=1,
        )

        self.assertEqual(result.status, "WATCH")
        self.assertEqual(result.committed_loss, 175)
        self.assertEqual(result.remaining_amount, 25)
        self.assertEqual(result.closed_today, 2)
        self.assertEqual(result.open_positions, 1)

    def test_realized_loss_and_open_risk_can_trigger_pause(self):
        result = build_daily_risk_summary(
            capital=10_000,
            loss_limit_percent=2,
            realized_pnl=-125,
            realized_loss=125,
            open_planned_risk=75,
        )

        self.assertEqual(result.status, "PAUSE")
        self.assertEqual(result.realized_loss, 125)
        self.assertEqual(result.committed_loss, 200)
        self.assertEqual(result.remaining_amount, 0)

    def test_realized_loss_alone_triggers_pause(self):
        result = build_daily_risk_summary(
            capital=10_000,
            loss_limit_percent=2,
            realized_pnl=-250,
            realized_loss=250,
            open_planned_risk=0,
        )

        self.assertEqual(result.status, "PAUSE")
        self.assertEqual(result.utilization_percent, 125)

    def test_invalid_or_non_finite_inputs_are_rejected(self):
        invalid_inputs = (
            {
                "capital": 0,
                "loss_limit_percent": 2,
                "realized_pnl": 0,
                "realized_loss": 0,
                "open_planned_risk": 0,
            },
            {
                "capital": 10_000,
                "loss_limit_percent": 0,
                "realized_pnl": 0,
                "realized_loss": 0,
                "open_planned_risk": 0,
            },
            {
                "capital": 10_000,
                "loss_limit_percent": 2,
                "realized_pnl": 0,
                "realized_loss": 0,
                "open_planned_risk": -1,
            },
            {
                "capital": 10_000,
                "loss_limit_percent": 2,
                "realized_pnl": 0,
                "realized_loss": -1,
                "open_planned_risk": 0,
            },
            {
                "capital": float("inf"),
                "loss_limit_percent": 2,
                "realized_pnl": 0,
                "realized_loss": 0,
                "open_planned_risk": 0,
            },
        )
        for kwargs in invalid_inputs:
            with self.subTest(kwargs=kwargs), self.assertRaises(DailyRiskError):
                build_daily_risk_summary(**kwargs)


if __name__ == "__main__":
    unittest.main()
