"""No GUI, broker or network calls: desktop paper execution and source regressions."""

from datetime import datetime, timedelta, timezone
import importlib.util
from types import SimpleNamespace
import threading
import time
import unittest
from unittest.mock import Mock, patch

_desktop_available = all(importlib.util.find_spec(name) is not None
                         for name in ("customtkinter", "matplotlib", "mplfinance", "numpy", "pandas"))
if _desktop_available:
    import loki_desktop as desktop
else:
    desktop = None


@unittest.skipIf(desktop is None, "Optional desktop dependencies are not installed")
class PaperAccountTests(unittest.TestCase):
    def test_pilot_sizing_cannot_exceed_cash_or_risk_including_costs(self):
        risk = desktop.AdvancedRiskManager()
        quantity = risk.calculate_position_size(10000, 100, 99, 1., cash=500)
        account = desktop.ProfessionalAccount(500)
        self.assertEqual(account.execute_trade("TEST", "BUY", quantity, 100, stop_loss=99)["status"], "filled")
        self.assertGreaterEqual(account.cash, -1e-10)
        stopped = account.close_single_position("TEST", 99)
        self.assertLessEqual(-stopped["trade"]["pnl"], 10000 * risk.risk_per_trade_pct)

    def test_pilot_sizing_never_forces_a_minimum_quantity(self):
        risk = desktop.AdvancedRiskManager()
        self.assertEqual(risk.calculate_position_size(0, 1000000, 900000), 0)
        self.assertEqual(risk.calculate_position_size(100, 100, None), 0)
        self.assertEqual(risk.calculate_position_size(100, 100, 101), 0)

    def test_pilot_allocation_cap_includes_costs(self):
        quantity = desktop.AdvancedRiskManager().calculate_position_size(10000, 100, 99.99, 1.)
        self.assertLessEqual(quantity * 100 * 1.0001 * 1.0005, 2000 + 1e-10)

    def test_roundtrip_pnl_reconciles_to_cash_after_both_entry_and_exit_fees(self):
        account = desktop.ProfessionalAccount(10000)
        account.execute_trade("TEST", "BUY", 10, 100)
        result = account.execute_trade("TEST", "SELL", 10, 101)
        self.assertAlmostEqual(result["trade"]["pnl"], account.cash - 10000)

    def test_partial_exits_allocate_entry_fees_once(self):
        account = desktop.ProfessionalAccount(10000)
        account.execute_trade("TEST", "BUY", 10, 100)
        first = account.execute_trade("TEST", "SELL", 4, 101)["trade"]["pnl"]
        second = account.execute_trade("TEST", "SELL", 6, 102)["trade"]["pnl"]
        self.assertAlmostEqual(first + second, account.cash - 10000)
        self.assertNotIn("TEST", account.positions)

    def test_nonfinite_orders_do_not_corrupt_cash(self):
        account = desktop.ProfessionalAccount(10000)
        for quantity, price in ((float("nan"), 100), (1, float("inf")), (-1, 100)):
            self.assertEqual(account.execute_trade("TEST", "BUY", quantity, price)["status"], "rejected")
        self.assertEqual(account.cash, 10000)

    def test_bad_protection_levels_and_actions_rejected(self):
        account = desktop.ProfessionalAccount()
        self.assertEqual(account.execute_trade("TEST", "BUY", 1, 100, stop_loss=110)["status"], "rejected")
        self.assertEqual(account.execute_trade("TEST", "BUY", 1, 100, take_profit=90)["status"], "rejected")
        self.assertEqual(account.execute_trade("TEST", "TYPO", 1, 100)["status"], "rejected")

    def test_configured_default_stop_and_target_apply(self):
        account = desktop.ProfessionalAccount()
        account.default_stop_loss_pct, account.default_take_profit_pct = .01, .04
        result = account.execute_trade("TEST", "BUY", 1, 100)
        fill = result["trade"]["price"]
        self.assertAlmostEqual(account.positions["TEST"]["stop_loss"], fill * .99)
        self.assertAlmostEqual(account.positions["TEST"]["take_profit"], fill * 1.04)

    def test_missing_close_quote_keeps_position(self):
        account = desktop.ProfessionalAccount()
        account.execute_trade("TEST", "BUY", 1, 100)
        self.assertEqual(account.close_single_position("TEST", 0)["status"], "rejected")
        self.assertIn("TEST", account.positions)


@unittest.skipIf(desktop is None, "Optional desktop dependencies are not installed")
class ExploratoryBacktestTests(unittest.TestCase):
    @staticmethod
    def bars():
        return [dict(timestamp=datetime(2026, 1, 1) + timedelta(hours=i),
                     open=100., high=101., low=99., close=100., volume=100.) for i in range(50)]

    def test_previous_closed_data_next_open_and_cash_reconciliation(self):
        seen = []
        class AlwaysBuy:
            def generate_signal(self, frame):
                seen.append(len(frame))
                return dict(action="BUY", confidence=.9, stop_loss=90., take_profit=110.)
        with patch.object(desktop, "MomentumStrategy", AlwaysBuy):
            report = desktop.QuantBacktester.run_backtest(self.bars(), "momentum")
        self.assertEqual(seen[0], 30)
        self.assertEqual(seen[-1], 49)
        self.assertAlmostEqual(report["trades"][0]["entry_price"], 100.01)
        self.assertGreater(report["total_fees"], 0)
        self.assertAlmostEqual(report["net_profit"], sum(trade["pnl"] for trade in report["trades"]))
        self.assertAlmostEqual(report["equity_curve"][-1], report["final_equity"])
        self.assertLess(report["return_pct"], 0)

    def test_stop_takes_precedence_when_both_levels_touch(self):
        bars = self.bars()
        bars[30].update(high=120., low=80.)
        strategy = Mock()
        strategy.generate_signal.return_value = dict(action="BUY", confidence=.9, stop_loss=90., take_profit=110.)
        with patch.object(desktop, "MomentumStrategy", return_value=strategy):
            report = desktop.QuantBacktester.run_backtest(bars, "momentum")
        self.assertEqual(report["trades"][0]["reason"], "STOP_LOSS")
        self.assertLess(report["trades"][0]["exit_price"], 90.)


@unittest.skipIf(desktop is None, "Optional desktop dependencies are not installed")
class DataSourceTests(unittest.TestCase):
    def setUp(self):
        self.app = object.__new__(desktop.ModernTradingInterface)
        self.app.guard = SimpleNamespace(halted=False)
        self.app.trading_mode = "paper"
        self.app.data_mode = "real"
        self.app.active_timeframe = "5m"
        self.app.real_market_data = SimpleNamespace(symbols={"BTC/USD": "BTC/USDT"})
        self.app._real_bars = {"BTC/USD": [{"close": 100}]}
        self.app._real_bars["BTC/USD"][0]["timestamp"] = datetime.now(timezone.utc)
        self.app.current_prices = {"BTC/USD": 100.}
        self.app._data_generation = 0
        self.app._data_lock = threading.RLock()
        self.app._last_real_poll = 0.
        self.app._real_bar_keys = {"BTC/USD": "5m"}
        self.app._quote_updated_at = {"BTC/USD": time.time()}
        self.app._bars_updated_at = {"BTC/USD": time.time()}
        self.app.market_sim = Mock()

    def test_real_mode_never_falls_back_to_simulated_candles(self):
        self.assertEqual(self.app._get_active_bars("AAPL"), [])
        self.app.market_sim.get_ohlcv.assert_not_called()

    def test_fresh_source_and_guard_both_required_for_entry(self):
        self.assertTrue(self.app._can_enter("BTC/USD"))
        self.app.guard.halted = True
        self.assertFalse(self.app._can_enter("BTC/USD"))
        self.assertTrue(self.app._has_fresh_data("BTC/USD"))

    def test_stale_unsupported_or_wrong_timeframe_cannot_enter(self):
        self.assertFalse(self.app._can_enter("AAPL"))
        self.app._quote_updated_at["BTC/USD"] -= 61
        self.assertFalse(self.app._can_enter("BTC/USD"))
        self.app._quote_updated_at["BTC/USD"] = time.time()
        self.app.active_timeframe = "1h"
        self.assertFalse(self.app._can_enter("BTC/USD"))
        self.assertEqual(self.app._get_active_bars("BTC/USD"), [])

    def test_timestamps_alone_cannot_mark_a_missing_quote_as_fresh(self):
        self.app.current_prices = {}
        self.assertFalse(self.app._has_fresh_data("BTC/USD"))

    def test_old_feed_generation_does_not_publish_prices_or_exit_positions(self):
        self.app.account = Mock()
        previous = self.app.current_prices.copy()
        self.assertIsNone(self.app._apply_feed_prices({"BTC/USD": 1}, -1, "real"))
        self.assertEqual(self.app.current_prices, previous)
        self.app.account.check_risk_triggers.assert_not_called()

    def test_feed_from_old_mode_does_not_publish_prices(self):
        self.app.account = Mock()
        self.assertIsNone(self.app._apply_feed_prices({"BTC/USD": 1}, 0, "simulated"))
        self.assertEqual(self.app.current_prices["BTC/USD"], 100.)

    def test_returning_old_candles_does_not_refresh_the_source(self):
        self.app._real_bars = {}
        self.app._real_bar_keys = {}
        self.app._bars_updated_at = {}
        self.app.real_market_data.fetch_ticker = Mock(return_value=100.)
        self.app.real_market_data.fetch_ohlcv = Mock(return_value=[dict(timestamp="2020-01-01T00:00:00Z")])
        self.app._poll_real_market()
        self.assertEqual(self.app._real_bars, {})
        self.assertFalse(self.app._has_fresh_data("BTC/USD"))

    def test_source_switch_during_ticker_fetch_discards_old_generation(self):
        self.app.current_prices = {}
        self.app._quote_updated_at = {}
        self.app._real_bars = {}
        def changed_source(symbol):
            self.app._data_generation += 1
            return 100.
        self.app.real_market_data.fetch_ticker = changed_source
        self.app.real_market_data.fetch_ohlcv = Mock()
        self.app._poll_real_market()
        self.assertEqual(self.app.current_prices, {})
        self.assertEqual(self.app._quote_updated_at, {})
        self.assertEqual(self.app._real_bars, {})
        self.app.real_market_data.fetch_ohlcv.assert_not_called()

    def test_source_switch_during_candle_fetch_discards_old_generation(self):
        self.app._real_bars = {}
        self.app._bars_updated_at = {}
        self.app._real_bar_keys = {}
        self.app.real_market_data.fetch_ticker = Mock(return_value=100.)
        def changed_source(*args):
            self.app._data_generation += 1
            self.app.current_prices = {}
            self.app._quote_updated_at = {}
            return [{"timestamp": datetime.now(timezone.utc)}]
        self.app.real_market_data.fetch_ohlcv = changed_source
        self.app._poll_real_market()
        self.assertEqual(self.app._real_bars, {})
        self.assertEqual(self.app._bars_updated_at, {})

    def test_emergency_halt_does_not_fill_from_stale_real_quote(self):
        self.app.account = desktop.ProfessionalAccount()
        self.app.account.execute_trade("BTC/USD", "BUY", 1, 100)
        self.app._quote_updated_at["BTC/USD"] = 1.
        self.app._sync_pilot_buttons = Mock()
        self.app._play_chime = Mock()
        self.app._force_chart_redraw = Mock()
        self.app._log = Mock()
        self.app.learner = Mock()
        with patch.object(desktop.messagebox, "askyesno", return_value=True), patch.object(desktop.messagebox, "showinfo"):
            self.app._emergency_halt()
        self.assertIn("BTC/USD", self.app.account.positions)
        self.assertTrue(self.app.guard.halted)

    def test_simulated_history_cannot_be_labeled_as_another_interval(self):
        self.app.data_mode = "simulated"
        self.app.tf_var = Mock()
        with patch.object(desktop.messagebox, "showinfo"):
            self.app._on_timeframe_change("1h")
        self.app.tf_var.set.assert_called_once_with("5m")
        self.assertEqual(self.app.active_timeframe, "5m")


@unittest.skipIf(desktop is None, "Optional desktop dependencies are not installed")
class DailyGuardTests(unittest.TestCase):
    def test_prior_profit_does_not_mask_today_loss(self):
        guard = desktop.TradingGuard()
        self.assertIsNone(guard.evaluate(dict(equity=12000, total_pnl=2000), "2026-01-01"))
        self.assertIn("daily", guard.evaluate(dict(equity=11400, total_pnl=1400), "2026-01-01"))

    def test_new_utc_day_sets_new_basis_without_auto_unhalting(self):
        guard = desktop.TradingGuard()
        guard.evaluate(dict(equity=10000), "2026-01-01")
        guard.evaluate(dict(equity=9500), "2026-01-01")
        self.assertTrue(guard.halted)
        guard.evaluate(dict(equity=9600), "2026-01-02")
        self.assertEqual(guard.day_start_equity, 9600)
        self.assertTrue(guard.halted)
        guard.reset()
        self.assertIsNone(guard.evaluate(dict(equity=9600), "2026-01-02"))


if __name__ == "__main__":
    unittest.main()
