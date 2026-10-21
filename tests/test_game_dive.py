"""Loki Dive arcade: bank integrity, typo-forgiving matcher wiring, honest flows.

The bank is hand-written data — the tests pinch it mechanically so a sloppy
entry (bad tier index, duplicate after folding, empty tier bucket, garbage
placeholder text) cannot ship in a working state. The engine asserts the
forgiving-matcher wiring exists in game.js and the template carries the new
controls. JS behaviour itself is exercised in the browser, not here; these
tests guard structure and content.
"""

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
    def __init__(self, source: str):
        self.source = source
        prompts_src = source[source.index("const prompts = ["):]
        self.qs = re.findall(r'q: "([^"]+)"', prompts_src)
        self.tier_def = re.findall(r'key: "([a-z]+)", name: "([^"]+)", points: (\d+)', source)
        body = prompts_src[: prompts_src.rindex("];")]
        self.blocks = re.findall(r'q: "[^"]+".*?a: \[(.*?)\]\s*\n\s*\}', body, re.S)
        carat = source[source.index("const tiers = ["):]
        self.tier_count = len(re.findall(r"\{ key:", carat))

    def entries(self):
        for block in self.blocks:
            for match in re.finditer(r'\["((?:[^"\\]|\\.)*)", (\d+)\]', block):
                yield match.group(1), int(match.group(2))


BANK_TEST = _BankReader(BANK.read_text(encoding="utf-8"))


class TestBankIntegrity:
    def test_bank_is_large_and_ranged(self):
        assert len(BANK_TEST.qs) >= 45, "the upgrade promised a big, varied bank"
        assert len(BANK_TEST.blocks) == len(BANK_TEST.qs)
        total = sum(1 for _ in BANK_TEST.entries())
        assert total >= 1000, "rarity layers need enough names to reward hunting"

    def test_every_prompt_has_every_tier_populated(self):
        for block in BANK_TEST.blocks:
            found = {}
            for tier in re.findall(r'\["(?:[^"\\]|\\.)*", (\d+)\]', block):
                tier = int(tier)
                assert tier in range(BANK_TEST.tier_count), f"tier index {tier} outside the known bands"
                found[tier] = found.get(tier, 0) + 1
            assert len(found) == BANK_TEST.tier_count, "a tier bucket sits empty — the ladder has a hole"
            assert min(found.values()) >= 2, "every tier needs at least two reachable answers"

    def test_no_duplicate_answer_after_folding(self):
        folded = {}
        for block in BANK_TEST.blocks:
            seen = {}
            for match in re.finditer(r'\["((?:[^"\\]|\\.)*)", (\d+)\]', block):
                answer = match.group(1)
                key = _fold(answer)
                assert key, "empty answer found"
                assert key not in seen, f"dup after folding: {answer!r} vs {seen[key]!r}"
                seen[key] = answer

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
        assert "loki_dive_recent" in BACKUP.read_text(encoding="utf-8"), "backups must carry the freshness memory"

    def test_extras_and_count_render(self):
        src = ENGINE.read_text(encoding="utf-8")
        assert "dive-end-extra" in src
        assert "dive-count" in src
        assert "Deepest find" in src


MISSING_ARTICLE = ('drop a leading "a"/"an"/"the" for matching ("a parrot" == "parrot")    s = s.replace')


class TestTemplateWiring:
    def test_new_controls_exist(self):
        src = TEMPLATE.read_text(encoding="utf-8")
        for marker in ('id="dive-skip"', 'id="dive-count"', 'id="dive-end-extra"',
                       'aria-live="polite"', 'id="dive-start-btn"', "Begin the dive"):
            assert marker in src
        assert "Typos get forgiven" in src, "the start screen must say spelling is forgiven"
        assert src.index('id="game"') > src.index('id="nav-more-group"'), "Bored? stays last in the nav"

    def test_game_scripts_are_versioned_and_present(self):
        src = TEMPLATE.read_text(encoding="utf-8")
        assert 'src="/static/js/game_data.js?v={{ version }}"' in src
        assert 'src="/static/js/game.js?v={{ version }}"' in src
