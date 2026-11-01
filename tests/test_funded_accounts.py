import json
import time

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from core import tradovate
from loki.api import funded, site_access
from loki.api.server import app

OWNER = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
TOKEN = "private-tradovate-token-for-testing"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LOKI_GATE_SECRET", "test-signing-secret")
    monkeypatch.setenv("LOKI_SITE_GATE", "0")
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setenv("LOKI_BROKER_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(tradovate, "snapshot", lambda environment, token: {
        "connected": True, "environment": environment, "accounts": [{"id": 7, "name": "Funded"}],
        "balances": [], "positions": [], "messages": [], "execution_enabled": False,
    })
    with TestClient(app) as c:
        c.cookies.set(site_access.SESSION_COOKIE, site_access.issue_session_cookie_value(OWNER, "owner@example.invalid", "Owner"))
        c.headers["X-Workspace-Owner"] = OWNER
        yield c


def connect(client):
    return client.post("/api/account/funded/connect", json={"environment": "demo", "access_token": TOKEN})


def test_encrypted_connection_survives_requests_without_exposing_token(client):
    response = connect(client)
    assert response.status_code == 200
    assert TOKEN not in response.text and TOKEN not in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    assert "no-store" in response.headers["cache-control"]
    assert client.get("/api/account/funded").json()["connected"] is True
    assert client.post("/api/account/funded/disconnect").status_code == 200
    assert client.get("/api/account/funded").json()["connected"] is False


def test_cross_user_and_stale_owner_never_receive_prior_connection(client):
    assert connect(client).status_code == 200
    client.cookies.set(site_access.SESSION_COOKIE, site_access.issue_session_cookie_value(OTHER, "other@example.invalid", "Other"))
    assert client.get("/api/account/funded").status_code == 409
    client.headers["X-Workspace-Owner"] = OTHER
    assert client.get("/api/account/funded").json()["connected"] is False


def test_guest_and_cross_origin_requests_are_rejected(client):
    assert client.post("/api/account/funded/connect", json={}, headers={"Origin": "https://evil.invalid"}).status_code == 403
    client.cookies.clear()
    assert connect(client).status_code == 401


def test_invalid_credentials_are_not_reflected_and_failed_verification_sets_no_cookie(client, monkeypatch):
    secret = "secret-" * 300
    response = client.post("/api/account/funded/connect", json={"environment": "demo", "access_token": secret})
    assert response.status_code == 422 and secret not in response.text
    assert client.post("/api/account/funded/connect", content="x" * 4097).status_code == 413
    def fail(*args):
        raise tradovate.TradovateError("Account not accessible")
    monkeypatch.setattr(tradovate, "snapshot", fail)
    response = connect(client)
    assert response.status_code == 422 and "set-cookie" not in response.headers


def test_expired_and_tampered_cookies_do_not_connect(client):
    data = {"owner": OWNER, "environment": "demo", "token": TOKEN, "expires": time.time() - 1}
    client.cookies.set(funded.COOKIE, funded.cipher().encrypt(json.dumps(data).encode()).decode(), path=funded.COOKIE_PATH)
    assert client.get("/api/account/funded").json()["connected"] is False
    client.cookies.set(funded.COOKIE, "tampered", path=funded.COOKIE_PATH)
    assert client.get("/api/account/funded").json()["connected"] is False


def test_account_reads_use_fixed_hosts_no_redirects_and_filter_foreign_accounts(monkeypatch):
    calls = []
    payloads = {"account/list": [{"id": 7, "name": "Funded"}],
                "position/list": [{"accountId": 7, "contractId": 10, "netPos": 1}, {"accountId": 999, "netPos": 9}],
                "cashBalance/list": [{"accountId": 7, "currencyId": 1, "amount": 1200}, {"accountId": 999, "amount": 999}]}
    class Reply:
        status_code = 200
        def __init__(self, payload): self.payload = payload
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_content(self, size): yield json.dumps(self.payload).encode()
    def get(url, **kwargs):
        calls.append((url, kwargs))
        return Reply(payloads[url.split('/v1/')[1]])
    monkeypatch.setattr(tradovate.requests, "get", get)
    result = tradovate.snapshot("demo", TOKEN)
    assert len(result["positions"]) == len(result["balances"]) == 1
    assert all(url.startswith(tradovate.HOSTS["demo"]) and not opts["allow_redirects"] for url, opts in calls)
    assert TOKEN not in json.dumps(result)
    with pytest.raises(tradovate.TradovateError):
        tradovate.read("demo", TOKEN, "order/placeorder")


def test_partial_data_failure_is_not_reported_as_empty_positions(monkeypatch):
    def read(environment, token, resource):
        if resource == "account/list": return [{"id": 7, "name": "Funded"}]
        raise tradovate.TradovateError("Read permission unavailable")
    monkeypatch.setattr(tradovate, "read", read)
    result = tradovate.snapshot("demo", TOKEN)
    assert result["connected"] and result["positions"] is None and result["balances"] is None
    assert len(result["messages"]) == 2
