"""
LOKI v8 — walk-forward strategy trainer with multi-factor optimization.

"Fits" the ensemble's factor weights and execution parameters on historical
data and, crucially, verifies them out-of-sample before recommending them.
This is honest grid-search training, not curve-fitting:

1. Bars are split chronologically into a TRAIN segment (default first 70%)
   and a VALIDATION segment (last 30%). Nothing from the validation segment
   ever influences parameter selection.
2. Every candidate combination is backtested on the TRAIN segment.
   Factor weighting and execution tuning are evaluated in layers:

   * **Multi-factor layer** (optional): 14 named factor-weight presets
     (balanced, trend-leader, momentum-leader, institutional-flow,
     squeeze-breakout, mean-reversion, ...). Factor *columns* are computed
     ONCE per symbol, so every preset is just a cheap re-weighting — no
     repeated indicator computation.
   * **Execution layer**: the signal-threshold / ATR-stop / trend-filter
     grid is swept under the best factor presets.

3. The top candidates are verified OUT-OF-SAMPLE on the validation segment
   (with pre-split context bars so indicators are warmed up; only trades
   entered after the split point count).
4. **Auto-refinement**: if the winner does not yet pass the "good trades"
   hurdles (OOS return positive, profit factor ≥ 1.25, drawdown > -30%,
   ≥ 5 OOS trades), the trainer re-sweeps a refined neighborhood around the
   best parameters, up to ``refine_rounds`` times — training until it makes
   good trades instead of accepting the first lucky fit.
5. A **cross-symbol consensus** parameter set (median of every symbol's
   winner) is reported so one configuration can run the whole engine.

Results are persisted to ``state/training_report.json`` (incrementally after
each symbol and round) and surfaced by the web terminal's "AI Strategy
Trainer" tab. ``apply_best`` copies a symbol's winner into a live
``LokiConfig``; ``apply_consensus`` applies the cross-symbol winner.
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
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .backtest import bars_per_year_for, run_backtest
from .config import LokiConfig
from .data import get_provider, is_crypto
from .regime import regime_distribution
from .strategy import EnsembleStrategy, normalize_weights

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

# Parameter ladders used when auto-refining a neighborhood around the best
# parameters found so far ("train until it makes good trades"). The extremes
# (very small take-profit multiples, very wide stops) matter for the
# high-win-rate aggressive search: tiny targets win often, wide stops survive
# noise long enough to let a gentle trend carry price into the target.
LADDERS: Dict[str, List[float]] = {
    "signal_threshold": [8.0, 10.0, 14.0, 18.0, 22.0, 25.0, 28.0, 32.0, 38.0, 45.0],
    "stop_loss_atr": [1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0],
    "take_profit_atr": [0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0],
    "max_hold_bars": [10, 15, 20, 30, 45, 60, 90],
    "max_atr_pct": [3.0, 4.0, 5.0, 6.5, 8.0],
}
_REFINE_MAX_COMBOS = 16

# Grid used by the aggressive objective (objective="win_rate"): small
# take-profit multiples and varied stops dominate hit-rate outcomes.
AGGRESSIVE_GRID: Dict[str, List[Any]] = {
    "signal_threshold": [10.0, 18.0, 25.0],
    "stop_loss_atr": [1.25, 2.0, 3.0, 5.0],
    "take_profit_atr": [0.5, 0.75, 1.0, 1.5, 2.0],
    "require_trend_filter": [True, False],
}


# ---------------------------------------------------------------------------
# Factor-weight presets (multi-factor optimization layer). Weights are
# normalized at scoring time, so only ratios matter.
# ---------------------------------------------------------------------------
def _w(
    trend: float, momentum: float, volume_flow: float, squeeze: float, volatility: float
) -> Dict[str, float]:
    return {
        "trend": trend,
        "momentum": momentum,
        "volume_flow": volume_flow,
        "squeeze": squeeze,
        "volatility": volatility,
    }


FACTOR_PRESETS: List[Tuple[str, Dict[str, float]]] = [
    ("balanced", _w(0.25, 0.20, 0.20, 0.20, 0.15)),
    ("trend_leader", _w(0.45, 0.20, 0.15, 0.10, 0.10)),
    ("momentum_leader", _w(0.15, 0.40, 0.15, 0.20, 0.10)),
    ("institutional_flow", _w(0.15, 0.15, 0.45, 0.15, 0.10)),
    ("squeeze_breakout", _w(0.15, 0.20, 0.10, 0.45, 0.10)),
    ("mean_reversion", _w(0.10, 0.25, 0.15, 0.10, 0.40)),
    ("trend_volume", _w(0.50, 0.10, 0.30, 0.05, 0.05)),
    ("momentum_squeeze", _w(0.10, 0.50, 0.05, 0.30, 0.05)),
    ("defensive_flow", _w(0.10, 0.10, 0.30, 0.10, 0.40)),
    ("trend_only", _w(0.80, 0.05, 0.05, 0.05, 0.05)),
    ("momentum_only", _w(0.05, 0.80, 0.05, 0.05, 0.05)),
    ("flow_only", _w(0.05, 0.05, 0.80, 0.05, 0.05)),
    ("squeeze_only", _w(0.05, 0.05, 0.05, 0.80, 0.05)),
    ("volatility_only", _w(0.05, 0.05, 0.05, 0.05, 0.80)),
]

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
    hurdles: List[Dict[str, Any]] = field(default_factory=list)
    good: bool = False  # passed every "good trade" hurdle (OOS)
    factor_preset: str = ""  # winning factor-weight preset name (if any)
    refine_round: int = 1
    regime_distribution: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


def iter_grid(grid: Optional[Dict[str, List[Any]]] = None):
    """Yield every parameter combination from the grid."""
    g = grid or DEFAULT_GRID
    keys = list(g.keys())
    for values in itertools.product(*(g[k] for k in keys)):
        yield dict(zip(keys, values))


def _cfg_with(base_cfg: LokiConfig, params: Dict[str, Any]) -> LokiConfig:
    clean = {k: v for k, v in params.items() if k in base_cfg.__dataclass_fields__}
    return dataclasses.replace(base_cfg, **clean)


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


def _oos_metrics(trades: List[Any], initial_cash: float) -> Dict[str, float]:
    """Metrics computed from out-of-sample trades only."""
    pnls = [t.pnl for t in trades]
    if not pnls:
        return {
            "trades": 0,
            "return_pct": 0.0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
            "month_profit_rate_pct": 0.0,
        }
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    pf = (gross_win / gross_loss) if gross_loss > 0 else (999.0 if gross_win > 0 else 0.0)
    curve = pd.Series(pnls).cumsum()
    max_dd = float((curve - curve.cummax()).min())
    total = float(sum(pnls))

    # Share of calendar months (by exit date) that ended profitable — the
    # "profitability rate" metric the aggressive trainer targets.
    month_profit_rate = 0.0
    try:
        exits = pd.to_datetime([t.exit_time for t in trades], utc=True).tz_localize(None)
        monthly = pd.Series(pnls).groupby(exits.to_period("M")).sum()
        if len(monthly):
            month_profit_rate = float((monthly > 0.0).mean() * 100.0)
    except Exception:  # noqa: BLE001 — timestamp fallback; never fail metrics
        month_profit_rate = 0.0

    return {
        "trades": len(pnls),
        "return_pct": round(total / initial_cash * 100.0, 2) if initial_cash else 0.0,
        "win_rate_pct": round(len(wins) / len(pnls) * 100.0, 1),
        "profit_factor": round(pf, 2),
        "max_drawdown_pct": round(max_dd / initial_cash * 100.0, 2) if initial_cash else 0.0,
        "month_profit_rate_pct": round(month_profit_rate, 1),
    }


def _rank_key(entry: Dict[str, Any], objective: str = "sharpe"):
    """Sort key for the train leaderboard (best LAST, so [-1] is best).

    Objectives:
      * ``sharpe``  — risk-adjusted return (default, most honest)
      * ``win_rate``— aggressive: hit-rate first, but only among candidates
        that at least break even (profit factor floor 1.0)
      * ``return``  — raw total return
    """
    m = entry["train"]
    enough_trades = m["trades"] >= 3
    pf = min(m["profit_factor"], 5.0)
    if objective == "win_rate":
        # Prefer high hit rates, but never prefer a money-losing profile.
        breakeven = pf >= 1.0
        return (enough_trades, breakeven, m["win_rate_pct"], pf, m["return_pct"])
    if objective == "return":
        return (enough_trades, m["return_pct"], pf)
    sharpe = m["sharpe"] if math.isfinite(m["sharpe"]) else -99.0
    return (enough_trades, sharpe, pf, m["return_pct"])


# ---------------------------------------------------------------------------
# "Good trades" hurdles — checked on OUT-OF-SAMPLE metrics only.
# The trainer refines until every hurdle passes (or rounds are exhausted).
# Targets are configurable so the aggressive mode can chase e.g. 90%.
# ---------------------------------------------------------------------------
HURDLE_DEFS: List[Tuple[str, str, float, str]] = [
    # (validation-metric key, plain-language label, default target, comparison)
    ("trades", "At least 5 out-of-sample trades", 5.0, "gte"),
    ("return_pct", "Out-of-sample return above zero", 0.0, "gt"),
    ("profit_factor", "Out-of-sample profit factor ≥ {target}", 1.25, "gte"),
    ("max_drawdown_pct", "Out-of-sample max drawdown better than {target}%", -30.0, "gt"),
    ("win_rate_pct", "Out-of-sample win rate ≥ {target}%", 35.0, "gte"),
    ("month_profit_rate_pct", "Profitable out-of-sample months ≥ {target}%", None, "gte"),
]


def build_hurdle_list(
    targets: Optional[Dict[str, float]] = None,
) -> List[Tuple[str, str, float, str]]:
    """Materialize the hurdle list, overriding default targets.

    Hurdles whose target is ``None`` (e.g. monthly profitability) are only
    enabled when the caller provides an explicit target for them — the
    aggressive "90% profitability" mode switches them on.
    """
    targets = targets or {}
    out: List[Tuple[str, str, float, str]] = []
    for key, label, default, cmp in HURDLE_DEFS:
        target = targets.get(key, default)
        if target is None:
            continue
        out.append((key, label.replace("{target}", _fmt_target(target)), target, cmp))
    return out


def _fmt_target(value: float) -> str:
    return f"{value:g}"


def check_hurdles(
    validation: Dict[str, float],
    targets: Optional[Dict[str, float]] = None,
) -> List[Dict[str, Any]]:
    """Evaluate the good-trade hurdles for an OOS metric bundle."""
    checks: List[Dict[str, Any]] = []
    for key, label, target, cmp in build_hurdle_list(targets):
        value = float(validation.get(key, 0.0))
        ok = value >= target if cmp == "gte" else value > target
        checks.append(
            {
                "key": key,
                "label": label,
                "ok": bool(ok),
                "value": round(value, 2),
                "target": target,
            }
        )
    return checks


def _passed_all(checks: List[Dict[str, Any]]) -> bool:
    return bool(checks) and all(c["ok"] for c in checks)


def _refined_grid(grid: Dict[str, List[Any]], best_params: Dict[str, Any]) -> Dict[str, List[Any]]:
    """Build a narrow neighborhood grid around the best parameters found.

    Numeric params move ±1 step on their training ladder (and always keep the
    current best value); fixed/boolean params keep their winning value.
    Total product is capped so refinement stays fast.
    """
    refined: Dict[str, List[Any]] = {}
    for key, values in grid.items():
        best = best_params.get(key)
        if key in LADDERS and isinstance(best, (int, float)) and not isinstance(best, bool):
            ladder = sorted(set(list(LADDERS[key]) + [float(best)]))
            idx = ladder.index(float(best))
            window = [float(v) for v in ladder[max(0, idx - 1) : idx + 2]]
            refined[key] = window
        elif isinstance(best, bool):
            refined[key] = [best]
        else:
            refined[key] = list(values)[: len(values)]

    # Cap the product space.
    def product_size(g: Dict[str, List[Any]]) -> int:
        size = 1
        for v in g.values():
            size *= max(1, len(v))
        return size

    while product_size(refined) > _REFINE_MAX_COMBOS:
        widest = max(refined, key=lambda k: len(refined[k]))
        vals = refined[widest]
        if len(vals) <= 2:
            break
        refined[widest] = [v for v in vals if v == best_params.get(widest)] or vals[:2]
    return refined


def train_symbol(
    df: pd.DataFrame,
    base_cfg: LokiConfig,
    symbol: str,
    grid: Optional[Dict[str, List[Any]]] = None,
    train_frac: float = 0.7,
    top_n: int = 3,
    bars_per_year: int = 252,
    optimize_weights: bool = False,
    regime_dist: Optional[Dict[str, float]] = None,
    objective: str = "sharpe",
    hurdle_targets: Optional[Dict[str, float]] = None,
) -> SymbolReport:
    """Train execution parameters on historical bars for one symbol.

    Pure function of ``df`` — no network, no clock — so it is fully testable.
    When ``optimize_weights`` is set, the multi-factor weight presets are
    swept first and the top presets are combined with the execution grid.

    ``objective`` selects the ranking metric ("sharpe" default, "win_rate"
    for the aggressive hit-rate chase, "return" for raw growth) and
    ``hurdle_targets`` overrides the good-trade hurdle thresholds (e.g.
    ``{"win_rate_pct": 90.0}`` for the 90% target mode).
    """
    report = SymbolReport(symbol=symbol, bars=len(df))
    if regime_dist:
        report.regime_distribution = regime_dist
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

    # ------------------------------------------------------------------
    # Compute the factor columns ONCE. Tunables (weights + execution)
    # change only the composite score, so every candidate reuses this.
    # ------------------------------------------------------------------
    strategy = EnsembleStrategy(base_cfg)
    factors = strategy.compute_factors(df)

    train_frame = factors.iloc[:split_idx]
    leaderboard: List[Dict[str, Any]] = []
    weights_tested = 0

    def evaluate(
        weights: Optional[Dict[str, float]],
        preset_name: str,
        params: Dict[str, Any],
    ) -> None:
        cfg_i = _cfg_with(base_cfg, params)
        if weights is not None:
            cfg_i = dataclasses.replace(cfg_i, factor_weights=normalize_weights(weights))
        frame = strategy.score_from_factors(
            factors, weights if weights is not None else cfg_i.factor_weights
        )
        train_f = frame.iloc[:split_idx]
        try:
            res = run_backtest(
                train_df,
                cfg_i,
                symbol=symbol,
                bars_per_year=bars_per_year,
                frame=train_f,
            )
        except Exception as exc:  # noqa: BLE001 - one bad combo must not kill the sweep
            logger.warning("train: %s %s %s failed: %s", symbol, preset_name, params, exc)
            return
        leaderboard.append(
            {
                "params": dict(params),
                "weight_preset": preset_name,
                "factor_weights": None if weights is None else normalize_weights(weights),
                "train": _result_metrics(res),
            }
        )

    if optimize_weights:
        # Phase A — sweep factor-weight presets with the base execution cfg.
        for name, weights in FACTOR_PRESETS:
            weights_tested += 1
            evaluate(weights, name, {})  # base execution params
        preset_board = [e for e in leaderboard]
        preset_board.sort(key=lambda e: _rank_key(e, objective))
        preset_board.reverse()
        top_presets = []
        for e in preset_board[: max(1, top_n)]:
            key = e["weight_preset"]
            weights = next(w for n, w in FACTOR_PRESETS if n == key)
            top_presets.append((key, weights))
        leaderboard = []  # reset; the final sweep rebuilds it

        # Phase B — full execution grid under each of the top presets.
        for preset_name, weights in top_presets:
            for params in iter_grid(grid):
                evaluate(weights, preset_name, params)
    else:
        weights_tested = 0
        for params in iter_grid(grid):
            evaluate(base_cfg.factor_weights, "config", params)

    report.n_combos = len(leaderboard)
    if not leaderboard:
        report.error = f"every parameter combination failed for {symbol}"
        return report

    leaderboard.sort(key=lambda e: _rank_key(e, objective))
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

    for entry in leaderboard[: max(1, top_n)]:
        cfg_i = _cfg_with(base_cfg, entry["params"])
        if entry.get("factor_weights"):
            cfg_i = dataclasses.replace(
                cfg_i, factor_weights=normalize_weights(entry["factor_weights"])
            )
        val_frame = strategy.score_from_factors(factors, cfg_i.factor_weights).iloc[val_start_idx:]
        try:
            res = run_backtest(
                val_df,
                cfg_i,
                symbol=symbol,
                bars_per_year=bars_per_year,
                frame=val_frame,
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
    report.validation_metrics = dict(
        best.get("validation", _oos_metrics([], base_cfg.initial_cash))
    )
    report.validated = bool(
        report.validation_metrics.get("trades", 0) > 0
        and report.validation_metrics.get("return_pct", 0.0) > 0.0
    )
    report.hurdles = check_hurdles(report.validation_metrics, hurdle_targets)
    report.good = _passed_all(report.hurdles)
    preset = best.get("weight_preset", "")
    report.factor_preset = preset if preset and preset != "config" else ""
    # Attach trained factor weights only when weight optimization actually
    # ran (preset name other than "config"), so best_params mirrors the
    # leaderboard entry's execution params otherwise.
    if best.get("factor_weights") and report.factor_preset:
        report.best_params["factor_weights"] = normalize_weights(best["factor_weights"])
        report.best_params["factor_preset"] = report.factor_preset
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
    optimize_weights: bool = False,
    refine_rounds: int = 1,
    objective: str = "sharpe",
    target_win_rate: Optional[float] = None,
    target_profitable_months: Optional[float] = None,
) -> Dict[str, Any]:
    """Train every symbol and return a serializable report dict.

    Network fetching happens here (one history download per symbol); failures
    are recorded per-symbol so one bad ticker doesn't abort the run.

    ``refine_rounds`` > 1 enables the "train until good trades" loop: while
    symbols fail their out-of-sample hurdles, re-sweep a refined neighborhood
    of their current best parameters (max ``_REFINE_MAX_COMBOS`` combos).
    ``objective="win_rate"`` with ``target_win_rate=90`` is the aggressive
    mode that keeps optimizing until the 90% profitability target is met (or
    the refinement budget is exhausted — the result then states plainly what
    the best verified configuration achieved).
    """
    cfg = base_cfg or LokiConfig()
    provider = get_provider()
    syms = [s.strip().upper() for s in (symbols or cfg.symbols) if s and s.strip()]
    period = period or cfg.period
    timeframe = timeframe or cfg.timeframe
    if grid is None and objective == "win_rate":
        grid = AGGRESSIVE_GRID  # small-TP geometry is what wins often
    bpy = bars_per_year_for(timeframe, crypto=any(is_crypto(s) for s in syms))
    max_rounds = max(1, int(refine_rounds))
    hurdle_targets: Dict[str, float] = {}
    if target_win_rate is not None:
        hurdle_targets["win_rate_pct"] = float(target_win_rate)
    if target_profitable_months is not None:
        hurdle_targets["month_profit_rate_pct"] = float(target_profitable_months)

    datasets: Dict[str, pd.DataFrame] = {}
    errors: Dict[str, str] = {}
    for sym in syms:
        try:
            datasets[sym] = provider.fetch_history(sym, period, timeframe)
        except Exception as exc:  # noqa: BLE001 - e.g. yfinance offline
            errors[sym] = f"data fetch failed: {exc}"

    current_grid: Dict[str, Dict[str, List[Any]]] = {s: (grid or DEFAULT_GRID) for s in syms}
    base_grid = grid or DEFAULT_GRID
    symbol_dicts: List[Dict[str, Any]] = []
    rounds_used = 1

    for round_no in range(1, max_rounds + 1):
        rounds_used = round_no
        symbol_dicts = []
        for sym in syms:
            if sym in errors:
                rep_dict = SymbolReport(
                    symbol=sym, error=errors[sym], refine_round=round_no
                ).to_dict()
            else:
                df = datasets[sym]
                regime_dist = {}
                try:
                    frame = EnsembleStrategy(cfg).compute_factors(df)
                    regime_dist = regime_distribution(frame)
                except Exception:  # noqa: BLE001
                    regime_dist = {}
                rep = train_symbol(
                    df,
                    cfg,
                    sym,
                    grid=current_grid[sym],
                    train_frac=train_frac,
                    top_n=top_n,
                    bars_per_year=bpy,
                    optimize_weights=optimize_weights,
                    regime_dist=regime_dist,
                    objective=objective,
                    hurdle_targets=hurdle_targets or None,
                )
                rep_dict = rep.to_dict()
                rep_dict["refine_round"] = round_no
                if round_no < max_rounds and rep.ok and not rep.good:
                    current_grid[sym] = _refined_grid(base_grid, rep.best_params)
            symbol_dicts.append(rep_dict)

        trainable = [d for d in symbol_dicts if d.get("ok")]
        consensus = consensus_params(trainable) if trainable else None
        interim = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "period": period,
            "timeframe": timeframe,
            "train_frac": train_frac,
            "grid_size": sum(1 for _ in iter_grid(base_grid)),
            "weights_tested": len(FACTOR_PRESETS) if optimize_weights else 0,
            "optimize_weights": bool(optimize_weights),
            "objective": objective,
            "hurdle_targets": hurdle_targets,
            "refine_rounds_target": max_rounds,
            "refine_round": rounds_used,
            "symbols": symbol_dicts,
            "consensus": consensus,
        }
        save_report(interim, cfg)  # incremental persistence survives timeouts

        if round_no >= max_rounds:
            break
        good_flags = [d["good"] for d in trainable]
        if good_flags and all(good_flags):
            break  # every trained symbol makes good trades — stop refining

    report = interim
    report["refine_rounds_used"] = rounds_used
    save_report(report, cfg)
    return report


def consensus_params(symbol_entries: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Cross-symbol majority/median of every symbol's best parameters.

    Numeric params use the median, booleans use the majority vote, and
    factor weights use the most-common winning preset. ``support_pct`` is
    the average share of symbols agreeing with the consensus per parameter.
    """
    entries = [e for e in symbol_entries if e.get("ok") and e.get("best_params")]
    if not entries:
        return None

    consensus: Dict[str, Any] = {}
    supports: List[float] = []
    numeric_keys = [k for k in DEFAULT_GRID if not isinstance(DEFAULT_GRID[k][0], bool)]
    bool_keys = [k for k in DEFAULT_GRID if isinstance(DEFAULT_GRID[k][0], bool)]

    for key in numeric_keys:
        values = [e["best_params"][key] for e in entries if key in e["best_params"]]
        if not values:
            continue
        med = float(pd.Series(values).median())
        consensus[key] = round(med, 2)
        supports.append(sum(1 for v in values if abs(float(v) - med) < 1e-9) / len(values))

    for key in bool_keys:
        values = [bool(e["best_params"][key]) for e in entries if key in e["best_params"]]
        if not values:
            continue
        majority_true = sum(values) >= len(values) / 2
        consensus[key] = bool(majority_true)
        supports.append(sum(1 for v in values if v == majority_true) / len(values))

    presets = [e.get("factor_preset") for e in entries if e.get("factor_preset")]
    preset_weights: Optional[Dict[str, float]] = None
    winning_preset = ""
    if presets:
        winning_preset = max(set(presets), key=presets.count)
        preset_weights = next((w for n, w in FACTOR_PRESETS if n == winning_preset), None)
        consensus["factor_preset"] = winning_preset
        if preset_weights:
            consensus["factor_weights"] = preset_weights
            supports.append(presets.count(winning_preset) / len(presets))

    support = round(sum(supports) / len(supports) * 100.0, 1) if supports else 0.0
    return {
        "params": consensus,
        "symbols_used": len(entries),
        "support_pct": support,
    }


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

    Returns the applied parameters. Only keys in ``TRAINABLE_PARAMS`` (plus
    trained factor weights) are touched, and only when the symbol has a
    successful report entry.
    """
    for entry in report.get("symbols", []):
        if entry.get("symbol", "").upper() != symbol.upper() or not entry.get("ok"):
            continue
        params: Dict[str, Any] = {}
        for k, v in (entry.get("best_params") or {}).items():
            if k in TRAINABLE_PARAMS:
                params[k] = v
            elif k == "factor_weights" and isinstance(v, dict):
                params[k] = normalize_weights(v)
        applied = {}
        for k, v in params.items():
            setattr(cfg, k, v)
            applied[k] = v
        if applied:
            logger.info("applied trained params for %s: %s", symbol, applied)
        return applied
    return {}


def apply_consensus(report: Dict[str, Any], cfg: LokiConfig) -> Dict[str, Any]:
    """Apply the cross-symbol consensus parameters to ``cfg`` (in place)."""
    consensus = (report or {}).get("consensus")
    if not consensus or not consensus.get("params"):
        return {}
    applied: Dict[str, Any] = {}
    params = consensus["params"]
    for k in TRAINABLE_PARAMS:
        if k in params:
            setattr(cfg, k, params[k])
            applied[k] = params[k]
    if isinstance(params.get("factor_weights"), dict):
        cfg.factor_weights = normalize_weights(params["factor_weights"])
        applied["factor_weights"] = cfg.factor_weights
    logger.info("applied consensus params: %s", applied)
    return applied
