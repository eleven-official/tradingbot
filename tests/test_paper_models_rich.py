"""Rich daily-feature family: chronology, Newton convergence, gates and sizing."""

from copy import deepcopy
from datetime import date, timedelta
import math

import pytest
from core.fusion import learning
from core.fusion import paper_models as models
from core.fusion import paper_models_rich as rich
from core.fusion.paper_evidence import assess
from core.strategy_lab import validate_bars


def _fixture(years=11, *, scale=1.0, momentum=0.008, drift=0.001, base=100.0):
    rows = []
    previous = base
    start = date(2014, 1, 1)
    for i in range(round(years * 365.25)):
        day = start + timedelta(days=i)
        if day.weekday() > 4:
            continue
        opening = previous * (1 + 0.001 * math.sin(i / 19))
        close = opening * (1 + momentum * math.sin(i / 11) + drift)
        rows.append(
            {
                "timestamp": day.isoformat(),
                "open": opening * scale,
                "high": max(opening, close) * 1.003 * scale,
                "low": min(opening, close) * 0.997 * scale,
                "close": close * scale,
                "volume": 100000,
            }
        )
        previous = close
    return rows


@pytest.fixture(scope="module")
def trained():
    rows = _fixture()
    return rows, rich.train_instrument(rows, "SPY", 10, source={"name": "RICH UNIT FIXTURE"})


@pytest.fixture(scope="module")
def affordable():
    # 1x price scale leaves the whole-unit 1000 USD cap unable to buy a unit
    # in this fixture's later years; a quarter scale keeps the policy tradeable.
    rows = _fixture(scale=0.25)
    return rows, rich.train_instrument(rows, "QQQ", 10, source={"name": "RICH AFFORDABLE FIXTURE"})


@pytest.fixture(scope="module")
def flat():
    rows = _fixture(momentum=0.0, drift=0.0)
    return rows, rich.train_instrument(rows, "SPY", 10, source={"name": "RICH FLAT FIXTURE"})


def test_windows_trials_version_and_honest_flags(trained):
    _, report = trained
    assert 9.8 <= report["coverage"]["years"] <= 10.01
    assert report["coverage"]["bars"] > 2400
    assert report["training"]["end"] < report["validation"]["start"]
    assert report["validation"]["end"] < report["test"]["start"]
    assert len(report["validation"]["trials"]) == 3
    assert report["artifact"]["version"] == "loki_instrument_daily_rich_v3"
    assert report["artifact"]["model"]["feature_names"] == list(rich.FEATURES)
    assert report["target_70_percent_proven"] is False
    assert report["live_automation_available"] is False


def test_rich_features_never_read_later_candles():
    rows = _fixture()
    baseline = rich.feature_vector(validate_bars(rows), 100)
    for row in rows[101:]:
        for field in ("open", "high", "low", "close"):
            row[field] *= 3
    assert rich.feature_vector(validate_bars(rows), 100) == baseline


def test_cost_stress_uses_frozen_model_and_preserves_cash_policy(flat, affordable):
    _, cash = flat
    assert cash["cost_stress"]["closed_trades"] == 0
    assert cash["profitability_checks"]["positive_after_costs"] is False
    rows, report = affordable
    bars = validate_bars([row for row in rows if row["timestamp"] >= report["coverage"]["start"]])
    samples = [
        (
            bars[i + 1].timestamp.date(),
            rich.feature_vector(bars, i),
            int(bars[i + 1].close > bars[i + 1].open),
            i + 1,
        )
        for i in range(20, len(bars) - 1)
    ]
    test = samples[int(len(samples) * 0.8) :]
    expected = models.replay(
        bars,
        test,
        report["artifact"]["model"],
        report["artifact"]["threshold"],
        scorer=rich.predict,
        cost_multiple=2,
    )
    assert report["cost_stress"] == expected
    assert report["profitability_checks"]["forward_profitability_proven"] is False


def test_changing_only_test_prices_cannot_change_model_scaling_or_threshold(trained):
    rows, original = trained
    changed = deepcopy(rows)
    for row in changed:
        if row["timestamp"] >= original["test"]["start"]:
            for key in ("open", "high", "low", "close"):
                row[key] *= 1.5
    altered = rich.train_instrument(changed, "SPY", 10, source={"name": "PI"})
    assert altered["artifact"] == original["artifact"]
    assert altered["artifact_sha256"] == original["artifact_sha256"]
    assert altered["data_sha256"] != original["data_sha256"]


def test_missing_history_is_not_padded_or_claimed_as_complete():
    with pytest.raises(ValueError, match="incomplete"):
        rich.train_instrument(_fixture(3), "SPY", 5, source={})


def test_duplicate_dates_and_current_daily_candles_are_rejected():
    rows = _fixture()
    rows[-1]["timestamp"] = date.today().isoformat()
    with pytest.raises(ValueError, match="completed"):
        rich.train_instrument(rows, "SPY", 10, source={})


def _gradient_norm(model, train):
    gradients = [0.0] * (len(rich.FEATURES) + 1)
    total = len(train)
    for _, vector, label in train:
        scaled = [
            max(-10, min(10, (value - mean) / scale))
            for value, mean, scale in zip(vector, model["means"], model["scales"])
        ]
        score = learning._sigmoid(
            model["intercept"] + sum(w * x for w, x in zip(model["weights"], scaled))
        )
        gradients[0] += score - label
        for index, value in enumerate(scaled):
            gradients[index + 1] += (score - label) * value
    # the rich fit penalizes weights only, with its own ridge constant
    return max(
        (
            abs(value / total)
            if index == 0
            else abs(value / total + 0.01 * model["weights"][index - 1])
        )
        for index, value in enumerate(gradients)
    )


def test_newton_fit_reaches_a_converged_ridge_solution(trained):
    rows, report = trained
    bars_all = validate_bars(rows)
    days = [bar.timestamp.date() for bar in bars_all]
    cutoff = days[-1] - timedelta(days=round(report["requested_years"] * 365.25))
    window = validate_bars([row for row, day in zip(rows, days) if day >= cutoff])
    samples = [
        (
            window[index + 1].timestamp.date(),
            rich.feature_vector(window, index),
            int(window[index + 1].close > window[index + 1].open),
        )
        for index in range(20, len(window) - 1)
    ]
    train = samples[: int(len(samples) * 0.6)]
    assert len(train) == report["training"]["examples"]
    model = report["artifact"]["model"]
    assert _gradient_norm(model, train) < 1e-6
    assert all(math.isfinite(value) for value in model["weights"])
    assert all(math.isfinite(value) for value in model["means"])


def test_training_is_deterministic(trained):
    rows, report = trained
    again = rich.train_instrument(rows, "SPY", 10, source={"name": "RICH UNIT FIXTURE"})
    assert again["artifact_sha256"] == report["artifact_sha256"]
    assert again["validation"]["trials"] == report["validation"]["trials"]


def test_doubled_cost_gate_orders_and_zero_trades_honestly(affordable):
    rows, report = affordable
    trials = report["validation"]["trials"]
    for trial in trials:  # doubling per-side costs can never raise net return
        assert trial["doubled_cost_net_return"] <= trial["net_return"]
    if report["artifact"]["threshold"] is not None:
        chosen = next(t for t in trials if t["threshold"] == report["artifact"]["threshold"])
        assert chosen["closed_trades"] >= 5
        assert chosen["net_return"] > 0 and chosen["expectancy_usd"] > 0
        assert chosen["doubled_cost_net_return"] > 0
        assert chosen["max_drawdown"] <= 0.03
        assert report["status"] == "experimental_paper_policy"
    else:
        assert report["status"] == "no_validation_edge_wait_in_cash"


def test_evidence_gate_matches_later_period_arithmetic(affordable):
    _, report = affordable
    result = assess(report)
    test = report["test"]
    later_ok = (
        test["closed_trades"] >= 3
        and test["net_return"] > 0
        and test["expectancy_usd"] > 0
        and test["max_drawdown"] <= 0.03
    )
    assert result["future_profitability_proven"] is False
    if later_ok and report["artifact"]["threshold"] is not None:
        assert result["status"] == "experimental_paper_candidate"
        assert result["entry_allowed"] is True and result["can_start"] is True
    elif report["artifact"]["threshold"] is None:
        assert result["status"] == "cash_only"
        assert result["entry_allowed"] is False and result["can_start"] is True
    else:
        assert result["status"] == "blocked"
        assert result["entry_allowed"] is False and result["can_start"] is False


def test_cash_outcome_when_scores_never_cross_thresholds(flat):
    _, report = flat
    assert report["artifact"]["threshold"] is None
    assert report["status"] == "no_validation_edge_wait_in_cash"
    assert report["test"]["closed_trades"] == 0 and report["test"]["net_return"] == 0
    result = assess(report)
    assert result["cash_only"] is True and result["entry_allowed"] is False
    assert result["can_start"] is True and result["reasons"] == []


def test_whole_unit_cap_skips_sub_unit_entries():
    rows = [
        {
            "timestamp": f"2020-01-0{i+1}",
            "open": 2000.0,
            "high": 2100.0,
            "low": 1990.0,
            "close": 2000.0,
            "volume": 1000.0,
        }
        for i in range(3)
    ]
    bars = validate_bars(rows)
    fixed = {
        "intercept": 10.0,
        "weights": [0.0] * len(rich.FEATURES),
        "means": [0.0] * len(rich.FEATURES),
        "scales": [1.0] * len(rich.FEATURES),
    }
    result = models.replay(
        bars,
        [(b.timestamp.date(), [0.1] * len(rich.FEATURES), 1, i) for i, b in enumerate(bars)],
        fixed,
        0.6,
        scorer=lambda *_: 0.99,
    )
    assert result["closed_trades"] == 0
    assert result["net_return"] == 0 and result["win_rate"] is None


def test_save_load_roundtrip_is_account_scoped(affordable, monkeypatch, tmp_path):
    rows, report = affordable
    monkeypatch.setenv("LOKI_PAPER_AI_DB", str(tmp_path / "research.sqlite3"))
    models.save_model("account-a", report, rows)
    with pytest.raises(ValueError):
        models.load_model("account-b", report["id"])
    models.save_model("account-b", report)
    assert models.load_model("account-a", report["id"]) == models.load_model(
        "account-b", report["id"]
    )
