"""Site access gate + personalized accounts + public trained book.

The deployed site asks for an access code before it opens, then for an
email/password account with a nickname. These tests cover the flow without
any network access (Supabase calls are stubbed).
"""

from fastapi.testclient import TestClient

from loki.api import site_access
from loki.api.server import app

client = TestClient(app)
client_nofollow = TestClient(app, follow_redirects=False)


class TestAccessCode:
    def test_default_code(self, monkeypatch):
        monkeypatch.delenv("LOKI_SITE_CODE", raising=False)
        assert site_access.code_matches("flat head")
        assert site_access.code_matches("flathead")
        assert site_access.code_matches("flathead")
        assert site_access.code_matches("  FLAT HEAD  ")
        assert site_access.code_matches("flat, head!")
        assert site_access.code_matches("flat-head")
        assert not site_access.code_matches("flat hed")
        assert not site_access.code_matches("")

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("LOKI_SITE_CODE", "pineapple")
        assert site_access.code_matches("Pineapple")
        assert not site_access.code_matches("flat head")

    def test_nicknames(self, monkeypatch):
        monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
        monkeypatch.delenv("SUPABASE_KEY", raising=False)
        assert site_access.clean_nickname("Moon Runner") == "Moon Runner"
        assert site_access.clean_nickname("  moon-runner_2 ") == "moon-runner_2"
        assert site_access.clean_nickname("x") == ""
        assert site_access.clean_nickname("bad nick!name") == ""
        assert site_access.clean_nickname("x" * 30) == ""


class TestGateFlow:
    def test_locked_pages_redirect_without_cookie(self, monkeypatch):
        monkeypatch.setenv("VERCEL", "1")
        for path in ("/", "/terminal/", "/paper-tools", "/login"):
            response = client_nofollow.get(path)
            assert response.status_code == 303, path
            assert response.headers["location"] == "/gate", path

    def test_gate_endpoints_stay_open_without_cookie(self, monkeypatch):
        monkeypatch.setenv("VERCEL", "1")
        assert client_nofollow.get("/gate").status_code == 200
        assert client_nofollow.get("/health").status_code == 200
        assert client_nofollow.get("/static/js/loki_auth.js").status_code == 200

    def test_wrong_code_rejected_right_code_opens(self, monkeypatch):
        monkeypatch.setenv("VERCEL", "1")
        rejected = client.post("/api/gate", json={"code": "chocolate"})
        assert rejected.status_code == 403

        accepted = client.post("/api/gate", json={"code": "flat head"})
        assert accepted.status_code == 200
        cookie = accepted.cookies.get(site_access.GATE_COOKIE)
        assert cookie and site_access.verify_gate_cookie_value(cookie)

        opened = client_nofollow.get("/", cookies={site_access.GATE_COOKIE: cookie})
        assert opened.status_code == 200

        still_locked_for_login = client_nofollow.get(
            "/login", cookies={site_access.GATE_COOKIE: cookie}
        )
        assert still_locked_for_login.status_code == 200

    def test_gate_disabled_locally(self, monkeypatch):
        monkeypatch.delenv("VERCEL", raising=False)
        monkeypatch.delenv("LOKI_SITE_GATE", raising=False)
        assert client_nofollow.get("/").status_code == 200


class TestGateThrottle:
    def test_repeated_failures_get_throttled_then_success_clears(self, monkeypatch):
        monkeypatch.setenv("VERCEL", "1")
        monkeypatch.setattr(site_access, "_GATE_ATTEMPTS", {})
        for _ in range(10):
            assert client.post("/api/gate", json={"code": "nope"}).status_code == 403
        throttled = client.post("/api/gate", json={"code": "flat head"})
        assert throttled.status_code == 429

        monkeypatch.setattr(site_access, "_GATE_ATTEMPTS", {})
        assert client.post("/api/gate", json={"code": "nope"}).status_code == 403
        accepted = client.post("/api/gate", json={"code": "flat head"})
        assert accepted.status_code == 200
        # A correct code clears the failure record for that client.
        assert site_access._GATE_ATTEMPTS.get("testclient") in (None, [])


class TestAccounts:
    def _stub_admin(self, monkeypatch):
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
        monkeypatch.delenv("SUPABASE_KEY", raising=False)

    def test_guest_mode_when_accounts_unconfigured(self, monkeypatch):
        self._stub_admin(monkeypatch)
        response = client.get("/api/auth/session")
        assert response.status_code == 200
        assert response.json() == {"enabled": False}

    def test_sign_up_sets_personalized_session(self, monkeypatch):
        self._stub_admin(monkeypatch)

        async def fake_create(email, password, nickname):
            assert nickname
            return {"id": "usr_42"}

        monkeypatch.setattr(site_access, "create_account", fake_create)
        response = client.post(
            "/api/auth/sign-up",
            json={"email": "moon@test.io", "password": "longenough12", "nickname": "Moon Runner"},
        )
        assert response.status_code == 200
        assert response.json() == {"email": "moon@test.io", "nickname": "Moon Runner"}

        session = client.get("/api/auth/session")
        assert session.status_code == 200
        assert session.json()["enabled"] is True
        assert session.json()["nickname"] == "Moon Runner"

    def test_sign_in_uses_stored_nickname(self, monkeypatch):
        self._stub_admin(monkeypatch)

        async def fake_grant(email, password):
            return {"id": "usr_42", "user_metadata": {"nickname": "Old Nick"}}

        monkeypatch.setattr(site_access, "sign_in_with_password", fake_grant)
        response = client.post(
            "/api/auth/login",
            json={"email": "moon@test.io", "password": "longenough12"},
        )
        assert response.status_code == 200
        assert response.json() == {"email": "moon@test.io", "nickname": "Old Nick"}

    def test_logout_clears_session(self, monkeypatch):
        response = client.post("/api/auth/logout")
        assert response.status_code == 200
        assert "session" in response.text or response.json() == {"ok": True}

    def test_sign_up_rejects_bad_nickname_and_short_password(self, monkeypatch):
        self._stub_admin(monkeypatch)
        short = client.post(
            "/api/auth/sign-up",
            json={"email": "moon@test.io", "password": "short", "nickname": "Moon Runner"},
        )
        assert short.status_code == 422

        bad = client.post(
            "/api/auth/sign-up",
            json={"email": "moon@test.io", "password": "longenough12", "nickname": "bad!name"},
        )
        assert bad.status_code == 400


class TestPublicTrainedBook:
    def test_research_book_is_public_and_complete(self, monkeypatch):
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
        response = client.get("/api/fusion/research-book")
        assert response.status_code == 200
        book = response.json()
        symbols = {entry["symbol"] for entry in book["symbols"]}
        assert {"SPY", "QQQ", "BTC-USD", "AAPL", "ETH-USD"} <= symbols
        spy = next(entry for entry in book["symbols"] if entry["symbol"] == "SPY")
        assert spy["win_rate_pct"] >= 90
        assert spy["final_holdout"]["win_rate_pct"] >= 90

    def test_no_launcher_token_in_public_book(self):
        response = client.get("/api/fusion/research-book")
        assert "local_token" not in response.json()
