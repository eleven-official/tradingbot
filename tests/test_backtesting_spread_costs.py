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


if __name__ == "__main__":
    unittest.main()

