from fastapi.testclient import TestClient

from loki.api import ai_chat
from loki.api.server import app
import pytest


@pytest.fixture(autouse=True)
def reset_limits(monkeypatch):
    monkeypatch.setattr(ai_chat, "_REQUEST_COUNTS", {})


def test_name_alone_never_grants_admin(monkeypatch, tmp_path):
    monkeypatch.setattr(ai_chat, "_DB_DIR", tmp_path)
    monkeypatch.setattr(ai_chat, "_DB_PATH", tmp_path / "chat.db")
    monkeypatch.delenv("LOKI_CHAT_ADMIN_CODE", raising=False)
    with TestClient(app) as client:
        assert (
            client.post("/api/ai/chat/access", json={"name": "joshua mathew"}).json()["admin"]
            is False
        )
        assert client.post("/api/ai/chat/wipe").status_code == 403


def test_rate_limit_and_cookie_tampering(monkeypatch, tmp_path):
    monkeypatch.setattr(ai_chat, "_DB_DIR", tmp_path)
    monkeypatch.setattr(ai_chat, "_DB_PATH", tmp_path / "chat.db")
    signed = ai_chat.encode_chat_cookie("member", False)
    assert ai_chat.decode_chat_cookie(signed.replace('"admin":false', '"admin":true')) is None
    with TestClient(app) as client:
        for _ in range(60):
            assert client.post("/api/ai/chat/logout").status_code == 200
        response = client.post("/api/ai/chat/logout")
        assert response.status_code == 429
        assert response.headers["retry-after"] == "60"


def test_history_isolated_and_cross_site_writes_blocked(monkeypatch, tmp_path):
    monkeypatch.setattr(ai_chat, "_DB_DIR", tmp_path)
    monkeypatch.setattr(ai_chat, "_DB_PATH", tmp_path / "chat.db")
    with TestClient(app) as first, TestClient(app) as second:
        for client in (first, second):
            assert client.post("/api/ai/chat/access", json={"name": "same name"}).status_code == 200
        identity = first.get("/api/ai/chat/whoami").json()
        ai_chat.record_turn("user", "same name", "private message", identity["sid"])
        assert any(
            t["text"] == "private message" for t in first.get("/api/ai/chat/memory").json()["turns"]
        )
        reply = second.get("/api/ai/chat/memory")
        assert not reply.json()["turns"]
        assert "no-store" in reply.headers["cache-control"]
        assert (
            second.post(
                "/api/ai/chat/access",
                json={"name": "other"},
                headers={"Origin": "https://evil.example"},
            ).status_code
            == 403
        )
