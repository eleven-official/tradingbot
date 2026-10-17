"""Evaluate a local OHLCV CSV/JSON file without broker credentials or orders."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from core.strategy_lab import evaluate_strategy


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="CSV with timestamp/open/high/low/close/volume, or a JSON list of bars")
    parser.add_argument("--output", type=Path, default=Path("reports/strategy_lab_report.json"), help="Save the complete JSON research report")
    parser.add_argument("--config", type=Path, help="Optional JSON object of LabConfig settings")
    parser.add_argument("--fee-bps", type=float, help="Fee on each entry/exit in basis points")
    parser.add_argument("--slippage-bps", type=float, help="Adverse slippage on each entry/exit in basis points")
    parser.add_argument("--periods-per-year", type=int, help="Bar frequency used for annualization (252 session days, 365 continuous daily bars)")
    args = parser.parse_args(argv)
    try:
        if args.output.resolve() == args.input.resolve() or (args.config and args.output.resolve() == args.config.resolve()):
            raise ValueError("Output must be a different file from the dataset and research config")
        config = {}
        if args.config:
            config = json.loads(args.config.read_text(encoding="utf-8-sig"))
            if not isinstance(config, dict):
                raise ValueError("Research config must be a JSON object")
        for option in ("fee_bps", "slippage_bps", "periods_per_year"):
            if getattr(args, option) is not None:
                config[option] = getattr(args, option)
        with args.input.open(encoding="utf-8-sig", newline="") as source:
            if args.input.suffix.lower() == ".json":
                bars = json.load(source)
            elif args.input.suffix.lower() == ".csv":
                reader = csv.DictReader(source)
                bars = []
                for bar in reader:
                    bars.append(bar)
                    if len(bars) > 10_000:
                        raise ValueError("A research run is limited to 10000 bars")
            else:
                raise ValueError("Input must be a .csv or .json file")
        report = evaluate_strategy(bars, config)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    except (OSError, ValueError, TypeError, csv.Error) as exc:
        print(f"Research failed: {exc}", file=sys.stderr)
        return 2

    summary = report["summary"]
    print(f"Research status: {report['status']}")
    print(f"Forward net return: {summary['total_return']:.2%}; baseline: {report['benchmark']['total_return']:.2%}")
    print(f"Maximum drawdown: {summary['max_drawdown']:.2%}; closed trades: {summary['total_trades']}")
    if summary["win_rate"] is not None:
        lower, upper = summary["win_rate_ci95"]
        print(f"Observed win rate: {summary['win_rate']:.2%}; descriptive 95% interval: {lower:.2%} to {upper:.2%}")
    for reason in report["rejection_reasons"]:
        print(f"- {reason}")
    print(f"Report: {args.output.resolve()}")
    print("Historical research cannot guarantee profits. Live trading remains disabled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
