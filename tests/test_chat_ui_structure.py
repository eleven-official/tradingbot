"""Wiring contract for the room's UI: ids referenced by the script exist,
quick-ask chips route through the composer, and the page keeps the passcode
screen, stream, memory panel and admin box reachable. No JS runtime in CI —
these pins live at the DOM/contract level instead."""

import re


def test_every_js_id_exists_in_the_page():
    src = open("static/js/ai_chat.js", encoding="utf-8").read()
    template = open("templates/ai_chat.html", encoding="utf-8").read()
    ids = set(re.findall(r"\$\('([A-Za-z0-9_-]+)'\)", src))
    missing = [i for i in ids if f'id="{i}"' not in template]
    assert not missing, missing


def test_chips_and_copy_button_are_wired():
    src = open("static/js/ai_chat.js", encoding="utf-8").read()
    template = open("templates/ai_chat.html", encoding="utf-8").read()
    assert "data-ask" in template and template.count('data-ask="') >= 4
    assert "composerSubmit(chip.dataset.ask)" in src
    assert "navigator.clipboard.writeText" in src
    assert "copy.className = 'copy'" in src


def test_rooms_gates_and_words_stay_honest():
    template = open("templates/ai_chat.html", encoding="utf-8").read()
    assert "It never places orders" in template
    # the room opened up: the gate is a name, not a passcode — the page must say so
    assert "OPEN ROOM" in template
    assert "no passcode needed" in template.lower()
    assert "LOKI'S MEMORY" in template
