"""Offline, cost-aware walk-forward research for a long-only trend strategy.

This module deliberately has no broker, market-data, or machine-learning dependency.
It evaluates supplied bars; a favorable result is a paper-research candidate, never
permission to trade or a forecast of future returns.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class LabConfig:
    initial_capital: float = 10_000.0
    fee_bps: float = 10.0
    slippage_bps: float = 5.0
    periods_per_year: int = 252
    n_splits: int = 3
    min_train_bars: int = 100
    gap_bars: int = 1
    target_volatility: float = 0.15
    max_exposure: float = 0.5
    trailing_stop_pct: float = 0.08
    min_trades: int = 20
    max_drawdown: float = 0.20
    min_win_rate: float = 0.70

    def __post_init__(self) -> None:
        for name in ("periods_per_year", "n_splits", "min_train_bars", "gap_bars", "min_trades"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be an integer")
        for field in fields(self):
            value = getattr(self, field.name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{field.name} must be finite and numeric")
        if not 0 < self.initial_capital <= 1e15:
            raise ValueError("initial_capital must be positive and no more than 1e15")
        if not 0 <= self.fee_bps <= 500 or not 0 <= self.slippage_bps <= 500:
            raise ValueError("fee_bps and slippage_bps must be between 0 and 500")
        if not 1 <= self.periods_per_year <= 525_600:
            raise ValueError("periods_per_year must match the bar frequency (1..525600)")
        if not 2 <= self.n_splits <= 10:
            raise ValueError("n_splits must be between 2 and 10")
        if self.min_train_bars < 61 or self.gap_bars < 1:
            raise ValueError("min_train_bars must be at least 61 and gap_bars at least 1")
        if not 0 < self.target_volatility <= 2 or not 0 < self.max_exposure <= 1:
            raise ValueError("target_volatility must be in (0, 2] and max_exposure in (0, 1]")
        if not 0 < self.trailing_stop_pct < 1 or not 0 < self.max_drawdown < 1:
            raise ValueError("trailing_stop_pct and max_drawdown must be between 0 and 1")
        if self.min_trades < 1:
            raise ValueError("min_trades must be positive")
        if not 0 <= self.min_win_rate <= 1:
            raise ValueError("min_win_rate must be between 0 and 1")


@dataclass(frozen=True)
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class TrendParameters:
    fast: int
    slow: int


# A fixed, deliberately small search space. Cash must beat an unconvincing
# training result; the test window is never used to choose parameters.
CANDIDATES = (TrendParameters(5, 20), TrendParameters(10, 40), TrendParameters(20, 60))


def _timestamp(value: Any) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        # Date-only / naive timestamps have a documented UTC interpretation.
        normalized = parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
        if not math.isfinite(normalized.timestamp()):
            raise ValueError("Non-finite timestamp")
        return normalized
    except (TypeError, ValueError, OverflowError, OSError) as exc:
        raise ValueError("Each bar needs an ISO8601 timestamp") from exc


def validate_bars(data: Sequence[Mapping[str, Any]]) -> list[Bar]:
    """Reject bad ordering, duplicate timestamps and inconsistent candles.

    A pandas DataFrame is also accepted by duck typing, without importing pandas.
    Its index supplies timestamps when it has no ``timestamp`` column.
    """
    if hasattr(data, "to_dict") and hasattr(data, "index"):
        records = data.to_dict("records")
        data = [dict(record, timestamp=record.get("timestamp", index)) for index, record in zip(data.index, records)]
    if not isinstance(data, (list, tuple)) or not data or len(data) > 10_000:
        raise ValueError("Provide between 1 and 10000 OHLCV bars")
    bars: list[Bar] = []
    for i, record in enumerate(data):
        if not isinstance(record, Mapping) or not {"timestamp", "open", "high", "low", "close", "volume"} <= record.keys():
            raise ValueError(f"Bar {i} needs timestamp, open, high, low, close and volume")
        timestamp = _timestamp(record["timestamp"])
        if bars and timestamp <= bars[-1].timestamp:
            raise ValueError("Bar timestamps must be unique and sorted in ascending time order")
        try:
            if any(isinstance(record[key], bool) for key in ("open", "high", "low", "close", "volume")):
                raise ValueError("Boolean price")
            values = [float(record[key]) for key in ("open", "high", "low", "close", "volume")]
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"Bar {i} OHLCV values must be numeric") from exc
        if not all(math.isfinite(value) for value in values) or min(values[:4]) <= 0 or values[4] < 0:
            raise ValueError(f"Bar {i} prices must be finite and positive, and volume non-negative")
        open_, high, low, close, volume = values
        if not low <= min(open_, close) <= max(open_, close) <= high:
            raise ValueError(f"Bar {i} has inconsistent OHLC prices")
        bars.append(Bar(timestamp, open_, high, low, close, volume))
    return bars


def _win_interval(wins: int, total: int) -> list[float] | None:
    """Wilson interval; zero trades are missing evidence rather than 0% wins."""
    if not total:
        return None
    z = statistics.NormalDist().inv_cdf(0.975)
    fraction = wins / total
    denominator = 1 + z * z / total
    centre = (fraction + z * z / (2 * total)) / denominator
    half = z * math.sqrt(fraction * (1 - fraction) / total + z * z / (4 * total * total)) / denominator
    return [max(0.0, centre - half), min(1.0, centre + half)]


def _metrics(initial: float, equity: list[float], trades: list[dict[str, Any]], config: LabConfig) -> dict[str, Any]:
    previous = initial
    peak = initial
    max_drawdown = 0.0
    returns: list[float] = []
    for value in equity:
        returns.append(value / previous - 1 if previous > 0 else 0.0)
        previous = value
        peak = max(peak, value)
        max_drawdown = min(max_drawdown, value / peak - 1)
    final = equity[-1] if equity else initial
    deviation = statistics.stdev(returns) if len(returns) > 1 else 0.0
    wins = [trade["pnl"] for trade in trades if trade["pnl"] > 0]
    losses = [trade["pnl"] for trade in trades if trade["pnl"] < 0]
    profit_factor = sum(wins) / abs(sum(losses)) if losses else None
    if profit_factor is not None and not math.isfinite(profit_factor):
        profit_factor = None
    annual_log_return = math.log(final / initial) * config.periods_per_year / len(equity) if equity and final > 0 else 0.0
    # Do not emit non-JSON infinities when very short/extreme data is supplied.
    annualized = -1.0 if final <= 0 else math.expm1(annual_log_return) if annual_log_return < 700 else None
    return {
        "initial_capital": initial,
        "final_capital": final,
        "total_return": final / initial - 1,
        "annualized_return": annualized,
        "max_drawdown": max_drawdown,
        "sharpe_ratio": statistics.mean(returns) / deviation * math.sqrt(config.periods_per_year) if deviation else 0.0,
        "total_trades": len(trades),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate": len(wins) / len(trades) if trades else None,
        "win_rate_ci95": _win_interval(len(wins), len(trades)),
        "expectancy": statistics.mean(trade["pnl"] for trade in trades) if trades else None,
        "profit_factor": profit_factor,
        "total_fees": sum(trade["fees"] for trade in trades),
        "total_slippage": sum(trade["slippage"] for trade in trades),
        "observations": len(equity),
    }


def _signal(bars: list[Bar], index: int, parameters: TrendParameters, config: LabConfig) -> float:
    """Allocation formed from completed bars only; index is the execution bar."""
    if index < parameters.slow:
        return 0.0
    closes = [bar.close for bar in bars[index - parameters.slow:index]]
    if closes[-1] <= statistics.mean(closes) or statistics.mean(closes[-parameters.fast:]) <= statistics.mean(closes):
        return 0.0
    recent = closes[-21:]
    returns = [current / previous - 1 for previous, current in zip(recent, recent[1:])]
    volatility = statistics.stdev(returns) * math.sqrt(config.periods_per_year) if len(returns) > 1 else 0.0
    return min(config.max_exposure, config.target_volatility / volatility) if volatility > 0 else config.max_exposure


def analyze_trend(
    data: Sequence[Mapping[str, Any]], parameters: Mapping[str, Any] | TrendParameters,
    config: Mapping[str, Any] | LabConfig | None = None,
) -> dict[str, Any]:
    """Analyze completed candles with a frozen research parameter pair.

    The caller must exclude the currently forming candle. This uses exactly the
    research signal's completed-bar calculation for the *next* opening fill;
    it does not fit parameters or place orders. ``suggested_stop`` is a fresh
    entry reference, not the trailing high of an existing position.
    """
    if isinstance(parameters, Mapping):
        if set(parameters) != {"fast", "slow"}:
            raise ValueError("Trend parameters need fast and slow only")
        parameters = TrendParameters(**parameters)
    if not isinstance(parameters, TrendParameters):
        raise ValueError("parameters must be a frozen fast/slow pair")
    if (any(isinstance(value, bool) or not isinstance(value, int) for value in (parameters.fast, parameters.slow))
            or not 1 <= parameters.fast < parameters.slow <= 1000):
        raise ValueError("Trend parameters must satisfy 1 <= fast < slow <= 1000")
    if config is None:
        config = LabConfig()
    elif isinstance(config, Mapping):
        try:
            config = LabConfig(**config)
        except TypeError as exc:
            raise ValueError("Unknown research settings") from exc
    if not isinstance(config, LabConfig):
        raise ValueError("config must be a mapping of research settings")
    bars = validate_bars(data)
    allocation = _signal(bars, len(bars), parameters, config)
    return {
        "target_allocation": allocation,
        "latest_close": bars[-1].close,
        "suggested_stop": bars[-1].close * (1 - config.trailing_stop_pct),
        "timestamp": bars[-1].timestamp.isoformat(),
        "observations": len(bars),
        "parameters": asdict(parameters),
        "completed_bars_only": True,
    }


def _simulate(
    bars: list[Bar], start: int, end: int, parameters: TrendParameters | None,
    config: LabConfig, capital: float, multiplier: float = 1.0, benchmark: bool = False,
) -> dict[str, Any]:
    """Unlevered cash/share accounting with entry and exit costs.

    Positions close on the next open after a completed-bar exit/stop signal.
    All remaining positions liquidate at the last close, with costs included.
    """
    fee = config.fee_bps * multiplier / 10_000
    slip = config.slippage_bps * multiplier / 10_000
    cash = capital
    shares = 0.0
    entry: dict[str, Any] | None = None
    high_close = 0.0
    equity: list[float] = []
    trades: list[dict[str, Any]] = []

    def close(index: int, raw_price: float, reason: str) -> None:
        nonlocal cash, shares, entry
        price = raw_price * (1 - slip)
        proceeds = shares * price
        exit_fee = proceeds * fee
        cash += proceeds - exit_fee
        trades.append({
            "entry_timestamp": entry["timestamp"],
            "exit_timestamp": bars[index].timestamp.isoformat(),
            "entry_price": entry["price"], "exit_price": price,
            "quantity": shares,
            "pnl": proceeds - exit_fee - entry["outlay"],
            "fees": entry["fee"] + exit_fee,
            "slippage": entry["slippage"] + shares * (raw_price - price),
            "exit_reason": reason,
        })
        shares = 0.0
        entry = None

    for index in range(start, end):
        bar = bars[index]
        allocation = 1.0 if benchmark else _signal(bars, index, parameters, config) if parameters else 0.0
        stopped = False
        if shares and not benchmark:
            high_close = max(high_close, bars[index - 1].close)
            stopped = bars[index - 1].close <= high_close * (1 - config.trailing_stop_pct)
        if shares and (allocation == 0 or stopped):
            close(index, bar.open, "trailing_close_signal" if stopped else "trend_exit")
        # Only the completed bar's volume is known at an opening fill.
        # Avoid exiting/re-entering on the same open after a stop signal.
        previous_volume = bars[index - 1].volume if index else 0.0
        if not shares and cash > 0 and allocation > 0 and not stopped and previous_volume > 0:
            raw_price = bar.open
            price = raw_price * (1 + slip)
            outlay = cash * allocation
            shares = outlay / (price * (1 + fee))
            entry_fee = shares * price * fee
            cash -= outlay
            entry = {
                "timestamp": bar.timestamp.isoformat(), "price": price,
                "outlay": outlay, "fee": entry_fee,
                "slippage": shares * (price - raw_price),
            }
            high_close = raw_price
        if index == end - 1 and shares:
            close(index, bar.close, "window_end")
        equity.append(cash + shares * bar.close)
    return {"equity": equity, "trades": trades, "metrics": _metrics(capital, equity, trades, config)}


def _select(bars: list[Bar], train_end: int, config: LabConfig) -> tuple[TrendParameters | None, float, list[dict[str, Any]]]:
    selected = None
    best = 0.0
    trials: list[dict[str, Any]] = []
    for parameters in CANDIDATES:
        metrics = _simulate(bars, 0, train_end, parameters, config, config.initial_capital)["metrics"]
        # Both profit and a risk-adjusted score must beat cash in training.
        score = metrics["sharpe_ratio"] + metrics["max_drawdown"] if metrics["total_return"] > 0 else 0.0
        trials.append({"parameters": asdict(parameters), "train_score": score, "train_return": metrics["total_return"]})
        if score > best:
            selected, best = parameters, score
    return selected, best, trials


def _regime_analysis(
    bars: Sequence[Mapping[str, Any]],
    curve: Sequence[Mapping[str, Any]],
    benchmark_curve: Sequence[Mapping[str, Any]],
    trades: Sequence[Mapping[str, Any]],
    first_test: int,
    initial_capital: float,
) -> dict[str, Any]:
    """Re-slice the untouched test windows by simple, explainable regimes.

    Labels use only causal information: the 20-bar price change (±2% thresholds)
    and the trailing 20-bar mean absolute return (high volatility above 1.5× the
    test-window median, taking precedence over trend labels). Contributions are
    additive equity deltas while a regime is in force — snapshots inside the
    tested windows, never stand-alone strategy results.
    """
    lookback = 20
    total = len(curve)
    if total <= lookback or first_test <= lookback:
        return {"rules": "The history before the test window is too short for regime bucketing.", "rows": []}

    def equity_at(point: Any) -> float:
        return float(point["equity"]) if isinstance(point, Mapping) else float(point)

    closes: list[float] = [float(bar["close"]) if isinstance(bar, Mapping) else float(bar.close) for bar in bars]
    momentum: list[float] = []
    dispersion: list[float] = []
    for i in range(total):
        index = first_test + i
        momentum.append(closes[index] / closes[index - lookback] - 1.0)
        window = [abs(closes[j] / closes[j - 1] - 1.0) for j in range(index - lookback + 1, index + 1)]
        dispersion.append(statistics.fmean(window))
    high_vol_threshold = 1.5 * statistics.median(dispersion)
    labels: list[str] = []
    buckets: dict[str, dict[str, Any]] = {}

    def bucket(label: str) -> dict[str, Any]:
        return buckets.setdefault(
            label,
            {"regime": label, "bars": 0, "strategy": 0.0, "benchmark": 0.0, "exits": 0, "pnl_sum": 0.0},
        )

    strategy_prev, benchmark_prev = initial_capital, initial_capital
    for i in range(total):
        if dispersion[i] > high_vol_threshold:
            label = "High volatility"
        elif momentum[i] >= 0.02:
            label = "Trending up"
        elif momentum[i] <= -0.02:
            label = "Trending down"
        else:
            label = "Ranging"
        labels.append(label)
        row = bucket(label)
        row["bars"] += 1
        row["strategy"] += equity_at(curve[i]) - strategy_prev
        row["benchmark"] += equity_at(benchmark_curve[i]) - benchmark_prev
        strategy_prev, benchmark_prev = equity_at(curve[i]), equity_at(benchmark_curve[i])

    exit_index: dict[str, int] = {}
    for i, point in enumerate(curve):
        exit_index.setdefault(point["timestamp"], i)
    for trade in trades:
        position_of_exit = exit_index.get(str(trade.get("exit_timestamp")))
        if position_of_exit is None:
            continue
        row = bucket(labels[position_of_exit])
        row["exits"] += 1
        row["pnl_sum"] += float(trade.get("pnl", 0.0))

    ordered = ("Trending up", "Trending down", "Ranging", "High volatility")
    rows: list[dict[str, Any]] = []
    for label in ordered:
        row = buckets.get(
            label,
            {"regime": label, "bars": 0, "strategy": 0.0, "benchmark": 0.0, "exits": 0, "pnl_sum": 0.0},
        )
        rows.append({
            "regime": label,
            "bars": row["bars"],
            "share_pct": row["bars"] / total * 100,
            "strategy_contribution_pct": row["strategy"] / initial_capital * 100,
            "benchmark_contribution_pct": row["benchmark"] / initial_capital * 100,
            "trades_closed_in_bucket": row["exits"],
            "average_trade_pnl": row["pnl_sum"] / row["exits"] if row["exits"] else None,
        })
    return {
        "rules": (
            "Trending up/down: the 20-bar price change is at least ±2%. High volatility: the trailing "
            "20-bar mean absolute return exceeds 1.5× its test-window median, and this label takes precedence "
            "over trend labels; remaining bars are ranging. Contributions are the equity deltas while the "
            "regime was in force inside the same untouched test windows — fragments of one run, not stand-alone strategies."
        ),
        "rows": rows,
    }


def evaluate_strategy(data: Sequence[Mapping[str, Any]], config: Mapping[str, Any] | LabConfig | None = None) -> dict[str, Any]:
    """Run train-only selection, untouched forward tests and fixed-parameter stress.

    At least 20 test bars per fold are required. Inputs are local observations;
    provenance, correctness and point-in-time availability remain the caller's
    responsibility. Values in the returned report are JSON serializable.
    """
    if config is None:
        config = LabConfig()
    elif isinstance(config, Mapping):
        unknown = set(config) - {field.name for field in fields(LabConfig)}
        if unknown:
            raise ValueError(f"Unknown research settings: {', '.join(sorted(map(str, unknown)))}")
        config = LabConfig(**config)
    elif not isinstance(config, LabConfig):
        raise ValueError("config must be a mapping of research settings")
    bars = validate_bars(data)
    minimum = config.min_train_bars + config.gap_bars + config.n_splits * 20
    if len(bars) < minimum:
        raise ValueError(f"Need at least {minimum} bars for these walk-forward settings")
    # Extreme finite inputs can still overflow portfolio accounting. Reject a
    # numerically unusable price range instead of producing misleading metrics.
    prices = [value for bar in bars for value in (bar.open, bar.close)]
    if max(prices) > 1e100 or min(prices) < 1e-100 or max(prices) / min(prices) > 1e100:
        raise ValueError("Price range is too extreme for reliable portfolio accounting")

    test_size = (len(bars) - config.min_train_bars - config.gap_bars) // config.n_splits
    first_test = len(bars) - test_size * config.n_splits
    folds: list[dict[str, Any]] = []
    equity: list[float] = []
    baseline_equity: list[float] = []
    trades: list[dict[str, Any]] = []
    baseline_trades: list[dict[str, Any]] = []
    all_trials: list[dict[str, Any]] = []
    capital = baseline_capital = config.initial_capital
    for fold in range(config.n_splits):
        start = first_test + fold * test_size
        end = start + test_size
        train_end = start - config.gap_bars
        parameters, score, trials = _select(bars, train_end, config)
        result = _simulate(bars, start, end, parameters, config, capital)
        baseline = _simulate(bars, start, end, None, config, baseline_capital, benchmark=True)
        folds.append({
            "fold": fold + 1, "train_end": bars[train_end - 1].timestamp.isoformat(),
            "test_start": bars[start].timestamp.isoformat(), "test_end": bars[end - 1].timestamp.isoformat(),
            "train_observations": train_end, "test_observations": test_size,
            "parameters": asdict(parameters) if parameters else {"mode": "cash"},
            "train_score": score, "metrics": result["metrics"],
            "benchmark_return": baseline["metrics"]["total_return"],
        })
        all_trials.extend(dict(trial, fold=fold + 1) for trial in trials)
        equity.extend(result["equity"])
        baseline_equity.extend(baseline["equity"])
        trades.extend(dict(trade, fold=fold + 1) for trade in result["trades"])
        baseline_trades.extend(baseline["trades"])
        capital = equity[-1]
        baseline_capital = baseline_equity[-1]

    summary = _metrics(config.initial_capital, equity, trades, config)
    baseline_metrics = _metrics(config.initial_capital, baseline_equity, baseline_trades, config)
    stress: list[dict[str, Any]] = []
    # Parameters stay frozen across cost scenarios. Re-optimizing would hide
    # sensitivity to execution costs.
    for multiplier in (1.0, 1.5, 2.0, 3.0):
        stress_equity: list[float] = []
        stress_trades: list[dict[str, Any]] = []
        stress_capital = config.initial_capital
        for i, fold in enumerate(folds):
            parameters = TrendParameters(**fold["parameters"]) if "fast" in fold["parameters"] else None
            start = first_test + i * test_size
            result = _simulate(bars, start, start + test_size, parameters, config, stress_capital, multiplier)
            stress_equity.extend(result["equity"])
            stress_trades.extend(result["trades"])
            stress_capital = stress_equity[-1]
        stress_metrics = _metrics(config.initial_capital, stress_equity, stress_trades, config)
        stress.append({"multiplier": multiplier, **stress_metrics})

    reasons: list[str] = []
    if summary["total_trades"] < config.min_trades:
        reasons.append(f"Only {summary['total_trades']} closed out-of-sample trades; need at least {config.min_trades}.")
    if config.min_win_rate > 0:
        if summary["win_rate"] is None or summary["win_rate"] < config.min_win_rate:
            reasons.append(f"Observed out-of-sample win rate does not meet the {config.min_win_rate:.0%} research target.")
        elif summary["win_rate_ci95"][0] < config.min_win_rate:
            reasons.append(f"The descriptive 95% win-rate interval does not establish a {config.min_win_rate:.0%} win rate.")
    if summary["total_return"] <= 0:
        reasons.append("Out-of-sample return after fees and slippage is not positive.")
    if summary["total_return"] <= baseline_metrics["total_return"]:
        reasons.append("Strategy did not beat the buy-and-hold baseline after costs.")
    if abs(summary["max_drawdown"]) > config.max_drawdown:
        reasons.append("Out-of-sample drawdown exceeds the configured research limit.")
    if sum(fold["metrics"]["total_return"] > 0 for fold in folds) < math.ceil(config.n_splits * 2 / 3):
        reasons.append("Too few forward windows have positive returns.")
    if stress[-1]["total_return"] <= 0:
        reasons.append("Return is not positive with fees and slippage at 3x the configured values.")

    peak = config.initial_capital
    curve: list[dict[str, Any]] = []
    for index, (value, benchmark_value) in enumerate(zip(equity, baseline_equity), start=first_test):
        peak = max(peak, value)
        curve.append({"timestamp": bars[index].timestamp.isoformat(), "equity": value,
                      "benchmark_equity": benchmark_value, "drawdown": value / peak - 1})
    canonical = [[bar.timestamp.isoformat(), bar.open, bar.high, bar.low, bar.close, bar.volume] for bar in bars]
    fingerprint = hashlib.sha256(json.dumps(canonical, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return {
        "status": "needs_more_evidence" if reasons else "paper_candidate",
        "live_trading_enabled": False,
        "strategy": "Volatility-sized long-only trend with a trailing close exit",
        "data_fingerprint": fingerprint, "bars": len(bars),
        "win_rate_target": config.min_win_rate,
        "win_rate_target_met": bool(summary["win_rate"] is not None and summary["win_rate"] >= config.min_win_rate),
        "win_rate_target_supported": bool(summary["win_rate_ci95"] is not None and summary["win_rate_ci95"][0] >= config.min_win_rate),
        "test_start": bars[first_test].timestamp.isoformat(), "test_end": bars[-1].timestamp.isoformat(),
        "config": asdict(config), "summary": summary, "benchmark": baseline_metrics,
        "excess_return": summary["total_return"] - baseline_metrics["total_return"],
        "folds": folds, "cost_stress": stress, "equity_curve": curve,
        "regime_metrics": _regime_analysis(bars, curve, baseline_equity, trades, first_test, config.initial_capital),
        "trades": trades, "trial_count": len(all_trials), "trial_ledger": all_trials,
        "rejection_reasons": reasons,
        "assumptions": [
            "Historical research cannot guarantee profitability or a 70% win rate.",
            "Parameters are selected on expanding training windows; only later test windows enter headline metrics.",
            "Gap bars are excluded from fitting; completed bars before each execution may warm up indicators.",
            "Signals use completed closes and execute at the next open; a trailing exit can gap beyond its threshold.",
            "Long only, no leverage, fixed entry size, no intrabar stop-fill assumptions; cash earns zero interest.",
            "max_exposure and target_volatility size entries; held exposure and volatility can drift after entry.",
            "Fees and adverse slippage apply on both entry and exit; every fold ends with liquidation at its final close.",
            "The full-exposure buy-and-hold benchmark uses the same test windows and transaction costs.",
            "Cost stress holds selected parameters fixed and multiplies both fees and slippage.",
            "periods_per_year must match bar frequency; Sharpe assumes zero risk-free return.",
            "Win-rate intervals are descriptive Wilson intervals; serial dependence can make uncertainty larger.",
            "A zero-volume completed bar blocks the next entry; exits assume liquidity. No spread, market impact, funding, taxes or dividends are modeled.",
            "Input provenance and point-in-time availability are not independently verified; naive timestamps are interpreted as UTC.",
            "Regime rows re-slice these same test windows into trending, ranging and high-volatility fragments; they are one run's pieces, not separate strategies.",
        ],
    }
