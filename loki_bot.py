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


def cmd_council(bot: LokiBot, args):
    report = bot.agent_scan(args.symbols)
    print(f"=== Multi-Agent Council Report ({len(report.get('trails', {}))} symbols) ===")
    for sym, trail in report.get("trails", {}).items():
        director = next((t for t in trail if t.get("agent") == "director"), {})
        quant = next((t for t in trail if t.get("agent") == "quant"), {})
        risk = next((t for t in trail if t.get("agent") == "risk"), {})
        execution = next((t for t in trail if t.get("agent") == "execution"), {})

        action = quant.get("action", "HOLD")
        score = quant.get("score", 0.0)
        sq = quant.get("squeeze_status", "OFF")
        print(f"\n[{sym}] Action: {action} | Score: {score:+.1f} | Squeeze: {sq}")
        print(f"  Thesis   : {director.get('thesis', '')}")
        print(f"  Risk     : {'APPROVED' if risk.get('approved') else 'BLOCKED'} (qty={risk.get('qty', 0):.2f}, reason={risk.get('reason')})")
        if quant.get("reasons"):
            print(f"  Factors  : {', '.join(quant['reasons'])}")
        if execution.get("executed"):
            print(f"  Hermes   : Executed on {bot.mode.upper()}")


def cmd_web(bot: LokiBot, args):
    import uvicorn
    print(f"🚀 Starting Loki Quantum Web Terminal on http://{args.host}:{args.port}")
    uvicorn.run("loki.api.server:app", host=args.host, port=args.port, reload=args.reload)


def main(argv=None):
    p = argparse.ArgumentParser(prog="loki_bot", description="LOKI Quantum Trading Engine")
    p.add_argument("--mode", choices=["paper", "live"], default=None,
                   help="override the configured trading mode")
    p.add_argument("--symbols", nargs="*", default=None, help="symbols to operate on")
    p.add_argument("--log", default="INFO")

    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("backtest", help="backtest the ensemble strategy")
    b.add_argument("--symbols", nargs="*", default=None, help="symbols to operate on")
    b.set_defaults(func=cmd_backtest)

    w = sub.add_parser("walkforward", help="walk-forward out-of-sample validation")
    w.add_argument("--symbol", default="AAPL")
    w.add_argument("--splits", type=int, default=4)
    w.set_defaults(func=cmd_walkforward)

    s = sub.add_parser("scan", help="scan for current signals")
    s.add_argument("--symbols", nargs="*", default=None, help="symbols to operate on")
    s.set_defaults(func=cmd_scan)

    c = sub.add_parser("council", help="run multi-agent deliberation council")
    c.add_argument("--symbols", nargs="*", default=None, help="symbols to operate on")
    c.set_defaults(func=cmd_council)

    wb = sub.add_parser("web", help="start real-time web command terminal")
    wb.add_argument("--host", default="127.0.0.1")
    wb.add_argument("--port", type=int, default=8000)
    wb.add_argument("--reload", action="store_true")
    wb.set_defaults(func=cmd_web)

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
