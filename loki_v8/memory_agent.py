"""Memory agent: causal self-review of past Director postures on real bars.

Before the Director speaks, this module replays the recent history and grades
how the same posture logic performed. It reads only bars available at each
past decision point, so nothing it reports could see forward. The lesson is
typed into the Director's thesis; sizing, gates and order paths are untouched
(there is no order path from research or review agents).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

HORIZON = 5  # bars until a past posture is graded as right or wrong
MAX_SAMPLES = 24  # bounded review window, sampled every SAMPLE_STRIDE bars
SAMPLE_STRIDE = 3
MIN_BARS = HORIZON + 2
WEAK_RATE = 0.40  # below this, the review warns that the posture is fading


def _posture_at(frame: pd.DataFrame, i: int) -> str:
    """Posture the logic would have taken using only bars up to index i."""
    closes = frame["close"].iloc[max(0, i - 9) : i + 1]
    if len(closes) < 5:
        return "flat"
    slope = float(closes.iloc[-1] - closes.iloc[0])
    track = float(closes.std(ddof=0))
    if track <= 0.0:
        return "flat"
    strength = slope / (track * len(closes))
    if strength > 0.2:
        return "long"
    if strength < -0.2:
        return "short"
    return "flat"


def reflect(frame: Optional[pd.DataFrame], horizon: int = HORIZON) -> Dict[str, Any]:
    """Grade the posture record on ``frame``; never trades, never sees forward.

    The last bar of a fetched history may still be forming, so grading uses
    everything before it. Sampled every SAMPLE_STRIDE bars back to
    MAX_SAMPLES graded decisions, newest first.
    """
    recap: Dict[str, Any] = {
        "samples": 0,
        "postures": {},
        "long_ok": 0,
        "long_total": 0,
        "lesson": "",
        "applied": False,
        "horizon": horizon,
    }
    if frame is None or len(frame) <= MIN_BARS:
        recap["lesson"] = "not enough history to review yet"
        return recap

    closed = frame.iloc[:-1].reset_index(drop=True)
    graded = 0
    long_ok = 0
    long_total = 0
    start = max(0, len(closed) - horizon - 1 - MAX_SAMPLES * SAMPLE_STRIDE)
    for i in range(len(closed) - horizon - 1, start - 1, -SAMPLE_STRIDE):
        if graded >= MAX_SAMPLES:
            break
        entry = float(closed["close"].iloc[i])
        later = float(closed["close"].iloc[i + horizon])
        if not entry > 0.0:
            continue
        move = (later - entry) / entry
        posture = _posture_at(closed, i)
        if posture == "flat":
            hit = abs(move) <= 0.001
        else:
            hit = move > 0.0 if posture == "long" else move < 0.0
        graded += 1
        bucket = recap["postures"].setdefault(posture, {"ok": 0, "total": 0})
        bucket["total"] += 1
        if hit:
            bucket["ok"] += 1
        if posture == "long":
            long_total += 1
            long_ok += 1 if hit else 0

    recap["samples"] = graded
    recap["long_ok"] = long_ok
    recap["long_total"] = long_total
    lessons: List[str] = []
    if long_total >= 8:
        rate = long_ok / long_total
        recap["applied"] = True
        verdict = "holding up" if rate >= WEAK_RATE else "not working"
        lessons.append(
            f"long setups graded {long_ok}/{long_total} over the last {long_total} "
            f"samples — the trend playbook has been {verdict}"
        )
    else:
        lessons.append(f"only {long_total} long samples graded so far — too small to advise")
    short_bucket = recap["postures"].get("short", {"ok": 0, "total": 0})
    if short_bucket["total"] >= 8:
        short_rate = short_bucket["ok"] / short_bucket["total"]
        short_verdict = "holding up" if short_rate >= WEAK_RATE else "not working"
        lessons.append(
            f"short setups graded {short_bucket['ok']}/{short_bucket['total']} — {short_verdict}"
        )
    recap["lesson"] = "self-review: " + "; ".join(lessons)
    return recap


def director_notes(recap: Dict[str, Any]) -> Optional[str]:
    """The one-line lesson the Director may append to its thesis."""
    return str(recap.get("lesson") or "") or None
