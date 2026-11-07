"""Train and verify one universal strategy profile on 10-20 years of daily data.

Why universal: tuning parameters per symbol on one decade finds the corner of
that decade that looked best. Fitting ONE parameter set across a whole
universe of stocks/ETFs (and one for crypto) is far harder to overfit.

Protocol (chronological, nothing shuffled):

* development  — fit window: equities 2005-2018, crypto 2015-2020
* validation   — selection window: equities 2019-2022, crypto 2021-2022
* holdout      — untouched until the end: 2023 onward (both)

Each candidate is backtested once over the full history per symbol with the
same ``run_backtest`` the live engine mirrors; period metrics come from the
equity curve inside each window, so indicators are always warmed up and no
window sees later data. Candidates are ranked by the WORSE of their
development and validation scores. The holdout is only read for the final
report — it never influences which candidate wins.

Usage:
    python train_long_history.py                  # fetch via yfinance
    python train_long_history.py --data-dir DIR   # cached CSVs (SYMBOL.csv)
    python train_long_history.py --write-snapshot # store the winner for the live AI
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from loki_v8.backtest import run_backtest
from loki_v8.config import LokiConfig
from loki_v8.strategy import EnsembleStrategy

EQUITY_UNIVERSE = ["SPY", "QQQ", "IWM", "DIA", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "JPM", "XOM", "GLD", "TLT"]
CRYPTO_UNIVERSE = ["BTC-USD", "ETH-USD", "LTC-USD", "XRP-USD", "DOGE-USD", "ADA-USD", "BNB-USD", "LINK-USD"]

WINDOWS = {
    "equity": {"development": ("2005-01-01", "2018-12-31"), "validation": ("2019-01-01", "2022-12-31"), "holdout": ("2023-01-01", "2100-01-01")},
    "crypto": {"development": ("2015-01-01", "2020-12-31"), "validation": ("2021-01-01", "2022-12-31"), "holdout": ("2023-01-01", "2100-01-01")},
}

PRESETS = {
    "balanced": {"trend": 0.25, "momentum": 0.20, "volume_flow": 0.20, "squeeze": 0.20, "volatility": 0.15},
    "trend_leader": {"trend": 0.45, "momentum": 0.20, "volume_flow": 0.15, "squeeze": 0.10, "volatility": 0.10},
    "trend_only": {"trend": 0.80, "momentum": 0.05, "volume_flow": 0.05, "squeeze": 0.05, "volatility": 0.05},
    "trend_momentum": {"trend": 0.50, "momentum": 0.40, "volume_flow": 0.05, "squeeze": 0.0, "volatility": 0.05},
}

GRID = {
    "preset": list(PRESETS),
    "signal_threshold": [3.0, 8.0, 15.0, 30.0],
    "stop_loss_atr": [3.0, 6.0, 10.0],
    "trailing_stop_atr": [0.0, 8.0],
    "target_vol_pct": [12.0, 20.0, 30.0],
    "exit_mode": ["signal", "trend"],
}
FIXED = dict(
    sizing_mode="vol_target",
    max_exposure_pct=100.0,
    take_profit_atr=0.0,  # no fixed target: winners run until trend/stop exit
    max_hold_bars=0,
    require_trend_filter=True,
    regime_filter=True,
    breakeven_atr=0.0,
    partial_tp_atr=0.0,
    adaptive_threshold=False,
    conviction_sizing=False,
    vol_target_sizing=False,
    max_atr_pct=0.0,
    risk_per_trade_pct=1.0,
    max_daily_loss_pct=100.0,  # daily/streak halts are live-account guards,
    max_consecutive_losses=10_000,  # not part of the daily-bar strategy test
    slippage_bps=5.0,
)
FEE_BPS = 10.0  # charged per side on notional, on top of slippage


def load_history(symbol: str, data_dir: Optional[Path]) -> pd.DataFrame:
    if data_dir is not None and (data_dir / f"{symbol}.csv").exists():
        df = pd.read_csv(data_dir / f"{symbol}.csv", index_col=0, parse_dates=True)
    else:
        import yfinance as yf

        df = yf.download(symbol, start="2004-01-01", interval="1d", progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].dropna()
        if data_dir is not None:
            data_dir.mkdir(parents=True, exist_ok=True)
            df.to_csv(data_dir / f"{symbol}.csv")
    df.index = pd.DatetimeIndex(df.index).tz_localize(None)
    return df[(df["close"] > 0)].copy()


def candidates() -> List[Dict[str, Any]]:
    keys = list(GRID)
    return [dict(zip(keys, values)) for values in itertools.product(*(GRID[k] for k in keys))]


def config_for(params: Dict[str, Any]) -> LokiConfig:
    cfg = LokiConfig(initial_cash=100_000.0, **FIXED)
    extra = {k: v for k, v in params.items() if k != "preset"}
    return replace(cfg, factor_weights=dict(PRESETS[params["preset"]]), **extra)


def _period_stats(equity: pd.Series, trades: List[Any], start: str, end: str, bpy: int) -> Dict[str, float]:
    window = equity[(equity.index >= start) & (equity.index <= end)]
    if len(window) < 30:
        return {}
    rets = window.pct_change().dropna()
    years = len(window) / bpy
    total = window.iloc[-1] / window.iloc[0]
    cagr = (total ** (1 / years) - 1) * 100 if total > 0 and years > 0 else -100.0
    sd = rets.std()
    sharpe = float(rets.mean() / sd * math.sqrt(bpy)) if sd > 0 else 0.0
    peak = window.cummax()
    max_dd = float(((window / peak) - 1).min() * 100)
    exits = [t for t in trades if start <= str(pd.Timestamp(t.exit_time).date()) <= end]
    gross_w = sum(t.pnl for t in exits if t.pnl > 0)
    gross_l = -sum(t.pnl for t in exits if t.pnl < 0)
    return {
        "cagr_pct": round(cagr, 2),
        "sharpe": round(sharpe, 3),
        "max_dd_pct": round(max_dd, 2),
        "trades": len(exits),
        "win_rate_pct": round(100 * sum(1 for t in exits if t.pnl > 0) / len(exits), 1) if exits else 0.0,
        "profit_factor": round(gross_w / gross_l, 3) if gross_l > 0 else (99.0 if gross_w > 0 else 0.0),
    }


def _buy_hold(df: pd.DataFrame, start: str, end: str, bpy: int) -> Dict[str, float]:
    close = df["close"]
    eq = close / close.iloc[0] * 100_000.0
    return _period_stats(eq, [], start, end, bpy)


def _apply_fees(trades: List[Any]) -> None:
    """Charge FEE_BPS per side on notional (slippage is already in fills)."""
    for t in trades:
        fee = (t.entry_price + t.exit_price) * t.qty * FEE_BPS / 10_000.0
        t.pnl -= fee


def _fee_adjusted_equity(equity: pd.Series, trades: List[Any]) -> pd.Series:
    fees = pd.Series(0.0, index=equity.index)
    for t in trades:
        entry_fee = t.entry_price * t.qty * FEE_BPS / 10_000.0
        exit_fee = t.exit_price * t.qty * FEE_BPS / 10_000.0
        for stamp, fee in ((t.entry_time, entry_fee), (t.exit_time, exit_fee)):
            pos = equity.index.searchsorted(pd.Timestamp(stamp))
            if pos < len(fees):
                fees.iloc[pos] += fee
    return equity - fees.cumsum()


_FRAMES: Dict[Tuple[str, str], pd.DataFrame] = {}
_DATA: Dict[str, pd.DataFrame] = {}


def _init(data: Dict[str, pd.DataFrame]) -> None:
    global _DATA
    _DATA = data


def evaluate(args: Tuple[Dict[str, Any], str, str]) -> Dict[str, Any]:
    params, symbol, kind = args
    df = _DATA[symbol]
    bpy = 365 if kind == "crypto" else 252
    cfg = config_for(params)
    key = (symbol, params["preset"])
    frame = _FRAMES.get(key)
    if frame is None:
        frame = EnsembleStrategy(cfg).score_frame(df)
        _FRAMES[key] = frame
    res = run_backtest(df, cfg, symbol=symbol, bars_per_year=bpy, frame=frame)
    equity = _fee_adjusted_equity(res.equity_curve, res.trades)
    _apply_fees(res.trades)
    out = {"symbol": symbol, "kind": kind, "params": params}
    for name, (start, end) in WINDOWS[kind].items():
        out[name] = _period_stats(equity, res.trades, start, end, bpy)
        out[name + "_bh"] = _buy_hold(df, start, end, bpy)
    return out


def score(rows: List[Dict[str, Any]], window: str) -> float:
    """Mean Sharpe across symbols, minus a drawdown penalty beyond -30%."""
    vals = []
    for r in rows:
        stats = r.get(window) or {}
        if not stats:
            continue
        penalty = max(0.0, -30.0 - stats["max_dd_pct"]) / 30.0
        vals.append(stats["sharpe"] - penalty)
    return float(np.mean(vals)) if vals else -9.0


def run(kind: str, symbols: List[str], data_dir: Optional[Path], workers: int) -> Dict[str, Any]:
    data = {s: load_history(s, data_dir) for s in symbols}
    combos = candidates()
    jobs = [(c, s, kind) for c in combos for s in symbols]
    started = time.time()
    with ProcessPoolExecutor(max_workers=workers, initializer=_init, initargs=(data,)) as pool:
        results = list(pool.map(evaluate, jobs, chunksize=max(1, len(jobs) // (workers * 8))))
    by_combo: Dict[str, List[Dict[str, Any]]] = {}
    for r in results:
        by_combo.setdefault(json.dumps(r["params"], sort_keys=True), []).append(r)
    board = []
    for key, rows in by_combo.items():
        dev, val = score(rows, "development"), score(rows, "validation")
        board.append({"params": json.loads(key), "development_score": round(dev, 3), "validation_score": round(val, 3), "rank_score": round(min(dev, val), 3), "rows": rows})
    board.sort(key=lambda b: b["rank_score"], reverse=True)
    best = board[0]
    holdout = []
    for r in best["rows"]:
        h, hb = r.get("holdout") or {}, r.get("holdout_bh") or {}
        holdout.append({"symbol": r["symbol"], "strategy": h, "buy_hold": hb, "development": r.get("development"), "validation": r.get("validation")})
    pooled = _pooled(holdout)
    return {
        "kind": kind,
        "symbols": symbols,
        "windows": WINDOWS[kind],
        "candidates": len(combos),
        "seconds": round(time.time() - started, 1),
        "best_params": {**FIXED, **{k: v for k, v in best["params"].items() if k != "preset"}, "factor_preset": best["params"]["preset"], "factor_weights": PRESETS[best["params"]["preset"]]},
        "development_score": best["development_score"],
        "validation_score": best["validation_score"],
        "leaderboard": [{k: v for k, v in b.items() if k != "rows"} for b in board[:8]],
        "holdout": holdout,
        "holdout_pooled": pooled,
        "data_through": max(str(df.index[-1].date()) for df in data.values()),
    }


def _pooled(holdout: List[Dict[str, Any]]) -> Dict[str, Any]:
    strat = [h["strategy"] for h in holdout if h["strategy"]]
    bh = [h["buy_hold"] for h in holdout if h["buy_hold"]]
    profitable = sum(1 for s in strat if s["cagr_pct"] > 0)
    pf_ok = sum(1 for s in strat if s["profit_factor"] > 1.0)
    return {
        "symbols": len(strat),
        "profitable_symbols": profitable,
        "profit_factor_above_1": pf_ok,
        "mean_cagr_pct": round(float(np.mean([s["cagr_pct"] for s in strat])), 2) if strat else None,
        "mean_sharpe": round(float(np.mean([s["sharpe"] for s in strat])), 3) if strat else None,
        "mean_max_dd_pct": round(float(np.mean([s["max_dd_pct"] for s in strat])), 2) if strat else None,
        "buy_hold_mean_cagr_pct": round(float(np.mean([b["cagr_pct"] for b in bh])), 2) if bh else None,
        "buy_hold_mean_sharpe": round(float(np.mean([b["sharpe"] for b in bh])), 3) if bh else None,
        "buy_hold_mean_max_dd_pct": round(float(np.mean([b["max_dd_pct"] for b in bh])), 2) if bh else None,
        "total_trades": int(sum(s["trades"] for s in strat)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, default=Path("state/history"))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--out", type=Path, default=Path("state/long_history_report.json"))
    parser.add_argument("--write-snapshot", action="store_true", help="store winners in loki_v8/training_report_snapshot.json")
    args = parser.parse_args()
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "protocol": "universal profile; select on min(development, validation); holdout read once for reporting",
        "fees_bps_per_side": FEE_BPS,
        "slippage_bps_per_side": FIXED["slippage_bps"],
        "equity": run("equity", EQUITY_UNIVERSE, args.data_dir, args.workers),
        "crypto": run("crypto", CRYPTO_UNIVERSE, args.data_dir, args.workers),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1, default=str))
    for kind in ("equity", "crypto"):
        r = report[kind]
        print(f"\n== {kind}: {r['candidates']} candidates in {r['seconds']}s — best {r['best_params']['factor_preset']} "
              f"thr={r['best_params']['signal_threshold']} stop={r['best_params']['stop_loss_atr']} trail={r['best_params']['trailing_stop_atr']} "
              f"vol={r['best_params']['target_vol_pct']} | dev {r['development_score']} val {r['validation_score']}")
        print(f"{'symbol':9} {'HOLDOUT cagr':>12} {'sharpe':>7} {'maxDD':>7} {'trades':>6} {'win%':>5} {'PF':>6} | {'B&H cagr':>8} {'sharpe':>7} {'maxDD':>7}")
        for h in r["holdout"]:
            s, b = h["strategy"], h["buy_hold"]
            if not s:
                continue
            print(f"{h['symbol']:9} {s['cagr_pct']:>12} {s['sharpe']:>7} {s['max_dd_pct']:>7} {s['trades']:>6} {s['win_rate_pct']:>5} {s['profit_factor']:>6} | {b['cagr_pct']:>8} {b['sharpe']:>7} {b['max_dd_pct']:>7}")
        print("pooled:", r["holdout_pooled"])
    if args.write_snapshot:
        write_snapshot(report)
    print(f"\nreport written to {args.out}")


def write_snapshot(report: Dict[str, Any]) -> None:
    path = Path(__file__).parent / "loki_v8" / "training_report_snapshot.json"
    snap = json.loads(path.read_text(encoding="utf-8"))
    block: Dict[str, Any] = {"generated_at": report["generated_at"], "protocol": report["protocol"],
                             "fees_bps_per_side": report["fees_bps_per_side"], "slippage_bps_per_side": report["slippage_bps_per_side"]}
    for kind in ("equity", "crypto"):
        r = report[kind]
        pooled = r["holdout_pooled"]
        block[kind] = {
            "params": r["best_params"],
            "symbols": r["symbols"],
            "windows": r["windows"],
            "development_score": r["development_score"],
            "validation_score": r["validation_score"],
            "holdout_pooled": pooled,
            "holdout": [{"symbol": h["symbol"], "strategy": h["strategy"], "buy_hold": h["buy_hold"]} for h in r["holdout"]],
            "data_through": r["data_through"],
            # The live AI only uses a universal profile that made money out of sample.
            "verified": bool(pooled["symbols"] and pooled["mean_cagr_pct"] and pooled["mean_cagr_pct"] > 0
                             and pooled["profit_factor_above_1"] >= math.ceil(0.6 * pooled["symbols"])),
        }
    snap["universal"] = block
    path.write_text(json.dumps(snap, indent=1, default=str), encoding="utf-8")
    print(f"snapshot updated: {path}")


if __name__ == "__main__":
    main()
