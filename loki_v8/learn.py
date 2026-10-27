"""Learning from mistakes: analyse paper sessions, feed failures back into training.

This module closes the loop between simulated execution and parameter search.
It reads the crypto paper ledger, classifies every losing trade by regime,
holding time, signal strength, and exit reason, then produces concrete
parameter adjustments or a focused retraining grid for the next sweep.

Usage:
    python -m loki_v8.learn                    # analyse latest session
    python -m loki_v8.learn --retrain          # emit a focused grid + CLI for train_crypto
    python -m loki_v8.learn --session state/crypto_paper_sessions/session_20261027T143759.json
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from loki_v8.data import get_provider
from loki_v8.synthetic import evaluate_params
from loki_v8.config import LokiConfig

logger = logging.getLogger(__name__)

LEDGER_PATH = Path("state") / "crypto_paper_ledger.jsonl"
SESSION_DIR = Path("state") / "crypto_paper_sessions"

# Regime buckets based on 20-bar ATR percentile
REGIME_BUCKETS = ["low_vol", "normal", "high_vol"]

# Holding time buckets (bars)
HOLD_BUCKETS = [(0, 5), (5, 15), (15, 30), (30, 60), (60, 999)]

# Signal strength buckets (threshold multiple)
SIGNAL_BUCKETS = [(0, 1.0), (1.0, 1.5), (1.5, 2.0), (2.0, 999)]

# Exit reason taxonomy
EXIT_REASONS = ["stop_loss", "take_profit", "max_hold", "trailing", "breakeven", "signal_reversal"]


def load_latest_session() -> Optional[Dict[str, Any]]:
    """Load the most recent paper session JSON."""
    if not SESSION_DIR.exists():
        return None
    sessions = sorted(SESSION_DIR.glob("session_*.json"))
    if not sessions:
        return None
    with sessions[-1].open("r", encoding="utf-8") as f:
        return json.load(f)


def load_ledger(since_session: Optional[str] = None) -> List[Dict[str, Any]]:
    """Load all ledger entries, optionally filtered by session_id."""
    if not LEDGER_PATH.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with LEDGER_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
                if since_session and row.get("session_id") != since_session:
                    continue
                rows.append(row)
            except json.JSONDecodeError:
                continue
    return rows


def fetch_history_for_analysis(symbol: str, period: str = "2y") -> pd.DataFrame:
    """Fetch history for regime/ATR computation at trade timestamps."""
    provider = get_provider()
    return provider.fetch_history(symbol, period, "1d")


def compute_atr_percentile(
    history: pd.DataFrame,
    timestamp: pd.Timestamp,
    lookback: int = 20,
) -> float:
    """ATR percentile at a given timestamp (0-1)."""
    try:
        idx = history.index.get_indexer([timestamp], method="nearest")[0]
        if idx < lookback:
            return 0.5
        window = history.iloc[idx - lookback : idx]
        high = window["high"]
        low = window["low"]
        close = window["close"]
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(lookback).mean().iloc[-1]
        atr_series = tr.rolling(lookback).mean().dropna()
        if len(atr_series) < 10:
            return 0.5
        return float((atr_series < atr).mean())
    except Exception:
        return 0.5


def classify_regime(atr_pct: float) -> str:
    """Map ATR percentile to regime bucket."""
    if atr_pct < 0.33:
        return "low_vol"
    elif atr_pct < 0.66:
        return "normal"
    return "high_vol"


def classify_holding_bars(bars: int) -> str:
    for lo, hi in HOLD_BUCKETS:
        if lo <= bars < hi:
            return f"hold_{lo}_{hi if hi < 999 else 'inf'}"
    return "hold_60_inf"


def classify_signal_strength(signal_val: float, threshold: float) -> str:
    if threshold <= 0:
        return "unknown"
    ratio = signal_val / threshold
    for lo, hi in SIGNAL_BUCKETS:
        if lo <= ratio < hi:
            return f"sig_{lo}_{hi if hi < 999 else 'inf'}"
    return "sig_2.0_inf"


def analyse_losses(
    trades: List[Dict[str, Any]],
    histories: Dict[str, pd.DataFrame],
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Classify every losing trade and compute failure statistics."""
    threshold = params.get("signal_threshold", 10.0)
    stop_atr = params.get("stop_loss_atr", 3.0)
    tp_atr = params.get("take_profit_atr", 2.0)
    max_hold = params.get("max_hold_bars", 30)

    losses_by_regime = defaultdict(lambda: {"count": 0, "pnl": 0.0, "trades": []})
    losses_by_hold = defaultdict(lambda: {"count": 0, "pnl": 0.0, "trades": []})
    losses_by_signal = defaultdict(lambda: {"count": 0, "pnl": 0.0, "trades": []})
    losses_by_exit = defaultdict(lambda: {"count": 0, "pnl": 0.0, "trades": []})

    total_losses = 0
    total_loss_pnl = 0.0

    for t in trades:
        if t["pnl"] >= 0:
            continue
        total_losses += 1
        total_loss_pnl += t["pnl"]

        symbol = t["symbol"]
        history = histories.get(symbol)
        if history is None or history.empty:
            continue

        entry_ts = pd.Timestamp(t["entry_time"])
        exit_ts = pd.Timestamp(t["exit_time"])
        bars_held = t.get("holding_bars", 0)
        exit_reason = t.get("exit_reason", "unknown")

        # Regime at entry
        atr_pct = compute_atr_percentile(history, entry_ts)
        regime = classify_regime(atr_pct)

        # Signal strength (approximate from params and outcome)
        # We don't have the raw signal value in the ledger, so approximate
        # from how far the stop was hit vs tp
        signal_bucket = classify_signal_strength(threshold, threshold)  # placeholder

        hold_bucket = classify_holding_bars(bars_held)

        losses_by_regime[regime]["count"] += 1
        losses_by_regime[regime]["pnl"] += t["pnl"]
        losses_by_regime[regime]["trades"].append(t)

        losses_by_hold[hold_bucket]["count"] += 1
        losses_by_hold[hold_bucket]["pnl"] += t["pnl"]
        losses_by_hold[hold_bucket]["trades"].append(t)

        losses_by_signal[signal_bucket]["count"] += 1
        losses_by_signal[signal_bucket]["pnl"] += t["pnl"]
        losses_by_signal[signal_bucket]["trades"].append(t)

        losses_by_exit[exit_reason]["count"] += 1
        losses_by_exit[exit_reason]["pnl"] += t["pnl"]
        losses_by_exit[exit_reason]["trades"].append(t)

    return {
        "total_losses": total_losses,
        "total_loss_pnl": round(total_loss_pnl, 2),
        "by_regime": {k: {"count": v["count"], "total_pnl": round(v["pnl"], 2), "avg_pnl": round(v["pnl"] / v["count"], 2) if v["count"] else 0}
                      for k, v in losses_by_regime.items()},
        "by_hold": {k: {"count": v["count"], "total_pnl": round(v["pnl"], 2), "avg_pnl": round(v["pnl"] / v["count"], 2) if v["count"] else 0}
                    for k, v in losses_by_hold.items()},
        "by_signal": {k: {"count": v["count"], "total_pnl": round(v["pnl"], 2), "avg_pnl": round(v["pnl"] / v["count"], 2) if v["count"] else 0}
                      for k, v in losses_by_signal.items()},
        "by_exit": {k: {"count": v["count"], "total_pnl": round(v["pnl"], 2), "avg_pnl": round(v["pnl"] / v["count"], 2) if v["count"] else 0}
                    for k, v in losses_by_exit.items()},
    }


def suggest_parameter_adjustments(
    analysis: Dict[str, Any],
    current_params: Dict[str, Any],
) -> Dict[str, Any]:
    """Generate concrete parameter changes based on failure patterns."""
    suggestions = {"adjustments": [], "rationale": []}
    params = dict(current_params)

    # If most losses are stop_loss in high_vol -> widen stop, reduce size
    by_regime = analysis.get("by_regime", {})
    high_vol_losses = by_regime.get("high_vol", {}).get("count", 0)
    total_losses = analysis.get("total_losses", 1)

    if high_vol_losses / total_losses > 0.4:
        new_stop = round(params.get("stop_loss_atr", 3.0) * 1.25, 2)
        suggestions["adjustments"].append(
            f"stop_loss_atr: {params.get('stop_loss_atr')} -> {new_stop} (high-vol stop losses dominate)"
        )
        params["stop_loss_atr"] = new_stop

    # If losses cluster in short holds -> increase max_hold or widen stop
    by_hold = analysis.get("by_hold", {})
    short_hold_losses = sum(v["count"] for k, v in by_hold.items() if k.startswith("hold_0") or k.startswith("hold_5"))
    if short_hold_losses / total_losses > 0.5:
        new_hold = params.get("max_hold_bars", 30) + 15
        suggestions["adjustments"].append(
            f"max_hold_bars: {params.get('max_hold_bars')} -> {new_hold} (losses cluster in short holds)"
        )
        params["max_hold_bars"] = new_hold

    # If take_profit rarely hit -> reduce target or increase stop
    by_exit = analysis.get("by_exit", {})
    tp_hits = by_exit.get("take_profit", {}).get("count", 0)
    sl_hits = by_exit.get("stop_loss", {}).get("count", 0)
    if sl_hits > 0 and tp_hits / max(1, sl_hits) < 0.3:
        new_tp = round(max(1.0, params.get("take_profit_atr", 2.0) * 0.85), 2)
        suggestions["adjustments"].append(
            f"take_profit_atr: {params.get('take_profit_atr')} -> {new_tp} (take-profit hit rate {tp_hits}/{sl_hits+tp_hits})"
        )
        params["take_profit_atr"] = new_tp

    # If signal_reversal losses are high -> raise threshold
    rev_losses = by_exit.get("signal_reversal", {}).get("count", 0)
    if rev_losses / total_losses > 0.25:
        new_thresh = round(params.get("signal_threshold", 10.0) * 1.2, 1)
        suggestions["adjustments"].append(
            f"signal_threshold: {params.get('signal_threshold')} -> {new_thresh} (signal reversal losses high)"
        )
        params["signal_threshold"] = new_thresh

    suggestions["updated_params"] = params
    return suggestions


def generate_focused_grid(
    base_params: Dict[str, Any],
    analysis: Dict[str, Any],
) -> Dict[str, List[Any]]:
    """Generate a narrow grid around the suggested parameters for retraining."""
    grid = {
        "signal_threshold": [],
        "stop_loss_atr": [],
        "take_profit_atr": [],
        "max_hold_bars": [],
        "breakeven_atr": [0.0, 1.0],
        "require_trend_filter": [True],
    }

    # Signal threshold: ±20% around current
    base_thresh = base_params.get("signal_threshold", 10.0)
    grid["signal_threshold"] = sorted(set([
        round(base_thresh * 0.8, 1),
        base_thresh,
        round(base_thresh * 1.2, 1),
    ]))

    # Stop loss: ±25% around suggested
    base_sl = base_params.get("stop_loss_atr", 3.0)
    grid["stop_loss_atr"] = sorted(set([
        round(base_sl * 0.85, 2),
        base_sl,
        round(base_sl * 1.25, 2),
    ]))

    # Take profit: ±20% around suggested
    base_tp = base_params.get("take_profit_atr", 2.0)
    grid["take_profit_atr"] = sorted(set([
        round(base_tp * 0.85, 2),
        base_tp,
        round(base_tp * 1.2, 2),
    ]))

    # Hold: current ±15, min 20
    base_hold = base_params.get("max_hold_bars", 30)
    grid["max_hold_bars"] = sorted(set([
        max(20, base_hold - 15),
        base_hold,
        base_hold + 15,
    ]))

    # Filter out-of-bounds
    for k, v in grid.items():
        grid[k] = [x for x in v if x > 0]

    return grid


def evaluate_adjusted_params(
    symbol: str,
    params: Dict[str, Any],
    history: pd.DataFrame,
    bars_per_year: int = 365,
) -> Dict[str, float]:
    """Quick evaluation of a parameter set on recent history."""
    cfg = LokiConfig(period="1y", lookback_bars=60, signal_threshold=params.get("signal_threshold", 10.0))
    result = evaluate_params(history, params, cfg, symbol, bars_per_year)
    return {
        "trades": result.get("trades", 0),
        "return_pct": result.get("return_pct", 0.0),
        "win_rate_pct": result.get("win_rate_pct", 0.0),
        "profit_factor": result.get("profit_factor", 0.0),
        "max_drawdown_pct": result.get("max_drawdown_pct", 0.0),
        "expectancy": result.get("return_pct", 0.0) / max(1, result.get("trades", 1)),
    }


def run_learning_cycle(
    session_id: Optional[str] = None,
    symbols: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Full learning cycle: load session -> analyse -> suggest -> evaluate."""
    session = None
    if session_id:
        path = SESSION_DIR / f"session_{session_id}.json"
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                session = json.load(f)
    if session is None:
        session = load_latest_session()

    if not session:
        return {"error": "No paper session found"}

    trades = session.get("trades", [])
    if not trades:
        return {"error": "Session has no trades"}

    # Load histories for regime analysis
    universe = symbols or [s["symbol"] for s in session.get("symbols", [])]
    histories = {}
    for sym in universe:
        try:
            histories[sym] = fetch_history_for_analysis(sym, "2y")
        except Exception as e:
            logger.warning("History fetch failed for %s: %s", sym, e)
            histories[sym] = pd.DataFrame()

    # Get the parameters used (from first symbol's profile or consensus)
    first_symbol = session["symbols"][0] if session.get("symbols") else {}
    profile_source = first_symbol.get("profile", "unknown")
    preset = first_symbol.get("preset", "")

    # Use crypto_paper's profile_for to get actual params
    from loki_v8.crypto_paper import load_book, profile_for
    book = load_book()
    params, source = profile_for(book, universe[0] if universe else "BTC-USD")

    # Analyse
    analysis = analyse_losses(trades, histories, params)

    # Suggest adjustments
    suggestions = suggest_parameter_adjustments(analysis, params)

    # Generate focused grid
    focused_grid = generate_focused_grid(suggestions["updated_params"], analysis)

    # Quick evaluate the suggested params on recent data
    eval_results = {}
    for sym in universe[:3]:  # Limit to 3 symbols for speed
        if sym in histories and not histories[sym].empty:
            eval_results[sym] = evaluate_adjusted_params(sym, suggestions["updated_params"], histories[sym])

    return {
        "session_id": session.get("session_id"),
        "analysed_at": datetime.now().isoformat(timespec="seconds"),
        "profile_source": profile_source,
        "preset": preset,
        "original_params": params,
        "analysis": analysis,
        "suggestions": suggestions,
        "focused_grid": focused_grid,
        "quick_eval": eval_results,
    }


def print_report(report: Dict[str, Any]) -> None:
    """Pretty-print the learning report."""
    if "error" in report:
        print(f"Error: {report['error']}")
        return

    print(f"\n{'='*60}")
    print(f"LEARNING REPORT — {report['session_id']}")
    print(f"{'='*60}")
    print(f"Profile: {report['profile_source']} ({report['preset']})")
    print(f"Analysed: {report['analysed_at']}")

    print(f"\n--- Original Parameters ---")
    for k, v in report["original_params"].items():
        print(f"  {k}: {v}")

    a = report["analysis"]
    print(f"\n--- Loss Analysis ({a['total_losses']} losing trades, ${a['total_loss_pnl']:.2f}) ---")
    print("\nBy Regime:")
    for k, v in a["by_regime"].items():
        print(f"  {k}: {v['count']} losses, ${v['total_pnl']:.2f} total, ${v['avg_pnl']:.2f} avg")

    print("\nBy Holding Time:")
    for k, v in a["by_hold"].items():
        print(f"  {k}: {v['count']} losses, ${v['total_pnl']:.2f} total, ${v['avg_pnl']:.2f} avg")

    print("\nBy Exit Reason:")
    for k, v in a["by_exit"].items():
        print(f"  {k}: {v['count']} losses, ${v['total_pnl']:.2f} total, ${v['avg_pnl']:.2f} avg")

    print(f"\n--- Suggested Adjustments ---")
    for adj in report["suggestions"]["adjustments"]:
        print(f"  • {adj}")

    print(f"\n--- Focused Retraining Grid ---")
    for k, v in report["focused_grid"].items():
        print(f"  {k}: {v}")

    if report.get("quick_eval"):
        print(f"\n--- Quick Evaluation (top 3 symbols) ---")
        for sym, metrics in report["quick_eval"].items():
            print(f"  {sym}: {metrics['trades']} trades, {metrics['return_pct']:.2f}% ret, "
                  f"{metrics['win_rate_pct']:.1f}% wr, PF {metrics['profit_factor']:.2f}, "
                  f"exp ${metrics['expectancy']:.2f}/trade")


def main() -> None:
    parser = argparse.ArgumentParser(description="Learn from paper trading mistakes")
    parser.add_argument("--session", help="Specific session ID to analyse")
    parser.add_argument("--symbols", nargs="+", help="Symbols to focus on")
    parser.add_argument("--retrain", action="store_true", help="Print train_crypto CLI for focused grid")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    report = run_learning_cycle(session_id=args.session, symbols=args.symbols)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
        return

    print_report(report)

    if args.retrain and "focused_grid" in report:
        grid = report["focused_grid"]
        # Build CLI for train_crypto
        grid_str = " ".join(f"{k}={','.join(str(x) for x in v)}" for k, v in grid.items())
        print(f"\n--- Focused retrain command ---")
        print(f"python -m loki_v8.train_crypto --symbols {' '.join(args.symbols or ['BTC-USD', 'ETH-USD'])} \\")
        print(f"  --grid '{grid_str}' --rounds 2 --workers 4")


if __name__ == "__main__":
    main()