"""The expanded dive (2.19.0): endless waters + a personal field journal.

Both layers live entirely in the browser. The structural pins here keep the
honest boundaries of that expansion:

* endless dives never publish to, or race, the shared board;
* the field journal records only what YOU found and never prints answers
  for waters you have not chartered;
* the classic seven-round dive stays exactly as shipped;
* the new controls exist in the served markup and carry the theme styles.
"""
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[1]

GAME_JS = (REPO / "static" / "js" / "game.js").read_text(encoding="utf-8")
INDEX = (REPO / "templates" / "index.html").read_text(encoding="utf-8")
STYLE = (REPO / "static" / "css" / "style.css").read_text(encoding="utf-8")


def test_endless_mode_is_a_real_second_way_to_dive():
    assert "MISS_LIMIT = 2" in GAME_JS
    assert "ROUND_MS_FLOOR = 14000" in GAME_JS
    assert '"loki_dive_best_endless"' in GAME_JS  # separate best, this browser only
    assert 'state.mode === "endless"' in GAME_JS  # a real branch, not a slogan
    assert "moreOrder()" in GAME_JS  # the order reshuffles when the pool turns over
    assert "Endless · round" in GAME_JS  # the round label names the mode honestly


def test_endless_dives_never_race_the_shared_board():
    assert 'state.mode !== "endless" && window.LokiDiveBoard' in GAME_JS
    assert "the shared board ranks classic dives only." in GAME_JS


def test_the_surface_button_is_a_real_escape_hatch():
    assert "dive-surface-btn" in GAME_JS and 'id="dive-surface-btn"' in INDEX
    assert "Surface now" in INDEX
    assert "surfaced early" in GAME_JS  # surfacing mid-round is named on the end card


def test_classic_dive_stays_exactly_unchanged():
    assert "const ROUNDS_PER_DIVE = 7;" in GAME_JS
    assert '"loki_dive_best"' in GAME_JS
    assert '"Round " + state.round + " of " + ROUNDS_PER_DIVE' in GAME_JS
    assert "CLEAN_SWEEP_BONUS = 50" in GAME_JS


def test_the_field_journal_charters_your_waters_only():
    assert '"loki_dive_journal"' in GAME_JS
    assert "if (r.tier === null) return;" in GAME_JS  # misses write nothing
    assert "not chartered yet" in GAME_JS  # unseen waters show a marker, never an answer


def test_the_journal_never_prints_answer_words():
    match = re.search(r"function renderJournal\(.*?\n  \}", GAME_JS, re.S)
    assert match, "renderJournal must exist"
    body = match.group(0)
    assert "dive-journal-unknown" in body  # unseen marker
    assert "bank.tiers[entry.best].name" in body  # tier names only
    for banned in (".a[", "findAnswer", "esc(entry.answer)"):
        assert banned not in body, f"journal must not render answers via {banned}"


def test_mode_is_restored_and_choosable():
    assert '"loki_dive_mode"' in GAME_JS
    assert 'id="dive-mode-classic"' in INDEX and 'aria-pressed="true"' in INDEX
    assert 'id="dive-mode-endless"' in INDEX and 'aria-pressed="false"' in INDEX
    assert "function pickMode" in GAME_JS


def test_new_badges_are_declared_with_honest_how_notes():
    for marker in ('id: "survivor"', 'id: "naturalist"', 'id: "cartographer"'):
        assert marker in GAME_JS
    assert 'awardBadge("survivor")' in GAME_JS
    assert 'awardBadge("naturalist")' in GAME_JS
    assert 'awardBadge("cartographer")' in GAME_JS


def test_the_markup_wires_the_journal_panel():
    assert 'id="dive-journal"' in INDEX
    assert 'id="dive-journal-head"' in INDEX
    assert 'id="dive-journal-list"' in INDEX


def test_the_styles_carry_the_new_surfaces():
    assert ".dive-modes" in STYLE
    assert ".dive-mode-pick" in STYLE
    assert '.dive-mode-pick[aria-pressed="true"]' in STYLE
    assert ".dive-journal-row" in STYLE
    assert ".dive-journal-unseen" in STYLE


def test_the_desktop_handle_exposes_the_new_layers():
    assert "window.LokiDive = " in GAME_JS, "the LokiDive handle must stay exposed"
    assert "mode: () => state.mode" in GAME_JS
    assert "journal: () => loadJournal()" in GAME_JS


def test_the_progress_ladder_is_hidden_only_in_endless():
    assert 'dive-progress"].hidden = state.mode === "endless"' in GAME_JS
