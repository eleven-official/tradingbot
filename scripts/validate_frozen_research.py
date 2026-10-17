"""Freeze research code/configuration, then evaluate operator-supplied observations.

No downloading, tuning, live orders, credentials or provider calls. Run `freeze`
before `evaluate`. An existing freeze/result is never overwritten. Dataset paths
refer to operator-provided snapshots with source and usage-rights metadata. This
tool neither acquires nor verifies commercial data rights. See
docs/research/VALIDATION.md for the manifest schema and sample limitations.
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.fusion.quant import ShadowConfig, _features, _replay, _win_interval
from core.strategy_lab import LabConfig, TrendParameters, _select, _simulate, validate_bars

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
MONTHS = (1, 4, 7, 10)
SOURCE_FILES = (
    "core/strategy_lab.py", "core/fusion/quant.py", "third_party/vibe_trading/indicators.py",
    "third_party/vibe_trading/factor_analysis.py",
    "scripts/validate_frozen_research.py",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def configs(periods: int):
    trend = LabConfig(periods_per_year=periods, max_exposure=.20)
    fusion = ShadowConfig(periods_per_year=periods, max_exposure=.20)
    return trend, fusion


def load_manifest(directory: Path, interval: str, usage_context: str) -> dict:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("interval") != interval or manifest.get("quote_currency") != "USDT":
        raise ValueError("Dataset manifest has an unexpected interval or quote currency")
    rights = manifest.get("usage_rights", {})
    if (not isinstance(manifest.get("source"), str) or not manifest["source"].strip() or
        not isinstance(rights, dict) or not isinstance(rights.get("basis"), str) or not rights["basis"].strip() or
        not isinstance(rights.get("reference"), str) or not rights["reference"].strip() or
        not isinstance(rights.get("permitted_uses"), list) or usage_context not in rights["permitted_uses"]):
        raise ValueError(f"Manifest needs source and usage_rights (basis, reference, permitted_uses including {usage_context}); operator must supply appropriately licensed data")
    return manifest


def load_snapshot(directory: Path, name: str, manifest: dict) -> list:
    metadata = manifest["snapshots"][name]
    filename = metadata.get("file", f"{name}.json")
    if not isinstance(filename, str) or Path(filename).name != filename or not filename.endswith(".json"):
        raise ValueError("Snapshot filenames must be JSON basenames within the supplied data directory")
    path = directory / filename
    if digest(path) != metadata["sha256"]:
        raise ValueError(f"Normalized snapshot checksum differs: {name}")
    rows = json.loads(path.read_text(encoding="utf-8"))
    bars = validate_bars(rows)
    if len(bars) != metadata["rows"] or bars[0].timestamp.isoformat() != metadata["start"] or bars[-1].timestamp.isoformat() != metadata["end"]:
        raise ValueError(f"Normalized snapshot metadata differs: {name}")
    seconds = 86400 if manifest["interval"] == "1d" else 300
    if any((right.timestamp - left.timestamp).total_seconds() != seconds for left, right in zip(bars, bars[1:])):
        raise ValueError(f"Snapshot is not contiguous: {name}")
    if manifest["interval"] == "5m":
        first = bars[0].timestamp
        expected = calendar.monthrange(first.year, first.month)[1] * 288
        if len(bars) != expected or (first.day, first.hour, first.minute, first.second, first.microsecond) != (1, 0, 0, 0, 0):
            raise ValueError(f"Intraday snapshot must contain one complete UTC calendar month: {name}")
    return rows


def verify_archives(directory: Path, manifest: dict) -> None:
    # Only hashes are read here; prices are not inspected to construct a freeze.
    for source in manifest.get("sources", []):
        filename = source["url"].rsplit("/", 1)[-1]
        if "/" in filename or "\\" in filename:
            raise ValueError("Invalid archive filename")
        path = directory / "raw" / filename
        if digest(path) != source["sha256"]:
            raise ValueError(f"Archive checksum differs: {filename}")
        checksum = path.with_suffix(".zip.CHECKSUM").read_text(encoding="ascii").split()
        if len(checksum) != 2 or checksum[0].lower() != source["sha256"] or checksum[1].lstrip("*") != filename:
            raise ValueError(f"Official checksum sidecar differs: {filename}")


def freeze(args) -> None:
    if args.freeze.exists():
        raise ValueError("Freeze already exists; it cannot be overwritten")
    daily = load_manifest(args.daily, "1d", args.usage_context)
    intraday = load_manifest(args.intraday, "5m", args.usage_context)
    # Record code/configuration and snapshot identities before loading any test
    # prices. Loading manifests/checksums does not inspect price observations.
    record = {"protocol_version": 2, "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
              "source_sha256": {name: digest(ROOT / name) for name in SOURCE_FILES},
              "daily_manifest_sha256": digest(args.daily / "manifest.json"),
              "intraday_manifest_sha256": digest(args.intraday / "manifest.json"),
              "usage_context": args.usage_context,
              "data_permission_evidence": {"daily": daily["usage_rights"], "intraday": intraday["usage_rights"],
                  "limitation": "Operator-supplied permission assertions and references; not independently authenticated by Loki."},
              "configs": {label: {"trend": asdict(configs(periods)[0]), "fusion": asdict(configs(periods)[1])}
                          for label, periods in (("1d", 365), ("5m", 365 * 288))},
              "protocol": {"daily_training": "2021-01-01 through 2024-12-31",
                           "daily_holdout": "2025-01-01 through 2025-12-31",
                           "intraday_training": "Each matching calendar month of 2024, evaluated separately.",
                           "intraday_holdout": "2025 January, April, July and October, each separate; first 60 bars warm up only.",
                           "trend_selection": "Existing fixed 3-pair candidate set, training-only Sharpe plus drawdown; cash if unconvincing.",
                           "fusion_selection": "No fitting or search; fixed Vibe-derived indicator conjunction and risk settings.",
                           "costs": "10 bps fee and 5 bps slippage per side; repeat at 2x and 3x, without reselection.",
                           "independent_pools": "Each symbol/month starts a separate 10000 USDT pool; no portfolio-level return aggregation.",
                           "evidence_limit": "Historical operator-reserved sample, not a prospective live trial or guarantee. Prior inspection cannot be established by the tool."},
              "selected_trend": {}}
    # Persist the immutable pre-price checkpoint first. A second sidecar records
    # training-only selections. This ensures even a failed training stage leaves
    # an audit of the code and protocol that existed before holdout evaluation.
    write_new(args.freeze, record)
    verify_archives(args.daily, daily)
    verify_archives(args.intraday, intraday)
    decisions = {}
    for symbol in SYMBOLS:
        training_manifest = {**daily, "snapshots": daily["training_snapshots"]}
        training = load_snapshot(args.daily, symbol, training_manifest)
        training_bars = validate_bars(training)
        if training_bars[0].timestamp.isoformat() != "2021-01-01T00:00:00+00:00" or training_bars[-1].timestamp.isoformat() != "2024-12-31T00:00:00+00:00":
            raise ValueError("Daily training snapshot must cover exactly 2021 through 2024; holdout prices belong in a separate file")
        parameters, score, trials = _select(training_bars, len(training), configs(365)[0])
        decisions[f"{symbol}-1d"] = {"parameters": asdict(parameters) if parameters else None, "train_score": score,
                                     "trial_ledger": trials, "training_rows": len(training)}
        for month in MONTHS:
            name = f"{symbol}-5m-2024-{month:02d}"
            rows = load_snapshot(args.intraday, name, intraday)
            if any(not row["timestamp"].startswith(f"2024-{month:02d}-") for row in rows):
                raise ValueError("Intraday training timestamps must belong to the named 2024 month")
            parameters, score, trials = _select(validate_bars(rows), len(rows), configs(365 * 288)[0])
            decisions[f"{symbol}-5m-{month:02d}"] = {"parameters": asdict(parameters) if parameters else None,
                "train_score": score, "trial_ledger": trials, "training_rows": len(rows)}
    selections = {"freeze_sha256": digest(args.freeze), "selected_at_utc": datetime.now(timezone.utc).isoformat(),
                  "selected_trend": decisions, "holdout_price_observations_inspected": False}
    selection_path = args.freeze.with_suffix(".selections.json")
    write_new(selection_path, selections)
    print(json.dumps({"freeze": str(args.freeze), "freeze_sha256": digest(args.freeze),
                      "selections": str(selection_path), "selections_sha256": digest(selection_path),
                      "training_sets": len(decisions), "holdout_evaluated": False}))


def compact_result(name, strategy, bars, start, config, parameters=None):
    if strategy == "fusion":
        feature_rows = _features(bars, config.periods_per_year)
        results = [_replay(bars, feature_rows, config, multiplier, start_index=start) for multiplier in (1, 2, 3)]
        summary = results[0]["summary"]
        trades = results[0]["trades"]
        curve = results[0]["equity"]
        stress = [{"cost_multiplier": multiplier, **{key: result["summary"][key]
                  for key in ("total_return", "max_drawdown", "win_rate", "total_trades")}}
                  for multiplier, result in zip((1, 2, 3), results)]
    else:
        results = [_simulate(bars, start, len(bars), parameters, config, config.initial_capital, multiplier)
                   for multiplier in (1, 2, 3)]
        summary, trades, curve = results[0]["metrics"], results[0]["trades"], results[0]["equity"]
        stress = [{"cost_multiplier": multiplier, **{key: result["metrics"][key]
                  for key in ("total_return", "max_drawdown", "win_rate", "total_trades")}}
                  for multiplier, result in zip((1, 2, 3), results)]
    baseline_config = configs(config.periods_per_year)[0]
    benchmark = _simulate(bars, start, len(bars), None, baseline_config, config.initial_capital, benchmark=True)["metrics"]
    days = (bars[-1].timestamp - bars[start].timestamp).total_seconds() / 86400
    return {"dataset": name, "strategy": strategy, "parameters": asdict(parameters) if parameters else None,
            "test_start": bars[start].timestamp.isoformat(), "test_end": bars[-1].timestamp.isoformat(),
            "test_bars": len(bars) - start, "warmup_bars": start, "calendar_days": days,
            "summary": summary, "benchmark": {key: benchmark[key] for key in ("total_return", "max_drawdown", "total_fees")},
            "cost_stress": stress, "trades": trades,
            "equity_curve": [{"timestamp": bars[start + i].timestamp.isoformat(), "equity": value}
                             for i, value in enumerate(curve) if i % max(1, len(curve) // 150) == 0 or i == len(curve) - 1],
            "win_rate_target": .70, "observed_target_met": summary["win_rate"] is not None and summary["win_rate"] >= .70,
            "descriptive_lower_bound_met": summary["win_rate_ci95"] is not None and summary["win_rate_ci95"][0] >= .70,
            "future_win_rate_guaranteed": False}


def aggregate(results):
    output = []
    for strategy in ("trend", "fusion"):
        for interval in ("1d", "5m"):
            rows = [row for row in results if row["strategy"] == strategy and f"-{interval}" in row["dataset"]]
            trades = [trade for row in rows for trade in row["trades"]]
            wins = sum(trade["pnl"] > 0 for trade in trades)
            output.append({"strategy": strategy, "interval": interval, "independent_test_pools": len(rows),
                           "total_trades": len(trades), "winning_trades": wins,
                           "win_rate": wins / len(trades) if trades else None,
                           "descriptive_win_rate_ci95": _win_interval(wins, len(trades)),
                           "positive_net_return_pools": sum(row["summary"]["total_return"] > 0 for row in rows),
                           "return_range": [min(row["summary"]["total_return"] for row in rows), max(row["summary"]["total_return"] for row in rows)],
                           "note": "Pooled trades are correlated across symbols/time; Wilson interval is descriptive only. Returns are separate account pools."})
    return output


def evaluate(args):
    if args.output.exists():
        raise ValueError("Result path exists; reserved-sample results cannot be overwritten")
    freeze_record = json.loads(args.freeze.read_text(encoding="utf-8"))
    selections = json.loads(args.freeze.with_suffix(".selections.json").read_text(encoding="utf-8"))
    if selections["freeze_sha256"] != digest(args.freeze):
        raise ValueError("Freeze checkpoint differs from its training selections")
    for name, expected in freeze_record["source_sha256"].items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"Frozen code changed before evaluation: {name}")
    for directory, key in ((args.daily, "daily"), (args.intraday, "intraday")):
        if digest(directory / "manifest.json") != freeze_record[f"{key}_manifest_sha256"]:
            raise ValueError("Dataset manifest changed after freeze")
    usage_context = freeze_record["usage_context"]
    daily, intraday = load_manifest(args.daily, "1d", usage_context), load_manifest(args.intraday, "5m", usage_context)
    verify_archives(args.daily, daily)
    verify_archives(args.intraday, intraday)
    results = []
    for symbol in SYMBOLS:
        rows = load_snapshot(args.daily, symbol, daily)
        bars = validate_bars(rows)
        start = next((i for i, bar in enumerate(bars) if bar.timestamp.year == 2025), None)
        if start is None:
            raise ValueError("Daily snapshot has no 2025 test observations")
        training = load_snapshot(args.daily, symbol, {**daily, "snapshots": daily["training_snapshots"]})
        if rows[:start] != training or bars[-1].timestamp.isoformat() != "2025-12-31T00:00:00+00:00":
            raise ValueError("Daily holdout snapshot must contain the identical training history followed by complete 2025")
        selection = selections["selected_trend"][f"{symbol}-1d"]["parameters"]
        for strategy in ("trend", "fusion"):
            config = (LabConfig if strategy == "trend" else ShadowConfig)(**freeze_record["configs"]["1d"][strategy])
            result = compact_result(f"{symbol}-1d-2025", strategy, bars, start, config,
                                    TrendParameters(**selection) if selection and strategy == "trend" else None)
            results.append(result)
            print(json.dumps({"completed": result["dataset"], "strategy": strategy, "summary": result["summary"]}), flush=True)
        for month in MONTHS:
            name = f"{symbol}-5m-2025-{month:02d}"
            bars = validate_bars(load_snapshot(args.intraday, name, intraday))
            if any(bar.timestamp.year != 2025 or bar.timestamp.month != month for bar in bars):
                raise ValueError("Intraday holdout timestamps must belong to the named 2025 month")
            selection = selections["selected_trend"][f"{symbol}-5m-{month:02d}"]["parameters"]
            for strategy in ("trend", "fusion"):
                config = (LabConfig if strategy == "trend" else ShadowConfig)(**freeze_record["configs"]["5m"][strategy])
                result = compact_result(name, strategy, bars, 60, config,
                                        TrendParameters(**selection) if selection and strategy == "trend" else None)
                results.append(result)
                print(json.dumps({"completed": name, "strategy": strategy, "trades": result["summary"]["total_trades"],
                                  "win_rate": result["summary"]["win_rate"], "return": result["summary"]["total_return"]}), flush=True)
    record = {"evaluated_at_utc": datetime.now(timezone.utc).isoformat(), "freeze_sha256": digest(args.freeze),
              "selections_sha256": digest(args.freeze.with_suffix(".selections.json")),
              "source": daily["source"], "quote_currency": "USDT", "protocol": freeze_record["protocol"],
              "usage_context": usage_context, "data_permission_evidence": freeze_record["data_permission_evidence"],
              "aggregate": aggregate(results), "results": results,
              "conclusion": "The 70% future winning-trade target is not guaranteed. Read observed results and correlated-sample limitations.",
              "limitations": ["One exchange, three surviving crypto assets, daily 2025 and four selected 2025 intraday months only.",
                              "Test observations were reserved for this audit, not collected prospectively after deployment.",
                              "Training data had already been examined in earlier research; no parameter changes are made after this freeze.",
                              "Partial pooled-trade independence and historical costs do not establish a persistent trading edge.",
                              "Cash is a valid training result; zero trades mean no evidence about win rate.",
                              "Funding, taxes, order-book depth, outages, venue minimums and tick sizes are not modeled.",
                              "Monthly 5m snapshots are separate; gaps are never represented as contiguous candles.",
                              "Performance of separate asset/month pools is not the return of a simultaneously traded portfolio."]}
    write_new(args.output, record)
    print(json.dumps({"output": str(args.output), "sha256": digest(args.output), "aggregate": record["aggregate"]}, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "evaluate"))
    parser.add_argument("--daily", type=Path, default=ROOT / ".test-tmp/licensed-research/daily")
    parser.add_argument("--intraday", type=Path, default=ROOT / ".test-tmp/licensed-research/intraday")
    parser.add_argument("--usage-context", choices=("commercial_research", "personal_research"), default="commercial_research")
    parser.add_argument("--freeze", type=Path, default=ROOT / ".test-tmp/licensed-research/audit/freeze.json")
    parser.add_argument("--output", type=Path, default=ROOT / ".test-tmp/licensed-research/audit/results.json")
    args = parser.parse_args(argv)
    try:
        (freeze if args.action == "freeze" else evaluate)(args)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"Research audit failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
