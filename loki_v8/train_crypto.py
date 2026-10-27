"""Crypto-focused training pass for the Loki v8 strategy book.

Why this exists separately from ``train.train()``: a crypto book is a
different animal from an equity book, and the honest differences have to be
baked into the protocol rather than left to defaults.

* **24/7 tape.** Daily crypto bars are 365/year, not 252. Sharpe and every
  annualised metric silently lie if the wrong constant is used.
* **Higher realised volatility.** The default ``max_atr_pct`` gate that
  keeps equities out of crash-era entries throws away most of a crypto tape;
  the refinement ladder is allowed to widen it, and the hurdle set is scaled
  to crypto noise instead of equity noise.
* **Small-sample traps.** A 90% hit rate on 16 out-of-sample crypto trades
  is noise. The hurdle set here asks for a win rate a crypto tape can
  actually sustain *together with* a profit factor floor, so the trainer
  cannot win by shrinking the sample.
* **Parallelism.** One symbol takes ~4 minutes because the multi-factor
  layer evaluates ~370 backtests. Training ten symbols serially is a coffee
  break; training them across a process pool is not.

The pass is additive: it trains the crypto universe, computes a
crypto-only consensus, and merges every symbol it did NOT evaluate forward
from the existing book. Nothing that was already verified is dropped.

Run:
    python -m loki_v8.train_crypto
    python -m loki_v8.train_crypto --rounds 3 --workers 6
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# The crypto book. Chosen for liquidity and for having enough history to
# split honestly (warmup 250 bars + 30 tradeable + a 20% holdout).
DEFAULT_CRYPTO_UNIVERSE: Tuple[str, ...] = (
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "BNB-USD",
    "XRP-USD",
    "ADA-USD",
    "DOGE-USD",
    "LINK-USD",
    "AVAX-USD",
    "LTC-USD",
)

# Daily bars in a calendar year. Crypto never closes.
CRYPTO_BARS_PER_YEAR = 365

# Hurdles a crypto profile has to clear OUT OF SAMPLE before it is called a
# good trade. Deliberately not the 90% equity target: on a tape this noisy
# that number is only reachable by over-fitting the development window.
#
# The hit-rate bar sits low on purpose. Under the old 70% target the only way
# to clear it was a 0.62-ATR take-profit against a 4.25-ATR stop — a geometry
# that wins small and often, then gives several wins back on one loss. Win
# rate is therefore a weak description of an edge, and profit factor plus a
# survivable drawdown describe it better. Return still has to be positive and
# the month coverage still has to clear a majority, so a profile cannot pass
# on one lucky quarter.
CRYPTO_HURDLES: Dict[str, float] = {
    "trades": 10.0,
    "return_pct": 0.0,          # >0, comparison is "gt"
    "profit_factor": 1.5,
    "max_drawdown_pct": -30.0,
    "win_rate_pct": 45.0,
    "month_profit_rate_pct": 55.0,
}

# Execution grid for crypto. Symmetric enough that neither side of the trade
# is structurally favoured: the take-profit multiple can exceed the stop
# multiple, so a 40% hit rate is allowed to be profitable. The hit-rate grid
# this replaces capped take-profit at 1.0 ATR against 3.5–7.0 ATR stops, which
# made the sweep a search for the smallest possible target rather than for an
# edge. 24 combinations, swept against the factor presets.
CRYPTO_GRID: Dict[str, List[Any]] = {
    "signal_threshold": [8.0, 14.0, 20.0],
    "stop_loss_atr": [2.0, 3.5, 5.0],
    "take_profit_atr": [1.5, 2.5, 4.0],
    "max_hold_bars": [30, 90],
    "breakeven_atr": [0.0, 1.0],
    "require_trend_filter": [True],
}


def _grid_size(grid: Dict[str, List[Any]]) -> int:
    """Number of distinct parameter combinations a grid sweeps."""
    size = 1
    for values in grid.values():
        size *= max(1, len(values))
    return size

SNAPSHOT_PATH = Path(__file__).parent / "training_report_snapshot.json"


@dataclass
class CryptoJob:
    symbol: str
    round_no: int
    grid: Optional[Dict[str, List[Any]]]
    optimization_period: str
    timeframe: str
    windows: Tuple[int, ...] = (5, 7, 10)
    synthetic_seeds: Tuple[int, ...] = (11, 23, 37, 53, 71)
    robustness: bool = True


def _train_job(job: CryptoJob) -> Dict[str, Any]:
    """Train one symbol in this process and return a serialisable report dict.

    Mirrors ``train.train()``'s per-symbol handling (80/20 reserve, factor
    regime distribution, final holdout that is never used for selection)
    without touching disk, so it is safe to run inside a process pool.
    """
    from loki_v8.backtest import bars_per_year_for, run_backtest
    from loki_v8.config import LokiConfig
    from loki_v8.data import get_provider, is_crypto
    from loki_v8.regime import regime_distribution
    from loki_v8.strategy import EnsembleStrategy
    from loki_v8.train import (
        SymbolReport,
        _cfg_with,
        _data_quality_note,
        _oos_metrics,
        train_symbol,
    )

    symbol = job.symbol
    cfg = LokiConfig(period=job.optimization_period, timeframe=job.timeframe)
    grid = job.grid or CRYPTO_GRID
    bpy = bars_per_year_for(job.timeframe, crypto=is_crypto(symbol))

    try:
        history = get_provider().fetch_history(symbol, job.optimization_period, job.timeframe)
    except Exception as exc:  # noqa: BLE001 - one bad ticker must not abort the sweep
        return SymbolReport(symbol=symbol, error=f"data fetch failed: {exc}").to_dict()

    if history is None or history.empty:
        return SymbolReport(symbol=symbol, error="data fetch returned no bars").to_dict()

    split = int(len(history) * 0.8)
    development = history.iloc[:split].copy()

    regime_dist: Dict[str, float] = {}
    try:
        regime_dist = regime_distribution(EnsembleStrategy(cfg).compute_factors(development))
    except Exception:  # noqa: BLE001 - descriptive only
        regime_dist = {}

    started = time.perf_counter()
    report = train_symbol(
        development,
        cfg,
        symbol,
        grid=grid,
        train_frac=0.7,
        top_n=4,
        bars_per_year=bpy,
        optimize_weights=True,
        regime_dist=regime_dist,
        objective="expectancy",
        hurdle_targets=CRYPTO_HURDLES,
        walk_forward=True,
        folds=2,
    )
    payload = report.to_dict()
    payload["refine_round"] = job.round_no
    payload["train_seconds"] = round(time.perf_counter() - started, 1)
    payload["data_quality"] = _data_quality_note(development)
    payload["bars_per_year"] = bpy

    # Final holdout — the last 20% the legend above was never allowed to
    # see during the grid sweep. Recorded, never used for selection.
    if report.ok and report.best_params:
        try:
            candidate = _cfg_with(cfg, report.best_params)
            warmup_start = max(0, split - max(candidate.lookback_bars, 250))
            frame = EnsembleStrategy(candidate).score_frame(history)
            frame.loc[frame.index < history.index[split], "score"] = 0.0
            result = run_backtest(
                history.iloc[warmup_start:],
                candidate,
                symbol=symbol,
                bars_per_year=bpy,
                frame=frame.iloc[warmup_start:],
            )
            holdout_trades = [t for t in result.trades if t.entry_time >= history.index[split]]
            payload["final_holdout"] = {
                "start": str(history.index[split]),
                "end": str(history.index[-1]),
                "bars": len(history) - split,
                "metrics": _oos_metrics(holdout_trades, candidate.initial_cash),
                "used_for_selection": False,
            }
        except Exception as exc:  # noqa: BLE001
            payload["final_holdout"] = {"error": str(exc), "used_for_selection": False}

    # Robustness gate. Two checks that the optimizer's sample cannot fake:
    # the same parameters re-run over shorter trailing windows, and the same
    # parameters on bootstrapped tapes built from this symbol's own returns.
    # ``good`` only survives if the hurdle set, both checks, and the data all
    # agree — a profile that lives entirely in one decade is not a profile.
    if job.robustness and report.ok and report.best_params:
        from loki_v8 import synthetic as synth

        hurdle_good = bool(payload.get("good"))
        try:
            window_check = synth.validate_windows(
                history,
                report.best_params,
                cfg,
                symbol,
                bpy,
                windows=job.windows,
            )
        except Exception as exc:  # noqa: BLE001 - a broken check is a failed check
            window_check = {"windows": [], "passes": False, "error": str(exc)}
        synthetic_bars = max(600, int(len(history) * 0.6))
        try:
            synthetic_check = synth.validate_synthetic(
                history,
                report.best_params,
                cfg,
                symbol,
                bpy,
                seeds=job.synthetic_seeds,
                bars=synthetic_bars,
            )
        except Exception as exc:  # noqa: BLE001
            synthetic_check = {"tapes": [], "passes": False, "error": str(exc), "reasons": [str(exc)]}

        payload["hurdles_passed"] = hurdle_good
        payload["window_validation"] = window_check
        payload["synthetic_validation"] = synthetic_check
        gate = gate_verdict(hurdle_good, window_check, synthetic_check)
        payload["good"] = gate["good"]
        payload["validation_gate"] = {k: v for k, v in gate.items() if k != "good"}
    return payload


def gate_verdict(
    hurdles: bool,
    window: Optional[Dict[str, Any]],
    synthetic: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Combine the hurdle set with both robustness checks into one verdict.

    Pure and cheap so the composition itself can be tested without a sweep:
    ``good`` survives only when all three agree. A missing check is a failed
    check — silence is never a pass.

    ``verdict`` distinguishes three states, because "the tapes lost money" and
    "the tapes barely traded" are not the same finding and a wide exit geometry
    produces the second one routinely:

    - ``verified``   — all three checks passed.
    - ``research only`` — a check ran and the edge failed it.
    - ``untested``   — a check could not reach the fill floor, so it never got
      to measure the edge. ``good`` is still False (thin evidence is never
      promotion), but the label says why.
    """
    from loki_v8 import synthetic as synth

    windows_ok = bool(window.get("passes")) if window else False
    synthetic_ok = bool(synthetic.get("passes")) if synthetic else False
    good = bool(hurdles and windows_ok and synthetic_ok)

    # `powered` is only meaningfully absent on results produced before the
    # flag existed; treat those as powered so old snapshots keep their label.
    synthetic_powered = bool(synthetic.get("powered", True)) if synthetic else True
    unpowered = bool(synthetic and not synthetic_ok and not synthetic_powered)
    if good:
        verdict = "verified"
    elif unpowered:
        verdict = "untested"
    else:
        verdict = "research only"

    return {
        "hurdles": bool(hurdles),
        "windows": windows_ok,
        "synthetic": synthetic_ok,
        "synthetic_powered": synthetic_powered,
        "good": good,
        "verdict": verdict,
        "detail": synth.summarise(window, synthetic),
    }


def _load_existing() -> Dict[str, Any]:
    try:
        if SNAPSHOT_PATH.exists():
            return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("existing snapshot unreadable (%s); starting fresh", exc)
    return {}


def _merge(existing: Dict[str, Any], fresh: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Fresh entries win — unless the fresh one failed and the stored one did not.

    A crashed worker or a transient fetch error must never demote a verified
    profile back to untrained: the published book only loses a symbol when the
    new run genuinely failed to train it *and* there was nothing valid to keep.
    """
    by_symbol: Dict[str, Dict[str, Any]] = {}
    for entry in existing.get("symbols", []) or []:
        symbol = str(entry.get("symbol") or "").upper()
        if symbol:
            by_symbol[symbol] = entry
    for entry in fresh:
        symbol = str(entry.get("symbol") or "").upper()
        if not symbol:
            continue
        previous = by_symbol.get(symbol)
        if previous and previous.get("ok") and not entry.get("ok"):
            kept = dict(previous)
            kept["stale_reason"] = str(entry.get("error") or "re-run failed")[:160]
            by_symbol[symbol] = kept
            continue
        by_symbol[symbol] = entry
    return [by_symbol[key] for key in sorted(by_symbol)]


def _hurdle_summary(entry: Dict[str, Any]) -> str:
    if not entry.get("ok"):
        return f"failed: {entry.get('error', '')[:60]}"
    passed = sum(1 for h in entry.get("hurdles", []) if h.get("ok"))
    total = len(entry.get("hurdles", []))
    return f"{passed}/{total} hurdles"


def run(
    universe: Optional[Tuple[str, ...]] = None,
    rounds: int = 2,
    workers: Optional[int] = None,
    optimization_period: str = "10y",
    timeframe: str = "1d",
    write_snapshot: bool = True,
    windows: Tuple[int, ...] = (5, 7, 10),
    synthetic_seeds: Tuple[int, ...] = (11, 23, 37, 53, 71),
    robustness: bool = True,
    custom_grid: Optional[Dict[str, List[Any]]] = None,
) -> Dict[str, Any]:
    """Train the crypto universe and write the merged snapshot."""
    from loki_v8.train import consensus_params

    symbols = tuple(universe or DEFAULT_CRYPTO_UNIVERSE)
    rounds = max(1, int(rounds))
    workers = max(1, int(workers or min(6, (os.cpu_count() or 2))))

    started = time.perf_counter()
    results: Dict[str, Dict[str, Any]] = {}

    def sweep(jobs: List[CryptoJob], label: str) -> None:
        if not jobs:
            return
        print(f"[{label}] training {len(jobs)} symbol(s) across {workers} process(es)", flush=True)
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_train_job, job): job for job in jobs}
            for future in as_completed(futures):
                job = futures[future]
                try:
                    payload = future.result()
                except Exception as exc:  # noqa: BLE001 - a crashed worker is one symbol
                    payload = {"symbol": job.symbol, "ok": False, "error": f"worker crashed: {exc}"}
                results[job.symbol] = payload
                metrics = payload.get("validation_metrics") or {}
                gate = payload.get("validation_gate") or {}
                print(
                    f"  {job.symbol:>10}  good={str(payload.get('good')):>5}  "
                    f"{_hurdle_summary(payload):<14} "
                    f"trades={metrics.get('trades', 0):>3} "
                    f"ret={metrics.get('return_pct', 0):>6}% "
                    f"win={metrics.get('win_rate_pct', 0):>5}% "
                    f"pf={metrics.get('profit_factor', 0):>5} "
                    f"{payload.get('train_seconds', '?')}s  "
                    f"[{gate.get('detail', 'no robustness check')}]",
                    flush=True,
                )

    sweep(
        [
            CryptoJob(
                s,
                1,
                custom_grid,
                optimization_period,
                timeframe,
                windows,
                synthetic_seeds,
                robustness,
            )
            for s in symbols
        ],
        "round 1",
    )

    for round_no in range(2, rounds + 1):
        from loki_v8.train import _refined_grid

        # A symbol with no usable result is retried, not skipped: an `ok`
        # profile that missed a hurdle gets a refined grid, and a symbol whose
        # worker died gets another attempt instead of being quietly dropped.
        failing = [
            symbol
            for symbol in symbols
            if not (results.get(symbol, {}).get("ok") and results[symbol].get("good"))
        ]
        if not failing:
            print(f"[round {round_no}] every symbol cleared its hurdles — stopping", flush=True)
            break
        jobs = [
            CryptoJob(
                symbol,
                round_no,
                _refined_grid(CRYPTO_GRID, (results.get(symbol) or {}).get("best_params") or {}),
                optimization_period,
                timeframe,
                windows,
                synthetic_seeds,
                robustness,
            )
            for symbol in failing
        ]
        sweep(jobs, f"round {round_no}")

    fresh = [results[s] for s in symbols if s in results]
    ordered = [entry for entry in fresh if entry.get("symbol")]
    merged = _merge(_load_existing(), ordered)

    crypto_trainable = [e for e in ordered if e.get("ok") and e.get("best_params")]
    all_trainable = [e for e in merged if e.get("ok") and e.get("best_params")]

    # Consensus is built from crypto profiles that cleared EVERY gate when any
    # did; otherwise from every trained profile, so the book still has a
    # starting point. Which one it was is recorded — never implied.
    verified = [e for e in crypto_trainable if e.get("good")]
    consensus_source = "verified" if verified else ("trained" if crypto_trainable else "none")
    consensus_pool = verified or crypto_trainable

    report: Dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "period": optimization_period,
        "timeframe": timeframe,
        "train_frac": 0.7,
        "grid_size": _grid_size(CRYPTO_GRID),
        "weights_tested": 14,
        "optimize_weights": True,
        "objective": "expectancy",
        "selection": "walk_forward",
        "hurdle_targets": dict(CRYPTO_HURDLES),
        "refine_rounds_target": rounds,
        "refine_rounds_used": rounds,
        "crypto_universe": list(symbols),
        "bars_per_year": CRYPTO_BARS_PER_YEAR,
        "symbols": merged,
        "consensus": consensus_params(all_trainable) if all_trainable else None,
        "crypto_consensus": consensus_params(consensus_pool) if consensus_pool else None,
        "consensus_source": consensus_source,
        "verified_symbols": [e.get("symbol") for e in verified],
        "robustness": {
            "enabled": bool(robustness),
            "windows": list(windows),
            "synthetic_seeds": list(synthetic_seeds),
            "verified": len(verified),
            "trained": len(crypto_trainable),
            "gate": (
                "good requires the OOS hurdle set AND every trailing window AND the "
                "bootstrapped-tape check"
            ),
        },
        "evaluation_protocol": {
            "development_fraction": 0.8,
            "final_holdout_fraction": 0.2,
            "validation_used_for_refinement": True,
            "final_holdout_used_for_selection": False,
            "cross_window_validation": bool(robustness),
            "synthetic_tape_validation": bool(robustness),
            "rank_objective": "expectancy",
            "finalist_selection": "walk_forward",
            "note": (
                "Crypto book trained on 80% of each symbol's daily history; the last 20% "
                "is reported as final_holdout and never used for selection. Candidates are "
                "ranked on mean return per trade with a profit-factor floor, not hit rate, "
                "then the finalists are re-run on two anchored forward folds and the winner "
                "is the one whose worst fold survived. Profiles are then re-run on trailing "
                "5/7/10y slices and on block-bootstrapped tapes of the same symbol's returns. "
                "All of these reuse the same underlying history, so they measure regime "
                "dependence and path dependence, not independent evidence of future returns."
            ),
        },
        "training_seconds": round(time.perf_counter() - started, 1),
    }

    if write_snapshot:
        SNAPSHOT_PATH.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"\nsnapshot written: {SNAPSHOT_PATH} ({len(merged)} symbols)", flush=True)

    print(
        f"\ndone in {report['training_seconds']}s — "
        f"{sum(1 for e in ordered if e.get('good'))}/{len(ordered)} crypto symbols cleared "
        f"hurdles + windows + synthetic tapes",
        flush=True,
    )
    consensus = report.get("crypto_consensus") or {}
    if consensus:
        print("crypto consensus:", json.dumps(consensus.get("params", {})), flush=True)
        print("consensus support:", consensus.get("support_pct"), "%", flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the Loki crypto strategy book.")
    parser.add_argument("--symbols", default="", help="comma-separated; default is the built-in crypto universe")
    parser.add_argument("--rounds", type=int, default=2, help="refinement rounds (default 2)")
    parser.add_argument("--workers", type=int, default=0, help="processes (0 = auto)")
    parser.add_argument("--period", default="10y", help="yfinance history window (default 10y)")
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument(
        "--windows",
        default="5,7,10",
        help="trailing year slices each profile is re-tested on (default 5,7,10)",
    )
    parser.add_argument(
        "--synthetic-seeds",
        default="11,23,37,53,71",
        help="seeds for the bootstrapped tapes (default 11,23,37,53,71)",
    )
    parser.add_argument(
        "--no-robustness",
        action="store_true",
        help="skip the window + synthetic gate (report the hurdle result only)",
    )
    parser.add_argument("--no-write", action="store_true", help="report only, do not touch the snapshot")
    parser.add_argument("--grid", default="", help="custom grid as key=val1,val2... pairs (e.g. 'signal_threshold=8,14 stop_loss_atr=2,3')")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    universe = tuple(s.strip().upper() for s in args.symbols.split(",") if s.strip()) or None
    windows = tuple(int(v) for v in args.windows.split(",") if v.strip()) or (5, 7, 10)
    seeds = tuple(int(v) for v in args.synthetic_seeds.split(",") if v.strip()) or (11, 23, 37, 53, 71)
    # Parse custom grid if provided
    custom_grid = None
    if args.grid.strip():
        custom_grid = {}
        for pair in args.grid.split():
            if "=" in pair:
                k, vals = pair.split("=", 1)
                custom_grid[k.strip()] = [float(v) if "." in v else int(v) for v in vals.split(",") if v.strip()]
        print(f"Using custom grid: {json.dumps(custom_grid)}", flush=True)
    run(
        universe=universe,
        rounds=args.rounds,
        workers=args.workers or None,
        optimization_period=args.period,
        timeframe=args.timeframe,
        write_snapshot=not args.no_write,
        windows=windows,
        synthetic_seeds=seeds,
        robustness=not args.no_robustness,
        custom_grid=custom_grid,
    )


if __name__ == "__main__":
    main()
