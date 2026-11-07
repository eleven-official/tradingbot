"""Chat survives serverless hosting: read-only code dir and recycled instances."""

from loki.api import ai_chat


def test_unwritable_memory_dir_falls_back_to_temp(monkeypatch, tmp_path):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("file, so mkdir underneath it fails like a read-only deploy")
    fallback = tmp_path / "fallback"
    monkeypatch.setattr(ai_chat, "_DB_DIR", blocker / "ai_chat")
    monkeypatch.setattr(ai_chat, "_DB_PATH", blocker / "ai_chat" / "memory.sqlite3")
    monkeypatch.setattr(ai_chat, "_FALLBACK_DB_DIR", fallback)
    ai_chat.record_turn("user", "tester", "hello", session="s1")
    assert (fallback / "memory.sqlite3").exists()
    assert ai_chat.recall_turns(5, "s1")[-1]["text"] == "hello"


def test_cookie_survives_a_new_process_secret(monkeypatch):
    monkeypatch.setenv("LOKI_CHAT_SESSION_SECRET", "operator-chosen-secret")
    cookie = ai_chat.encode_chat_cookie("tester", False)
    # A cold start draws a new random fallback; the configured secret wins.
    monkeypatch.setattr(ai_chat, "_PROCESS_SECRET", b"x" * 32)
    assert ai_chat.decode_chat_cookie(cookie)["name"] == "tester"


def test_cookie_signed_with_other_secret_is_rejected(monkeypatch):
    monkeypatch.setenv("LOKI_CHAT_SESSION_SECRET", "one")
    cookie = ai_chat.encode_chat_cookie("tester", True)
    monkeypatch.setenv("LOKI_CHAT_SESSION_SECRET", "two")
    assert ai_chat.decode_chat_cookie(cookie) is None
