"""A separate pullback hypothesis with training-only selection and adverse fills.

This is an unvalidated research candidate, not a promise of a higher win rate.
Only three declared recipes are tried. Test prices never select a recipe. Reusing
the same uploaded test history still makes it explored data, not a fresh holdout.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import statistics

from core.fusion.quant import _bars, _config, _summary, _symbol
from third_party.vibe_trading.indicators import compute_rsi


@dataclass(frozen=True)
class PullbackRecipe:
    rsi_ceiling: int
    band_sigma: float
    stop_atr: float
    target_atr: float


RECIPES = (
    PullbackRecipe(30, 1.5, 2.0, 1.5),
    PullbackRecipe(35, 1.75, 1.75, 1.25),
    PullbackRecipe(25, 2.0, 2.25, 1.75),
)
STRATEGY_ID = "loki_pullback_reversion_v1"


def _features(bars):
    closes = [bar.close for bar in bars]
    rsi = compute_rsi(closes)
    ranges = [
        (
            max(
                bar.high - bar.low,
                abs(bar.high - bars[index - 1].close),
                abs(bar.low - bars[index - 1].close),
            )
            if index
            else bar.high - bar.low
        )
        for index, bar in enumerate(bars)
    ]
    result = []
    for index, bar in enumerate(bars):
        result.append(
            None
            if index < 99
            else {
                "close": bar.close,
                "rsi": rsi[index],
                "mean20": statistics.mean(closes[index - 19 : index + 1]),
                "std20": statistics.pstdev(closes[index - 19 : index + 1]),
                "mean100": statistics.mean(closes[index - 99 : index + 1]),
                "atr": statistics.mean(ranges[index - 13 : index + 1]),
            }
        )
    return result


def _entry(feature, recipe):
    return bool(
        feature
        and feature["rsi"] is not None
        and feature["std20"] > 0
        and feature["close"] >= feature["mean100"]
        and feature["close"] <= feature["mean20"] - recipe.band_sigma * feature["std20"]
        and feature["rsi"] <= recipe.rsi_ceiling
        and 0 < feature["atr"] / feature["close"] <= 0.08
    )


def _replay(bars, features, config, recipe, start, end=None, multiplier=1):
    end = len(bars) if end is None else end
    cash, units, entry = config.initial_capital, 0.0, None
    equity, trades = [], []
    fee, slip = config.fee_bps * multiplier / 10000, config.slippage_bps * multiplier / 10000
    peak, halted = cash, False

    def close(index, reference, reason):
        nonlocal cash, units, entry
        fill = reference * (1 - slip)
        proceeds, exit_fee = units * fill, units * fill * fee
        cash += proceeds - exit_fee
        trades.append(
            {
                "entry_timestamp": entry["timestamp"],
                "exit_timestamp": bars[index].timestamp.isoformat(),
                "entry_price": entry["price"],
                "exit_price": fill,
                "quantity": units,
                "pnl": proceeds - exit_fee - entry["outlay"],
                "fees": entry["fee"] + exit_fee,
                "slippage": entry["slippage"] + units * (reference - fill),
                "exit_reason": reason,
            }
        )
        units, entry = 0.0, None

    def intrabar_exit(index):
        bar = bars[index]
        if bar.open <= entry["stop"]:
            close(index, bar.open, "stop_gap")
        elif bar.open >= entry["target"]:
            close(index, entry["target"], "target_limit")
        elif bar.low <= entry["stop"]:
            # OHLC cannot reveal which threshold came first. Choose the loss.
            close(index, entry["stop"], "stop_first_if_ambiguous")
        elif bar.high >= entry["target"]:
            close(index, entry["target"], "target_limit")

    for index in range(start, end):
        bar, previous, feature = bars[index], bars[index - 1], features[index - 1]
        had_position = bool(units)
        if units:
            if halted or index - entry["index"] >= config.max_holding_bars:
                close(index, bar.open, "drawdown_halt" if halted else "holding_limit")
            else:
                intrabar_exit(index)
        if (
            not had_position
            and not units
            and not halted
            and recipe is not None
            and index < end - 1
            and _entry(feature, recipe)
        ):
            stop = bar.open - recipe.stop_atr * feature["atr"]
            target = bar.open + recipe.target_atr * feature["atr"]
            fill = bar.open * (1 + slip)
            unit_cash = fill * (1 + fee)
            unit_risk = unit_cash - stop * (1 - slip) * (1 - fee)
            reward = target * (1 - slip) * (1 - fee) - unit_cash
            if stop > 0 and unit_risk > 0 and reward / unit_risk >= 0.6:
                units = min(
                    cash * config.max_exposure / unit_cash,
                    cash * config.risk_per_trade / unit_risk,
                    previous.volume * 0.005,
                )
                if units > 0:
                    outlay = units * unit_cash
                    entry = {
                        "timestamp": bar.timestamp.isoformat(),
                        "index": index,
                        "price": fill,
                        "outlay": outlay,
                        "fee": units * fill * fee,
                        "slippage": units * (fill - bar.open),
                        "stop": stop,
                        "target": target,
                    }
                    cash = max(0, cash - outlay)
                    intrabar_exit(index)
        marked = cash + units * bar.close
        peak = max(peak, marked)
        halted = halted or marked / peak - 1 <= -config.max_drawdown
        equity.append(marked)
    if units:
        close(end - 1, bars[end - 1].close, "end_of_test_liquidation")
        equity[-1] = cash
    return {
        "summary": _summary(config.initial_capital, equity, trades),
        "trades": trades,
        "equity": equity,
        "drawdown_halt_triggered": halted,
    }


def evaluate_pullback(data, config=None, *, symbol="BTC/USDT", train_fraction=0.6):
    """Compare three fixed hypotheses on training prices, then freeze one for testing."""
    bars, settings, symbol = _bars(data, 260), _config(config), _symbol(symbol)
    if (
        isinstance(train_fraction, bool)
        or not isinstance(train_fraction, (int, float))
        or not math.isfinite(train_fraction)
        or not 0.5 <= train_fraction <= 0.8
    ):
        raise ValueError("train_fraction must be between .5 and .8")
    split = int(len(bars) * train_fraction)
    if split < 130 or len(bars) - split < 50:
        raise ValueError("Need at least 130 training bars and 50 later test bars")
    features, trials = _features(bars), []
    chosen, score = None, 0.0
    for recipe in RECIPES:
        base = _replay(bars, features, settings, recipe, 100, split)
        stress = _replay(bars, features, settings, recipe, 100, split, 2)
        summary = base["summary"]
        eligible = (
            summary["total_trades"] >= 10
            and summary["expectancy"] is not None
            and summary["expectancy"] > 0
            and summary["total_return"] > 0
            and stress["summary"]["total_return"] > 0
        )
        candidate_score = summary["total_return"] - abs(summary["max_drawdown"]) / 2
        trials.append(
            {
                "parameters": asdict(recipe),
                "summary": summary,
                "double_cost_return": stress["summary"]["total_return"],
                "eligible": eligible,
            }
        )
        if eligible and candidate_score > score:
            chosen, score = recipe, candidate_score
    result = _replay(bars, features, settings, chosen, split)
    stress = [
        _replay(bars, features, settings, chosen, split, multiplier=multiple)
        for multiple in (1, 2, 3)
    ]
    summary, reasons = result["summary"], []
    interval = summary["win_rate_ci95"]
    exit_dates = {row["exit_timestamp"][:10] for row in result["trades"]}
    if chosen is None:
        reasons.append(
            "No training recipe met the net-return, expectancy, trade-count and doubled-cost checks; cash was selected."
        )
    if summary["total_trades"] < 100:
        reasons.append(
            "At least 100 completed test trades are required; current evidence is limited."
        )
    if interval is None or interval[0] < settings.min_win_rate:
        reasons.append("The descriptive 95% lower win-rate bound does not meet the target.")
    if len(exit_dates) < 30:
        reasons.append(
            "Trades span fewer than 30 distinct exit dates; temporal coverage is limited."
        )
    if any(row["summary"]["total_return"] <= 0 for row in stress):
        reasons.append("Positive return is required at base, doubled and tripled trading costs.")
    if summary["expectancy"] is None or summary["expectancy"] <= 0:
        reasons.append("Positive completed-trade expectancy after costs is required.")
    if result["drawdown_halt_triggered"]:
        reasons.append("The test triggered its drawdown halt.")
    fingerprint = hashlib.sha256(
        json.dumps(
            [
                [bar.timestamp.isoformat(), bar.open, bar.high, bar.low, bar.close, bar.volume]
                for bar in bars
            ],
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    return {
        "strategy_id": STRATEGY_ID,
        "symbol": symbol,
        "mode": "research_only",
        "validation_mode": "chronological_split_exploratory",
        "config": asdict(settings),
        "data_fingerprint": fingerprint,
        "train_end": bars[split - 1].timestamp.isoformat(),
        "test_start": bars[split].timestamp.isoformat(),
        "test_end": bars[-1].timestamp.isoformat(),
        "parameters": asdict(chosen) if chosen else {},
        "training_trials": trials,
        "summary": summary,
        "trades": result["trades"],
        "equity_curve": [
            {"timestamp": bar.timestamp.isoformat(), "equity": value}
            for bar, value in zip(bars[split:], result["equity"])
        ],
        "cost_stress": [
            {"multiplier": multiple, **row["summary"]} for multiple, row in zip((1, 2, 3), stress)
        ],
        "target_evidence": {
            "target": settings.min_win_rate,
            "sample_meets_checks": not reasons,
            "fresh_holdout_verified": False,
            "future_win_rate_guaranteed": False,
        },
        "status": "historical_sample_meets_checks" if not reasons else "needs_more_evidence",
        "rejection_reasons": reasons,
        "live_trading_enabled": False,
        "assumptions": [
            "Long-only oversold pullbacks above the 100-close average; all features use completed bars.",
            "Entries fill at the following open; both sides include adverse slippage and fees.",
            "Targets are limit-price references; stop wins when one bar touches stop and target. Gaps can increase losses.",
            "Sizing caps cash, planned stop risk, 20% default exposure, and 0.5% of preceding volume.",
            "The three declared recipes are selected only on earlier training results; cash is a valid choice.",
            "Uploaded provenance and prior inspection are unverified. Repeated tests on the same sample can overfit.",
            "No leverage, funding, exchange lot sizes, order-book queue or partial-fill modeling.",
            "The Wilson interval assumes independent trades; correlated trades weaken evidence. No future 70% win rate is proven.",
        ],
    }
