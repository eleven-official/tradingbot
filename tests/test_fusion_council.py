"""The AutoHedge role integration must never turn weak evidence into orders."""
import copy
import json
import unittest

from core.fusion.council import CouncilConfig, build_council_report
from core.fusion.portfolio import new_portfolio
from core.fusion.quant import run_shadow_replay
from tests.test_fusion_quant import sample_bars


class FusionCouncilTests(unittest.TestCase):
    def test_role_pipeline_is_explicit_no_model_or_order_claim(self):
        bars = sample_bars()
        report = build_council_report(bars)
        self.assertEqual(report["engine"], "deterministic_role_pipeline")
        self.assertEqual([row["role"] for row in report["analysts"]], ["quant", "sentiment", "risk", "execution"])
        self.assertIsNone(report["analysts"][1]["evidence"]["sentiment"])
        self.assertEqual(report["analysts"][1]["status"], "missing_evidence")
        self.assertFalse(report["performance_target"]["supported"])
        self.assertEqual(report["director"]["decision"], "wait")
        self.assertIn("checks are not satisfied", report["director"]["summary"])
        self.assertFalse(report["live_trading_enabled"])
        self.assertFalse(report["proposal"]["executable"])
        self.assertEqual(report["analysts"][3]["evidence"]["orders_submitted"], 0)
        json.dumps(report, allow_nan=False)

    def test_high_wins_from_other_strategy_do_not_validate_the_factor_rule(self):
        bars = sample_bars()
        fingerprint = run_shadow_replay(bars)["data_fingerprint"]
        research = {"data_fingerprint": fingerprint, "strategy_id": "other_strategy", "validation_mode": "chronological_forward_test",
                    "summary": {"total_trades": 200, "win_rate": .9, "win_rate_ci95": [.84, .94],
                                "total_return": .2, "expectancy": 4}}
        report = build_council_report(bars, research=research)
        target = report["performance_target"]
        self.assertTrue(target["meets_observed_target"])
        self.assertTrue(target["same_observations"])
        self.assertFalse(target["same_strategy"])
        self.assertFalse(target["supported"])
        self.assertTrue(any("different strategy" in reason for reason in target["reasons"]))

    def test_existing_exposure_and_cash_cap_the_draft_with_both_side_costs(self):
        bars = sample_bars()
        snapshot = {"equity": 10000, "cash": 8500, "currency": "USDT",
                    "positions": [{"symbol": "BTC/USDT", "market_value": 1500}]}
        before = copy.deepcopy(snapshot)
        report = build_council_report(bars, portfolio=snapshot)
        proposal = report["proposal"]
        self.assertLessEqual(proposal["cash_required"], 500.00001)
        self.assertLessEqual(proposal["planned_loss_at_stop"], 50.00001)
        self.assertEqual(snapshot, before)
        self.assertFalse(proposal["executable"])

    def test_no_capacity_no_draft(self):
        snapshot = {"equity": 10000, "cash": 8000, "currency": "USDT",
                    "positions": [{"symbol": "BTC/USDT", "market_value": 2000}]}
        report = build_council_report(sample_bars(), portfolio=snapshot)
        self.assertIsNone(report["proposal"])
        self.assertEqual(report["director"]["decision"], "wait")

    def test_paper_ledger_supported_without_mutation_and_currency_mismatch_blocks(self):
        state = new_portfolio(10000, quote_currency="USD")
        before = copy.deepcopy(state)
        report = build_council_report(sample_bars(), portfolio={"state": state})
        check = next(row for row in report["risk_checks"] if row["name"] == "Quote currency agrees")
        self.assertFalse(check["passed"])
        self.assertEqual(state, before)
        self.assertIn("Quote currency agrees", report["proposal"]["blocked_by"])

    def test_incomplete_valuation_and_bad_risk_settings_rejected(self):
        with self.assertRaises(ValueError):
            build_council_report(sample_bars(), portfolio={"equity": 10000, "cash": 9000, "positions": []})
        with self.assertRaises(ValueError):
            build_council_report(sample_bars(), config={"require_research_evidence": "no"})
        with self.assertRaises(ValueError):
            CouncilConfig(max_portfolio_exposure=.1, max_exposure=.2)

    def test_gate_opt_out_is_explicit_scenario_planning_still_inert(self):
        # Find an input ending when all fixed factors agree, independently of
        # any future profitability. No synthetic data is performance evidence.
        bars = sample_bars()
        for end in range(61, len(bars)):
            report = build_council_report(bars[:end], config={"require_research_evidence": False})
            if report["director"]["stance"] == "long_candidate":
                break
        self.assertEqual(report["director"]["decision"], "paper_proposal")
        self.assertFalse(report["performance_target"]["supported"])
        self.assertFalse(report["proposal"]["executable"])
        self.assertTrue(any("explicitly disabled" in row["detail"] for row in report["risk_checks"]))

    def test_news_context_binds_for_inspection_and_never_moves_a_gate(self):
        bars = sample_bars()
        news = {
            "status": "ok",
            "score": 0.35,
            "headlines_read": 12,
            "top": [
                {"title": "record quarter beats estimates", "publisher": "Wire", "score": 0.6},
                {"title": "supplier slowdown feared for fall", "publisher": "Wire", "score": -0.45},
            ],
            "method": "matched words carry fixed weights; the score is their clamped mean",
        }
        with_news = build_council_report(bars, news_evidence=news)
        without = build_council_report(bars)
        self.assertEqual(with_news["analysts"][1]["status"], "news_context")
        self.assertEqual(without["analysts"][1]["status"], "missing_evidence")
        packet = with_news["analysts"][1]["evidence"]["news"]
        self.assertEqual(packet["score"], .35)
        self.assertEqual(packet["headlines_read"], 12)
        self.assertEqual(len(packet["top"]), 2)
        lowered = " ".join(with_news["analysts"][1]["concerns"]).lower()
        self.assertIn("no council gate consults news context", lowered)
        # Bonds of the honest kind: the packet cannot change sizing, checks or verdict.
        self.assertEqual(without["risk_checks"], with_news["risk_checks"])
        self.assertEqual(
            [row["status"] for row in without["analysts"] if row["role"] != "sentiment"],
            [row["status"] for row in with_news["analysts"] if row["role"] != "sentiment"],
        )
        self.assertEqual(without["director"]["decision"], with_news["director"]["decision"])
        json.dumps(with_news, allow_nan=False)

    def test_news_packet_validation_leaves_no_side_channel(self):
        base = {
            "status": "ok",
            "score": .2,
            "headlines_read": 5,
            "top": [{"title": "records a quarter of growth", "publisher": "Wire", "score": .3}],
            "method": "matched words carry fixed weights",
        }
        bads = [
            dict(base, score=1.5),
            dict(base, headlines_read=0),
            dict(base, headlines_read=51),
            dict(base, method="short"),
            dict(base, top=[]),
            dict(base, top=[{"title": "records a quarter of growth", "publisher": "", "score": .3}] * 31),
            dict(base, top=[{"title": "ab", "publisher": "", "score": .3}]),
            dict(base, top=[{"title": "ok title here", "publisher": "", "score": 2}]),
            dict(base, status="abstain"),
        ]
        for index, bad in enumerate(bads):
            with self.subTest(index=index):
                with self.assertRaises(ValueError):
                    build_council_report(sample_bars(), news_evidence=bad)

    def test_news_and_mirofish_cannot_share_the_sentiment_seat(self):
        miro = {"engine": "bundled_mirofish_native", "symbol": "BTC/USDT", "report": {"status": "completed"}}
        with self.assertRaises(ValueError):
            build_council_report(
                sample_bars(),
                miro_research=miro,
                news_evidence={
                    "status": "ok",
                    "score": 0,
                    "headlines_read": 1,
                    "top": [{"title": "one quiet headline", "publisher": "", "score": 0}],
                    "method": "matched words carry fixed weights here",
                },
            )


if __name__ == "__main__":
    unittest.main()
