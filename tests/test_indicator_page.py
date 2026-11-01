"""The /indicator page: gated access, rendered source, copy affordances."""

from fastapi.testclient import TestClient

from loki.api import site_access
from loki.api.server import app

client = TestClient(app)
client_nofollow = TestClient(app, follow_redirects=False)


def _open_gate(browser):
    code = site_access.expected_code()
    opened = browser.post(
        "/api/gate", json={"code": code, "accepted_terms": True}
    )
    assert opened.status_code == 200
    return opened


def test_indicator_page_serves_pine_source_when_gate_is_off(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("LOKI_SITE_GATE", raising=False)
    response = client.get("/indicator")
    assert response.status_code == 200
    body = response.text
    assert "Pine Editor" in body
    assert "indicator(" in body
    assert "Lorentz" in body or "Lorentz-distance" in body
    assert "sha256 " in body  # hash shown so members can verify the paste


def test_indicator_page_is_gated_on_remote_deployments(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    blocked = client_nofollow.get("/indicator")
    assert blocked.status_code == 303
    assert blocked.headers["location"] == "/gate"
    in_page = client.get("/gate")
    assert in_page.status_code == 200


def test_wrong_code_does_not_open_the_indicator_page(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    denied = client.post("/api/gate", json={"code": "wrong-code", "accepted_terms": True})
    assert denied.status_code == 403
    assert client_nofollow.get("/indicator").status_code == 303


def test_gate_code_plus_terms_opens_the_indicator_page(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    # https client so secure gate cookies (set when VERCEL is on) circulate
    browser = TestClient(app, base_url="https://testserver")
    _open_gate(browser)
    response = browser.get("/indicator")
    assert response.status_code == 200
    # the full script body is present, not a summary
    assert "@version=5" in response.text
    assert "alertcondition" in response.text
    assert "KNN" in response.text


def test_gate_rejects_without_terms_tick(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    body = client.post("/api/gate", json={"code": site_access.expected_code()})
    assert body.status_code == 403
