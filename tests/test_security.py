"""Security hardening: isolation between users, unforgeable cookies, limits, headers."""

import base64
import hashlib
import hmac
import json
import re
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from loki.api import ai_chat, member_data, rate_limit, site_access
from loki.api.server import app

ROOT = Path(__file__).resolve().parents[1]
ALICE = "11111111-1111-4111-8111-111111111111"
BOB = "22222222-2222-4222-8222-222222222222"


@pytest.fixture
def signed_in(monkeypatch):
    monkeypatch.setenv("LOKI_GATE_SECRET", "test-signing-secret-for-security-suite")
    monkeypatch.setenv("LOKI_SITE_GATE", "0")
    monkeypatch.delenv("VERCEL", raising=False)
    calls = []

    def fake_database(method, path, body=None, prefer=None):
        calls.append((method, path, body))
        if method == "GET":
            return [{"items": {"loki_ai_paper_v1": "{}"}, "updated_at": "2026-11-07T00:00:00Z"}]
        return [{"updated_at": "2026-11-07T00:00:00Z"}]

    monkeypatch.setattr(member_data, "database", fake_database)
    client = TestClient(app)
    client.cookies.set(site_access.SESSION_COOKIE, site_access.issue_session_cookie_value(ALICE, "alice@example.invalid", "Alice"))
    return client, calls


class TestUserIsolation:
    def test_reads_and_writes_only_ever_touch_the_signed_in_account(self, signed_in):
        client, calls = signed_in
        assert client.get("/api/account/workspace", headers={"X-Workspace-Owner": ALICE}).status_code == 200
        assert client.put("/api/account/workspace", headers={"X-Workspace-Owner": ALICE},
                          json={"items": {"loki_ai_paper_v1": "{}"}}).status_code == 200
        assert all(BOB not in json.dumps(c) for c in calls)
        assert f"user_id=eq.{ALICE}" in calls[0][1]
        assert calls[1][2]["user_id"] == ALICE

    def test_naming_another_user_is_refused_before_the_database(self, signed_in):
        client, calls = signed_in
        assert client.get("/api/account/workspace", headers={"X-Workspace-Owner": BOB}).status_code == 409
        assert client.put("/api/account/workspace", headers={"X-Workspace-Owner": BOB},
                          json={"items": {"loki_ai_paper_v1": "{}"}}).status_code == 409
        assert calls == []

    def test_no_session_means_no_data(self, monkeypatch):
        monkeypatch.setattr(member_data, "database", lambda *a, **k: pytest.fail("database must not be reached"))
        anon = TestClient(app)
        assert anon.get("/api/account/workspace").status_code == 401
        assert anon.get("/api/account/me").status_code == 401

    def test_tampered_session_cookie_is_rejected(self, monkeypatch):
        monkeypatch.setenv("LOKI_GATE_SECRET", "test-signing-secret-for-security-suite")
        good = site_access.issue_session_cookie_value(ALICE, "alice@example.invalid", "Alice")
        payload, sig = good.rsplit(".", 1)
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        data["uid"] = BOB
        forged = base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=") + "." + sig
        assert site_access.read_session_cookie_value(forged) is None

    def test_credentials_can_never_be_saved_to_the_cloud(self, signed_in):
        client, calls = signed_in
        bad = client.put("/api/account/workspace", headers={"X-Workspace-Owner": ALICE},
                         json={"items": {"alpaca_keys": "secret"}})
        assert bad.status_code == 400 and calls == []

    def test_chat_history_is_per_browser_session(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ai_chat, "_DB_DIR", tmp_path)
        monkeypatch.setattr(ai_chat, "_DB_PATH", tmp_path / "memory.sqlite3")
        a, b = TestClient(app), TestClient(app)
        a.post("/api/ai/chat/access", json={"name": "Alice", "code": ""})
        b.post("/api/ai/chat/access", json={"name": "Bob", "code": ""})
        a.post("/api/ai/chat/message", json={"text": "my private note about AAPL"})
        turns = b.get("/api/ai/chat/memory").json()["turns"]
        assert all("private note" not in t["text"] for t in turns)


class TestUnforgeableCookies:
    def test_public_deployment_without_secrets_fails_closed(self, monkeypatch):
        for name in ("LOKI_GATE_SECRET", "VERCEL", *site_access.SUPABASE_KEY_ENV_NAMES):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv("LOKI_SITE_GATE", "1")
        dev_constant = hashlib.sha256(site_access._COOKIE_SALT + b"loki-local-dev-gate").digest()
        assert site_access._secret() != dev_constant
        # A gate badge forged with the public constant does not open the door.
        payload = str(int(time.time()) + 3600)
        forged = payload + "." + hmac.new(dev_constant, payload.encode(), hashlib.sha256).hexdigest()
        assert site_access.verify_gate_cookie_value(forged) is False

    def test_chat_admin_cannot_be_forged_without_a_configured_secret(self, monkeypatch):
        for name in ("LOKI_GATE_SECRET", "LOKI_CHAT_SESSION_SECRET", "VERCEL", *site_access.SUPABASE_KEY_ENV_NAMES):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv("LOKI_SITE_GATE", raising=False)
        payload = json.dumps({"name": "joshua mathew", "admin": True, "sid": "x" * 48, "iat": int(time.time())},
                             separators=(",", ":"))
        dev_key = hmac.new(hashlib.sha256(site_access._COOKIE_SALT + b"loki-local-dev-gate").digest(),
                           b"loki-chat-session", hashlib.sha256).digest()
        forged = payload + "." + hmac.new(ai_chat._COOKIE_SALT + dev_key, payload.encode(), hashlib.sha256).hexdigest()
        assert ai_chat.decode_chat_cookie(forged) is None

    def test_cookies_are_secure_behind_https(self, monkeypatch):
        monkeypatch.delenv("VERCEL", raising=False)
        monkeypatch.delenv("LOKI_SECURE_COOKIES", raising=False)
        https = SimpleNamespace(url=SimpleNamespace(scheme="https"), headers={})
        http = SimpleNamespace(url=SimpleNamespace(scheme="http"), headers={})
        assert site_access.cookie_secure(https) is True
        assert site_access.cookie_secure(http) is False
        monkeypatch.setenv("LOKI_SECURE_COOKIES", "1")
        assert site_access.cookie_secure(http) is True


class TestRateLimits:
    @pytest.fixture(autouse=True)
    def limits_on(self, monkeypatch):
        monkeypatch.setenv("LOKI_RATE_LIMITS", "1")
        rate_limit.reset()
        yield
        rate_limit.reset()

    def test_password_guessing_is_throttled(self, monkeypatch):
        async def refuse(email, password):
            raise HTTPException(401, "Wrong email or password.")

        monkeypatch.setattr(site_access, "sign_in_with_password", refuse)
        client = TestClient(app)
        codes = [client.post("/api/auth/login", json={"email": "a@b.co", "password": "guess-1234"}).status_code
                 for _ in range(12)]
        assert codes[:10] == [401] * 10
        assert codes[10] == 429

    def test_operator_key_guessing_is_throttled(self, monkeypatch):
        monkeypatch.setenv("LOKI_REVENUE_KEY", "the-real-operator-key")
        client = TestClient(app)
        codes = [client.get("/api/revenue/statement", headers={"X-Operator-Key": f"guess{i}"}).status_code
                 for i in range(22)]
        assert 429 in codes and codes.count(403) == 20

    def test_spoofed_forwarded_for_does_not_reset_the_limit(self, monkeypatch):
        monkeypatch.delenv("VERCEL", raising=False)
        request = SimpleNamespace(headers={"x-forwarded-for": "9.9.9.9"}, client=SimpleNamespace(host="1.2.3.4"))
        assert rate_limit.client_key(request) == "1.2.3.4"


class TestHeadersAndScripts:
    def test_security_headers_on_every_page(self):
        response = TestClient(app).get("/terms")
        csp = response.headers["content-security-policy"]
        assert "script-src 'self'" in csp and "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0]
        assert "frame-ancestors 'self'" in csp and "object-src 'none'" in csp
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "SAMEORIGIN"
        assert "camera=()" in response.headers["permissions-policy"]

    def test_no_template_contains_inline_script(self):
        for template in (ROOT / "templates").glob("*.html"):
            text = template.read_text(encoding="utf-8")
            for tag in re.findall(r"<script\b[^>]*>", text):
                assert "src=" in tag, f"inline script in {template.name}: {tag}"
            assert not re.search(r"\son(click|load|error|submit|change|input|mouseover)\s*=", text), template.name
