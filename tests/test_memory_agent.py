"""Memory agent: causal self-review of past Director postures."""

from __future__ import annotations

import random
from types import SimpleNamespace

import pandas as pd

from loki_v8 import memory_agent
from loki_v8.agents import DirectorAgent
from loki_v8.config import LokiConfig


def _frame(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [1000] * len(closes),
        }
    )


def _rising(n: int = 200, seed: int = 7) -> list[float]:
    rng = random.Random(seed)
    price = 100.0
    closes = []
    for _ in range(n):
        price *= 1.004  # consistent upward drift
        closes.append(price + rng.uniform(-0.3, 0.3))
    return closes


def _falling(n: int = 200, seed: int = 11) -> list[float]:
    rng = random.Random(seed)
    price = 400.0
    closes = []
    cycle = 0
    for _ in range(n):
        cycle += 1
        # Falling tape with occasional small relief bounces: long setups
        # appear enough to grade, but most resolve against the longs.
        drift = -0.0035 if cycle % 9 else 0.002
        price *= 1.0 + drift
        closes.append(price + rng.uniform(-0.25, 0.25))
    return closes


def test_rising_tape_rewards_long_setups():
    recap = memory_agent.reflect(_frame(_rising()))
    long_bucket = recap["postures"].get("long", {"ok": 0, "total": 0})
    assert recap["applied"] is True
    assert long_bucket["total"] >= 8
    rate = long_bucket["ok"] / long_bucket["total"]
    assert rate >= 0.7
    assert "holding up" in recap["lesson"]


def test_falling_tape_warns_when_longs_fade():
    recap = memory_agent.reflect(_frame(_falling()))
    long_bucket = recap["postures"].get("long", {"ok": 0, "total": 0})
    if long_bucket["total"] >= 8:
        assert long_bucket["ok"] / long_bucket["total"] < 0.4
        assert "not working" in recap["lesson"]
    else:
        #采样不足 path: an honest refusal to grade is the correct behavior
        assert recap["applied"] is False


def test_short_history_refuses_to_advise():
    recap = memory_agent.reflect(_frame(_rising(5)))
    assert recap["applied"] is False
    assert recap["samples"] == 0
    assert recap["lesson"].startswith("not enough history")


def test_review_is_deterministic():
    frame = _frame(_rising())
    assert memory_agent.reflect(frame) == memory_agent.reflect(frame)


def test_review_never_reads_the_forming_last_bar():
    frame = _frame(_rising())
    mangled = frame.copy()
    mangled.iloc[-1, mangled.columns.get_loc("close")] = 999999.0
    # The fetched last bar may still be forming; grading must ignore it.
    assert memory_agent.reflect(frame) == memory_agent.reflect(mangled)


def test_director_carries_the_self_review_in_its_thesis():
    director = DirectorAgent(LokiConfig())
    regime = SimpleNamespace(state="BULL", confidence=88.0, trend_score=1.5, adx=24.0)
    out = director.run("SPY", regime, "self-review: 9/10 long setups graded — holding up")
    assert out["posture"] == "long"
    assert out["thesis"].endswith("self-review: 9/10 long setups graded — holding up")


def test_director_works_without_notes_back_compat():
    director = DirectorAgent(LokiConfig())
    regime = SimpleNamespace(state="RANGING", confidence=40.0, trend_score=0.2, adx=12.0)
    out = director.run("SPY", regime)
    assert "self-review" not in out["thesis"]
