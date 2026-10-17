#!/usr/bin/env python3
"""LOKI v8 command-line interface.

Examples:
    python loki_bot.py backtest --symbols AAPL SPY BTC-USD
    python loki_bot.py walkforward --symbol AAPL
    python loki_bot.py scan
    python loki_bot.py paper --once
    python loki_bot.py paper --interval 60
"""
from __future__ import annotations

import argparse
import logging
import sys

from loki_v8 import config as _config
from loki_v8.backtest import monte_carlo
from loki_v8.bot import LokiBot


def _setup_logging(level: str = "INFO"):
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def cmd_backtest(bot: LokiBot, args):
    results = bot.backtest_all(args.symbols)
    for sym, r in results.items():
        print(r.summary())
        mc = monte_carlo(r.trades)
        print(f"  Monte Carlo: mean {mc['mean']:+.2f}% | 5-95% [{mc['p5']:+.2f}%, {mc['p95']:+.2f}%] | "
              f"P(profitable) {mc['p_positive']:.0f}%")
        print()


def cmd_walkforward(bot: LokiBot, args):
    folds = bot.walk_forward(args.symbol, n_splits=args.splits)
    print(f"=== Walk-forward: {args.symbol} ({len(folds)} folds) ===")
    for i, r in enumerate(folds, 1):
        print(f"[fold {i}] return {r.total_return_pct:+.2f}% | trades {r.total_trades} | "
              f"win {r.win_rate_pct:.0f}% | PF {r.profit_factor:.2f} | maxDD {r.max_drawdown_pct:.1f}%")


def cmd_scan(bot: LokiBot, args):
    signals = bot.scan(args.symbols)
    if not signals:
        print("No signals.")
        return
    for s in signals:
        print(f"{s.action:4s} {s.symbol:12s} score={s.score:+6.1f} conf={s.confidence:.0f}% "
              f"entry={s.entry_price:.2f} stop={s.stop_loss:.2f} target={s.take_profit:.2f}")


def cmd_run(bot: LokiBot, args):
    if args.mode:
        bot.switch_mode(args.mode)
    bot.run(interval=args.interval, once=args.once)


def main(argv=None):
    p = argparse.ArgumentParser(prog="loki_bot", description="LOKI v8 trading engine")
    p.add_argument("--mode", choices=["paper", "live"], default=None,
                   help="override the configured trading mode")
    p.add_argument("--symbols", nargs="*", default=None, help="symbols to operate on")
    p.add_argument("--log", default="INFO")

    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("backtest", help="backtest the ensemble strategy")
    b.set_defaults(func=cmd_backtest)

    w = sub.add_parser("walkforward", help="walk-forward out-of-sample validation")
    w.add_argument("--symbol", default="AAPL")
    w.add_argument("--splits", type=int, default=4)
    w.set_defaults(func=cmd_walkforward)

    s = sub.add_parser("scan", help="scan for current signals")
    s.set_defaults(func=cmd_scan)

    r = sub.add_parser("paper", help="run the paper/live trading loop")
    r.add_argument("--interval", type=float, default=60.0)
    r.add_argument("--once", action="store_true", help="run a single iteration then exit")
    r.set_defaults(func=cmd_run)

    args = p.parse_args(argv)
    _setup_logging(args.log)
    bot = LokiBot(_config.default_config())
    args.func(bot, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
