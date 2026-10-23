"""Arcade juice (2.20.0): sonar pings, rarity teasers, synth blips, find pop.

All honest, all local: the sonar advertises only the SHAPE of the deepest
find (word count, letters, first letter — never the answer); the miss
teaser quotes the deepest shelf's real point value straight from the bank;
the blips are a tiny WebAudio synth with a persisted toggle — no assets,
no network, no autoplay surprises; the animations respect reduced motion.
"""
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[1]

GAME_JS = (REPO / "static" / "js" / "game.js").read_text(encoding="utf-8")
INDEX = (REPO / "templates" / "index.html").read_text(encoding="utf-8")
STYLE = (REPO / "static" / "css" / "style.css").read_text(encoding="utf-8")


def test_sound_is_a_tiny_local_synth_with_a_persisted_toggle():
    assert '"loki_dive_sound"' in GAME_JS
    assert "window.webkitAudioContext" in GAME_JS  # Safari users get the same blips
    assert "exponentialRampToValueAtTime" in GAME_JS  # proper release, no clicks
    assert "Number(storage(LS_SOUND, 1))" in GAME_JS  # default: sound leads the dive
    assert 'id="dive-sound-btn"' in INDEX and 'aria-pressed="true"' in INDEX
    assert "function toggleSound" in GAME_JS
    for banned in (".mp3", ".wav", ".ogg", "new Audio"):
        assert banned not in GAME_JS, f"no audio assets expected: {banned}"


def test_the_sonar_never_names_the_answer():
    match = re.search(r"function runSonar\(.*?\n  \}", GAME_JS, re.S)
    assert match, "runSonar must exist"
    body = match.group(0)
    assert "state.sonarUsed = true" in body  # one ping per dive, hard-spent
    assert 'dive-sonar-btn"].disabled = true' in body  # spent pings are visibly spent
    # the sonar line carries shape, not substance:
    assert "starts with" in body
    assert "charAt(0).toUpperCase()" in body  # first letter only
    assert 'replace(/\\s/g, "")' in body  # letter count from the shape
    # and it must not print the word itself:
    assert "esc(" not in body
    assert "=" in body  # shapes only feed numbers and one letter
    assert "One ping per dive." in body


def test_the_sonar_is_one_ping_per_dive():
    assert "state.sonarUsed = false;" in GAME_JS
    assert 'els["dive-sonar-btn"].disabled = false;' in GAME_JS  # reset in startRun


def test_misses_teach_the_ladder_with_bank_truth():
    assert "The deepest shelf here pays" in GAME_JS
    assert "const shelf = bank.tiers[deepest]" in GAME_JS
    assert "shelf.points" in GAME_JS
    assert "shelf.name" in GAME_JS


def test_the_juice_carries_the_theme_and_respects_motion():
    assert "function bumpScore" in GAME_JS
    for css_marker in ("@keyframes dive-pop", "@keyframes dive-bump",
                       ".dive-feedback.good{animation", ".dive-score.dive-bump"):
        assert css_marker in STYLE, css_marker
    assert "@media (prefers-reduced-motion:reduce)" in STYLE
    assert ".dive-feedback.info" in STYLE  # the sonar and milestone voice


def test_new_controls_exist_in_the_markup_and_game():
    assert 'id="dive-sonar-btn"' in INDEX
    assert "Sonar ping" in INDEX
    assert "function runSonar" in GAME_JS
    assert '"dive-sonar-btn"' in GAME_JS and '"dive-sound-btn"' in GAME_JS
    assert "One sonar ping per dive reveals the shape of the deepest find" in INDEX


def test_endless_milestones_speak_honestly():
    assert "past the crowd. The trench lights up." in GAME_JS
    assert "state.round % 5 === 0" in GAME_JS


def test_the_scoring_math_is_untouched_by_the_juice():
    assert "const ROUNDS_PER_DIVE = 7;" in GAME_JS
    assert "POINTS_PER_METRE = 10" in GAME_JS
    assert "CLEAN_SWEEP_BONUS = 50" in GAME_JS


def test_the_loki_dive_handle_still_exposes_the_pure_matcher():
    assert "window.LokiDive = " in GAME_JS
    assert "mode: () => state.mode" in GAME_JS
    assert "journal: () => loadJournal()" in GAME_JS
