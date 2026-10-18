"""
LOKI v8 — walk-forward strategy trainer.

"Fits" the ensemble's execution parameters on historical data and, crucially,
verifies them out-of-sample before recommending them. This is grid-search
training with an honest holdout, not curve-fitting:

1. Bars are split chronologically into a TRAIN segment (default first 70%)
   and a VALIDATION segment (last 30%). Nothing from the validation segment
   ever influences parameter selection.
2. Every candidate parameter combination is backtested on the TRAIN segment
   (indicator scoring is computed once per symbol and reused — the tunables
   affect execution, not scoring). Candidates are ranked by train Sharpe,
   with a minimum-trade requirement so a lucky 1-trade run cannot win.
3. The top candidates are then evaluated out-of-sample on the VALIDATION
   segment (with pre-split context bars so indicators are properly warmed
   up; only trades entered after the split point count).
4. The recommended ("best") parameters are the top-ranked train candidate;
   the report states plainly whether they *validated* (positive out-of-sample
   return) so nobody mistakes an in-sample fit for a proven edge.

Results are persisted to ``state/training_report.json`` and surfaced by the
web terminal's "Strategy Trainer" tab. ``apply_best`` copies the winning
parameters into a live ``LokiConfig``.
"""
from __future__ import annotations

import dataclasses
import itertools
import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from .backtest import bars_per_year_for, run_backtest
from .config import LokiConfig
from .data import get_provider, is_crypto
from .strategy import EnsembleStrategy

logger = logging.getLogger(__name__)

# Parameters the trainer is allowed to tune. Each maps to a LokiConfig field
# applied by ``run_backtest`` when entering/exiting trades.
DEFAULT_GRID: Dict[str, List[Any]] = {
    "signal_threshold": [18.0, 25.0, 32.0],
    "stop_loss_atr": [1.5, 2.5],
    "take_profit_atr": [2.5, 4.0],
    "require_trend_filter": [True, False],
}
TRAINABLE_PARAMS = tuple(DEFAULT_GRID)

REPORT_FILENAME = "training_report.json"

# Minimum bars required beyond the indicator warmup before a symbol is
# considered trainable at all.
_MIN_EXTRA_BARS = 80
_MIN_TRAIN_TRADEABLE = 30


@dataclass
class SymbolReport:
    """Training outcome for one symbol."""
    symbol: str
    ok: bool = False
    error: str = ""
    bars: int = 0
    train_bars: int = 0
    validation_bars: int = 0
    n_combos: int = 0
    best_params: Dict[str, Any] = field(default_factory=dict)
    train_metrics: Dict[str, float] = field(default_factory=dict)
    validation_metrics: Dict[str, float] = field(default_factory=dict)
    validated: bool = False
    leaderboard: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


def iter_grid(grid: Optional[Dict[str, List[Any]]] = None):
    """Yield every parameter combination from the grid."""
    g = grid or DEFAULT_GRID
    keys = list(g.keys())
    for values in itertools.product(*(g[k] for k in keys)):
        yield dict(zip(keys, values))


def _cfg_with(base_cfg: LokiConfig, params: Dict[str, Any]) -> LokiConfig:
    return dataclasses.replace(base_cfg, **params)


def _result_metrics(res) -> Dict[str, float]:
    """Headline metrics from a BacktestResult."""
    pf = res.profit_factor
    return {
        "trades": int(res.total_trades),
        "return_pct": round(float(res.total_return_pct), 2),
        "win_rate_pct": round(float(res.win_rate_pct), 1),
        "profit_factor": round(float(pf), 2) if math.isfinite(pf) else 999.0,
        "max_drawdown_pct": round(float(res.max_drawdown_pct), 2),
        "sharpe": round(float(res.sharpe), 2),
    }


def _oos_metrics(
    trades: List[Any], initial_cash: float
) -> Dict[str, float]:
    """Metrics computed from out-of-sample trades only."""
    pnls = [t.pnl for t in trades]
    if not pnls:
        return {
            "trades": 0, "return_pct": 0.0, "win_rate_pct": 0.0,
            "profit_factor": 0.0, "max_drawdown_pct": 0.0,
        }
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    pf = (gross_win / gross_loss) if gross_loss > 0 else (999.0 if gross_win > 0 else 0.0)
    curve = pd.Series(pnls).cumsum()
    max_dd = float((curve - curve.cummax()).min())
    total = float(sum(pnls))
    return {
        "trades": len(pnls),
        "return_pct": round(total / initial_cash * 100.0, 2) if initial_cash else 0.0,
        "win_rate_pct": round(len(wins) / len(pnls) * 100.0, 1),
        "profit_factor": round(pf, 2),
        "max_drawdown_pct": round(max_dd / initial_cash * 100.0, 2) if initial_cash else 0.0,
    }


def _rank_key(entry: Dict[str, Any]):
    """Sort key for the train leaderboard (best last, so [-1] is best)."""
    m = entry["train"]
    enough_trades = m["trades"] >= 3
    sharpe = m["sharpe"] if math.isfinite(m["sharpe"]) else -99.0
    pf = min(m["profit_factor"], 5.0)
    return (enough_trades, sharpe, pf, m["return_pct"])


def train_symbol(
    df: pd.DataFrame,
    base_cfg: LokiConfig,
    symbol: str,
    grid: Optional[Dict[str, List[Any]]] = None,
    train_frac: float = 0.7,
    top_n: int = 3,
    bars_per_year: int = 252,
) -> SymbolReport:
    """Train execution parameters on historical bars for one symbol.

    Pure function of ``df`` — no network, no clock — so it is fully testable.
    """
    report = SymbolReport(symbol=symbol, bars=len(df))
    warmup = max(base_cfg.lookback_bars, 60)

    if df is None or df.empty or len(df) < warmup + _MIN_EXTRA_BARS:
        report.error = (
            f"insufficient history for {symbol}: {0 if df is None else len(df)} bars, "
            f"need at least {warmup + _MIN_EXTRA_BARS} (indicator warmup is {warmup})"
        )
        return report

    split_idx = int(len(df) * train_frac)
    if split_idx - warmup < _MIN_TRAIN_TRADEABLE or len(df) - split_idx < 20:
        report.error = (
            f"history for {symbol} too short to split honestly "
            f"({len(df)} bars, warmup {warmup}, train_frac {train_frac})"
        )
        return report

    train_df = df.iloc[:split_idx]
    split_time = df.index[split_idx]
    report.train_bars = len(train_df)
    report.validation_bars = len(df) - split_idx

    # Score the bars once; tunables affect execution only, so every combo
    # reuses the same scored frame.
    scored = EnsembleStrategy(base_cfg).score_frame(df)
    train_frame = scored.iloc[:split_idx]

    grid = grid or DEFAULT_GRID
    leaderboard: List[Dict[str, Any]] = []
    for params in iter_grid(grid):
        cfg_i = _cfg_with(base_cfg, params)
        try:
            res = run_backtest(
                train_df, cfg_i, symbol=symbol,
                bars_per_year=bars_per_year, frame=train_frame,
            )
        except Exception as exc:  # noqa: BLE001 - one bad combo must not kill the sweep
            logger.warning("train: %s %s failed: %s", symbol, params, exc)
            continue
        leaderboard.append({"params": params, "train": _result_metrics(res)})

    report.n_combos = len(leaderboard)
    if not leaderboard:
        report.error = f"every parameter combination failed for {symbol}"
        return report

    leaderboard.sort(key=_rank_key)
    leaderboard.reverse()  # best first
    report.leaderboard = leaderboard

    # ------------------------------------------------------------------
    # Out-of-sample validation of the top candidates.
    # The validation run starts `warmup` bars before the split so the
    # indicators are warmed up, but only trades ENTERED at/after the split
    # timestamp count as out-of-sample.
    # ------------------------------------------------------------------
    val_start_idx = max(0, split_idx - warmup)
    val_df = df.iloc[val_start_idx:]
    val_frame = scored.iloc[val_start_idx:]

    for entry in leaderboard[: max(1, top_n)]:
        cfg_i = _cfg_with(base_cfg, entry["params"])
        try:
            res = run_backtest(
                val_df, cfg_i, symbol=symbol,
                bars_per_year=bars_per_year, frame=val_frame,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("train(val): %s %s failed: %s", symbol, entry["params"], exc)
            entry["validation"] = _oos_metrics([], base_cfg.initial_cash)
            entry["validated"] = False
            continue
        oos_trades = [t for t in res.trades if t.entry_time >= split_time]
        entry["validation"] = _oos_metrics(oos_trades, base_cfg.initial_cash)

    best = leaderboard[0]
    report.best_params = dict(best["params"])
    report.train_metrics = dict(best.get("train", {}))
    report.validation_metrics = dict(best.get("validation", _oos_metrics([], base_cfg.initial_cash)))
    report.validated = bool(
        report.validation_metrics.get("trades", 0) > 0
        and report.validation_metrics.get("return_pct", 0.0) > 0.0
    )
    report.ok = True
    return report


def train(
    symbols: Optional[List[str]] = None,
    base_cfg: Optional[LokiConfig] = None,
    period: Optional[str] = None,
    timeframe: Optional[str] = None,
    grid: Optional[Dict[str, List[Any]]] = None,
    train_frac: float = 0.7,
    top_n: int = 3,
) -> Dict[str, Any]:
    """Train every symbol and return a serializable report dict.

    Network fetching happens here (one history download per symbol); failures
    are recorded per-symbol so one bad ticker doesn't abort the run.
    """
    cfg = base_cfg or LokiConfig()
    provider = get_provider()
    syms = [s.strip().upper() for s in (symbols or cfg.symbols) if s and s.strip()]
    period = period or cfg.period
    timeframe = timeframe or cfg.timeframe
    bpy = bars_per_year_for(timeframe, crypto=any(is_crypto(s) for s in syms))

    symbol_reports: List[Dict[str, Any]] = []
    for sym in syms:
        try:
            df = provider.fetch_history(sym, period, timeframe)
            rep = train_symbol(
                df, cfg, sym, grid=grid, train_frac=train_frac,
                top_n=top_n, bars_per_year=bpy,
            )
        except Exception as exc:  # noqa: BLE001 - e.g. yfinance offline
            rep = SymbolReport(symbol=sym, error=f"data fetch failed: {exc}")
        symbol_reports.append(rep.to_dict())

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "period": period,
        "timeframe": timeframe,
        "train_frac": train_frac,
        "grid_size": sum(1 for _ in iter_grid(grid)),
        "symbols": symbol_reports,
    }
    save_report(report, cfg)
    return report


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def report_path(cfg: Optional[LokiConfig] = None) -> Path:
    state_dir = Path((cfg or LokiConfig()).state_dir)
    return state_dir / REPORT_FILENAME


def save_report(report: Dict[str, Any], cfg: Optional[LokiConfig] = None) -> Path:
    path = report_path(cfg)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        tmp.replace(path)
    except Exception as exc:  # noqa: BLE001 - persistence is best-effort (e.g. read-only FS)
        logger.warning("could not persist training report: %s", exc)
    return path


def load_report(cfg: Optional[LokiConfig] = None) -> Optional[Dict[str, Any]]:
    path = report_path(cfg)
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not load training report: %s", exc)
        return None


def apply_best(report: Dict[str, Any], symbol: str, cfg: LokiConfig) -> Dict[str, Any]:
    """Copy a symbol's best trained parameters into ``cfg`` (in place).

    Returns the applied parameters. Only keys in ``TRAINABLE_PARAMS`` are
    touched, and only when the symbol has a successful report entry.
    """
    for entry in report.get("symbols", []):
        if entry.get("symbol", "").upper() != symbol.upper() or not entry.get("ok"):
            continue
        params = {
            k: v for k, v in (entry.get("best_params") or {}).items()
            if k in TRAINABLE_PARAMS
        }
        for k, v in params.items():
            setattr(cfg, k, v)
        logger.info("applied trained params for %s: %s", symbol, params)
        return params
    return {}
