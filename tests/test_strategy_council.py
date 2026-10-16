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


    def test_missing_market_context_cannot_be_reported_as_aligned(self):
        report = build_strategy_council(
            strategy="Trend strategy", signal="BUY", sentiment=None, regime=None,
        )
        self.assertEqual(report["decision"], "REVIEW")
        self.assertEqual(report["members"][3]["stance"], "NEEDS_EVIDENCE")
        self.assertIn("unavailable", report["members"][3]["reason"])

    def test_neutral_sentiment_and_missing_trend_raise_evidence_gaps(self):
        report = build_strategy_council(
            strategy="Trend strategy", signal="SELL", sentiment="Neutral",
            regime="RANGE", trend_composite=float("nan"),
        )
        self.assertEqual(report["decision"], "REVIEW")
        skeptic = report["members"][3]["reason"]
        self.assertIn("Sentiment is neutral", skeptic)
        self.assertIn("Market trend evidence is unavailable", skeptic)

    def test_market_watcher_includes_named_trend_components(self):
        report = build_strategy_council(
            strategy="Trend strategy", signal="HOLD", sentiment="Bullish",
            regime="TRENDING", trend_composite=0.4,
            trend_components={"ema_alignment": 0.8, "breadth": -0.2},
            conditions=["above VWAP"],
        )
        evidence = report["members"][1]["evidence"]
        self.assertTrue(any("ema_alignment: +0.80" in item for item in evidence))
        self.assertTrue(any("breadth: -0.20" in item for item in evidence))

    def test_optional_collection_inputs_accept_none_and_single_strings(self):
        report = build_strategy_council(
            strategy="Trend strategy", signal="HOLD", sentiment="Neutral",
            regime="RANGE", conditions="inside opening range", recent_blockers=None,
        )
        self.assertEqual(report["decision"], "WAIT")
        self.assertIn("inside opening range", report["members"][1]["evidence"])

    def test_blocker_string_is_preserved_as_one_reason(self):
        report = build_strategy_council(
            strategy="Trend strategy", signal="BUY", sentiment="Bullish",
            regime="TRENDING", trend_composite=0.7,
            recent_blockers="Risk gate blocked candidate",
        )
        self.assertEqual(report["decision"], "REVIEW")
        self.assertIn("Risk gate blocked candidate", report["members"][3]["reason"])


if __name__ == "__main__":
    unittest.main()

