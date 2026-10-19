"""Execution-cost accounting tests for the OHLC backtester."""
from datetime import datetime, timedelta
import unittest

import pandas as pd

from loki.backtest.backtesting_engine import (
    BacktestingEngine,
    ExecutionModel,
    Order,
    OrderSide,
    OrderType,
    monte_carlo_simulation,
)


class BacktestingSpreadCostTests(unittest.TestCase):
    def test_market_fill_reports_spread_separately_from_slippage(self):
        model = ExecutionModel(
            commission_pct=0.001,
            slippage_pct=0.0,
            spread_pct=0.002,
        )
        order = Order("1", datetime(2025, 1, 1), "TEST", OrderSide.BUY,
                      OrderType.MARKET, 1)

        filled, fill_price, commission, slippage = model.execute_order(
            order, current_price=100.0, bar_high=100.0, bar_low=100.0
        )

        self.assertTrue(filled)
        self.assertAlmostEqual(fill_price, 100.0)
        self.assertAlmostEqual(order.spread, 0.1)
        self.assertAlmostEqual(commission, 0.1)
        self.assertEqual(slippage, 0.0)

    def test_round_trip_trade_includes_both_sides_of_costs(self):
        engine = BacktestingEngine(
            initial_capital=10_000.0,
            commission_pct=0.001,
            slippage_pct=0.0,
            spread_pct=0.002,
        )
        entered = datetime(2025, 1, 1, 10)
        exited = entered + timedelta(hours=1)
        buy = Order("1", entered, "TEST", OrderSide.BUY, OrderType.MARKET, 1)
        sell = Order("2", exited, "TEST", OrderSide.SELL, OrderType.MARKET, 1)

        engine.orders = [buy]
        engine._process_orders(entered, 100.0, 100.0, 100.0)
        engine.orders = [sell]
        engine._process_orders(exited, 110.0, 110.0, 110.0)

        trade = engine.trades[0]
        expected_commission = buy.commission + sell.commission
        expected_spread = buy.spread + sell.spread
        expected_gross = sell.fill_price - buy.fill_price

        self.assertAlmostEqual(trade.commission, expected_commission)
        self.assertAlmostEqual(trade.spread, expected_spread)
        self.assertAlmostEqual(trade.gross_pnl, expected_gross)
        self.assertAlmostEqual(
            trade.pnl,
            expected_gross - expected_commission - buy.spread - sell.spread,
        )
        self.assertAlmostEqual(engine.capital, engine.initial_capital + trade.pnl)
        self.assertNotIn("TEST", engine.positions)

        engine.equity_curve = [engine.initial_capital, engine.capital]
        engine.timestamps = [entered, exited]
        result = engine._calculate_metrics(entered, exited)
        self.assertAlmostEqual(result.total_spread, expected_spread)
        self.assertAlmostEqual(result.total_commission, expected_commission)
        self.assertAlmostEqual(result.total_net_pnl, trade.pnl)
        self.assertAlmostEqual(result.expectancy, trade.pnl)

    def test_limit_fill_keeps_limit_price_and_charges_spread_separately(self):
        model = ExecutionModel(spread_pct=0.02)
        order = Order("1", datetime(2025, 1, 1), "TEST", OrderSide.BUY,
                      OrderType.LIMIT, 1, price=99.0)

        filled, fill_price, _commission, slippage = model.execute_order(
            order, current_price=98.0, bar_high=100.0, bar_low=97.0
        )

        self.assertTrue(filled)
        self.assertEqual(fill_price, 98.0)
        self.assertAlmostEqual(order.spread, 0.98)
        self.assertEqual(slippage, 0.0)

    def test_end_of_replay_liquidation_costs_are_in_total_return(self):
        engine = BacktestingEngine(
            initial_capital=10_000.0,
            commission_pct=0.001,
            slippage_pct=0.0,
            spread_pct=0.002,
        )
        times = pd.date_range("2025-01-01", periods=2, freq="h")
        bars = pd.DataFrame(
            {"close": [100.0, 110.0], "high": [100.0, 110.0], "low": [100.0, 110.0]},
            index=times,
        )

        def buy_once(data, positions, capital):
            if len(data) == 2:
                return [Order("1", times[1], "TEST", OrderSide.BUY, OrderType.MARKET, 1)]
            return []

        result = engine.run_backtest(bars, buy_once, symbol="TEST")

        self.assertEqual(result.total_trades, 1)
        self.assertAlmostEqual(result.total_return, result.total_net_pnl)
        self.assertLess(result.total_return, 0.0)
        self.assertGreater(result.total_spread, 0.0)
        self.assertGreater(result.total_commission, 0.0)


    def test_execution_cost_rates_reject_negative_and_non_finite_values(self):
        for name, value in (("commission_pct", -0.1), ("slippage_pct", float("nan")),
                            ("spread_pct", float("inf"))):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, "finite and non-negative"):
                    ExecutionModel(**{name: value})

    def test_execution_rejects_invalid_prices_quantity_and_bar_range(self):
        model = ExecutionModel()
        order = Order("1", datetime(2025, 1, 1), "TEST", OrderSide.BUY,
                      OrderType.MARKET, 1)
        cases = (
            ((0.0, 100.0, 99.0), "market prices"),
            ((100.0, 99.0, 100.0), "bar_high"),
        )
        for prices, message in cases:
            with self.subTest(prices=prices):
                with self.assertRaisesRegex(ValueError, message):
                    model.execute_order(order, *prices)
        order.quantity = 0
        with self.assertRaisesRegex(ValueError, "order quantity"):
            model.execute_order(order, 100.0, 101.0, 99.0)

    def test_limit_and_stop_orders_require_a_finite_positive_trigger(self):
        model = ExecutionModel()
        stamp = datetime(2025, 1, 1)
        limit = Order("1", stamp, "TEST", OrderSide.BUY, OrderType.LIMIT, 1)
        stop = Order("2", stamp, "TEST", OrderSide.SELL, OrderType.STOP, 1)
        with self.assertRaisesRegex(ValueError, "limit price"):
            model.execute_order(limit, 100.0, 101.0, 99.0)
        with self.assertRaisesRegex(ValueError, "stop price"):
            model.execute_order(stop, 100.0, 101.0, 99.0)

    def test_stop_gap_models_gap_and_percentage_slippage(self):
        model = ExecutionModel(commission_pct=0.001, slippage_pct=0.01, spread_pct=0.004)
        order = Order("1", datetime(2025, 1, 1), "TEST", OrderSide.SELL,
                      OrderType.STOP, 2, stop_price=95.0)
        filled, price, commission, slippage = model.execute_order(
            order, current_price=90.0, bar_high=101.0, bar_low=89.0
        )
        self.assertTrue(filled)
        self.assertEqual(price, 95.0)
        self.assertAlmostEqual(slippage, (5.0 + 0.95) * 2)
        self.assertAlmostEqual(commission, 95.0 * 2 * 0.001)
        self.assertAlmostEqual(order.spread, 95.0 * 0.004 / 2 * 2)

    def test_untriggered_stop_has_no_execution_costs(self):
        model = ExecutionModel()
        order = Order("1", datetime(2025, 1, 1), "TEST", OrderSide.SELL,
                      OrderType.STOP, 2, stop_price=95.0)
        filled, price, commission, slippage = model.execute_order(
            order, current_price=100.0, bar_high=101.0, bar_low=96.0
        )
        self.assertFalse(filled)
        self.assertEqual((price, commission, slippage, order.spread), (0.0, 0.0, 0.0, 0.0))

    def test_non_realistic_fills_keep_commission_but_disable_spread_and_slippage(self):
        model = ExecutionModel(commission_pct=0.001, slippage_pct=0.01,
                               use_realistic_fills=False, spread_pct=0.02)
        order = Order("1", datetime(2025, 1, 1), "TEST", OrderSide.BUY,
                      OrderType.MARKET, 2)
        filled, price, commission, slippage = model.execute_order(order, 100.0, 101.0, 99.0)
        self.assertTrue(filled)
        self.assertEqual(price, 100.0)
        self.assertAlmostEqual(commission, 0.2)
        self.assertEqual(slippage, 0.0)
        self.assertEqual(order.spread, 0.0)

    def test_partial_closes_allocate_entry_costs_and_reconcile_account_cash(self):
        engine = BacktestingEngine(
            initial_capital=10_000.0,
            commission_pct=0.01,
            slippage_pct=0.002,
            spread_pct=0.004,
        )
        opened = datetime(2025, 1, 1, 10)
        first_exit = opened + timedelta(hours=1)
        second_exit = opened + timedelta(hours=2)
        buy = Order("buy", opened, "TEST", OrderSide.BUY, OrderType.MARKET, 10)
        engine.orders = [buy]
        engine._process_orders(opened, 100.0, 100.0, 100.0)
        first = Order("sell-1", first_exit, "TEST", OrderSide.SELL, OrderType.MARKET, 4)
        engine.orders = [first]
        engine._process_orders(first_exit, 110.0, 110.0, 110.0)
        remaining = engine.positions["TEST"]
        self.assertEqual(remaining.quantity, 6)
        self.assertAlmostEqual(remaining.entry_commission, buy.commission * 0.6)
        self.assertAlmostEqual(remaining.entry_spread, buy.spread * 0.6)
        final = Order("sell-2", second_exit, "TEST", OrderSide.SELL, OrderType.MARKET, 6)
        engine.orders = [final]
        engine._process_orders(second_exit, 90.0, 90.0, 90.0)
        self.assertNotIn("TEST", engine.positions)
        self.assertEqual([trade.quantity for trade in engine.trades], [4, 6])
        self.assertAlmostEqual(sum(trade.pnl for trade in engine.trades),
                               engine.capital - engine.initial_capital)
        self.assertAlmostEqual(sum(trade.commission for trade in engine.trades),
                               buy.commission + first.commission + final.commission)

    def test_monte_carlo_repeats_with_a_fixed_seed_and_rejects_bad_parameters(self):
        engine = BacktestingEngine(initial_capital=1_000.0, commission_pct=0,
                                   slippage_pct=0, spread_pct=0)
        times = pd.date_range("2025-01-01", periods=3, freq="h")
        bars = pd.DataFrame({"close": [100.0, 101.0, 103.0],
                             "high": [100.0, 101.0, 103.0],
                             "low": [100.0, 101.0, 103.0]}, index=times)

        def buy_then_close(data, positions, capital):
            if len(data) == 2:
                return [Order("buy", times[1], "TEST", OrderSide.BUY, OrderType.MARKET, 1)]
            if len(data) == 3 and "TEST" in positions:
                return [Order("sell", times[2], "TEST", OrderSide.SELL, OrderType.MARKET, 1)]
            return []

        result = engine.run_backtest(bars, buy_then_close, symbol="TEST")
        first = monte_carlo_simulation(result, n_simulations=100, random_seed=7)
        second = monte_carlo_simulation(result, n_simulations=100, random_seed=7)
        self.assertEqual(first, second)
        self.assertEqual(first["random_seed"], 7)
        for kwargs in ({"n_simulations": 0}, {"confidence_level": 1.0},
                       {"confidence_level": float("nan")}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    monte_carlo_simulation(result, **kwargs)

    def test_engine_requires_positive_finite_starting_capital(self):
        for capital in (0.0, -1.0, float("inf")):
            with self.subTest(capital=capital):
                with self.assertRaisesRegex(ValueError, "initial_capital"):
                    BacktestingEngine(initial_capital=capital)


if __name__ == "__main__":
    unittest.main()

