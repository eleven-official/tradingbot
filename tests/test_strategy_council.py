"""Tests for the non-executing strategy council."""
import unittest

from core_engine.strategy_council import build_strategy_council


class StrategyCouncilTests(unittest.TestCase):
    def test_no_candidate_means_wait(self):
        report = build_strategy_council(
            strategy="Trend strategy", signal="HOLD", sentiment="Bullish", regime="RANGE"
        )
        self.assertEqual(report["decision"], "WAIT")
        self.assertEqual(len(report["members"]), 4)

    def test_conflicting_evidence_is_raised_to_the_skeptic(self):
        report = build_strategy_council(
            strategy="Trend strategy",
            signal="BUY",
            sentiment="Bearish",
            regime="TRENDING",
            trend_composite=-0.4,
            recent_blockers=["VIX gate blocked the candidate"],
        )
        self.assertEqual(report["decision"], "REVIEW")
        skeptic = report["members"][3]
        self.assertIn("DISSENT", skeptic["stance"])
        self.assertIn("sentiment", skeptic["reason"])
        self.assertIn("VIX gate", skeptic["reason"])

    def test_aligned_candidate_still_defers_to_existing_risk_gates(self):
        report = build_strategy_council(
            strategy="Trend strategy",
            signal="BUY",
            sentiment="Bullish",
            regime="TRENDING",
            trend_composite=0.7,
            conviction="HIGH",
        )
        self.assertEqual(report["decision"], "CANDIDATE")
        self.assertIn("risk and execution gates", report["decision_reason"])
        self.assertIn("never places orders", report["authority_note"])

    def test_open_position_takes_precedence_over_new_signal(self):
        report = build_strategy_council(
            strategy="Trend strategy",
            signal="SELL",
            sentiment="Bearish",
            regime="TRENDING",
            active_trade=True,
        )
        self.assertEqual(report["decision"], "MANAGE_OPEN_POSITION")

    def test_news_evidence_is_limited_and_not_claimed_as_causation(self):
        report = build_strategy_council(
            strategy="Trend strategy",
            signal="HOLD",
            sentiment="Bullish",
            regime="RANGE",
            news_headlines=[
                {"title": f"Headline {i}", "source": "Wire", "polarity": 0.5}
                for i in range(5)
            ],
        )
        catalyst = report["members"][0]
        self.assertEqual(len(catalyst["evidence"]), 3)
        self.assertIn("do not prove", catalyst["reason"])


if __name__ == "__main__":
    unittest.main()

