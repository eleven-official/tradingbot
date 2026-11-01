"""LOKI v8 — rigorous walk-forward validation with purging & embargo.

Standard walk-forward still leaks: the validation fold immediately follows
the training fold, so the market regime hasn't changed. The optimizer can
"cheat" by fitting to the transition period.

This module implements:
1. **Purged K-Fold** — gap between train and test (no shared regime)
2. **Embargo** — additional gap after test to prevent future leakage
3. **Combinatorial Purged CV** — multiple train/test splits, aggregated
4. **Path-wise CV** — for time series, every split is a path, not random

All splits are fully deterministic (seed-based) and logged so results
are exactly reproducible.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .config import LokiConfig
from .backtest import run_backtest, BacktestResult
from .strategy import EnsembleStrategy

logger = logging.getLogger(__name__)

STATE_DIR = Path("state") / "validation"
STATE_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class FoldResult:
    """Result of one validation fold."""
    fold_id: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    purge_bars: int
    embargo_bars: int
    metrics: Dict[str, float]
    params: Dict[str, Any]
    passed: bool
    error: str = ""


@dataclass
class ValidationReport:
    """Complete validation report."""
    symbol: str
    method: str  # "purged_kfold", "combinatorial", "pathwise"
    n_folds: int
    purge_bars: int
    embargo_bars: int
    folds: List[FoldResult]
    aggregate: Dict[str, float]
    passed: bool
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    data_fingerprint: str = ""


def data_fingerprint(df: pd.DataFrame) -> str:
    """Deterministic fingerprint of a dataframe for reproducibility."""
    columns = [name for name in ("open", "high", "low", "close", "volume") if name in df]
    values = df[columns].astype(float).round(10)
    payload = pd.util.hash_pandas_object(values, index=True).to_numpy().tobytes()
    digest = hashlib.blake2b(payload, digest_size=16).hexdigest()
    return f"{len(df)}b:{digest}"


def purged_kfold_indices(
    n_bars: int,
    n_splits: int = 5,
    purge_bars: int = 20,
    embargo_bars: int = 5,
) -> List[Tuple[np.ndarray, np.ndarray]]:
    """Generate purged K-fold indices for time series.

    Each fold:
    - Train: [0, test_start - purge_bars)
    - Test: [test_start, test_end)
    - Embargo: [test_end, test_end + embargo_bars) — excluded from next train

    The purge removes the transition period where regime is shared.
    The embargo prevents using future information that "leaks" via
    overlapping features (rolling windows, indicators with lookback).
    """
    if n_splits < 2 or purge_bars < 0 or embargo_bars < 0:
        raise ValueError("Need at least two splits and nonnegative gaps")
    if n_bars < n_splits * 30:
        raise ValueError(f"Need at least {n_splits * 30} bars for {n_splits} folds")

    fold_size = n_bars // n_splits
    indices = []

    for i in range(n_splits):
        test_start = i * fold_size
        test_end = n_bars if i == n_splits - 1 else (i + 1) * fold_size

        # Purge: gap before test
        train_end = max(0, test_start - purge_bars)

        # Train is everything before the purge
        train_idx = np.arange(0, train_end)

        # Test is the fold
        test_idx = np.arange(test_start, test_end)

        if len(train_idx) > 50 and len(test_idx) > 20:
            indices.append((train_idx, test_idx))

    return indices


def combinatorial_purged_cv_indices(
    n_bars: int,
    n_splits: int = 4,
    n_test_folds: int = 2,
    purge_bars: int = 20,
    embargo_bars: int = 5,
) -> List[Tuple[np.ndarray, np.ndarray]]:
    """Combinatorial Purged CV: all combinations of test folds.

    Instead of sequential folds, we choose all combinations of
    n_test_folds from n_splits total folds. This gives more robust
    aggregation and tests the model against more regime transitions.

    Total combinations = C(n_splits, n_test_folds)
    """
    from itertools import combinations

    if n_splits < 2 or not 1 <= n_test_folds < n_splits or purge_bars < 0 or embargo_bars < 0:
        raise ValueError("Invalid combinatorial folds or negative gaps")
    if n_bars < n_splits * 30:
        raise ValueError("Insufficient bars for combinatorial folds")
    fold_size = n_bars // n_splits
    fold_bounds = [(i * fold_size, n_bars if i == n_splits - 1 else (i + 1) * fold_size) for i in range(n_splits)]

    all_combos = list(combinations(range(n_splits), n_test_folds))
    indices = []

    for combo in all_combos:
        test_ranges = [fold_bounds[i] for i in combo]
        test_start = min(r[0] for r in test_ranges)
        test_end = max(r[1] for r in test_ranges)

        # Purge before test
        train_end = max(0, test_start - purge_bars)
        train_idx = np.arange(0, train_end)

        # Test is union of selected folds
        test_parts = [np.arange(r[0], r[1]) for r in test_ranges]
        test_idx = np.concatenate(test_parts)

        if len(train_idx) > 50 and len(test_idx) > 20:
            indices.append((train_idx, test_idx))

    return indices


def pathwise_cv_indices(
    n_bars: int,
    min_train_bars: int = 500,
    step_bars: int = 252,  # ~1 year
    test_bars: int = 60,   # ~quarter
    purge_bars: int = 20,
    embargo_bars: int = 5,
) -> List[Tuple[np.ndarray, np.ndarray]]:
    """Path-wise CV: expanding window with fixed test horizon.

    Train: [0, t)
    Purge: [t - purge, t)
    Test: [t, t + test_bars)
    Embargo: [t + test_bars, t + test_bars + embargo)
    Next train: [0, t + test_bars + embargo)

    This mimics real deployment: model trained on all history up to t,
    tested on the next quarter, then retrained.
    """
    if min_train_bars < 1 or step_bars < 1 or test_bars < 1 or purge_bars < 0 or embargo_bars < 0:
        raise ValueError("Walk-forward windows must be positive and gaps nonnegative")
    indices = []
    t = min_train_bars

    while t + test_bars <= n_bars:
        train_end = max(0, t - purge_bars)
        train_idx = np.arange(0, train_end)
        test_idx = np.arange(t, min(t + test_bars, n_bars))

        if len(train_idx) > 50 and len(test_idx) > 10:
            indices.append((train_idx, test_idx))

        t += step_bars

    return indices


def run_fold(
    df: pd.DataFrame,
    train_idx: np.ndarray,
    test_idx: np.ndarray,
    params: Dict[str, Any],
    base_cfg: LokiConfig,
    bars_per_year: int,
    symbol: str,
) -> Tuple[Dict[str, float], List]:
    """Run backtest on one fold."""
    # A single backtest would otherwise trade the unselected gap between test
    # blocks, falsely counting those returns as out-of-sample performance.
    if len(test_idx) == 0 or np.any(np.diff(test_idx) != 1):
        raise ValueError("Fold backtests require a nonempty contiguous test interval")
    train_df = df.iloc[train_idx].copy()
    test_df = df.iloc[test_idx].copy()

    # Need warmup bars for indicators on test
    warmup = max(base_cfg.lookback_bars, 60)
    if len(train_idx) > 0:
        # Include warmup bars before test
        test_start = test_idx[0]
        val_start = max(0, test_start - warmup)
        val_df = df.iloc[val_start:test_idx[-1]+1].copy()
    else:
        val_df = test_df

    cfg = LokiConfig(**{**base_cfg.to_dict(), **params})
    strategy = EnsembleStrategy(cfg)

    # Score once
    scored = strategy.score_frame(val_df)
    # Zero out scores before test start
    if len(train_idx) > 0:
        test_start_time = val_df.index[test_start - val_start] if test_start >= val_start else val_df.index[0]
        scored.loc[scored.index < test_start_time, "score"] = 0.0

    result = run_backtest(
        val_df,
        cfg,
        symbol=symbol,
        bars_per_year=bars_per_year,
        frame=scored,
    )

    # Only count trades that ENTERED during test period
    test_start_time = df.index[test_idx[0]]
    oos_trades = [t for t in result.trades if t.entry_time >= test_start_time]

    if not oos_trades:
        return {"trades": 0, "return_pct": 0.0, "win_rate_pct": 0.0,
                "profit_factor": 0.0, "max_drawdown_pct": 0.0}, []

    pnls = [t.pnl for t in oos_trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    pf = (gross_win / gross_loss) if gross_loss > 0 else (999.0 if gross_win > 0 else 0.0)

    # Include starting equity; otherwise the first losing trade has zero drawdown.
    equity_curve = pd.Series([0.0] + pnls).cumsum()
    max_dd = float((equity_curve - equity_curve.cummax()).min())

    return {
        "trades": len(pnls),
        "return_pct": round(sum(pnls) / cfg.initial_cash * 100.0, 2),
        "win_rate_pct": round(len(wins) / len(pnls) * 100.0, 1),
        "profit_factor": round(pf, 2),
        "max_drawdown_pct": round(max_dd / cfg.initial_cash * 100.0, 2),
    }, oos_trades


def validate_params_purged(
    df: pd.DataFrame,
    params: Dict[str, Any],
    base_cfg: LokiConfig,
    symbol: str,
    bars_per_year: int,
    method: str = "purged_kfold",
    n_splits: int = 5,
    purge_bars: int = 20,
    embargo_bars: int = 5,
    min_trades: int = 5,
    min_profit_factor: float = 1.1,
    min_return_pct: float = 0.0,
) -> ValidationReport:
    """Run full purged validation on a parameter set."""
    n_bars = len(df)
    fp = data_fingerprint(df)

    if method == "purged_kfold":
        fold_indices = purged_kfold_indices(n_bars, n_splits, purge_bars, embargo_bars)
    elif method == "combinatorial":
        fold_indices = combinatorial_purged_cv_indices(n_bars, n_splits, 2, purge_bars, embargo_bars)
    elif method == "pathwise":
        fold_indices = pathwise_cv_indices(n_bars, 500, 252, 60, purge_bars, embargo_bars)
    else:
        raise ValueError(f"Unknown method: {method}")

    folds = []
    for fold_id, (train_idx, test_idx) in enumerate(fold_indices):
        try:
            metrics, trades = run_fold(df, train_idx, test_idx, params, base_cfg, bars_per_year, symbol)

            passed = (
                metrics["trades"] >= min_trades
                and metrics["profit_factor"] >= min_profit_factor
                and metrics["return_pct"] > min_return_pct
            )

            folds.append(FoldResult(
                fold_id=fold_id,
                train_start=str(df.index[train_idx[0]]) if len(train_idx) else "",
                train_end=str(df.index[train_idx[-1]]) if len(train_idx) else "",
                test_start=str(df.index[test_idx[0]]),
                test_end=str(df.index[test_idx[-1]]),
                purge_bars=purge_bars,
                embargo_bars=embargo_bars,
                metrics=metrics,
                params=params,
                passed=passed,
            ))
        except Exception as e:
            logger.warning("Fold %d failed: %s", fold_id, e)
            folds.append(FoldResult(
                fold_id=fold_id,
                train_start="", train_end="", test_start="", test_end="",
                purge_bars=purge_bars, embargo_bars=embargo_bars,
                metrics={}, params=params, passed=False, error=str(e)
            ))

    # Aggregate
    passed_folds = [f for f in folds if f.passed]
    all_passed = len(passed_folds) == len(folds) and len(folds) > 0

    if folds:
        aggregate = {
            "mean_return_pct": round(np.mean([f.metrics.get("return_pct", 0) for f in folds]), 2),
            "mean_win_rate_pct": round(np.mean([f.metrics.get("win_rate_pct", 0) for f in folds]), 1),
            "mean_profit_factor": round(np.mean([f.metrics.get("profit_factor", 0) for f in folds]), 2),
            "mean_max_drawdown_pct": round(np.mean([f.metrics.get("max_drawdown_pct", 0) for f in folds]), 2),
            "mean_trades": round(np.mean([f.metrics.get("trades", 0) for f in folds]), 1),
            "pass_rate": round(len(passed_folds) / len(folds) * 100.0, 1),
            "worst_fold_return_pct": round(min(f.metrics.get("return_pct", 0) for f in folds), 2),
            "worst_fold_profit_factor": round(min(f.metrics.get("profit_factor", 0) for f in folds), 2),
        }
    else:
        aggregate = {}

    return ValidationReport(
        symbol=symbol,
        method=method,
        n_folds=len(folds),
        purge_bars=purge_bars,
        embargo_bars=embargo_bars,
        folds=folds,
        aggregate=aggregate,
        passed=all_passed,
        data_fingerprint=fp,
    )


def save_validation_report(report: ValidationReport, path: Optional[Path] = None) -> Path:
    if path is None:
        path = STATE_DIR / f"validation_{report.symbol}_{report.method}_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "symbol": report.symbol,
        "method": report.method,
        "n_folds": report.n_folds,
        "purge_bars": report.purge_bars,
        "embargo_bars": report.embargo_bars,
        "folds": [
            {
                "fold_id": f.fold_id,
                "train_start": f.train_start,
                "train_end": f.train_end,
                "test_start": f.test_start,
                "test_end": f.test_end,
                "purge_bars": f.purge_bars,
                "embargo_bars": f.embargo_bars,
                "metrics": f.metrics,
                "params": f.params,
                "passed": f.passed,
                "error": f.error,
            }
            for f in report.folds
        ],
        "aggregate": report.aggregate,
        "passed": report.passed,
        "generated_at": report.generated_at,
        "data_fingerprint": report.data_fingerprint,
    }
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return path


def print_validation_report(report: ValidationReport) -> None:
    print(f"\n{'='*80}")
    print(f"PURGED VALIDATION — {report.symbol} ({report.method})")
    print(f"{'='*80}")
    print(f"Data fingerprint: {report.data_fingerprint}")
    print(f"Folds: {report.n_folds} | Purge: {report.purge_bars} bars | Embargo: {report.embargo_bars} bars")
    print(f"Overall: {'PASSED' if report.passed else 'FAILED'}")

    print(f"\n{'Fold':>4} {'Train Period':<25} {'Test Period':<25} {'Trades':>6} {'Ret%':>8} {'WR%':>7} {'PF':>6} {'DD%':>7} {'Pass':>6}")
    print(f"{'-'*80}")
    for f in report.folds:
        m = f.metrics
        train_p = f"{f.train_start[:10]}→{f.train_end[:10]}" if f.train_start else "N/A"
        test_p = f"{f.test_start[:10]}→{f.test_end[:10]}"
        print(f"{f.fold_id:>4} {train_p:<25} {test_p:<25} "
              f"{m.get('trades', 0):>6} {m.get('return_pct', 0):>8.2f} "
              f"{m.get('win_rate_pct', 0):>7.1f} {m.get('profit_factor', 0):>6.2f} "
              f"{m.get('max_drawdown_pct', 0):>7.2f} {'YES' if f.passed else 'NO':>6}")

    if report.aggregate:
        a = report.aggregate
        print(f"\nAggregate: mean_ret={a['mean_return_pct']:.2f}% "
              f"mean_wr={a['mean_win_rate_pct']:.1f}% "
              f"mean_pf={a['mean_profit_factor']:.2f} "
              f"mean_dd={a['mean_max_drawdown_pct']:.2f}% "
              f"pass_rate={a['pass_rate']:.1f}%")
        print(f"Worst fold: ret={a['worst_fold_return_pct']:.2f}% pf={a['worst_fold_profit_factor']:.2f}")


# ---------------------------------------------------------------------------
# Integration with trainer
# ---------------------------------------------------------------------------

def validate_best_params(
    df: pd.DataFrame,
    best_params: Dict[str, Any],
    base_cfg: LokiConfig,
    symbol: str,
    bars_per_year: int,
    methods: Sequence[str] = ("purged_kfold", "pathwise"),
    **kwargs,
) -> Dict[str, ValidationReport]:
    """Validate best params with multiple methods."""
    reports = {}
    for method in methods:
        try:
            report = validate_params_purged(
                df, best_params, base_cfg, symbol, bars_per_year, method=method, **kwargs
            )
            reports[method] = report
        except Exception as e:
            logger.warning("Validation method %s failed: %s", method, e)
            reports[method] = ValidationReport(
                symbol=symbol, method=method, n_folds=0, purge_bars=0, embargo_bars=0,
                folds=[], aggregate={}, passed=False, error=str(e)
            )
    return reports


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run purged validation on trained params")
    parser.add_argument("--symbol", default="BTC-USD")
    parser.add_argument("--period", default="3y")
    parser.add_argument("--method", choices=["purged_kfold", "combinatorial", "pathwise"], default="purged_kfold")
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--purge", type=int, default=20)
    parser.add_argument("--embargo", type=int, default=5)
    args = parser.parse_args()

    from .data import get_provider
    from .train import load_report, apply_params

    provider = get_provider()
    history = provider.fetch_history(args.symbol, args.period, "1d")
    if history is None or history.empty:
        print(f"No data for {args.symbol}")
        return

    # Load trained params
    report = load_report()
    params, _ = report.get("consensus", {}).get("params", {}), "consensus"
    if not params:
        # Try symbol-specific
        for entry in report.get("symbols", []):
            if entry.get("symbol") == args.symbol and entry.get("best_params"):
                params = entry["best_params"]
                break

    if not params:
        print("No trained params found")
        return

    cfg = LokiConfig(period=args.period, timeframe="1d")
    from .train import apply_params
    apply_params(cfg, params)

    bars_per_year = 365 if args.symbol.endswith("-USD") else 252

    report = validate_params_purged(
        history, params, cfg, args.symbol, bars_per_year,
        method=args.method, n_splits=args.n_splits,
        purge_bars=args.purge, embargo_bars=args.embargo
    )

    print_validation_report(report)
    path = save_validation_report(report)
    print(f"\nSaved: {path}")


if __name__ == "__main__":
    main()
