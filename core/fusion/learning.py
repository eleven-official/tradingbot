"""Transparent supervised learning on past returns, separate from trading proof.

Fixed logistic model and fixed training schedule; no test-driven search. Supports
up to 250000 daily observations offline. All features and scaling are causal;
targets are dated by the return being predicted, so boundary labels cannot leak.
The conversational assistant is not an LLM trained by this module.
"""

from __future__ import annotations

from collections import deque
from datetime import date, timedelta
import hashlib
import json
import math
import statistics

MODEL_ID = "loki_market_direction_logistic_v1"
FEATURES = ("last_return", "mean_5", "mean_20", "volatility_20", "positive_fraction_20")
SPEC = {
    "train_through": "2023-12-31",
    "validate_through": "2024-12-31",
    "test_from": "2026-01-01",
    "epochs": 60,
    "learning_rate": 0.08,
    "l2": 0.01,
    "positive_signal_threshold": 0.6,
    "feature_lag_days": 2,
}


def validate_observations(rows):
    if not isinstance(rows, (list, tuple)) or not 250 <= len(rows) <= 250_000:
        raise ValueError("Provide 250..250000 dated return observations")
    parsed = []
    for row in rows:
        try:
            day = date.fromisoformat(str(row["timestamp"])[:10])
            if isinstance(row["return"], bool):
                raise ValueError("Boolean return")
            value = float(row["return"])
        except (TypeError, KeyError, ValueError, OverflowError) as exc:
            raise ValueError("Each observation needs an ISO date and numeric return") from exc
        if not math.isfinite(value) or not -1 < value <= 10:
            raise ValueError("Returns must be finite decimals in (-1, 10]")
        if parsed and day <= parsed[-1][0]:
            raise ValueError("Observation dates must be unique and strictly increasing")
        parsed.append((day, value))
    return parsed


def examples(observations):
    history, result = deque(maxlen=20), []
    previous = None
    # Require a continuous window. Missing days are not forward-filled.
    for index, (day, value) in enumerate(observations):
        if previous is not None and day - previous != timedelta(days=1):
            history.clear()
        # Deliberate two-day lag: day t predicts return on t+2, allowing a full
        # daily publication delay. Metadata also warns actual release latency
        # is unverified. No current or future target enters a feature.
        if len(history) == 20 and index + 1 < len(observations):
            next_day, target = observations[index + 1]
            if next_day - day == timedelta(days=1):
                values = list(history)
                result.append(
                    (
                        next_day,
                        [
                            values[-1],
                            statistics.mean(values[-5:]),
                            statistics.mean(values),
                            statistics.pstdev(values),
                            sum(item > 0 for item in values) / 20,
                        ],
                        int(target > 0),
                    )
                )
        history.append(value)
        previous = day
    return result


def _sigmoid(value):
    return 1 / (1 + math.exp(-max(-30, min(30, value))))


def fit(train):
    means = [statistics.mean(row[1][i] for row in train) for i in range(len(FEATURES))]
    scales = [statistics.pstdev(row[1][i] for row in train) or 1 for i in range(len(FEATURES))]
    features = [
        [
            max(-10, min(10, (value - mean) / scale))
            for value, mean, scale in zip(row[1], means, scales)
        ]
        for row in train
    ]
    base = (sum(row[2] for row in train) + 1) / (len(train) + 2)
    weights, bias = [0.0] * len(FEATURES), math.log(base / (1 - base))
    for _ in range(SPEC["epochs"]):
        gradients, intercept = [0.0] * len(weights), 0.0
        for vector, row in zip(features, train):
            residual = _sigmoid(bias + sum(w * x for w, x in zip(weights, vector))) - row[2]
            intercept += residual
            for index, value in enumerate(vector):
                gradients[index] += residual * value
        bias -= SPEC["learning_rate"] * intercept / len(train)
        weights = [
            w - SPEC["learning_rate"] * (gradient / len(train) + SPEC["l2"] * w)
            for w, gradient in zip(weights, gradients)
        ]
    return {
        "weights": weights,
        "intercept": bias,
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


def metrics(model, sample):
    scores = [predict(model, row[1]) for row in sample]
    positives = [
        index for index, value in enumerate(scores) if value >= SPEC["positive_signal_threshold"]
    ]
    base = model["training_up_frequency"]
    correct = sum((score >= 0.5) == bool(row[2]) for score, row in zip(scores, sample))
    ups, downs = sum(row[2] for row in sample), sum(not row[2] for row in sample)
    up_hits = sum(score >= 0.5 and row[2] for score, row in zip(scores, sample))
    down_hits = sum(score < 0.5 and not row[2] for score, row in zip(scores, sample))
    return {
        "examples": len(sample),
        "start": sample[0][0].isoformat(),
        "end": sample[-1][0].isoformat(),
        "direction_accuracy": correct / len(sample),
        "balanced_accuracy": (up_hits / ups + down_hits / downs) / 2 if ups and downs else None,
        "brier_score": sum((score - row[2]) ** 2 for score, row in zip(scores, sample))
        / len(sample),
        "baseline_brier_score": sum((base - row[2]) ** 2 for row in sample) / len(sample),
        "training_majority_baseline_accuracy": sum((base >= 0.5) == bool(row[2]) for row in sample)
        / len(sample),
        "positive_signals": len(positives),
        "positive_signal_precision": (
            sum(sample[index][2] for index in positives) / len(positives) if positives else None
        ),
    }


def train_research(rows, *, source=None):
    observations = validate_observations(rows)
    data = examples(observations)
    train = [row for row in data if row[0].isoformat() <= SPEC["train_through"]]
    validation = [
        row
        for row in data
        if SPEC["train_through"] < row[0].isoformat() <= SPEC["validate_through"]
    ]
    test = [row for row in data if row[0].isoformat() >= SPEC["test_from"]]
    if len(train) < 200 or len(validation) < 50 or len(test) < 50:
        raise ValueError(
            "Need 200 training labels through 2023, 50 validation labels in 2024, and 50 test labels from 2026"
        )
    fingerprint = hashlib.sha256(
        json.dumps(
            [(day.isoformat(), value) for day, value in observations], separators=(",", ":")
        ).encode()
    ).hexdigest()
    train_fingerprint = hashlib.sha256(
        json.dumps(
            [(day.isoformat(), vector, label) for day, vector, label in train],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    model = fit(train)
    artifact = {
        "model_id": MODEL_ID,
        "specification": SPEC.copy(),
        "training_fingerprint": train_fingerprint,
        "training_labels_through": train[-1][0].isoformat(),
        **model,
    }
    artifact_hash = hashlib.sha256(
        json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    validation_metrics, test_metrics = metrics(model, validation), metrics(model, test)
    better = test_metrics["brier_score"] < test_metrics["baseline_brier_score"]
    return {
        "model_id": MODEL_ID,
        "mode": "research_only",
        "source": source or {"name": "Operator-supplied returns; rights and provenance unverified"},
        "data_fingerprint": fingerprint,
        "observations": len(observations),
        "coverage": {
            "start": observations[0][0].isoformat(),
            "end": observations[-1][0].isoformat(),
        },
        "training": {
            "examples": len(train),
            "start": train[0][0].isoformat(),
            "end": train[-1][0].isoformat(),
        },
        "validation": validation_metrics,
        "test": test_metrics,
        "test_by_year": [
            metrics(model, [row for row in test if row[0].year == year])
            for year in sorted({row[0].year for row in test})
        ],
        "artifact": artifact,
        "artifact_sha256": artifact_hash,
        "status": "research_signal_only" if better else "no_predictive_improvement",
        "beats_constant_probability_baseline": better,
        "trading_win_rate": None,
        "target_70_percent_proven": False,
        "live_trading_enabled": False,
        "limitations": [
            "This predicts the sign of a daily return. Direction accuracy and signal precision are not completed-trade win rates or profitability.",
            "One fixed regularized logistic model; weights and scaling fit only to labels through 2023. 2024 validation and 2026+ test labels never update weights or select settings.",
            "2025 is excluded from headline evaluation because earlier Loki research inspected that market period. Cross-market correlation still limits independence.",
            "Features end two days before the target return; actual historical publication availability is unverified. Retrospective benchmark design or revisions can create hindsight bias.",
            "Missing calendar days reset the feature window. No prices, candles, volume, fills, fees or P&L are invented from return factors.",
            "Historical experiments remain exploratory; this is not a certified untouched holdout. Repeated testing requires a new future sample.",
            "Scores have not been independently calibrated. No transfer to BTC/ETH execution, profitable trading edge, or future 70% win rate is established.",
            "Market-model training does not fine-tune Loki's local conversational assistant. No real-money trading is enabled.",
        ],
    }
