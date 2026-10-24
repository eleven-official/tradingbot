"""Behavioral wiring checks for the built-in advanced-terminal page.

The page is intentionally honest when no launcher session token exists;
these structural tests pin the polite-retry behavior that a plain browser
proof hit: backoff instead of a 403 storm, a banner that names the real
reason, and console noise that does not repeat on every cycle.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source() -> str:
    return (ROOT / "templates" / "v8_terminal.html").read_text(encoding="utf-8")


def test_status_polls_back_off_instead_of_storming():
    js = source()
    assert "let statusFailures = 0;" in js
    assert "let autoFailures = 0;" in js
    # The schedule function: 10s normally, 30s after three straight failures.
    assert "statusFailures >= 3 ? 30000 : 10000" in js
    assert "(function statusLoop() {" in js


def test_console_noise_is_throttled():
    js = source()
    assert "if (statusFailures === 1 || statusFailures % 5 === 0) console.error('Status fetch error:', e);" in js
    assert "if (autoFailures === 1 || autoFailures % 5 === 0) console.error('Auto status error:', e);" in js


def test_offline_banner_names_the_launcher_reason():
    js = source()
    # setConnection accepts the failure detail and rewrites the banner.
    assert "function setConnection(ok, detail)" in js
    assert "needs the local Loki launcher and its session token" in js
    assert "Polling continues, politely spaced" in js


def test_paper_loop_button_admits_the_lock_instead_of_silently_failing():
    js = source()
    assert "function setAutoLocked" in js
    assert "LAUNCHER REQUIRED" in js
    assert "btn.disabled = false;" in js  # a launcher arriving restores control
    assert "setAutoLocked(String(e && e.message || e));" in js  # status-failure path


def test_offline_banner_offers_the_working_browser_runner():
    js = source()
    assert "offline-banner-cta" in js
    assert "cta.href = '/#ai'" in js
    assert "Open the browser AI runner" in js


def test_real_account_button_leaves_for_the_workspace_view():
    js = source()
    assert "window.top.location.assign('/#real-market')" in js


def test_kpi_cards_do_not_advertise_engine_numbers_without_an_engine():
    html = source()
    assert "$100,000.00" not in html  # invented default removed
    assert '<span class="brand-badge">LIVE</span>' not in html  # paper-only page


def test_terminal_assets_and_engine_route_exist():
    assert (ROOT / "static" / "css" / "v8_terminal.css").exists()
    engine = (ROOT / "loki" / "api" / "terminal_v8.py").read_text(encoding="utf-8")
    assert '@app.post("/api/bot/autonomous")' in engine
    assert '@app.get("/api/bot/autonomous")' in engine


def test_notice_strip_is_themed_prose_not_an_inline_blob():
    html = source()
    # the honesty strip carries real classes and the exact same copy
    assert '<div class="notice-strip">' in html
    assert "Advanced paper engine" in html
    assert "a 70% trade win rate is unproven" in html
    assert 'style="padding:12px 24px' not in html  # no glued-on styling
    css = (ROOT / "static" / "css" / "v8_terminal.css").read_text(encoding="utf-8")
    assert ".notice-strip {" in css
    assert "var(--text-muted)" in css


def test_brand_tile_is_the_loki_letter_and_assets_are_versioned():
    html = source()
    assert 'class="brand-logo" aria-hidden="true">L<' in html
    assert 'href="/favicon.ico?v={{ version }}"' in html
    assert 'href="/static/css/v8_terminal.css?v={{ version }}"' in html
    css = (ROOT / "static" / "css" / "v8_terminal.css").read_text(encoding="utf-8")
    assert "font-family: var(--font-mono)" in css.split(".brand-logo {", 1)[1][:400]
