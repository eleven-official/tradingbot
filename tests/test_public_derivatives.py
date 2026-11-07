"""Contract identity, delayed fills, and validation/holdout isolation."""

from copy import deepcopy
from datetime import date, timedelta
import json

import train_public_derivatives as research


def test_replay_costs_and_nonoverlap(monkeypatch):
    monkeypatch.setattr(research, "predict", lambda model, x: 0.9)
    rows = [
        dict(entry="2025-01-06", exit="2025-01-08", capital=100, x=[], gross=0, cost=3.3),
        dict(entry="2025-01-07", exit="2025-01-09", capital=100, x=[], gross=999, cost=3.3),
    ]
    result = research.replay(rows, {}, 0.6)
    assert result["trades"] == 1
    assert result["net_pnl_usd"] == -3.3
    assert result["closed_trade_max_drawdown"] > 0
    assert research.replay(rows, {}, 0.6, 2)["net_pnl_usd"] == -6.6


def quote(day, strike="100", delta="0.50", bid="1", ask="1.10"):
    return dict(
        date=day,
        expiration="2025-02-21",
        strike=strike,
        call_put="Call",
        bid=bid,
        ask=ask,
        delta=delta,
        vol=".2",
        gamma=".02",
    )


def test_options_delay_entry_and_preserve_contract():
    rows = [
        quote("2025-01-06"),
        quote("2025-01-07", ask="2"),
        quote("2025-01-08", bid="3", ask="3.10"),
    ]
    (example,) = research.option_examples(rows)
    assert example["entry"] == "2025-01-07"
    assert example["exit"] == "2025-01-08"
    assert example["gross"] == 100
    assert example["cost"] == 3.30
    # A better signal-date contract with missing later quotes cannot be replaced
    # retrospectively by a contract known to have subsequent observations.
    rows[0]["delta"] = ".60"
    rows.append(quote("2025-01-06", strike="101"))
    (remaining,) = research.option_examples(rows)
    assert remaining["selected_for_replay"] is False
    assert research.replay([remaining], {}, 0.6)["trades"] == 0


def test_futures_no_roll_return_or_future_volume_selection():
    days = [date(2025, 1, 1) + timedelta(days=i) for i in range(32)]
    days = [d for d in days if d.weekday() < 5]
    rows = []
    for contract, price, volume in (("2025-02-19", 20, 1000), ("2025-03-19", 40, 200)):
        rows += [
            dict(date=str(d), contract=contract, open=price, close=price + 0.1, volume=volume)
            for d in days
        ]
    examples = research.futures_examples(rows)
    assert examples
    assert all(r["contract"] == "2025-02-19" for r in examples)
    assert all(abs(r["gross"] - 100) < 1e-8 for r in examples)


def test_holdout_changes_do_not_change_model_or_threshold(tmp_path, monkeypatch):
    monkeypatch.setattr(research, "ROOT", tmp_path)
    rows = []
    for year in (2023, 2024, 2025):
        for i in range(60):
            day = date(year, 2, 1) + timedelta(days=i)
            rows.append(
                dict(
                    signal=str(day),
                    entry=str(day + timedelta(days=1)),
                    exit=str(day + timedelta(days=2)),
                    x=[i % 3, 0.1, 0.2, 0.3, 0.4],
                    gross=10 if i % 3 else -5,
                    cost=1,
                    capital=100,
                )
            )
    research.train(rows, "fixture", list("abcde"))
    original = json.loads((tmp_path / "fixture-report.json").read_text())
    changed = deepcopy(rows)
    for row in changed:
        if row["signal"].startswith("2025"):
            row["gross"] = -999
    research.train(changed, "fixture", list("abcde"))
    altered = json.loads((tmp_path / "fixture-report.json").read_text())
    assert altered["model"] == original["model"]
    assert altered["threshold"] == original["threshold"]
    assert altered["validation"] == original["validation"]
