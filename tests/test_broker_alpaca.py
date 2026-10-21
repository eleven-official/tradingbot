"""Alpaca paper relay: gate-only access, browser-held keys, honest error maps.

The relay must never invent account facts, never reach the network for badly
shaped keys, touch only Alpaca's PAPER endpoint with the caller's credentials,
and surface Alpaca's own rejections as plain human messages. The keys must
also stay out of the workspace backup export entirely.
"""

import json
import urllib.error
from pathlib import Path

from fastapi.testclient import TestClient

import loki.api.broker_alpaca as module
from loki.api.server import app

ROOT = Path(__file__).resolve().parents[1]

client = TestClient(app)

KEYS = {
    "key_id": "PKTESTKEY123456",
    "secret_key": "abcdefghij0123456789abcdefghij0123456789",
}

ACCOUNT_PAYLOAD = {
    "id": "e0f9secret-identity-value",
    "contact_email": "someone@alpaca.invalid",
    "status": "ACTIVE",
    "account_number": "PA0001XYZ9",
    "currency": "USD",
    "cash": "100000.505",
    "equity": 120000.333,
    "buying_power": "400000",
    "trading_blocked": False,
    "account_blocked": False,
    "pattern_day_trader": False,
}


class FakeResponse:
    def __init__(self, raw: bytes):
        self._raw = raw

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _deferred(assert_later):
    """Return a fake urlopen that always records and never fires locally."""
    def fake(request, timeout=None):
        assert_later["request"] = request
        return FakeResponse(json.dumps(ACCOUNT_PAYLOAD).encode())
    return fake


class TestRelayAccess:
    def test_relay_requires_the_access_door(self, monkeypatch):
        fresh = TestClient(app)
        response = fresh.post("/api/broker/alpaca/test", json=KEYS)
        assert response.status_code == 403
        assert "access door" in response.json()["detail"]


class TestRelay:
    def gate(self):
        opened = client.post("/api/gate", json={"code": "flathead"})
        assert opened.status_code == 200

    def test_bad_key_shapes_never_reach_the_network(self, monkeypatch):
        self.gate()
        attempts = {"n": 0}

        def forbidden(*args, **kwargs):
            attempts["n"] += 1
            raise AssertionError("badly shaped keys must be refused before any network hop")

        monkeypatch.setattr(module.urllib.request, "urlopen", forbidden)
        assert client.post("/api/broker/alpaca/test", json={**KEYS, "key_id": "short"}).status_code == 422
        assert client.post(
            "/api/broker/alpaca/test",
            json={**KEYS, "secret_key": "tooshort"},
        ).status_code == 422
        assert client.post("/api/broker/alpaca/test", json={"key_id": "okokayok1!2"}).status_code == 422
        assert attempts["n"] == 0

    def test_valid_keys_reach_the_paper_endpoint_with_credential_headers(self, monkeypatch):
        self.gate()
        later = {}

        def fake(request, timeout=None):
            later["request"] = request
            return FakeResponse(json.dumps(ACCOUNT_PAYLOAD).encode())

        monkeypatch.setattr(module.urllib.request, "urlopen", fake)
        response = client.post("/api/broker/alpaca/test", json=KEYS)
        assert response.status_code == 200
        assert response.json() == {"ok": True, "account_status": "ACTIVE", "paper": True}
        request = later["request"]
        assert request.full_url == "https://paper-api.alpaca.markets/v2/account"
        headers = {name.lower(): value for name, value in request.header_items()}
        assert headers.get("apca-api-key-id") == KEYS["key_id"]
        assert headers.get("apca-api-secret-key") == KEYS["secret_key"]
        assert "lokiworkspace" in (headers.get("user-agent") or "").lower()

    def test_account_view_whitelists_what_leaves_the_relay(self, monkeypatch):
        self.gate()
        later = {}
        monkeypatch.setattr(module.urllib.request, "urlopen", _deferred(later))
        response = client.post("/api/broker/alpaca/account", json=KEYS)
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {
            "paper",
            "status",
            "account_number",
            "currency",
            "cash",
            "equity",
            "buying_power",
            "trading_blocked",
            "account_blocked",
        }
        assert body["paper"] is True
        assert body["cash"] == 100000.51  # relay rounds to cents (0.505 floats above)
        assert body["equity"] == 120000.33
        assert body["account_number"] == "01XYZ9"  # masked to the tail: no full identity
        assert "contact_email" not in body
        assert "id" not in body

    def test_rejected_keys_answer_honestly_as_401(self, monkeypatch):
        self.gate()

        def fake(request, timeout=None):
            raise urllib.error.HTTPError("https://paper-api.alpaca.markets/v2/account", 401, "no", None, None)

        monkeypatch.setattr(module.urllib.request, "urlopen", fake)
        response = client.post("/api/broker/alpaca/test", json=KEYS)
        assert response.status_code == 401
        assert "rejected those keys" in response.json()["detail"]

    def test_unreachable_alpaca_answers_503_not_a_fake_success(self, monkeypatch):
        self.gate()

        def fake(request, timeout=None):
            raise urllib.error.URLError(OSError("no route to host"))

        monkeypatch.setattr(module.urllib.request, "urlopen", fake)
        response = client.post("/api/broker/alpaca/test", json=KEYS)
        assert response.status_code == 503
        assert "unreachable" in response.json()["detail"]

    def test_unparseable_answer_answers_502(self, monkeypatch):
        self.gate()

        def fake(request, timeout=None):
            return FakeResponse(b'<<"nope"')

        monkeypatch.setattr(module.urllib.request, "urlopen", fake)
        response = client.post("/api/broker/alpaca/test", json=KEYS)
        assert response.status_code == 502
        assert "could not parse" in response.json()["detail"]

    def test_rate_limit_maps_to_503_with_patience(self, monkeypatch):
        self.gate()

        def fake(request, timeout=None):
            raise urllib.error.HTTPError("https://paper-api.alpaca.markets/v2/account", 429, "slow", None, None)

        monkeypatch.setattr(module.urllib.request, "urlopen", fake)
        response = client.post("/api/broker/alpaca/test", json=KEYS)
        assert response.status_code == 503
        assert "rate-limiting" in response.json()["detail"]


class TestSiteHygiene:
    def test_backup_export_excludes_alpaca_keys(self):
        source = (ROOT / "static" / "js" / "backup.js").read_text(encoding="utf-8")
        assert "loki_alpaca" not in source, "live API keys must never ride the backup export"

    def test_panel_script_and_router_are_wired(self):
        index = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        assert 'id="alpaca-keys-form"' in index
        assert "static/js/alpaca_keys.js" in index
        server = (ROOT / "loki" / "api" / "server.py").read_text(encoding="utf-8")
        assert "broker_alpaca_router" in server
