"""Instrument-specific five/ten-year research models and immutable local artifacts.

Fit weights/scaling on the first 60%; select among three thresholds on the next
20%; report the final 20% without using it to select a model. No live authority.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import statistics

from core.strategy_lab import validate_bars, _win_interval
from core.fusion.learning import fit, predict, FEATURES

MODEL_VERSION = "loki_instrument_daily_logistic_v1"
POLICY = {
    "allocation": 0.10,
    "max_notional": 1000.0,
    "stop_pct": 0.02,
    "take_profit_pct": 0.04,
    "max_holding_sessions": 5,
    "fee_bps": 10.0,
    "slippage_bps": 5.0,
}


@contextmanager
def database():
    path = Path(
        os.environ.get(
            "LOKI_PAPER_AI_DB",
            str(Path(__file__).resolve().parents[2] / "state/paper_ai/research.sqlite3"),
        )
    ).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA synchronous=FULL")
        db.execute(
            "CREATE TABLE IF NOT EXISTS models(id TEXT NOT NULL,owner TEXT NOT NULL,report TEXT NOT NULL,PRIMARY KEY(owner,id))"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS datasets(id TEXT NOT NULL,owner TEXT NOT NULL,rows TEXT NOT NULL,PRIMARY KEY(owner,id))"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS agents(scope TEXT PRIMARY KEY,owner TEXT NOT NULL,state TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS paper_actions(id TEXT PRIMARY KEY,scope TEXT NOT NULL,created REAL NOT NULL,state TEXT NOT NULL,body TEXT NOT NULL,response TEXT)"
        )
        yield db
    except sqlite3.Error as exc:
        raise ConnectionError(
            "Paper research journal is unavailable; no automatic order retry was made"
        ) from exc
    finally:
        db.close()


def feature_vector(bars, index=None):
    index = len(bars) - 1 if index is None else index
    if index < 20:
        raise ValueError("A prediction needs 21 completed daily bars")
    returns = [bars[i].close / bars[i - 1].close - 1 for i in range(index - 19, index + 1)]
    return [
        returns[-1],
        statistics.mean(returns[-5:]),
        statistics.mean(returns),
        statistics.pstdev(returns),
        sum(r > 0 for r in returns) / 20,
    ]


def replay(bars, samples, model, threshold):
    cash, qty, entry, age, peak, drawdown = 10000.0, 0, 0.0, 0, 10000.0, 0.0
    trades, curve = [], []
    fee, slip = POLICY["fee_bps"] / 10000, POLICY["slippage_bps"] / 10000

    def exit_at(price, reason, day):
        nonlocal cash, qty
        proceeds = qty * price * (1 - slip) * (1 - fee)
        pnl = proceeds - qty * entry * (1 + fee)
        cash += proceeds
        trades.append({"timestamp": day, "pnl": pnl, "reason": reason})
        qty = 0

    for sample in samples:
        bar = bars[sample[3]]
        score = predict(model, sample[1])
        want_long = threshold is not None and score >= threshold
        day = bar.timestamp.date().isoformat()
        exited = False
        if qty:
            if bar.open <= entry * (1 - POLICY["stop_pct"]):
                exit_at(bar.open, "stop_gap", day)
                exited = True
            elif not want_long or age >= POLICY["max_holding_sessions"]:
                exit_at(bar.open, "signal_or_time", day)
                exited = True
        if not qty and want_long and not exited:
            price = bar.open * (1 + slip)
            qty = math.floor(min(cash * 0.10, 1000.0) / (price * (1 + fee)))
            if qty:
                cash -= qty * price * (1 + fee)
                entry, age = price, 0
        if qty:
            stop, take = entry * (1 - POLICY["stop_pct"]), entry * (1 + POLICY["take_profit_pct"])
            if bar.low <= stop:
                exit_at(min(bar.open, stop), "stop_first", day)
            elif bar.high >= take:
                exit_at(take, "take_profit", day)
            age += 1
        equity = cash + qty * bar.close
        peak, drawdown = max(peak, equity), max(drawdown, 1 - equity / max(peak, equity))
        curve.append({"timestamp": day, "equity": equity})
    if qty and samples:
        last = bars[samples[-1][3]]
        exit_at(last.close, "evaluation_end", last.timestamp.date().isoformat())
        curve[-1]["equity"] = cash
        drawdown = max(drawdown, 1 - cash / peak)
    wins = sum(t["pnl"] > 0 for t in trades)
    return {
        "net_return": cash / 10000 - 1,
        "closed_trades": len(trades),
        "win_rate": wins / len(trades) if trades else None,
        "win_rate_95pct_interval": _win_interval(wins, len(trades)),
        "expectancy_usd": statistics.mean(t["pnl"] for t in trades) if trades else None,
        "max_drawdown": drawdown,
        "trades": trades,
        "equity_curve": curve,
    }


def train_instrument(rows, symbol, years, *, source):
    if years not in {5, 10} or not re.fullmatch(r"[A-Z][A-Z0-9./-]{0,15}", symbol):
        raise ValueError("Choose an instrument and a five- or ten-year daily history window")
    if not isinstance(rows, list) or not 500 <= len(rows) <= 5000:
        raise ValueError("Provide 500–5000 daily OHLCV observations")
    if any(
        not isinstance(row, dict)
        or set(row) != {"timestamp", "open", "high", "low", "close", "volume"}
        for row in rows
    ):
        raise ValueError(
            "Training rows must contain only timestamp, open, high, low, close and volume"
        )
    bars = validate_bars(rows)
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
    samples = []
    for index in range(20, len(bars) - 1):
        target = bars[index + 1]
        samples.append(
            (
                target.timestamp.date(),
                feature_vector(bars, index),
                int(target.close > target.open),
                index + 1,
            )
        )
    cut1, cut2 = int(len(samples) * 0.6), int(len(samples) * 0.8)
    train, validation, test = samples[:cut1], samples[cut1:cut2], samples[cut2:]
    model = fit(train)
    trials = []
    for threshold in (0.55, 0.60, 0.65):
        score = replay(bars, validation, model, threshold)
        trials.append(
            {
                "threshold": threshold,
                "net_return": score["net_return"],
                "closed_trades": score["closed_trades"],
                "expectancy_usd": score["expectancy_usd"],
            }
        )
    eligible = [
        t
        for t in trials
        if t["closed_trades"] >= 5 and t["net_return"] > 0 and t["expectancy_usd"] > 0
    ]
    threshold = (
        max(eligible, key=lambda t: (t["net_return"], t["threshold"]))["threshold"]
        if eligible
        else None
    )
    digest = hashlib.sha256(
        json.dumps(selected, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
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
        "id": hashlib.sha256((digest + artifact_hash).encode()).hexdigest(),
        "symbol": symbol,
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
            **replay(bars, test, model, threshold),
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
            "Weights/scaling use the first 60% of dates; three entry thresholds use validation only; the final 20% never selects settings.",
            "Five/ten years describes the full data window, including withheld evaluation dates; not all dates fit model weights.",
            "Fixed whole-unit long-only policy: at most 10% / 1000 USD, 2% stop, 4% take profit, five-session maximum; adverse same-bar stops take priority.",
            "Historical proxy executes at the next daily open with 10 bps fee and 5 bps slippage per side. Actual paper quotes, fills, delays and server-monitor stops differ.",
            "Direction scores are not calibrated win probabilities. An observed backtest is exploratory, not proof of future profitability or 70% wins.",
            "Current symbol selection and split-adjusted vendor history are retrospective; survivorship, revisions, single-venue daily aggregates and missing dividends limit this proxy. Wilson trade intervals are descriptive and do not correct serial dependence.",
            "Provider entitlements and data-use agreements apply. Exact input snapshots, model reports and paper journals stay in private local storage; credentials remain in server memory. No vendor history is bundled into public source.",
        ],
    }


def save_model(owner, report, rows=None):
    with database() as db:
        if rows is not None:
            window = [
                row
                for row, bar in zip(rows, validate_bars(rows))
                if report["coverage"]["start"]
                <= bar.timestamp.date().isoformat()
                <= report["coverage"]["end"]
            ]
            encoded = json.dumps(window, sort_keys=True, separators=(",", ":"), allow_nan=False)
            if hashlib.sha256(encoded.encode()).hexdigest() != report["data_sha256"]:
                raise ValueError("Training snapshot does not match the frozen model input hash")
            db.execute(
                "INSERT OR IGNORE INTO datasets VALUES(?,?,?)",
                (report["data_sha256"], owner, encoded),
            )
        db.execute(
            "INSERT OR IGNORE INTO models VALUES(?,?,?)", (report["id"], owner, json.dumps(report))
        )
    return report


def load_model(owner, identifier):
    with database() as db:
        row = db.execute(
            "SELECT report FROM models WHERE id=? AND owner=?", (identifier, owner)
        ).fetchone()
    if not row:
        raise ValueError("Train a model for this broker session or imported instrument first")
    return json.loads(row[0])


def load_dataset(owner, identifier):
    report = load_model(owner, identifier)
    with database() as db:
        row = db.execute(
            "SELECT rows FROM datasets WHERE id=? AND owner=?", (report["data_sha256"], owner)
        ).fetchone()
    if row is None:
        raise ValueError("No exact input snapshot is stored for this model")
    return {
        "symbol": report["symbol"],
        "source": report["source"],
        "data_sha256": report["data_sha256"],
        "bars": json.loads(row[0]),
    }
