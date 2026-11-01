"""Bounded lower-turnover comparisons on frozen, previously inspected history.

Validation selects a fixed rule at doubled costs. Later dates are diagnostic,
not a fresh holdout after earlier experiments have inspected those dates.
"""
from datetime import datetime, timezone
import hashlib
import json
import math
import statistics

from core.strategy_lab import validate_bars, _win_interval
from core.fusion import paper_models
from core.fusion.paper_rules import RULES, WARMUP, frozen_rule, signal_series, notional_budget
from core.fusion.instrument_history import MAX_HISTORY_BARS


INITIAL_CAPITAL = 10000.0


def replay(bars, signals, policy, start, end, *, cost_multiple=1):
    """Next-open entries, stop-first intraday exits, no same-bar re-entry."""
    if not WARMUP < start < end <= len(bars) or len(signals) != len(bars):
        raise ValueError("Replay needs a warmed-up, bounded daily interval")
    if cost_multiple not in (1, 2):
        raise ValueError("Cost stress is fixed at 1x or 2x")
    fee = policy["fee_bps"] / 10000 * cost_multiple
    slip = policy["slippage_bps"] / 10000 * cost_multiple
    cash, qty, entry, age = INITIAL_CAPITAL, 0, 0.0, 0
    peak, drawdown, exposure, costs = INITIAL_CAPITAL, 0.0, 0, 0.0
    entry_date, trades, curve = None, [], []

    def exit_at(price, reason, bar):
        nonlocal cash, qty, costs
        fill = price * (1 - slip)
        proceeds = qty * fill * (1 - fee)
        pnl = proceeds - qty * entry * (1 + fee)
        costs += qty * (price - fill + fill * fee)
        trades.append({"entry_date": entry_date, "timestamp": bar.timestamp.date().isoformat(),
                       "qty": qty, "entry_price": entry, "exit_price": fill,
                       "pnl": pnl, "reason": reason, "sessions": age})
        cash += proceeds
        qty = 0

    for index in range(start, end):
        bar, signal = bars[index], signals[index - 1]
        exited = False
        if qty:
            age += 1
            stop, take = entry * (1 - policy["stop_pct"]), entry * (1 + policy["take_profit_pct"])
            if bar.open <= stop:
                exit_at(bar.open, "stop_gap", bar)
                exited = True
            elif bar.open >= take:
                exit_at(take, "take_profit", bar)
                exited = True
            elif not signal["hold"] or age >= policy["max_holding_sessions"]:
                exit_at(bar.open, "signal_or_time", bar)
                exited = True
        if not qty and not exited and signal["enter"]:
            price = bar.open * (1 + slip)
            budget = notional_budget(policy, cash, cash, policy["max_notional"])
            qty = math.floor(budget / (price * (1 + fee)))
            if qty:
                cash -= qty * price * (1 + fee)
                costs += qty * (price - bar.open + price * fee)
                entry, age, entry_date = price, 0, bar.timestamp.date().isoformat()
        if qty:
            exposure += 1
            stop, take = entry * (1 - policy["stop_pct"]), entry * (1 + policy["take_profit_pct"])
            if bar.low <= stop:
                exit_at(min(bar.open, stop), "stop_first", bar)
            elif bar.high >= take:
                exit_at(take, "take_profit", bar)
        equity = cash + qty * bar.close
        peak = max(peak, equity)
        drawdown = max(drawdown, 1 - equity / peak)
        curve.append({"timestamp": bar.timestamp.date().isoformat(), "equity": equity})
    if qty:
        exit_at(bars[end - 1].close, "evaluation_end", bars[end - 1])
        curve[-1]["equity"] = cash
        drawdown = max(drawdown, 1 - cash / peak)
    wins = sum(t["pnl"] > 0 for t in trades)
    gain = sum(max(t["pnl"], 0) for t in trades)
    loss = -sum(min(t["pnl"], 0) for t in trades)
    return {
        "net_return": cash / INITIAL_CAPITAL - 1,
        "net_pnl_usd": cash - INITIAL_CAPITAL,
        "closed_trades": len(trades),
        "win_rate": wins / len(trades) if trades else None,
        "win_rate_95pct_interval": _win_interval(wins, len(trades)),
        "expectancy_usd": statistics.mean(t["pnl"] for t in trades) if trades else None,
        "profit_factor": gain / loss if loss else None,
        "max_drawdown": drawdown,
        "estimated_costs_usd": costs,
        "exposure_fraction": exposure / (end - start),
        "trades": trades,
        "equity_curve": curve,
    }


def compact(result):
    return {key: value for key, value in result.items() if key not in ("trades", "equity_curve")}


def passive(bars, start, end, multiple=1):
    fee, slip = 0.001 * multiple, 0.0005 * multiple
    opening = bars[start].open * (1 + slip)
    qty = math.floor(1000 / (opening * (1 + fee)))
    return (qty * bars[end - 1].close * (1 - slip) * (1 - fee)
            - qty * opening * (1 + fee)) / INITIAL_CAPITAL


def choose(trials):
    """Selection never sees the later evaluation interval."""
    eligible = [trial for trial in trials if trial["eligible"]]
    if not eligible:
        return None
    return max(eligible, key=lambda t: (t["stress"]["net_return"], -t["closed_trades"]))


def validate_execution_report(report):
    """Old saved reports must not retain the removed validation bypass."""
    from core.fusion.paper_rules import validate_artifact

    rule = validate_artifact(report["artifact"])
    if report["artifact"]["threshold"] is None:
        return
    trials = report.get("validation", {}).get("trials", [])
    winner = choose(trials)
    if winner is None or winner["rule"] != rule.name:
        raise ValueError("Saved paper rule did not pass validation; rerun the strategy comparison")


def compare(base, rows):
    if base.get("artifact", {}).get("version") not in {
        paper_models.MODEL_VERSION,
        "loki_instrument_daily_logistic_v1",
    }:
        raise ValueError("Choose an original instrument model as the comparison baseline")
    if not isinstance(rows, list) or not 850 <= len(rows) <= MAX_HISTORY_BARS:
        raise ValueError("Comparison needs a complete saved 5/10/15/20-year daily dataset")
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    if digest != base["data_sha256"]:
        raise ValueError("Comparison input differs from its frozen dataset")
    bars = validate_bars(rows)
    days = [b.timestamp.date().isoformat() for b in bars]
    validation_start = days.index(base["validation"]["start"])
    test_start = days.index(base["test"]["start"])
    if not WARMUP < validation_start < test_start < len(bars) - 20:
        raise ValueError("Saved chronological evaluation boundaries are invalid")
    trials, series = [], {}
    for rule in RULES:
        signals = series[rule.name] = signal_series(bars, rule)
        normal = replay(bars, signals, rule.policy(), validation_start, test_start)
        stress = replay(bars, signals, rule.policy(), validation_start, test_start, cost_multiple=2)
        boundaries = [validation_start + (test_start - validation_start) * i // 3 for i in range(4)]
        folds = [dict(start=days[a], end=days[b - 1], **compact(replay(
            bars, signals, rule.policy(), a, b, cost_multiple=2)))
            for a, b in zip(boundaries, boundaries[1:])]
        positive_folds = sum(f["net_return"] > 0 for f in folds)
        eligible = (normal["closed_trades"] >= 3 and normal["net_return"] > 0 and stress["net_return"] > 0
                    and positive_folds >= 2 and stress["max_drawdown"] <= 0.03 and normal["max_drawdown"] <= 0.03)
        trials.append({"rule": rule.name, "threshold": 1.0, **compact(normal),
                       "stress": compact(stress), "folds": folds,
                       "positive_folds": positive_folds, "eligible": eligible})
    chosen = choose(trials)
    selected = next((rule for rule in RULES if chosen and rule.name == chosen["rule"]), RULES[0])
    if chosen is None:
        threshold = None
        signals = [{"enter": False, "hold": False}] * len(bars)
    else:
        threshold = 1.0
        signals = series[selected.name]
    test = replay(bars, signals, selected.policy(), test_start, len(bars))
    stress = replay(bars, signals, selected.policy(), test_start, len(bars), cost_multiple=2)
    # Diagnostic rows are computed only after validation has frozen the choice.
    diagnostics = [dict(rule=r.name, **compact(replay(bars, series[r.name], r.policy(), test_start, len(bars)))) for r in RULES]
    artifact = {
        **frozen_rule(selected), "symbol": base["symbol"], "threshold": threshold,
        "features": ["completed_daily_trend", "momentum", "volatility_20"],
        "training_end": base["training"]["end"],
        "selection_end": base["validation"]["end"],
        "selection_fingerprint": hashlib.sha256(json.dumps(rows[:test_start], sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
    }
    artifact_hash = hashlib.sha256(json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "id": hashlib.sha256((digest + artifact_hash).encode()).hexdigest(),
        "symbol": base["symbol"], "requested_years": base["requested_years"],
        "coverage": base["coverage"], "training": base["training"],
        "validation": {"start": days[validation_start], "end": days[test_start - 1],
                       "examples": test_start - validation_start, "trials": trials},
        "test": {"start": days[test_start], "end": days[-1], "examples": len(bars) - test_start,
                 **test, "buy_and_hold_10pct_net_return": passive(bars, test_start, len(bars)), "cash_baseline_return": 0.0},
        "cost_stress": {"multiple": 2, **compact(stress)},
        "comparison": {"selection": chosen["rule"] if chosen else "cash", "candidates": diagnostics,
                       "baseline_model_id": base["id"], "baseline_test": compact(base["test"])},
        "artifact": artifact, "artifact_sha256": artifact_hash, "data_sha256": digest,
        "source": base["source"],
        "status": "experimental_paper_policy" if chosen else "no_validation_edge_wait_in_cash",
        "target_70_percent_proven": False, "live_automation_available": False,
        "forward_evidence": {"status": "not_yet_observed", "historical_dates_already_inspected": True,
                             "frozen_at": datetime.now(timezone.utc).isoformat(), "historical_end": days[-1]},
        "limitations": [
            "Five development rules: 50/200, 20/50 and 10/30 trends, 20/100 momentum, and a 5-day pullback in a 100-day uptrend. The rule set was expanded after earlier historical evaluations.",
            "Validation alone selects the largest net return at doubled costs, requiring three trades, two of three positive chronological blocks and at most 3% account drawdown. Each block starts in cash.",
            "The recent evaluation dates were previously inspected. These results are retrospective development evidence, not a newly untouched test or proof of future profitability.",
            "Rules use completed daily bars and enter at the next open. Whole units, 10%/1000 USD cap and 0.5% equity loss-at-stop sizing; gaps can exceed the planned stop loss.",
            "Paper execution shares the frozen signal and policy, but actual quotes, intraday path, fees and fills differ from daily-bar proxies. Server-monitored exits require an active browser heartbeat.",
            "Normal costs are 10 bps fees and 5 bps slippage per side; stress doubles both. All candidates and the matched passive 10% allocation are shown, including losing candidates.",
            "Positive history may simply reflect market exposure. Small samples, correlated trades, missing dividends and revised single-venue data limit the evidence; new forward paper observations are required.",
        ],
    }
