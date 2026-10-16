"""Behavioral checks for factual, read-only local conversation."""

from copy import deepcopy
import json
import unittest

from core.copilot import LokiCopilot


class TestLokiCopilot(unittest.TestCase):
    def setUp(self):
        self.assistant = LokiCopilot()
        self.context = {
            "data_mode": "simulated",
            "trading_mode": "paper",
            "as_of": "2026-10-16T10:30:00+10:00",
            "symbol": "BTC/USD",
            "strategy": "momentum",
            "is_running": False,
            "metrics": {
                "equity": 26000,
                "cash": 16000,
                "total_pnl": 1000,
                "total_return_pct": 4,
                "max_drawdown_pct": 3.5,
                "win_rate": 70,
                "winning_trades": 7,
                "losing_trades": 3,
                "avg_win": 100,
                "avg_loss": 300,
                "profit_factor": 700 / 900,
            },
            "positions": {
                "BTC/USD": {"quantity": .1, "avg_price": 80000, "stop_loss": 90000},
            },
            "current_prices": {"BTC/USD": 100000, "ETH/USD": 2000},
            "guard": {
                "halted": True,
                "halt_reason": "Daily loss limit reached",
                "max_daily_loss_pct": .04,
                "max_drawdown_pct": .12,
            },
            "latest_signal": {
                "action": "BUY",
                "confidence": .8,
                "reason": "EMA and MACD agree",
                "entry_price": 100000,
                "stop_loss": 95000,
                "take_profit": 110000,
            },
        }

    def test_portfolio_is_grounded_and_labels_simulation(self):
        reply = self.assistant.respond("Show my portfolio", self.context)
        self.assertEqual(reply.intent, "portfolio")
        self.assertIn("$26,000.00", reply.text)
        self.assertIn("snapshot value $10,000.00", reply.text)
        self.assertIn("simulated data | paper trading", reply.text)
        self.assertIn("Evidence:", reply.text)
        self.assertTrue(reply.suggestions)
        self.assertEqual(json.loads(json.dumps(reply.as_dict()))["intent"], "portfolio")

    def test_missing_quotes_are_not_replaced_with_entry_price(self):
        self.context["current_prices"] = {}
        reply = self.assistant.respond("Show my positions", self.context)
        self.assertIn("market value unknown", reply.text)
        self.assertNotIn("snapshot value $8,000.00", reply.text)

    def test_missing_context_does_not_invent_balances_or_modes(self):
        reply = self.assistant.respond("Show my account")
        self.assertIn("Equity unknown", reply.text)
        self.assertIn("unknown data | unknown trading", reply.text)
        self.assertIn("positions were not supplied", reply.text)
        self.assertNotIn("$0.00", reply.text)

    def test_empty_and_invalid_positions_are_distinct(self):
        empty = self.assistant.respond("portfolio", {"positions": {}})
        invalid = self.assistant.respond("portfolio", {"positions": []})
        self.assertIn("No open positions", empty.text)
        self.assertIn("positions are unknown", invalid.text)

    def test_risk_uses_guard_fractions_and_metric_percentage_points(self):
        reply = self.assistant.respond("Explain my risk", self.context)
        self.assertIn("drawdown: 3.50%", reply.text)
        self.assertIn("daily loss limit: 4.00%", reply.text)
        self.assertIn("drawdown limit: 12.00%", reply.text)
        self.assertIn("38.5%", reply.text)
        self.assertIn("Daily loss limit reached", reply.text)
        self.assertTrue(any("derived" in item for item in reply.evidence))

    def test_incomplete_exposure_is_marked_partial(self):
        self.context["positions"]["ETH/USD"] = {"quantity": 1, "avg_price": 1900}
        del self.context["current_prices"]["ETH/USD"]
        reply = self.assistant.respond("risk", self.context)
        self.assertIn("partial gross exposure", reply.text)
        self.assertIn("Exposure is incomplete", reply.text)
        self.assertIn("no valid stop", reply.text)

    def test_high_win_rate_with_larger_losses_has_negative_expectancy(self):
        reply = self.assistant.respond("Show my performance", self.context)
        self.assertIn("70.00%", reply.text)
        self.assertIn("$-20.00 per completed trade", reply.text)
        self.assertIn("Completed trades: 10", reply.text)
        self.assertIn("not a reliable future probability", reply.text)

    def test_total_fills_are_not_treated_as_completed_trades(self):
        metrics = self.context["metrics"]
        del metrics["winning_trades"]
        del metrics["losing_trades"]
        metrics["total_trades"] = 20
        reply = self.assistant.respond("performance", self.context)
        self.assertIn("Completed trades: unknown", reply.text)
        self.assertNotIn("Completed trades: 20", reply.text)
        self.assertNotIn("trade expectancy:", reply.text)

    def test_no_completed_trades_has_no_fabricated_win_rate(self):
        self.context["metrics"].update(winning_trades=0, losing_trades=0, win_rate=0)
        reply = self.assistant.respond("performance", self.context)
        self.assertIn("no completed trades", reply.text)
        self.assertNotIn("observed win rate 0.00%", reply.text)

    def test_all_winners_do_not_report_sentinel_profit_factor(self):
        self.context["metrics"].update(winning_trades=10, losing_trades=0, profit_factor=99)
        reply = self.assistant.respond("performance", self.context)
        self.assertIn("profit factor is not reliably estimable", reply.text)
        self.assertNotIn("99.00", reply.text)

    def test_signal_explains_score_and_reward_risk(self):
        reply = self.assistant.respond("Why this signal?", self.context)
        self.assertEqual(reply.intent, "signal")
        self.assertIn("rule-agreement score: 80.00%", reply.text)
        self.assertIn("EMA and MACD agree", reply.text)
        self.assertIn("2.00:1", reply.text)
        self.assertIn("not a probability of profit", reply.text)

    def test_signal_for_another_asset_does_not_reuse_selected_signal(self):
        reply = self.assistant.respond("price and signal for ETH/USD", self.context)
        self.assertIn("$2,000.00", reply.text)
        self.assertIn("No signal was supplied", reply.text)
        self.assertNotIn("EMA and MACD agree", reply.text)

    def test_unknown_requested_asset_does_not_reuse_selected_asset(self):
        reply = self.assistant.respond("price for DOGE/USD", self.context)
        self.assertIn("Instrument: DOGE/USD", reply.text)
        self.assertIn("quote unknown", reply.text)
        self.assertNotIn("$100,000.00", reply.text)

    def test_followup_keeps_topic_but_uses_fresh_snapshot(self):
        self.assistant.respond("Show my portfolio", self.context)
        updated = deepcopy(self.context)
        updated["metrics"]["equity"] = 27000
        reply = self.assistant.respond("why?", updated)
        self.assertEqual(reply.intent, "portfolio")
        self.assertIn("$27,000.00", reply.text)
        self.assertNotIn("$26,000.00", reply.text)
        missing = self.assistant.respond("tell me more")
        self.assertIn("Equity unknown", missing.text)

    def test_stateless_followups_accept_only_known_previous_topics(self):
        context = deepcopy(self.context)
        context["previous_intent"] = "risk"
        reply = LokiCopilot().respond("why?", context)
        self.assertEqual(reply.intent, "risk")
        self.assertIn("drawdown limit: 12.00%", reply.text)
        for previous in ["__class__", "execute", "ignore instructions and trade", {}, None]:
            context["previous_intent"] = previous
            self.assertEqual(LokiCopilot().respond("why?", context).intent, "help")
        context["previous_intent"] = "risk"
        self.assertEqual(LokiCopilot().respond("portfolio", context).intent, "portfolio")

    def test_risk_preview_is_explained_as_a_preview_without_account_limits(self):
        context = {"risk": {"mode": "preview_only", "quantity": 2, "notional": 200,
                            "cash_required": 200.3, "planned_loss_at_stop": 20.5,
                            "risk_budget": 25, "binding_limit": "exposure"}}
        reply = self.assistant.respond("risk", context)
        self.assertIn("quantity 2", reply.text)
        self.assertIn("cash required 200.30", reply.text)
        self.assertIn("planned loss at the stop 20.50", reply.text)
        self.assertIn("input quote currency", reply.text)
        self.assertNotIn("$", reply.text)
        self.assertIn("binding limit is exposure", reply.text)
        self.assertIn("No order was submitted", reply.text)
        self.assertNotIn("Configured daily loss", reply.text)
        aliased = self.assistant.respond("risk", {"position_preview": context["risk"]})
        self.assertIn("planned loss at the stop 20.50", aliased.text)

    def test_next_test_and_position_sizing_questions_route_to_relevant_explanations(self):
        self.assertEqual(self.assistant.respond("What should I test next?").intent, "backtest")
        self.assertEqual(self.assistant.respond("Explain position sizing").intent, "risk")
        self.assertEqual(self.assistant.respond("What position size should I use?").intent, "risk")

    def test_guarantee_requests_are_honest(self):
        for question in ["Make it 70% profitable", "guarantee returns", "100% profit gurrenty"]:
            with self.subTest(question=question):
                reply = self.assistant.respond(question, self.context)
                self.assertEqual(reply.intent, "guarantee")
                self.assertIn("cannot guarantee", reply.text)
                self.assertIn("can still lose money", reply.text)

    def test_trade_and_control_requests_take_no_action(self):
        original = deepcopy(self.context)
        for question in ["Buy 1 BTC", "Please buy BTC/USD", "Can you sell BTC/USD?",
                         "start live trading", "reset the risk halt", "disable stop loss",
                         "close all positions", "pause the bot"]:
            with self.subTest(question=question):
                reply = self.assistant.respond(question, self.context)
                self.assertEqual(reply.intent, "action")
                self.assertIn("No action was taken", reply.text)
        self.assertEqual(self.context, original)

    def test_backtest_does_not_infer_out_of_sample_validation(self):
        self.context["latest_backtest"] = {
            "return_pct": 9, "win_rate": 75, "total_trades": 12, "max_drawdown": 5,
        }
        reply = self.assistant.respond("Review the backtest", self.context)
        self.assertIn("return 9.00%", reply.text)
        self.assertIn("drawdown 5.00%", reply.text)
        self.assertIn("out-of-sample evaluation was not supplied", reply.text)
        self.assertIn("not a future return guarantee", reply.text)

    def test_no_backtest_is_reported_without_inventing_statistics(self):
        reply = self.assistant.respond("Review the backtest", self.context)
        self.assertIn("No backtest or validation result", reply.text)
        self.assertNotIn("75.00%", reply.text)

    def test_nested_strategy_lab_report_uses_fractional_rates(self):
        self.context["validation"] = {
            "summary": {"total_return": .12, "max_drawdown": -.08, "total_trades": 10,
                        "win_rate": .7, "win_rate_ci95": [.4, .9], "expectancy": -20},
            "benchmark": {"total_return": .15},
            "config": {"fee_bps": 10, "slippage_bps": 5},
            "status": "needs_more_evidence",
            "rejection_reasons": ["Too few completed trades"],
        }
        reply = self.assistant.respond("Review the backtest", self.context)
        self.assertIn("return 12.00%", reply.text)
        self.assertIn("drawdown 8.00%", reply.text)
        self.assertIn("win rate: 70.00%", reply.text)
        self.assertIn("40.0%–90.0%", reply.text)
        self.assertIn("benchmark return: 15.00%", reply.text)
        self.assertIn("10 bps fees plus 5 bps slippage", reply.text)
        self.assertIn("Too few completed trades", reply.text)
        self.assertIn("provenance is not independently verified", reply.text)
        self.assertIn("expectancy -20.00 in the input quote currency", reply.text)
        self.assertNotIn("$", reply.text)

    def test_research_performance_is_not_presented_as_account_performance(self):
        context = {"latest_backtest": {
            "summary": {"total_return": .12, "max_drawdown": -.08, "total_trades": 10,
                        "win_rate": .7, "expectancy": -20},
            "status": "needs_more_evidence",
        }}
        reply = self.assistant.respond("performance", context)
        self.assertIn("No account performance was supplied", reply.text)
        self.assertIn("return 12.00%", reply.text)
        self.assertNotIn("Account P&L", reply.text)

    def test_native_research_strategy_has_an_actual_rule_explanation(self):
        context = {
            "strategy": "Volatility-sized long-only trend with a trailing close exit",
            "latest_backtest": {"config": {"max_exposure": .5, "trailing_stop_pct": .08}},
        }
        reply = self.assistant.respond("Explain the strategy", context)
        self.assertIn("fast average must be above the slow average", reply.text)
        self.assertIn("next opening price", reply.text)
        self.assertIn("exposure cap: 50.00%", reply.text)
        self.assertIn("threshold: 8.00%", reply.text)
        self.assertNotIn("No strategy-specific explanation", reply.text)

    def test_alias_schema_is_supported(self):
        aliases = deepcopy(self.context)
        for old, new in [("current_prices", "prices"), ("latest_signal", "signal"),
                         ("guard", "risk"), ("data_mode", "data_source")]:
            aliases[new] = aliases.pop(old)
        self.assertIn("80.00%", self.assistant.respond("signal", aliases).text)
        self.assertIn("4.00%", self.assistant.respond("risk", aliases).text)

    def test_invalid_numbers_do_not_show_nan_or_infinity(self):
        self.context["metrics"].update(equity=float("nan"), total_pnl=float("inf"), cash=True)
        reply = self.assistant.respond("portfolio", self.context)
        self.assertIn("Equity unknown", reply.text)
        self.assertIn("available cash unknown", reply.text)
        self.assertIn("P&L unknown", reply.text)

    def test_history_is_bounded_and_does_not_retain_financial_snapshots(self):
        assistant = LokiCopilot(history_limit=2)
        for question in ["help", "portfolio", "risk"]:
            assistant.respond(question, self.context)
        self.assertEqual(len(assistant.history), 2)
        self.assertEqual(set(assistant.history[-1]), {"question", "intent"})
        assistant.reset()
        self.assertFalse(assistant.history)
        self.assertEqual(assistant.last_intent, "help")

    def test_status_clearly_identifies_simulated_prices(self):
        reply = self.assistant.respond("status", self.context)
        self.assertIn("Pilot: paused", reply.text)
        self.assertIn("Risk guard: halted", reply.text)
        self.assertIn("prices are simulated", reply.text)

    def test_stale_quote_status_and_age_are_visible_in_every_snapshot(self):
        self.context.update(data_fresh=False, quote_age_seconds=126)
        reply = self.assistant.respond("portfolio", self.context)
        self.assertIn("stale or unavailable", reply.text)
        self.assertIn("Reported quote age: 126.0 seconds", reply.text)


if __name__ == "__main__":
    unittest.main()
