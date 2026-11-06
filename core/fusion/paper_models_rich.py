"""Rich causal OHLCV feature family for the daily instrument research protocol.

Feature v3 uses only bars up to the prediction index: multi-horizon
momentum/means, volatility, normalized true range, overnight gap and a
14-session range statistic. Training fits to convergence with ridge Newton
steps; threshold selection uses the validation interval only, and the selected
threshold must also survive a doubled-cost replay before it is reported. The
final 20% is diagnostic and never selects settings. No live authority.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
import re
import sqlite3
import statistics

from core.fusion.learning import _sigmoid, _solve
from core.fusion.paper_models import POLICY, replay, _win_interval
from core.fusion.instrument_history import HISTORY_YEARS, MAX_HISTORY_BARS
from core.strategy_lab import validate_bars

MODEL_VERSION = "loki_instrument_daily_rich_v3"
FEATURES = (
    "last_return",
    "mean_5",
    "mean_10",
    "mean_20",
    "volatility_20",
    "atr_14_pct",
    "gap_pct",
    "stoch_14",
    "momentum_10",
)
THRESHOLDS = (0.55, 0.60, 0.65)


def feature_vector(bars, index=None):
    index = len(bars) - 1 if index is None else index
    if index < 20:
        raise ValueError("A prediction needs 21 completed daily bars")
    closes = [bars[j].close for j in range(index - 20, index + 1)]
    returns = [closes[j] / closes[j - 1] - 1 for j in range(1, len(closes))]
    previous_close = closes[-2]
    trues = []
    for j in range(index - 13, index + 1):
        before = bars[j - 1].close
        trues.append(
            max(
                bars[j].high - bars[j].low,
                abs(bars[j].high - before),
                abs(bars[j].low - before),
            )
            / before
        )
    window_low = min(bars[j].low for j in range(index - 13, index + 1))
    window_high = max(bars[j].high for j in range(index - 13, index + 1))
    span = window_high - window_low
    return [
        returns[-1],
        statistics.fmean(returns[-5:]),
        statistics.fmean(returns[-10:]),
        statistics.fmean(returns),
        statistics.pstdev(returns),
        sum(trues) / len(trues),
        bars[index].open / previous_close - 1,
        1.0 if span == 0 else (bars[index].close - window_low) / span,
        closes[-1] / closes[-11] - 1,
    ]


def fit(samples, feature_count=len(FEATURES)):
    means = [statistics.fmean(row[1][i] for row in samples) for i in range(feature_count)]
    scales = [
        statistics.pstdev(row[1][i] for row in samples) or 1 for i in range(feature_count)
    ]
    features = [
        tuple(
            max(-10, min(10, (value - mean) / scale))
            for value, mean, scale in zip(row[1], means, scales)
        )
        for row in samples
    ]
    labels = [row[2] for row in samples]
    base = (sum(labels) + 1) / (len(samples) + 2)
    ridge, floor = 0.01, 1e-10
    size = feature_count + 1

    def objective(coefficients):
        loss = 0.0
        for vector, label in zip(features, labels):
            score = _sigmoid(
                coefficients[0] + sum(c * x for c, x in zip(coefficients[1:], vector))
            )
            loss -= math.log(max(score, 1e-15)) if label else math.log(max(1 - score, 1e-15))
        return loss / len(samples) + ridge * sum(c * c for c in coefficients[1:]) / 2

    coefficients = [math.log(base / (1 - base))] + [0.0] * feature_count
    for _ in range(25):
        hess = [[floor] * size for _ in range(size)]
        grads = [0.0] * size
        for vector, label in zip(features, labels):
            point = [1.0, *vector]
            score = _sigmoid(
                coefficients[0] + sum(c * x for c, x in zip(coefficients[1:], vector))
            )
            weight = max(score * (1 - score), 1e-12)
            residual = score - label
            for row in range(size):
                point_row = point[row]
                grads[row] += residual * point_row
                pivot_row = hess[row]
                lead = weight * point_row
                for column in range(row, size):
                    pivot_row[column] += lead * point[column]
        n = len(samples)
        for row in range(size):
            grads[row] /= n
            if row:  # weights only; intercept carries no ridge penalty
                grads[row] += ridge * coefficients[row]
            for column in range(row, size):
                penalty = ridge if (row == column and column) else floor
                hess[row][column] = hess[column][row] = hess[row][column] / n + penalty
        if max(abs(value) for value in grads) < 1e-9:
            break
        step = _solve(hess, [-value for value in grads])
        current = objective(coefficients)
        factor, updated = 1.0, None
        for _ in range(5):
            trial = [c + factor * s for c, s in zip(coefficients, step)]
            if objective(trial) <= current + 1e-12:
                updated = trial
                break
            factor /= 2
        if updated is None:
            break
        coefficients = updated
    return {
        "weights": coefficients[1:],
        "intercept": coefficients[0],
        "means": means,
        "scales": scales,
        "training_up_frequency": base,
        "feature_names": list(FEATURES),
    }


def predict(model, vector):
    scaled = [
        max(-10, min(10, (value - mean) / scale))
        for value, mean, scale in zip(vector, model["means"], model["scales"])
    ]
    return _sigmoid(model["intercept"] + sum(w * x for w, x in zip(model["weights"], scaled)))


def train_instrument(rows, symbol, years, *, source):
    if years not in HISTORY_YEARS or not re.fullmatch(r"[A-Z][A-Z0-9./-]{0,15}", symbol):
        raise ValueError("Choose an instrument and a 5, 10, 15 or 20-year daily history window")
    if not isinstance(rows, list) or not 500 <= len(rows) <= MAX_HISTORY_BARS:
        raise ValueError("Provide 500–10000 daily OHLCV observations")
    if any(
        not isinstance(row, dict)
        or set(row) != {"timestamp", "open", "high", "low", "close", "volume"}
        for row in rows
    ):
        raise ValueError(
            "Training rows must contain only timestamp, open, high, low, close and volume"
        )
    bars = validate_bars(rows)
    if any(
        not isinstance(b.open, (int, float)) or not isinstance(b.high, (int, float))
        or not isinstance(b.low, (int, float))
        for b in bars
    ):
        raise ValueError("Rich features need numeric OHLC history")
    days = [b.timestamp.date() for b in bars]
    if len(set(days)) != len(days) or days[-1] >= datetime.now(timezone.utc).date():
        raise ValueError(
            "Use one completed candle per date; current/future daily candles are excluded"
        )
    cutoff = days[-1] - timedelta(days=round(years * 365.25))
    selected = [row for row, day in zip(rows, days) if day >= cutoff]
    bars = validate_bars(selected)
    coverage = (bars[-1].timestamp - bars[0].timestamp).days / 365.25
    if coverage < years - 0.20 or len(bars) < years * 170:
        raise ValueError(
            f"The provider supplied only {coverage:.2f} years / {len(bars)} daily bars; the requested {years}-year window is incomplete"
        )
    if any((after.timestamp - before.timestamp).days > 7 for before, after in zip(bars, bars[1:])):
        raise ValueError(
            "Daily history has a gap longer than seven calendar days; repair the source before training"
        )
    samples = [
        (
            bars[index + 1].timestamp.date(),
            feature_vector(bars, index),
            int(bars[index + 1].close > bars[index + 1].open),
            index + 1,
        )
        for index in range(20, len(bars) - 1)
    ]
    cut1, cut2 = int(len(samples) * 0.6), int(len(samples) * 0.8)
    train, validation, test = samples[:cut1], samples[cut1:cut2], samples[cut2:]
    model = fit(train)
    digest = hashlib.sha256(
        json.dumps(selected, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    trials = []
    threshold: float | None
    for threshold in THRESHOLDS:
        plain = replay(bars, validation, model, threshold, scorer=predict)
        cost2 = replay(
            bars, validation, model, threshold, scorer=predict, cost_multiple=2
        )
        trials.append(
            {
                "threshold": threshold,
                "net_return": plain["net_return"],
                "closed_trades": plain["closed_trades"],
                "expectancy_usd": plain["expectancy_usd"],
                "max_drawdown": plain["max_drawdown"],
                "doubled_cost_net_return": cost2["net_return"],
            }
        )
    eligible = [
        t for t in trials
        if t["closed_trades"] >= 5
        and t["net_return"] > 0
        and t["expectancy_usd"] > 0
        and t["doubled_cost_net_return"] > 0
        and t["max_drawdown"] <= 0.03
    ]
    threshold = (
        max(eligible, key=lambda t: (t["doubled_cost_net_return"], t["threshold"]))["threshold"]
        if eligible
        else None
    )
    artifact = {
        "version": MODEL_VERSION,
        "symbol": symbol,
        "features": list(FEATURES),
        "model": model,
        "threshold": threshold,
        "policy": dict(POLICY),
        "training_end": train[-1][0].isoformat(),
        "training_fingerprint": hashlib.sha256(
            json.dumps([(str(s[0]), s[1], s[2]) for s in train], separators=(",", ":")).encode()
        ).hexdigest(),
    }
    artifact_hash = hashlib.sha256(
        json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    def period(sample):
        return {
            "start": sample[0][0].isoformat(),
            "end": sample[-1][0].isoformat(),
            "examples": len(sample),
        }

    initial_price = bars[test[0][3]].open * 1.0005
    passive_qty = math.floor(1000 / (initial_price * 1.001))
    passive_return = (
        10000
        - passive_qty * initial_price * 1.001
        + passive_qty * bars[test[-1][3]].close * 0.9995 * 0.999
    ) / 10000 - 1
    return {
        "id": hashlib.sha256((digest + artifact_hash).encode()).hexdigest(),        "symbol": symbol,
        "requested_years": years,
        "coverage": {
            "start": bars[0].timestamp.date().isoformat(),
            "end": bars[-1].timestamp.date().isoformat(),
            "years": coverage,
            "bars": len(bars),
        },
        "training": period(train),
        "validation": dict(period(validation), trials=trials),
        "test": dict(
            period(test),
            **replay(bars, test, model, threshold, scorer=predict),
            buy_and_hold_10pct_net_return=passive_return,
            cash_baseline_return=0.0,
        ),
        "artifact": artifact,
        "artifact_sha256": artifact_hash,
        "data_sha256": digest,
        "source": source,
        "status": (
            "experimental_paper_policy"
            if threshold is not None
            else "no_validation_edge_wait_in_cash"
        ),
        "target_70_percent_proven": False,
        "live_automation_available": False,
        "limitations": [
            "Weights/scaling use the first 60%; thresholds use validation only with a doubled-cost gate; the final 20% never selects settings.",
            "Fixed whole-unit long-only policy: at most 10% / 1000 USD, 2% stop, 4% take profit, five-session maximum; adverse same-bar stops take priority. Entries are skipped when the 1000 USD cap cannot afford one whole unit at the prevailing price, so very high-priced instruments can report zero trades under this policy.",
            "Historical proxy executes at the next daily open with 10 bps fee and 5 bps slippage per side; doubled-cost gates apply to threshold selection only.",
            "Rich daily features cannot see intraday microstructure, short interest, intraday news or venue microstructure; vendor aggregates limit them.",
            "Direction scores are not calibrated win probabilities. An observed backtest is exploratory, not proof of future profitability or 70% wins.",
            "Provider rights apply; Yahoo/vendor revisions and adjustments can change every statistic. Wilson trade intervals are descriptive and do not correct serial dependence.",
        ],
    }
