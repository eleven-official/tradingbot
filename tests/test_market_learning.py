"""Historical training causality, data boundaries and account-free import contracts."""

from copy import deepcopy
from datetime import date, timedelta
import io
import math
from unittest.mock import patch
from urllib.request import Request

from fastapi.testclient import TestClient
import pytest

from core.copilot import LokiCopilot
from core.fusion import history
from core.fusion.learning import examples, predict, train_research, validate_observations
from scripts.train_market_research import write_new
from loki.api.server import app


def history_rows():
    start = date(2022, 1, 1)
    return [
        {
            "timestamp": (start + timedelta(days=i)).isoformat(),
            "return": 0.02 * math.sin(i / 5) + 0.003 * math.cos(i / 37),
        }
        for i in range((date(2026, 4, 1) - start).days)
    ]


def test_future_targets_cannot_fit_weights_or_normalizer():
    original = history_rows()
    changed = deepcopy(original)
    for row in changed:
        if row["timestamp"] >= "2024-01-01":
            row["return"] = -row["return"] * 2
    before, after = train_research(original), train_research(changed)
    assert before["artifact"] == after["artifact"]
    assert before["artifact_sha256"] == after["artifact_sha256"]
    assert before["data_fingerprint"] != after["data_fingerprint"]
    assert before["test"] != after["test"]
    assert before["training"]["end"] < before["validation"]["start"]
    assert before["validation"]["end"] < before["test"]["start"]
    assert before["test"]["start"] == "2026-01-01"


def test_feature_window_has_two_day_lag_and_gaps_reset_it():
    rows = validate_observations(history_rows())
    data = examples(rows)
    label_date, vector, label = data[0]
    assert label_date == rows[21][0]
    assert vector[0] == rows[19][1]
    assert label == int(rows[21][1] > 0)
    rows.pop(25)
    data = examples(rows)
    gap_day = date(2022, 1, 26)
    assert not [day for day, _, _ in data if gap_day <= day <= gap_day + timedelta(days=21)]


def test_scores_are_bounded_and_metrics_never_claim_trade_wins():
    report = train_research(history_rows())
    assert 0 < predict(report["artifact"], [1e20] * 5) < 1
    assert report["trading_win_rate"] is None
    assert report["target_70_percent_proven"] is False
    assert report["live_trading_enabled"] is False
    assert report["artifact"]["specification"]["epochs"] == 60
    assert report["test"]["brier_score"] >= 0
    assert report["source"]["name"].endswith("unverified")


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), -1, 11])
def test_invalid_returns_fail(value):
    rows = history_rows()
    rows[10]["return"] = value
    with pytest.raises(ValueError):
        validate_observations(rows)


def test_duplicate_dates_insufficient_splits_and_missing_columns_fail():
    rows = history_rows()
    rows[3]["timestamp"] = rows[2]["timestamp"]
    with pytest.raises(ValueError, match="unique"):
        train_research(rows)
    with pytest.raises(ValueError, match="2023"):
        train_research(history_rows()[:300])
    with pytest.raises(ValueError, match="CMKT"):
        history.parse_factor_csv("date,price\n2022-01-01,100\n")


def test_public_downloader_uses_fixed_host_cache_license_and_fingerprint(monkeypatch):
    text = "date,CMKT\n" + "\n".join(
        f"{row['timestamp']},{row['return']}" for row in history_rows()
    )
    response = io.BytesIO(text.encode())
    response.status = 200
    opener = type("Opener", (), {"open": lambda *_args, **_kwargs: response})()
    monkeypatch.setattr(history, "_cache", None)
    monkeypatch.setattr(history, "_retry_after", 0)
    with patch.object(history, "build_opener", return_value=opener) as build:
        dataset = history.public_history()
        assert history.public_history() is dataset
    build.assert_called_once()
    assert dataset["source"]["license"] == "CC BY 4.0"
    assert dataset["source"]["requires_api_key"] is False
    assert dataset["source"]["execution_prices"] is False
    assert len(dataset["source"]["sha256"]) == 64
    assert "Stoeckl" in dataset["source"]["attribution"]


def test_bad_or_oversized_download_backs_off_and_never_uses_mock_prices(monkeypatch):
    response = io.BytesIO(b"x" * (history.MAX_BYTES + 1))
    response.status = 200
    opener = type("Opener", (), {"open": lambda *_args, **_kwargs: response})()
    monkeypatch.setattr(history, "_cache", None)
    monkeypatch.setattr(history, "_retry_after", 0)
    with patch.object(history, "build_opener", return_value=opener) as build:
        with pytest.raises(ConnectionError, match="no substitute"):
            history.public_history()
        with pytest.raises(ConnectionError, match="one minute"):
            history.public_history()
    build.assert_called_once()
    assert history._cache is None


def test_download_rejects_redirect_to_other_hosts_or_insecure_scheme():
    redirects = history._PublisherRedirects()
    for url in (
        "http://huggingface.co/file",
        "https://example.com/file",
        "https://user@huggingface.co/file",
    ):
        with pytest.raises(ValueError, match="allowed"):
            redirects.redirect_request(Request(history.SOURCE_URL), None, 302, "", {}, url)


def test_api_and_conversation_explain_actual_training_without_credentials(monkeypatch):
    monkeypatch.setattr(
        history,
        "public_history",
        lambda: {"observations": history_rows(), "source": {"name": "Synthetic unit fixture"}},
    )
    with TestClient(app) as client:
        response = client.post("/api/fusion/learn-history")
        assert response.status_code == 200, response.text
        report = response.json()
    answer = LokiCopilot().respond("Explain my market model training", {"market_learning": report})
    assert "learning" in answer.topics
    assert "Direction accuracy is not a completed-trade win rate" in answer.text
    assert "2023-12-31" in answer.text
    assert "cannot place orders" in answer.text


def test_public_failure_is_503_without_substituting_a_successful_training_report(monkeypatch):
    def unavailable():
        raise ConnectionError("source unavailable")

    monkeypatch.setattr(history, "public_history", unavailable)
    with TestClient(app) as client:
        response = client.post("/api/fusion/learn-history")
    assert response.status_code == 503
    assert "artifact" not in response.json()


def test_experiment_files_cannot_overwrite_prior_evidence(tmp_path):
    path = tmp_path / "experiment.json"
    write_new(path, {"original": True})
    with pytest.raises(FileExistsError):
        write_new(path, {"original": False})
    assert path.read_text().strip() == '{\n  "original": true\n}'


def test_large_input_is_bounded_before_expensive_training():
    row = {"timestamp": "2022-01-01", "return": 0.01}
    with pytest.raises(ValueError, match="250000"):
        validate_observations([row] * 250001)
