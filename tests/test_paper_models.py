"""Labelled synthetic history verifies chronology and policy arithmetic, not edge."""

from copy import deepcopy
from datetime import date, timedelta
import math

import pytest
from core.fusion import learning
from core.fusion import paper_models as models
from core.strategy_lab import validate_bars

def historical_fixture(years=11):
    rows = []
    previous = 100.0
    start = date(2014, 1, 1)
    for i in range(round(years * 365.25)):
        day = start + timedelta(days=i)
        if day.weekday() > 4:
            continue
        opening = previous * (1 + 0.001 * math.sin(i / 19))
        close = opening * (1 + 0.008 * math.sin(i / 11) + 0.001)
        rows.append(
            {
                "timestamp": day.isoformat(),
                "open": opening,
                "high": max(opening, close) * 1.003,
                "low": min(opening, close) * 0.997,
                "close": close,
                "volume": 100000,
            }
        )
        previous = close
    return rows


@pytest.fixture(scope="module")
def trained():
    rows = historical_fixture()
    return rows, models.train_instrument(
        rows, "SPY", 10, source={"name": "SYNTHETIC UNIT TEST FIXTURE"}
    )


def test_ten_year_training_keeps_date_windows_and_target_evidence_separate(trained):
    rows, report = trained
    assert 9.8 <= report["coverage"]["years"] <= 10.01
    assert report["coverage"]["bars"] > 2400
    assert report["training"]["end"] < report["validation"]["start"]
    assert report["validation"]["end"] < report["test"]["start"]
    assert len(report["validation"]["trials"]) == 3
    assert report["target_70_percent_proven"] is False
    assert report["live_automation_available"] is False
    assert report["artifact"]["policy"]["fee_bps"] > 0


def test_changing_only_test_prices_cannot_change_model_scaling_or_selected_threshold(trained):
    rows, original = trained
    changed = deepcopy(rows)
    for row in changed:
        if row["timestamp"] >= original["test"]["start"]:
            for key in ("open", "high", "low", "close"):
                row[key] *= 1.5
    altered = models.train_instrument(
        changed, "SPY", 10, source={"name": "SYNTHETIC TEST PERTURBATION"}
    )
    assert altered["artifact"] == original["artifact"]
    assert altered["artifact_sha256"] == original["artifact_sha256"]
    assert altered["data_sha256"] != original["data_sha256"]


def test_missing_history_is_not_padded_or_claimed_as_five_years():
    with pytest.raises(ValueError, match="incomplete"):
        models.train_instrument(historical_fixture(3), "SPY", 5, source={})


def test_daily_features_never_read_later_candles():
    bars = historical_fixture()
    baseline = models.feature_vector(validate_bars(bars), 100)
    for row in bars[101:]:
        for field in ("open", "high", "low", "close"):
            row[field] *= 3
    assert models.feature_vector(validate_bars(bars), 100) == baseline


def test_cash_policy_has_no_fabricated_wins_and_source_models_are_account_scoped(
    trained, monkeypatch, tmp_path
):
    _, report = trained
    monkeypatch.setenv("LOKI_PAPER_AI_DB", str(tmp_path / "research.sqlite3"))
    models.save_model("account-a", report)
    with pytest.raises(ValueError):
        models.load_model("account-b", report["id"])
    models.save_model("account-b", report)
    assert models.load_model("account-a", report["id"]) == models.load_model(
        "account-b", report["id"]
    )
    bars = validate_bars(historical_fixture())
    sample = [(bars[22].timestamp.date(), models.feature_vector(bars, 21), 1, 22)]
    cash = models.replay(bars, sample, report["artifact"]["model"], None)
    assert cash["closed_trades"] == 0 and cash["win_rate"] is None and cash["net_return"] == 0


def test_stop_first_and_gap_exits_include_costs_without_same_bar_reentry():
    rows = [
        {
            "timestamp": f"2020-01-0{i+1}",
            "open": 100.0,
            "high": 110.0,
            "low": 90.0,
            "close": 100.0,
            "volume": 1000.0,
        }
        for i in range(3)
    ]
    bars = validate_bars(rows)
    fixed = {"intercept": 10.0, "weights": [0.0] * 5, "means": [0.0] * 5, "scales": [1.0] * 5}
    result = models.replay(
        bars, [(b.timestamp.date(), [0.0] * 5, 1, i) for i, b in enumerate(bars)], fixed, 0.6
    )
    assert result["closed_trades"] == 3
    assert all(t["reason"] == "stop_first" and t["pnl"] < 0 for t in result["trades"])
    assert result["net_return"] < 0


def test_duplicate_dates_and_incomplete_daily_bars_are_rejected():
    rows = historical_fixture()
    rows[-1]["timestamp"] = date.today().isoformat()
    with pytest.raises(ValueError, match="completed"):
        models.train_instrument(rows, "SPY", 10, source={})


def _gradient_norm(model, train):
    gradients = [0.0] * (len(models.FEATURES) + 1)
    total = len(train)
    for _, vector, label in train:
        scaled = [
            max(-10, min(10, (value - mean) / scale))
            for value, mean, scale in zip(vector, model["means"], model["scales"])
        ]
        score = learning._sigmoid(model["intercept"] + sum(w * x for w, x in zip(model["weights"], scaled)))
        gradients[0] += score - label
        for index, value in enumerate(scaled):
            gradients[index + 1] += (score - label) * value
    return max(
        abs(value / total + (learning.SPEC["l2"] * model["weights"][index - 1] if index else 0.0))
        for index, value in enumerate(gradients)
    )


def test_newton_fit_reaches_a_converged_ridge_solution(trained):
    rows, report = trained
    # Reproduce train_instrument's own windowing: year cutoff, warmup, positional split.
    bars_all = validate_bars(rows)
    days = [bar.timestamp.date() for bar in bars_all]
    requested = report["requested_years"]
    cutoff = days[-1] - timedelta(days=round(requested * 365.25))
    window = validate_bars([row for row, day in zip(rows, days) if day >= cutoff])
    samples = [
        (
            window[index + 1].timestamp.date(),
            models.feature_vector(window, index),
            int(window[index + 1].close > window[index + 1].open),
        )
        for index in range(20, len(window) - 1)
    ]
    train = samples[: int(len(samples) * 0.6)]
    assert len(train) == report["training"]["examples"]
    model = report["artifact"]["model"]
    assert _gradient_norm(model, train) < 1e-6
    assert all(math.isfinite(weight) for weight in model["weights"])


def test_fitting_is_deterministic_and_bounded_on_separable_data():
    from core.fusion import learning

    rows = [
        {"timestamp": (date(2018, 1, 1) + timedelta(days=i)).isoformat(),
         "return": 0.01 * math.sin(i / 9)}
        for i in range(1500)
    ]
    sample = [
        row for row in learning.examples(learning.validate_observations(rows))
        if row[0].isoformat() < "2018-06"
    ]
    assert learning.fit(sample) == learning.fit(sample)
    separable = [
        (date(2020, 1, 1) + timedelta(days=index), (0.9, 0.9, 0.9, 0.01, 1.0), 1)
        for index in range(200)
    ]
    model = learning.fit(separable)
    assert all(math.isfinite(w) for w in model["weights"])
    assert all(weight <= 25 for weight in model["weights"])
    assert learning.SPEC["solver"] == "ridge_newton"


def test_instrument_reports_use_the_current_model_version(trained):
    _, report = trained
    assert report["artifact"]["version"] == "loki_instrument_daily_logistic_v2"
    assert report["artifact"]["model"]["feature_names"] == list(models.FEATURES)
