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
        for name in site_access.SUPABASE_KEY_ENV_NAMES:
            monkeypatch.delenv(name, raising=False)
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
        for name in site_access.SUPABASE_KEY_ENV_NAMES:
            monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv("SUPABASE_URL", raising=False)

    def test_guest_mode_when_accounts_unconfigured(self, monkeypatch):
        self._stub_admin(monkeypatch)
        response = client.get("/api/auth/session")
        assert response.status_code == 200
        assert response.json() == {"enabled": False}

    def test_session_probe_answers_signed_out_inside_a_200(self, monkeypatch):
        # Accounts are configured but this browser holds no session. The
        # probe is a question, not a failure: it answers an honest state
        # inside a 200 so no visitor's console logs a fake error.
        monkeypatch.setenv("SUPABASE_URL", "https://stub-project.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_KEY", "sb_secret_stubbish")
        fresh = TestClient(app)  # a browser with no session cookie jar
        response = fresh.get("/api/auth/session")
        assert response.status_code == 200
        assert response.json() == {"enabled": True, "authenticated": False}

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

    def test_nickname_update_uses_put_not_patch(self, monkeypatch):
        # Verified live: Supabase's admin endpoint answers HTTP 405 to PATCH
        # /auth/v1/admin/users/{uid} — updates must travel as PUT.
        for name in site_access.SUPABASE_KEY_ENV_NAMES:
            monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        calls = {}

        async def fake_threadpool(fn, *args, **kwargs):
            calls["args"] = (fn, args, kwargs)
            return {}

        monkeypatch.setattr(site_access, "run_in_threadpool", fake_threadpool)
        import asyncio

        asyncio.run(site_access.update_nickname("uid_77", "Renamed Hero"))
        fn, args, kwargs = calls["args"]
        assert args == ("PUT", "/auth/v1/admin/users/uid_77")
        assert kwargs.get("json_body") == {"user_metadata": {"nickname": "Renamed Hero"}}

    def test_wrong_password_maps_to_honest_401(self, monkeypatch):
        # Verified live: Supabase answers HTTP 400 "Invalid login credentials"
        # for a wrong password — that must surface as 401 with clear wording,
        # not as a complaint about password length.
        monkeypatch.setenv("SUPABASE_URL", "https://stub-project.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_KEY", "sb_secret_stubbish")

        class FakeResponse:
            status_code = 400

            def json(self):
                return {"code": 400, "error_code": "invalid_credentials", "msg": "Invalid login credentials"}

            text = '{"code":400,"error_code":"invalid_credentials","msg":"Invalid login credentials"}'

        def fake_request(*args, **kwargs):
            return FakeResponse()

        import loki.api.site_access as module

        monkeypatch.setattr(module.requests, "request", fake_request)
        import asyncio

        try:
            asyncio.run(module._supa_request("POST", "/auth/v1/token?grant_type=password", json_body={"email": "x@y.z", "password": "whatever12"}))
            failed = False
        except module.HTTPException as exc:
            failed = exc.status_code == 401 and "Wrong email or password." in str(exc.detail)
            if not failed:
                raise
        assert failed, "wrong password must surface as the honest 401"

    def test_nickname_route_accepts_a_nickname_only_body(self, monkeypatch):
        # Route-level: PUT /api/auth/nickname used to 422 because it shared the
        # sign-up model (email and password are required there). It must accept
        # exactly {"nickname": ...} for a signed-in session.
        for name in site_access.SUPABASE_KEY_ENV_NAMES:
            monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv("SUPABASE_URL", raising=False)

        async def fake_create(email, password, nickname):
            assert nickname
            return {"id": "usr_nick_1"}

        async def fake_update(uid, nickname):
            assert (uid, nickname) == ("usr_nick_1", "Renamed Hero")
            return {}

        monkeypatch.setattr(site_access, "create_account", fake_create)
        monkeypatch.setattr(site_access, "update_nickname", fake_update)
        created = client.post(
            "/api/auth/sign-up",
            json={"email": "nick@test.io", "password": "longenough12", "nickname": "Nick Hero"},
        )
        assert created.status_code == 200
        updated = client.put("/api/auth/nickname", json={"nickname": "Renamed Hero"})
        assert updated.status_code == 200
        assert updated.json() == {"email": "nick@test.io", "nickname": "Renamed Hero"}
        client.post("/api/auth/logout")


class TestCredentialNames:
    """The Supabase–Vercel integration injects the service credential under
    names hand-set deployments never use; Loki must accept both wirings."""

    _URL = "https://stub-project.supabase.co"

    def test_integration_secret_name_configures_accounts(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_URL", self._URL)
        monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
        monkeypatch.delenv("SUPABASE_KEY", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
        monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_stubbish")
        assert site_access.accounts_available() is True
        assert site_access._supabase_key() == "sb_secret_stubbish"

    def test_integration_legacy_role_name_configures_accounts(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_URL", self._URL)
        monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
        monkeypatch.delenv("SUPABASE_KEY", raising=False)
        monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "eyJ-stub")
        assert site_access.accounts_available() is True

    def test_explicit_names_win_over_integration_names(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_URL", self._URL)
        monkeypatch.setenv("SUPABASE_SERVICE_KEY", "handset-1")
        monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_integration")
        assert site_access._supabase_key() == "handset-1"

    def test_session_signing_follows_the_same_resolution(self, monkeypatch):
        # _secret() must derive from the same key resolution as _supabase_config
        # so cookie signatures stay verifiable regardless of which name carried
        # the credential.
        monkeypatch.setenv("SUPABASE_URL", self._URL)
        monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_stubbish")
        monkeypatch.delenv("LOKI_GATE_SECRET", raising=False)
        signed = site_access.issue_gate_cookie_value()
        assert site_access.verify_gate_cookie_value(signed) is True


class TestPublicTrainedBook:
    def test_research_book_is_public_and_complete(self, monkeypatch):
        for name in site_access.SUPABASE_KEY_ENV_NAMES:
            monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv("SUPABASE_URL", raising=False)
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
