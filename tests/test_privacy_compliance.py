"""Privacy, cookies, age confirmation and data minimisation."""

import re
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from loki.api import ai_chat, member_data, site_access
from loki.api.server import app

ROOT = Path(__file__).resolve().parents[1]
UID = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def gated(monkeypatch):
    monkeypatch.setenv("LOKI_SITE_GATE", "1")
    monkeypatch.setenv("LOKI_GATE_SECRET", "privacy-suite-secret")
    monkeypatch.delenv("VERCEL", raising=False)
    return TestClient(app)


class TestAge:
    def test_gate_requires_an_18_plus_confirmation(self, gated):
        no_age = gated.post("/api/gate", json={"code": "flathead", "accepted_terms": True})
        assert no_age.status_code == 403 and "18" in no_age.json()["detail"]
        assert "set-cookie" not in no_age.headers
        ok = gated.post("/api/gate", json={"code": "flathead", "accepted_terms": True, "confirmed_age": True})
        assert ok.status_code == 200

    def test_sign_up_requires_age_and_never_asks_for_birth_date(self, monkeypatch):
        async def create(email, password, nickname):
            return {"id": UID}

        monkeypatch.setattr(site_access, "create_account", create)
        client = TestClient(app)
        body = {"email": "a@b.co", "password": "longenough12", "nickname": "Moon"}
        assert client.post("/api/auth/sign-up", json=body).status_code == 400
        assert client.post("/api/auth/sign-up", json={**body, "age_confirmed": True}).status_code == 200
        assert client.post("/api/auth/sign-up", json={**body, "age_confirmed": True, "birth_date": "2000-01-01"}).status_code == 422
        for page in ("gate.html", "login.html"):
            html = (ROOT / "templates" / page).read_text(encoding="utf-8").lower()
            assert 'type="date"' not in html and "date of birth" not in html


class TestPolicies:
    @pytest.mark.parametrize("path,needles", [
        ("/privacy", ["Privacy Policy", "30 days", "18 or older", "Supabase", "Vercel", "Download my account data", "Delete my account"]),
        ("/cookies", ["Cookie Policy", "loki_gate", "loki_terms", "loki_session", "loki_chat", "loki_tradovate", "no analytics"]),
        ("/terms", ["18 years old", "Hypothetical performance", "/privacy", "/cookies"]),
    ])
    def test_policy_pages_are_public_and_specific(self, gated, path, needles):
        page = gated.get(path)
        assert page.status_code == 200
        for needle in needles:
            assert needle.lower() in page.text.lower(), (path, needle)

    def test_every_cookie_the_code_sets_is_disclosed(self):
        policy = (ROOT / "templates" / "cookies.html").read_text(encoding="utf-8")
        names = set()
        for src in (ROOT / "loki" / "api").glob("*.py"):
            names |= set(re.findall(r'COOKIE(?:_NAME)? = "([a-z_]+)"', src.read_text(encoding="utf-8")))
        names |= set(re.findall(r'COOKIE = "([a-z_]+)"', (ROOT / "core" / "fusion" / "broker_link.py").read_text(encoding="utf-8")))
        assert names and all(name in policy for name in names), names

    def test_terms_version_bumped_so_everyone_re_accepts(self):
        assert site_access.TERMS_VERSION >= 6


class TestMinimisation:
    def test_no_third_party_resources_in_any_page(self):
        for template in (ROOT / "templates").glob("*.html"):
            text = template.read_text(encoding="utf-8")
            for tag in re.findall(r"<(?:script|link|img|iframe)\b[^>]*>", text):
                assert not re.search(r'(src|href)="https?://', tag) or "rel=\"noopener" in tag, (template.name, tag)

    def test_csp_allows_no_external_hosts(self):
        csp = TestClient(app).get("/terms").headers["content-security-policy"]
        assert "https://" not in csp

    def test_chat_turns_expire_after_30_days(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ai_chat, "_DB_DIR", tmp_path)
        monkeypatch.setattr(ai_chat, "_DB_PATH", tmp_path / "memory.sqlite3")
        ai_chat.record_turn("user", "old", "ancient message", session="s")
        with ai_chat._connect() as conn:
            conn.execute("UPDATE turns SET created_at = ?", (time.time() - 31 * 24 * 3600,))
        ai_chat.record_turn("user", "new", "fresh message", session="s")
        texts = [t["text"] for t in ai_chat.recall_turns(10, "s")]
        assert "fresh message" in texts and "ancient message" not in texts


class TestDataRights:
    @pytest.fixture
    def member(self, monkeypatch):
        monkeypatch.setenv("LOKI_GATE_SECRET", "privacy-suite-secret")
        monkeypatch.setenv("LOKI_SITE_GATE", "0")
        calls, deleted_users = [], []
        monkeypatch.setattr(member_data, "database", lambda method, path, body=None, prefer=None: calls.append((method, path)) or
                            ([{"items": {"loki_ai_paper_v1": "{}"}, "updated_at": "x"}] if method == "GET" else []))
        monkeypatch.setattr(member_data, "delete_auth_user", lambda uid: deleted_users.append(uid))
        client = TestClient(app)
        client.cookies.set(site_access.SESSION_COOKIE, site_access.issue_session_cookie_value(UID, "me@example.invalid", "Me"))
        return client, calls, deleted_users

    def test_export_returns_my_data_only(self, member):
        client, calls, _ = member
        res = client.get("/api/account/export")
        assert res.status_code == 200 and "attachment" in res.headers["content-disposition"]
        assert res.json()["account"]["email"] == "me@example.invalid"
        assert all(f"user_id=eq.{UID}" in path for _, path in calls)

    def test_delete_needs_confirmation_and_owner(self, member):
        client, calls, deleted = member
        assert client.post("/api/account/delete", json={"confirm": "yes"}, headers={"X-Workspace-Owner": UID}).status_code == 400
        assert client.post("/api/account/delete", json={"confirm": "DELETE"}, headers={"X-Workspace-Owner": "someone-else"}).status_code == 409
        assert calls == [] and deleted == []
        res = client.post("/api/account/delete", json={"confirm": "DELETE"}, headers={"X-Workspace-Owner": UID})
        assert res.status_code == 200 and deleted == [UID]
        assert {m for m, _ in calls} == {"DELETE"} and all(f"user_id=eq.{UID}" in p for _, p in calls)
        assert "loki_session" in res.headers.get("set-cookie", "")

    def test_anonymous_cannot_export_or_delete(self):
        anon = TestClient(app)
        assert anon.get("/api/account/export").status_code == 401
        assert anon.post("/api/account/delete", json={"confirm": "DELETE"}).status_code == 401
