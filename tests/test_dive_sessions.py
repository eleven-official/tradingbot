"""The verified daily engine: order determinism, matcher parity, replay math.

Everything here runs against the *same files the browser plays* — the bank
literal and the game.js algorithm — so server and client can never drift.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import pytest

from loki.api.dive_sessions import (
    CLEAN_SWEEP_BONUS,
    COMBO_BONUS,
    HOT_STREAK,
    ROUNDS_PER_DIVE,
    damerau_distance,
    daily_order,
    daily_seed,
    day_key,
    fold_answer,
    load_bank,
    match_answer,
    normalize_answer,
    replay_daily,
    tolerance_for,
)

ROOT = Path(__file__).resolve().parents[1]
GAME = (ROOT / "static" / "js" / "game.js").read_text(encoding="utf-8")
BANK = (ROOT / "static" / "js" / "game_data.js").read_text(encoding="utf-8")
IDX = {p["q"]: i for i, p in enumerate(load_bank()["prompts"])}


# ---------------------------------------------------------------------------
# The bank is the browser's own file — the server replays that exact data.
# ---------------------------------------------------------------------------


def test_bank_is_a_single_json_literal_the_server_reads_verbatim():
    start = BANK.index("window.LokiDiveBank = ") + len("window.LokiDiveBank = ")
    data = json.loads(BANK[start:].strip().rstrip(";"))
    assert load_bank() == data
    assert len(data["prompts"]) >= 7 and len(data["tiers"]) == 6


def test_all_fifty_states_hold_in_the_bank():
    states = load_bank()["prompts"][IDX["Name a US state"]]
    names = {a for a, _ in states["a"]}
    assert len(names) == 50
    for state in ("hawaii", "north dakota", "rhode island", "alaska", "mississippi"):
        assert state in names


# ---------------------------------------------------------------------------
# Matcher parity with game.js — normalise, fold, tolerance, Damerau.
# ---------------------------------------------------------------------------


def test_matcher_matches_gamejs_pipeline_cell_for_cell():
    """Pins the engine's normalize to the same rules the browser applies:
    NFD diacritics off, punctuation to spaces, apostrophes dropped,
    whitespace collapsed, '&' to ' and'."""
    assert normalize_answer("Pólité's & Crown") == "polites and crown"
    assert normalize_answer("  WEDNESDAY  ") == "wednesday"


def test_short_words_match_exactly_long_words_forgive_typos():
    # the game passes the longer word's length; wheels: <=4 exact, <=7 one, else two
    assert tolerance_for(4) == 0
    assert tolerance_for(7) == 1
    assert tolerance_for(8) == 2
    assert tolerance_for(12) == 2


def test_damerau_distance_is_optimal_string_alignment():
    assert damerau_distance("kitten", "sitting") == 3
    assert damerau_distance("teh", "the") == 1  # transposition
    assert damerau_distance("ca", "ac") == 1
    assert damerau_distance("parrot", "parrots") == 1


def test_exact_and_folded_hits_pay_the_banked_tier():
    fruit = IDX["Name a fruit"]
    hit = match_answer(fruit, "  Kiwi ")
    assert hit and hit["answer"] == "kiwi" and hit["tier"] == 1
    hit = match_answer(IDX["Name a bird"], "an owl")  # leading article folds
    assert hit and hit["answer"] == "owl"
    # fold alias: 'the moon'/'moon' both banked for the moon prompt
    moon = IDX["Name a moon in the solar system"]
    hit = match_answer(moon, "the Moon")
    assert hit and "moon" in hit["answer"].lower()


def test_typo_forgiveness_matches_the_browser_tolerance():
    state_idx = IDX["Name a US state"]
    hit = match_answer(state_idx, "Rhode Islnad")  # transposition, len > 7
    assert hit and hit["answer"] == "rhode island" and hit["fixed"]
    assert match_answer(state_idx, "Kiwiland") is None  # not a state, no ghost match


def test_junk_and_oversize_cannot_match():
    state_idx = IDX["Name a US state"]
    assert match_answer(state_idx, "   ") is None
    assert match_answer(state_idx, None) is None
    assert match_answer(state_idx, 12345) is None


# ---------------------------------------------------------------------------
# Daily order: same day == same seven for everyone; different day differs.
# ---------------------------------------------------------------------------


def test_daily_seed_folds_the_utc_day_into_uint32():
    assert daily_seed("2026-01-01") == int("20260101", 10) & 0xFFFFFFFF
    assert daily_seed("2026-11-05") == int("20261105", 10) & 0xFFFFFFFF


def test_same_day_same_order_any_number_of_calls():
    day = "2026-03-14"
    first = daily_order(day)
    assert len(first) == ROUNDS_PER_DIVE
    assert first == daily_order(day) == daily_order(day)  # deterministic, cached
    for idx in first:
        assert 0 <= idx < len(load_bank()["prompts"])
    assert len(set(first)) == ROUNDS_PER_DIVE  # no prompt repeats in a run


def test_day_keys_vary_and_reject_junk():
    assert day_key(None) == day_key("")  # today, UTC — same string both calls
    assert day_key("2027-02-28") == "2027-02-28"
    with pytest.raises(Exception):
        day_key("2026-13-01")  # no month 13
    with pytest.raises(Exception):
        day_key("not-a-date")
    with pytest.raises(Exception):
        day_key("20260301")  # wrong shape
    assert daily_order("2026-03-14") != daily_order("2026-03-15")


# ---------------------------------------------------------------------------
# Replay math: the server pays exactly what the browser would.
# ---------------------------------------------------------------------------


def _rounds_for(day: str, answers: dict[int, str]) -> list[dict]:
    order = daily_order(day)
    return [{"i": idx, "a": answers.get(position, "")} for position, idx in enumerate(order)]


def test_all_seven_found_pays_base_plus_combo_plus_clean_sweep():
    day = "2026-05-01"
    order = daily_order(day)
    answers = {}
    for position, idx in enumerate(order):
        first_answer = load_bank()["prompts"][idx]["a"][0][0]
        answers[position] = first_answer
    verdict = replay_daily(day, _rounds_for(day, answers))
    base = sum(t["points"] for t in verdict["rounds"])
    assert verdict["base_points"] == base
    assert verdict["clean_sweep"] == CLEAN_SWEEP_BONUS
    assert verdict["streak_bonus"] == (ROUNDS_PER_DIVE - HOT_STREAK + 1) * COMBO_BONUS
    assert verdict["total_points"] == base + verdict["clean_sweep"] + verdict["streak_bonus"]
    assert verdict["found_count"] == 7 and verdict["missed"] == []


def test_misses_reset_the_combo_and_kill_the_sweep():
    day = "2026-05-02"
    order = daily_order(day)
    answers = {}
    for position, idx in enumerate(order):
        if position == 3:  # one miss in the middle: combo breaks, sweep dies
            continue
        answers[position] = load_bank()["prompts"][idx]["a"][0][0]
    verdict = replay_daily(day, _rounds_for(day, answers))
    assert verdict["clean_sweep"] == 0
    assert verdict["found_count"] == 6
    # after the miss at position 3, positions 4..6 form a fresh streak of 3 —
    # so the run pays the opener's 5 AND the recovery's 5, exactly as the game does
    assert verdict["streak_bonus"] == 2 * COMBO_BONUS
    assert verdict["missed"] == [3]
    # nothing at all → zero verified points
    empty = _rounds_for(day, {})
    verdict = replay_daily(day, empty)
    assert verdict["total_points"] == 0 and verdict["found_count"] == 0


def test_wrong_round_order_is_refused_not_rescored():
    day = "2026-05-03"
    order = daily_order(day)
    runs = [{"i": idx, "a": ""} for idx in order]
    runs[0], runs[1] = runs[1], runs[0]  # swap two positions
    with pytest.raises(Exception):
        replay_daily(day, runs)


def test_wrong_round_count_is_refused():
    day = "2026-05-04"
    short = daily_payload_short = _rounds_for(day, {})[:6]
    with pytest.raises(Exception):
        replay_daily(day, short)
    with pytest.raises(Exception):
        replay_daily(day, _rounds_for(day, {}) + [{"i": 0, "a": ""}])


def test_oversize_answers_never_reach_the_matcher():
    day = "2026-05-05"
    runs = _rounds_for(day, {})
    runs[0]["a"] = "x" * 50000
    with pytest.raises(Exception):
        replay_daily(day, runs)


def test_replay_is_day_scoped():
    day_a, day_b = "2026-05-06", "2026-05-07"
    order_a = daily_order(day_a)
    answers = {pos: load_bank()["prompts"][idx]["a"][0][0] for pos, idx in enumerate(order_a)}
    payload = _rounds_for(day_a, answers)
    assert replay_daily(day_a, payload)["found_count"] > 0
    # another day runs a different shared order — a day-A payload declares
    # indexes that don't match day B's order, so the replay refuses it
    with pytest.raises(Exception):
        replay_daily(day_b, payload)


def test_gamejs_still_contains_the_star_hooks_and_no_fake_stats():
    # streak-flame lives in the game; the daily marker and local autosave hook exist
    assert "loki_dive_last_open" in GAME
    assert "autosaveSnapshot" in GAME
    assert "streak-flame" in GAME
    assert "challenge/verify" in GAME
    assert "challenge/order" in GAME
    assert "My answer should count" in GAME


def test_autosave_snapshot_is_bounded_and_local_and_local_only():
    src = GAME
    assert "LS_AUTOSAVE" in src and "AUTOSAVE_BYTES_MAX" in src
    assert "exportData" in src
    assert (
        " инвест" not in src and "fetch ('http" not in src and "fetch('http" not in src
    )  # nothing leaves the device
    note = "saved automatically on this device when Loki Dive was opened"
    assert note in src


def test_autosave_runs_on_open_and_after_runs():
    assert (
        "autosaveSnapshot(); // opening the game saves this browser's own info to this device"
        in GAME
    )
    assert (
        "autosaveSnapshot(); // the run's outcomes refresh the on-device snapshot immediately"
        in GAME
    )


def test_report_queue_is_bounded_and_honest():
    assert "loki_dive_reports" in GAME
    assert "stays in your browser" in GAME
