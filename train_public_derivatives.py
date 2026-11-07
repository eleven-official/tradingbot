"""Download public SPY options / individual VX contracts and fit research models.

Run: python train_public_derivatives.py
Cached raw responses and model reports remain in ignored state/public_derivatives.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import date, timedelta
import hashlib
import io
import json
import math
from pathlib import Path
import statistics

import requests

from core.fusion.learning import fit, predict, metrics

ROOT = Path("state/public_derivatives")
DOLT = "https://www.dolthub.com/api/v1alpha1/post-no-preference/options/master"


def download(name, url, params=None):
    path = ROOT / name
    if path.exists():
        cached = path.read_bytes()
        if params is None or json.loads(cached).get("query_execution_status") == "Success":
            return cached
    for attempt in range(3):
        try:
            with requests.get(url, params=params, timeout=120, stream=True) as response:
                if response.status_code == 404 or (params is None and response.status_code == 403):
                    (ROOT / (name + ".unavailable.json")).write_text(
                        json.dumps(
                            {
                                "url": url,
                                "status": response.status_code,
                                "checked": str(date.today()),
                            }
                        ),
                        encoding="utf-8",
                    )
                    return None
                response.raise_for_status()
                chunks, size = [], 0
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > 20_000_000:
                        raise ValueError("Response exceeds download ceiling")
                    chunks.append(chunk)
                content = b"".join(chunks)
            if (
                params is not None
                and json.loads(content).get("query_execution_status") != "Success"
            ):
                raise ValueError("Public SQL query failed")
            path.write_bytes(content)
            return content
        except (requests.RequestException, ValueError):
            if attempt == 2:
                raise
    raise RuntimeError("Download attempts exhausted")


def options_month(start):
    query = (
        "SELECT * FROM option_chain WHERE act_symbol = 'SPY' "
        f"AND date = '{start}' "
        "ORDER BY date, expiration, strike, call_put LIMIT 20000"
    )
    raw = download(f"options-day-{start}.json", DOLT, {"q": query})
    payload = json.loads(raw)
    if payload.get("query_execution_status") != "Success":
        raise ValueError(payload)
    rows = payload["rows"]
    if len(rows) >= 20000:
        raise ValueError("Options query truncated; narrow the date interval")
    return rows


def futures_month(period):
    year, month = period
    # Standard monthly VX expiration: 30 days before next month's third Friday.
    following = date(year + (month == 12), month % 12 + 1, 1)
    friday = following + timedelta(days=(4 - following.weekday()) % 7 + 14)
    expiry = friday - timedelta(days=30)
    url = (
        "https://cdn.cboe.com/data/us/futures/market_statistics/"
        f"historical_data/VX/VX_{expiry}.csv"
    )
    raw = download(f"VX_{expiry}.csv", url)
    if raw is None:
        return []
    rows = []
    for item in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
        day = date.fromisoformat(item["Trade Date"])
        values = [float(item[key]) for key in ("Open", "High", "Low", "Close")]
        opening, high, low, close = values
        volume = float(item["Total Volume"])
        if (
            all(0 < x < 1000 for x in values)
            and low <= min(opening, close)
            and high >= max(opening, close)
            and volume >= 100
            and day < expiry
            and day < date(2026, 1, 1)
        ):
            rows.append(
                {
                    "date": day.isoformat(),
                    "contract": str(expiry),
                    "open": opening,
                    "close": close,
                    "volume": volume,
                }
            )
    return rows


def option_examples(rows):
    chains = {}
    selected = {}
    for row in rows:
        try:
            bid, ask = float(row["bid"]), float(row["ask"])
            delta, vol, gamma = (float(row[k]) for k in ("delta", "vol", "gamma"))
            day, expiry = date.fromisoformat(row["date"]), date.fromisoformat(row["expiration"])
            dte = (expiry - day).days
            if not (
                0 < bid <= ask < 1000
                and 7 <= dte <= 60
                and -1 <= delta <= 1
                and 0 < vol < 5
                and 0 <= gamma < 5
            ):
                continue
        except (TypeError, ValueError):
            continue
        key = (row["expiration"], row["strike"], row["call_put"])
        chains.setdefault(key, []).append(
            (day, bid, ask, [delta, vol, gamma, dte / 365, (ask - bid) / ask])
        )
        if key[2] == "Call":
            rank = (abs(delta - 0.5), key)
            if day not in selected or rank < selected[day]:
                selected[day] = rank
    candidates = []
    for key, chain in chains.items():
        chain.sort()
        # Signal at t; buy ask at t+1, sell bid at t+2. No same-quote fills.
        for signal, entry, exit_ in zip(chain, chain[1:], chain[2:]):
            if key[2] != "Call":
                continue
            if not (0 < (entry[0] - signal[0]).days <= 4 and 0 < (exit_[0] - entry[0]).days <= 4):
                continue
            if entry[0] >= date.fromisoformat(key[0]) or exit_[0] >= date.fromisoformat(key[0]):
                continue
            gross = (exit_[1] - entry[2]) * 100
            cost = 1.30 + 2.0  # $0.65 commission and $0.01 adverse price/side.
            record = {
                "signal": str(signal[0]),
                "entry": str(entry[0]),
                "exit": str(exit_[0]),
                "contract": list(key),
                "x": signal[3],
                "gross": gross,
                "cost": cost,
                "capital": entry[2] * 100 + cost / 2,
                "selected_for_replay": selected.get(signal[0], (None, None))[1] == key,
            }
            candidates.append(record)
    return sorted(candidates, key=lambda r: (r["signal"], r["contract"]))


def futures_examples(rows):
    contracts = {}
    selected = {}
    for row in rows:
        contracts.setdefault(row["contract"], []).append(row)
        day = date.fromisoformat(row["date"])
        if (date.fromisoformat(row["contract"]) - day).days >= 7:
            rank = (-row["volume"], row["contract"])
            if row["date"] not in selected or rank < selected[row["date"]]:
                selected[row["date"]] = rank
    candidates = {}
    for contract, chain in contracts.items():
        chain.sort(key=lambda r: r["date"])
        for i in range(20, len(chain) - 1):
            signal, entry = chain[i], chain[i + 1]
            if selected.get(signal["date"], (None, None))[1] != contract:
                continue
            day = date.fromisoformat(signal["date"])
            if not 0 < (date.fromisoformat(entry["date"]) - day).days <= 4:
                continue
            if (date.fromisoformat(contract) - day).days < 7:
                continue
            window = chain[i - 20 : i + 1]
            if (day - date.fromisoformat(window[0]["date"])).days > 40:
                continue
            returns = [b["close"] / a["close"] - 1 for a, b in zip(window, window[1:])]
            x = [
                returns[-1],
                statistics.mean(returns[-5:]),
                statistics.mean(returns),
                statistics.pstdev(returns),
                sum(r > 0 for r in returns) / 20,
            ]
            record = {
                "signal": str(day),
                "entry": entry["date"],
                "exit": entry["date"],
                "contract": contract,
                "x": x,
                "gross": (entry["close"] - entry["open"]) * 1000,
                "cost": 106.0,
                "capital": 10000.0,
            }
            # Most liquid eligible contract at signal close, never next-day volume.
            rank = (-signal["volume"], contract)
            if day not in candidates or rank < candidates[day][0]:
                candidates[day] = (rank, record)
    return [value[1] for _, value in sorted(candidates.items())]


def replay(rows, model, threshold, multiple=1):
    pnl = 0.0
    count = 0
    peak, drawdown = 50000.0, 0.0
    trades = []
    last_exit = ""
    for row in rows:
        if not row.get("selected_for_replay", True):
            continue
        if row["entry"] <= last_exit or row["capital"] > 50000 + pnl:
            continue
        if predict(model, row["x"]) >= threshold:
            net = row["gross"] - multiple * row["cost"]
            pnl += net
            count += 1
            last_exit = row["exit"]
            peak = max(peak, 50000 + pnl)
            drawdown = max(drawdown, 1 - (50000 + pnl) / peak)
            trades.append(
                {
                    "contract": row.get("contract"),
                    "entry": row["entry"],
                    "exit": row["exit"],
                    "net_pnl_usd": net,
                }
            )
    return {
        "trades": count,
        "net_pnl_usd": pnl,
        "return_on_50000": pnl / 50000,
        "closed_trade_max_drawdown": drawdown,
        "trade_log": trades,
    }


def train(rows, name, feature_names):
    if any(len(r["x"]) != 5 or not all(math.isfinite(x) for x in r["x"]) for r in rows):
        raise ValueError("Nonfinite or malformed feature vector")
    train_rows = [r for r in rows if r["exit"] < "2024-01-01"]
    validation = [r for r in rows if r["signal"] >= "2024-01-01" and r["exit"] < "2025-01-01"]
    test = [r for r in rows if r["signal"] >= "2025-01-01" and r["exit"] < "2026-01-01"]
    if min(len(train_rows), len(validation), len(test)) < 50:
        raise ValueError(
            f"Insufficient chronological coverage: {list(map(len,(train_rows,validation,test)))}"
        )
    model = fit([(r["exit"], r["x"], int(r["gross"] > r["cost"])) for r in train_rows])
    model["feature_names"] = feature_names
    trials = [
        {
            "threshold": t,
            **replay(validation, model, t),
            "double_cost": replay(validation, model, t, 2),
        }
        for t in (0.55, 0.60, 0.65)
    ]
    eligible = [
        r
        for r in trials
        if r["trades"] >= 5 and r["net_pnl_usd"] > 0 and r["double_cost"]["net_pnl_usd"] > 0
    ]
    threshold = max(eligible, key=lambda r: r["net_pnl_usd"])["threshold"] if eligible else 1.1
    replay_counts = {
        key: sum(r.get("selected_for_replay", True) for r in sample)
        for key, sample in zip(("train", "validation", "test"), (train_rows, validation, test))
    }
    report = {
        "instrument": name,
        "mode": "offline_research_only",
        "model": model,
        "threshold": threshold,
        "status": (
            "insufficient_replay_coverage"
            if replay_counts["validation"] < 5
            else (
                "no_validation_edge_wait_in_cash"
                if not eligible
                else "experimental_research_policy"
            )
        ),
        "replay_eligible_examples": replay_counts,
        "unique_signal_dates": {
            key: len({r["signal"] for r in sample})
            for key, sample in zip(("train", "validation", "test"), (train_rows, validation, test))
        },
        "sample_counts": dict(
            zip(("train", "validation", "test"), map(len, (train_rows, validation, test)))
        ),
        "range": [rows[0]["signal"], rows[-1]["exit"]],
        "validation": trials,
        "test": replay(test, model, threshold),
        "double_cost_test": replay(test, model, threshold, 2),
        "holdout_prediction_metrics": metrics(
            model,
            [(date.fromisoformat(r["exit"]), r["x"], int(r["gross"] > r["cost"])) for r in test],
        ),
        "examples_sha256": hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest(),
        "limitations": [
            "Research artifacts are not connected to live or browser-paper execution.",
            "Public quotes/bars do not establish executable liquidity or future profitability.",
            "Fixed 2024 validation and 2025 holdout; training uses earlier dates.",
            "Options sample availability can bias contract selection; no underlying-price or corporate-action validation.",
            "VX daily open/close proxy excludes intraday margin paths; $50,000 account, assumed $10,000 collateral per contract, $3 commission and 0.05-point slippage per side. Historical exchange margin is not available.",
            "Missing holiday-shifted VX expirations are omitted, never synthesized.",
        ],
    }
    (ROOT / f"{name}-examples.json").write_text(json.dumps(rows), encoding="utf-8")
    (ROOT / f"{name}-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "instrument": name,
                "sample_counts": report["sample_counts"],
                "range": report["range"],
                "threshold": threshold,
                "test": {k: v for k, v in report["test"].items() if k != "trade_log"},
                "double_cost_test": {
                    k: v for k, v in report["double_cost_test"].items() if k != "trade_log"
                },
            },
            indent=2,
        )
    )


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    calendar_path = ROOT / "SPY-sessions.json"
    if not calendar_path.exists():
        import yfinance as yf

        frame = yf.download(
            "SPY", start="2023-01-01", end="2026-01-01", progress=False, auto_adjust=False
        )
        if len(frame) < 700:
            raise ValueError("Incomplete SPY trading-session calendar")
        calendar_path.write_text(json.dumps([str(day.date()) for day in frame.index]))
    sessions = set(json.loads(calendar_path.read_text()))
    days = [
        date(2023, 1, 1) + timedelta(days=i)
        for i in range((date(2026, 1, 1) - date(2023, 1, 1)).days)
    ]
    with ThreadPoolExecutor(max_workers=6) as pool:
        options = [
            r
            for batch in pool.map(options_month, [d for d in days if d.weekday() < 5])
            for r in batch
            if r["date"] in sessions
        ]
        futures = [
            r
            for batch in pool.map(
                futures_month,
                [(y, m) for y in range(2018, 2027) for m in range(1, 13) if (y, m) <= (2026, 1)],
            )
            for r in batch
        ]
    manifest = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(ROOT.iterdir())
        if p.suffix in (".csv", ".json")
        and (
            p.name.startswith("VX_")
            or p.name.startswith("options-day-")
            or p.name == "SPY-sessions.json"
        )
    }
    (ROOT / "manifest.json").write_text(
        json.dumps(
            {
                "sources": [
                    DOLT,
                    "https://cdn.cboe.com/data/us/futures/market_statistics/historical_data/VX/",
                ],
                "retrieved": str(date.today()),
                "unavailable": [
                    json.loads(p.read_text()) for p in sorted(ROOT.glob("*.unavailable.json"))
                ],
                "sha256": manifest,
            },
            indent=2,
        )
    )
    train(
        option_examples(options),
        "SPY-options",
        ["delta", "implied_volatility", "gamma", "years_to_expiry", "relative_spread"],
    )
    train(
        futures_examples(futures),
        "VX-futures",
        ["last_return", "mean_5", "mean_20", "volatility_20", "positive_fraction_20"],
    )


if __name__ == "__main__":
    main()
