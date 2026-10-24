"""Adversarial owner-boundary checks for private cloud state and public scores."""
import base64
import json
import time

import pytest
from fastapi.testclient import TestClient

from loki.api import dive_board, member_data, site_access
from loki.api.server import app

A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"


def member(uid):
    client = TestClient(app)
    client.cookies.set(site_access.SESSION_COOKIE, site_access.issue_session_cookie_value(uid, uid + "@example.com", "Same Nickname"))
    client.headers["X-Workspace-Owner"] = uid
    return client


@pytest.fixture
def store(monkeypatch):
    rows = {}
    calls = []

    def database(method, path, body=None, prefer=None):
        calls.append((method, path, body))
        if method == "POST":
            rows[body["user_id"]] = {"items": body["items"], "updated_at": body["updated_at"]}
            return [rows[body["user_id"]]]
        owner = path.split("user_id=eq.")[1].split("&")[0]
        return [rows[owner]] if owner in rows else []

    monkeypatch.setattr(member_data, "database", database)
    return rows, calls


def test_two_accounts_cannot_read_or_overwrite_each_other(store):
    a, b = member(A), member(B)
    assert a.put("/api/account/workspace", json={"items": {"loki.paper-journal.v1": "private A"}}).status_code == 200
    assert b.get("/api/account/workspace?user_id=" + A).json()["items"] == {}
    assert b.put("/api/account/workspace?user_id=" + A, json={"items": {"loki.paper-journal.v1": "private B"}}).status_code == 200
    assert a.get("/api/account/workspace").json()["items"]["loki.paper-journal.v1"] == "private A"
    assert b.get("/api/account/workspace").json()["items"]["loki.paper-journal.v1"] == "private B"
    spoof = b.put("/api/account/workspace", json={"user_id": A, "items": {}})
    assert spoof.status_code == 422


def test_anonymous_and_forged_sessions_never_reach_storage(store):
    anon = TestClient(app)
    for path in ("/api/account/me", "/api/account/workspace"):
        assert anon.get(path).status_code == 401
    anon.cookies.set(site_access.SESSION_COOKIE, site_access.issue_session_cookie_value(A, "a@example.com", "Alice") + "tampered")
    assert anon.get("/api/account/workspace").status_code == 401
    assert not store[1]


def test_cross_origin_write_is_refused_before_database(store):
    response = member(A).put("/api/account/workspace", headers={"Origin": "https://attacker.example"}, json={"items": {}})
    assert response.status_code == 403
    assert not store[1]


def test_stale_tab_cannot_save_or_restore_new_accounts_workspace(store):
    client = member(B)
    client.headers["X-Workspace-Owner"] = A
    assert client.put("/api/account/workspace", json={"items": {}}).status_code == 409
    assert client.get("/api/account/workspace").status_code == 409
    assert not store[1]


def test_private_data_never_cacheable_and_credentials_not_savable(store):
    client = member(A)
    assert "no-store" in client.get("/api/account/workspace").headers["cache-control"]
    assert "no-store" in client.get("/api/auth/session").headers["cache-control"]
    assert client.put("/api/account/workspace", json={"items": {"loki_alpaca_keys_v1": "secret"}}).status_code == 400
    assert client.put("/api/account/workspace", json={"items": {"loki_dive_best": "x" * 500001}}).status_code == 413
    assert not store[1][1:]


def test_score_ownership_comes_from_session_not_body(monkeypatch):
    monkeypatch.setattr(dive_board, "board_mode", lambda: "shared")
    monkeypatch.setattr(dive_board, "_WRITES", {})
    calls = []
    def publish(uid, nickname, best):
        calls.append((uid, nickname, best))
        return {"best": best}
    monkeypatch.setattr(dive_board, "shared_write", publish)
    assert TestClient(app).post("/api/dive/score", json={"nickname": "Victim", "best": 200}).status_code == 401
    for uid in (A, B):
        assert member(uid).post("/api/dive/score", json={"nickname": "Victim", "user_id": A, "best": 200}).status_code == 200
    assert calls == [(A, "Same Nickname", 200), (B, "Same Nickname", 200)]


def test_public_board_explicitly_excludes_private_columns(monkeypatch):
    class Reply:
        status_code = 200
        def json(self):
            return [{"nickname": "Player", "best_score": 3, "dives": 1, "user_id": A, "email": "secret@example.com", "items": {"private": "journal"}}]
    monkeypatch.setattr(dive_board, "_supa_send", lambda *args, **kwargs: Reply())
    row = dive_board._shared_read()["entries"][0]
    assert set(row) == {"nickname", "best", "dives", "updated_at"}


def test_expired_future_and_malformed_signed_sessions_rejected():
    assert site_access.read_session_cookie_value("payload.é") is None
    assert site_access.verify_gate_cookie_value("payload.é") is False
    assert site_access.read_terms_cookie_value("payload.é") == 0
    for stamp in (time.time() - site_access.SESSION_MAX_AGE - 10, time.time() + 3600, "garbage", None):
        payload = base64.urlsafe_b64encode(json.dumps({"uid": A, "email": "a@example.com", "nickname": "Alice", "iat": stamp}).encode()).decode()
        assert site_access.read_session_cookie_value(payload + "." + site_access._sign(payload)) is None


def test_login_cookie_is_httponly(monkeypatch):
    async def signin(email, password):
        return {"id": A, "user_metadata": {"nickname": "Alice"}}
    monkeypatch.setattr(site_access, "sign_in_with_password", signin)
    response = TestClient(app).post("/api/auth/login", json={"email": "a@example.com", "password": "longpassword"})
    assert response.status_code == 200
    assert "httponly" in response.headers["set-cookie"].lower()
    upgrade = member(A).get("/api/auth/session")
    assert "httponly" in upgrade.headers["set-cookie"].lower()
