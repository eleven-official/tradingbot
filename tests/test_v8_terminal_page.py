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


def test_terminal_assets_and_engine_route_exist():
    assert (ROOT / "static" / "css" / "v8_terminal.css").exists()
    engine = (ROOT / "loki" / "api" / "terminal_v8.py").read_text(encoding="utf-8")
    assert '@app.post("/api/bot/autonomous")' in engine
    assert '@app.get("/api/bot/autonomous")' in engine
