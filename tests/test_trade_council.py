import unittest

from loki.api.trade_council import CouncilRequest, evaluate_trade_council


def base_request(**changes):
    values = {
        "side": "BUY",
        "capital": 10_000,
        "risk_percent": 1,
        "entry_price": 100,
        "stop_price": 98,
        "target_price": 106,
        "current_price": 100,
        "trend": "BULLISH",
        "volatility_percent": 2,
        "volume_ratio": 1,
        "market_data_age_seconds": 10,
        "spread_percent": 0.1,
        "market_open": True,
    }
    values.update(changes)
    return CouncilRequest(**values)


class TradeCouncilTests(unittest.TestCase):
    def test_all_six_gates_pass_for_a_valid_buy_plan(self):
        decision = evaluate_trade_council(base_request())

        self.assertEqual(decision.action, "BUY")
        self.assertEqual(len(decision.reviews), 6)
        self.assertTrue(all(review.verdict == "PASS" for review in decision.reviews))

    def test_stale_market_data_skips_the_plan(self):
        decision = evaluate_trade_council(base_request(market_data_age_seconds=61))

        self.assertEqual(decision.action, "SKIP")
        self.assertEqual(decision.reviews[0].agent, "Scout")
        self.assertEqual(decision.reviews[0].verdict, "SKIP")

    def test_neutral_trend_requires_waiting_for_confirmation(self):
        decision = evaluate_trade_council(base_request(trend="NEUTRAL"))

        self.assertEqual(decision.action, "WAIT")
        self.assertEqual(decision.reviews[1].agent, "Trend")
        self.assertEqual(decision.reviews[1].verdict, "WAIT")

    def test_price_outside_entry_zone_requires_waiting(self):
        decision = evaluate_trade_council(base_request(current_price=101))

        self.assertEqual(decision.action, "WAIT")
        self.assertEqual(decision.reviews[2].agent, "Chart Guardian")
        self.assertEqual(decision.reviews[2].verdict, "WAIT")

    def test_unfavourable_reward_risk_skips_the_plan(self):
        decision = evaluate_trade_council(base_request(target_price=102))

        self.assertEqual(decision.action, "SKIP")
        self.assertEqual(decision.reviews[3].agent, "Risk Sentinel")
        self.assertEqual(decision.reviews[3].verdict, "SKIP")

    def test_excessive_volatility_skips_the_plan(self):
        decision = evaluate_trade_council(base_request(volatility_percent=6))

        self.assertEqual(decision.action, "SKIP")
        self.assertEqual(decision.reviews[4].agent, "Volatility Guardian")
        self.assertEqual(decision.reviews[4].verdict, "SKIP")

    def test_wide_spread_requires_waiting(self):
        decision = evaluate_trade_council(base_request(spread_percent=0.6))

        self.assertEqual(decision.action, "WAIT")
        self.assertEqual(decision.reviews[5].agent, "Execution Gate")
        self.assertEqual(decision.reviews[5].verdict, "WAIT")

    def test_low_volume_guidance_says_to_wait_for_participation(self):
        decision = evaluate_trade_council(base_request(volume_ratio=0.5))

        self.assertEqual(decision.action, "WAIT")
        self.assertIn("volume", decision.reviews[0].next_step.lower())
        self.assertIn("threshold", decision.reviews[0].next_step.lower())


if __name__ == "__main__":
    unittest.main()

