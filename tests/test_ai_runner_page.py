"""Pins for the AI paper-trading runner (static JS source).

The old runner only stepped while its own panel was on screen, so "Start AI
trading" did nothing the moment the user opened another section, backgrounded
the tab, or left the page — and fills were never saved at the moment they
happened, so a reload could wipe the paper account mid-trade.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def runner_source() -> str:
    return (ROOT / "static" / "js" / "ai_trading.js").read_text(encoding="utf-8")


def test_runner_does_not_stop_when_its_panel_is_hidden():
    js = runner_source()
    assert "if (document.hidden || $('ai-trading').hidden) return;" not in js
    assert "needs this tab visible" not in js
    assert "paused politely" not in js


def test_a_single_watch_lease_prevents_cross_tab_double_trading():
    js = runner_source()
    assert "const RUNNER_LEASE_KEY = 'loki_runner_lease';" in js
    assert "function claimRunner()" in js
    assert "if (!claimRunner()) return; // another open tab is already running the checks" in js


def test_every_check_is_bound_to_a_hard_timeout():
    js = runner_source()
    # The running step and the manual scan both abort a hung feed at 15 s;
    # a wedged request used to keep `busy` true forever and kill the runner.
    assert js.count("AbortSignal.timeout(15000)") == 2


def test_fills_and_log_lines_are_saved_the_moment_they_happen():
    js = runner_source()
    assert "save(); // fills, curve points and log lines survive a reload from here" in js
    # Four UI handlers (start/stop/reset/symbol) plus every step outcome and
    # the manual scan must persist state.
    assert js.count("save();") >= 8


def test_background_pages_keep_a_running_runner_alive():
    js = runner_source()
    assert "if (!$('ai-trading')) {" in js
    assert "if (state.running) startLoop();" in js


def test_runner_script_is_wired_into_every_workspace_page():
    for page in ("index.html", "paper_tools.html", "research_desk.html", "strategy_lab.html", "account.html"):
        html = (ROOT / "templates" / page).read_text(encoding="utf-8")
        assert 'src="/static/js/ai_trading.js?v={{ version }}"' in html, page
