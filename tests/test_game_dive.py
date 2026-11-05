"""Loki Dive arcade: bank integrity, typo-forgiving matcher wiring, honest flows.

The bank is hand-written data — the tests pinch it mechanically so a sloppy
entry (bad tier index, duplicate after folding, empty tier bucket, garbage
placeholder text) cannot ship in a working state. The engine asserts the
forgiving-matcher wiring exists in game.js and the template carries the new
controls. JS behaviour itself is exercised in the browser, not here; these
tests guard structure and content.
"""

import json
import re
from html.parser import HTMLParser
from pathlib import Path
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "static" / "js" / "game_data.js"
ENGINE = ROOT / "static" / "js" / "game.js"
TEMPLATE = ROOT / "templates" / "index.html"
BACKUP = ROOT / "static" / "js" / "backup.js"


def _fold(text: str) -> str:
    """Approximate the engine's folding: diacritics off, punctuation off."""
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return " ".join(text.split())


class _BankReader:
    """The bank is a single JSON literal (server and browser share it), so the
    reader parses the assignment body and works on real data, not regex."""

    def __init__(self, source: str):
        start = source.index("window.LokiDiveBank = ") + len("window.LokiDiveBank = ")
        data = json.loads(source[start:].strip().rstrip(";"))
        self.data = data
        self.tier_def = [(t["key"], t["name"], str(t["points"])) for t in data["tiers"]]
        self.tier_count = len(data["tiers"])
        self.qs = [p["q"] for p in data["prompts"]]
        self.blocks = [json.dumps(p["a"]) for p in data["prompts"]]
        self.prompts = data["prompts"]

    def entries(self):
        for p in self.prompts:
            for answer, tier in p["a"]:
                yield answer, tier


BANK_TEST = _BankReader(BANK.read_text(encoding="utf-8"))


class TestBankIntegrity:
    def test_bank_is_a_single_json_literal_the_server_can_replay(self):
        """The Python engine reads the exact file the browser plays."""
        source = BANK.read_text(encoding="utf-8")
        start = source.index("window.LokiDiveBank = ")
        data = json.loads(source[start + len("window.LokiDiveBank = ") :].strip().rstrip(";"))
        assert set(data) == {"tiers", "prompts"}
        assert len(data["tiers"]) == 6 and len(data["prompts"]) == len(BANK_TEST.qs)

    def test_the_us_state_prompt_bank_holds_all_fifty(self):
        states = next(p for p in BANK_TEST.prompts if p["q"] == "Name a US state")
        banked = {answer for answer, _ in states["a"]}
        missing = {
            "alaska",
            "arkansas",
            "connecticut",
            "hawaii",
            "illinois",
            "indiana",
            "kansas",
            "georgia",
            "louisiana",
            "maryland",
            "massachusetts",
            "minnesota",
            "montana",
            "nevada",
            "new jersey",
            "new mexico",
            "north carolina",
            "north dakota",
            "oklahoma",
            "pennsylvania",
            "south carolina",
            "south dakota",
            "tennessee",
            "texas",
            "utah",
            "virginia",
        }
        assert not (missing - banked), f"states still rejected by the bank: {missing - banked}"
        assert len(banked) == 50
        assert "All fifty" in states["rules"]

    def test_rules_never_promise_more_than_the_bank_holds(self):
        """Open prompts are curated banks; the rules must say so instead of
        claiming any X counts when only listed answers are accepted."""
        banned = (
            "any bird",
            "any real river",
            "all 118",
            "any club, any league",
            "anyone named",
            "spoken languages",
            "any commission",
            "any com",
        )
        for prompt in BANK_TEST.prompts:
            low = prompt["rules"].lower()
            assert not any(b in low for b in banned), prompt["q"]
            assert "hand-picked" in low or "curated" in low or "all fifty" in low, prompt["q"]

    def test_rarity_notes_are_editorial_not_measured(self):
        """No tier description may imply live player statistics were gathered."""
        for (_key, name, _points), tier in zip(BANK_TEST.tier_def, BANK_TEST.data["tiers"]):
            low = tier["note"].lower()
            assert "editor" in low, f"{name} note must name its editorial call"
            for banned in ("everyone gives", "players found", "gave this"):
                assert banned not in low, f"{name} note implies measured stats: {tier['note']!r}"

    def test_bank_is_large_and_ranged(self):
        assert len(BANK_TEST.qs) >= 45, "the upgrade promised a big, varied bank"
        assert len(BANK_TEST.blocks) == len(BANK_TEST.qs)
        total = sum(1 for _ in BANK_TEST.entries())
        assert total >= 1000, "rarity layers need enough names to reward hunting"

    def test_bank_grew_into_new_domains(self):
        assert len(BANK_TEST.qs) >= 57, "this wave promised seven fresh domains"
        for question in (
            "Name a sea",
            "Name a tea",
            "Name a typeface",
            "Name a fighter jet",
            "Name a currency",
            "Name a Norse god",
        ):
            assert question in BANK_TEST.qs, f"a promised domain is missing: {question}"

    def test_every_prompt_has_every_tier_populated(self):
        for block in BANK_TEST.blocks:
            found = {}
            for tier in re.findall(r'\["(?:[^"\\]|\\.)*", (\d+)\]', block):
                tier = int(tier)
                assert tier in range(
                    BANK_TEST.tier_count
                ), f"tier index {tier} outside the known bands"
                found[tier] = found.get(tier, 0) + 1
            assert (
                len(found) == BANK_TEST.tier_count
            ), "a tier bucket sits empty — the ladder has a hole"
            assert min(found.values()) >= 2, "every tier needs at least two reachable answers"

    def test_no_duplicate_answer_after_folding(self):
        """Engine parity: normalize keys are unique (buildIndex is first-wins);
        fold-level collisions are intended aliases and only allowed when every
        colliding entry carries the same tier, so a folded hit always pays the
        same points no matter which spelling reached it."""
        norm_seen = {}
        for prompt in BANK_TEST.prompts:
            norm_seen.clear()
            for answer, tier in prompt["a"]:
                norm_key = re.sub(r"[^a-z0-9 ]+", " ", answer.lower()).strip()
                assert (
                    norm_key not in norm_seen
                ), f"dup after normalize in {prompt['q']!r}: {answer!r}"
                norm_seen[norm_key] = answer
            fold_tiers = {}
            for answer, tier in prompt["a"]:
                key = _fold(answer)
                assert key, f"empty answer found in {prompt['q']!r}"
                if key in fold_tiers and fold_tiers[key] != tier:
                    raise AssertionError(f"fold alias crosses tiers in {prompt['q']!r}: {answer!r}")
                fold_tiers[key] = tier

    def test_bank_entries_look_real_not_placeholder(self):
        garbage_tokens = ("? ", "??", "NO", "todo", "tbd", "placeholder", "fixme", "lorem")
        for answer, tier in BANK_TEST.entries():
            low = answer.lower()
            for token in garbage_tokens:
                assert token not in low, f"placeholder-looking entry shipped: {answer!r}"
            assert answer == answer.strip(), f"leading/trailing spaces: {answer!r}"

    def test_questions_are_unique_and_varied(self):
        assert len(BANK_TEST.qs) == len(set(BANK_TEST.qs)), "a question repeats"
        domains = {q.split()[-2] if len(q.split()) > 2 else q for q in BANK_TEST.qs}

    def test_fresh_domains_landed_with_the_sparkline_wave(self):
        for question in (
            "Name a gemstone",
            "Name a mushroom",
            "Name a wind",
            "Name a type of boat",
        ):
            assert question in BANK_TEST.qs, f"a fresh domain is missing: {question}"
        spark_src = (ROOT / "static" / "js" / "game.js").read_text(encoding="utf-8")
        assert "renderSpark()" in spark_src  # end screen draws the browser's own trend
        board_src = (ROOT / "static" / "js" / "dive_board.js").read_text(encoding="utf-8")
        assert "visibilitychange" in board_src  # a returning tab re-fetches the board
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        assert 'id="dive-spark"' in html
        css = (ROOT / "static" / "css" / "style.css").read_text(encoding="utf-8")
        assert ".dive-spark svg" in css
        assert len({q.lower() for q in BANK_TEST.qs}) >= 45


class TestEngineWiring:
    def test_typo_forgiving_matcher_ships(self):
        src = ENGINE.read_text(encoding="utf-8")
        assert "damerauDistance" in src, "the Damerau-Levenshtein matcher is missing"
        assert "toleranceFor" in src, "length-aware tolerance is missing"
        assert "spelling forgiven" in src, "honest typo-fix feedback is missing"
        assert MISSING_ARTICLE not in src, "the dead article-stripping comment bug returned"

    def test_skip_clean_sweep_and_freshness_ship(self):
        src = ENGINE.read_text(encoding="utf-8")
        assert 'id === "dive-skip"' in src or "skipRound" in src
        assert "CLEAN_SWEEP_BONUS" in src
        assert 'LS_RECENT = "loki_dive_recent"' in src
        assert "freshOrder" in src
        assert "loki_dive_recent" in BACKUP.read_text(
            encoding="utf-8"
        ), "backups must carry the freshness memory"

    def test_extras_and_count_render(self):
        src = ENGINE.read_text(encoding="utf-8")
        assert "dive-end-extra" in src
        assert "dive-count" in src
        assert "Deepest find" in src

    def test_streak_combo_ships_and_breaks_honestly(self):
        src = ENGINE.read_text(encoding="utf-8")
        assert "COMBO_BONUS" in src, "the consecutive-find combo is missing"
        assert "HOT_STREAK" in src, "the streak must have a warm-up before it pays"
        assert (
            "state.streakBonus" in src
        ), "combo money needs its own bucket beside the clean-sweep bonus"
        assert src.count("state.streak = 0") >= 2, "skips and time-outs must both break the streak"

    def test_dive_history_ships_and_backs_up(self):
        engine = ENGINE.read_text(encoding="utf-8")
        assert 'LS_HISTORY = "loki_dive_history"' in engine
        assert "Recent dives" in engine, "the start screen trend line must render"
        assert "loki_dive_history" in BACKUP.read_text(
            encoding="utf-8"
        ), "the dive trend lives in backups like every other local truth"
        assert 'id="dive-history"' in TEMPLATE.read_text(encoding="utf-8")


MISSING_ARTICLE = (
    'drop a leading "a"/"an"/"the" for matching ("a parrot" == "parrot")    s = s.replace'
)


class TestTemplateWiring:
    def test_new_controls_exist(self):
        src = TEMPLATE.read_text(encoding="utf-8")
        for marker in (
            'id="dive-skip"',
            'id="dive-count"',
            'id="dive-end-extra"',
            'aria-live="polite"',
            'id="dive-start-btn"',
            "Begin the dive",
        ):
            assert marker in src
        assert "Typos get forgiven" in src, "the start screen must say spelling is forgiven"
        assert src.index('id="game"') > src.index(
            'id="nav-more-group"'
        ), "Bored? stays last in the nav"

    def test_game_scripts_are_versioned_and_present(self):
        src = TEMPLATE.read_text(encoding="utf-8")
        assert 'src="/static/js/game_data.js?v={{ version }}"' in src
        assert 'src="/static/js/game.js?v={{ version }}"' in src

    def test_dive_input_never_spellchecks_the_player(self):
        src = TEMPLATE.read_text(encoding="utf-8")
        assert re.search(
            r'id="dive-answer"[^>]*spellcheck="false"', src
        ), "an input a player may deliberately misspell must not be spell-checked"
        assert re.search(r'id="dive-answer"[^>]*autocapitalize="none"', src)
