"""The 404 contract: people get a themed page, machines keep machine JSON.

TestClient sends no Accept header at all, so the default path is JSON.
Browsers always ask for text/html, so they get the themed page.
Both halves of the split are pinned here so neither can silently regress.
"""
from __future__ import annotations

import pathlib

import loki.api.server as server_module
from fastapi.testclient import TestClient

REPO = pathlib.Path(__file__).resolve().parents[1]
client = TestClient(server_module.app)


def test_a_wrong_address_tells_people_so_with_the_site_looking():
    r = client.get("/nope", headers={"Accept": "text/html"})
    assert r.status_code == 404
    assert "text/html" in r.headers["content-type"]
    body = r.text
    assert "isn't on the" in body          # the honest headline
    assert "404" in body                    # the depth marker
    assert 'href="/"' in body               # way back to the desk
    assert "/favicon.ico" in body           # branded tab
    assert 'name="theme-color"' in body     # browser chrome tint


def test_the_404_page_is_on_theme_and_self_styled():
    t = (REPO / "templates" / "404.html").read_text(encoding="utf-8")
    assert "404" in t
    assert 'name="theme-color"' in t
    assert 'href="/favicon.ico?v={{ version }}"' in t   # cache-busted icon
    assert "JetBrains Mono" in t            # the site's terminal face


def test_machines_still_get_the_machine_json_for_unknown_paths():
    r = client.get("/nope")  # no Accept header → machine path
    assert r.status_code == 404
    assert r.json() == {"detail": "Not Found"}
    assert "application/json" in r.headers["content-type"]


def test_api_unknown_routes_stay_json_even_when_a_browser_asks():
    r = client.get("/api/bad-route", headers={"Accept": "text/html"})
    assert r.status_code == 404
    assert r.json() == {"detail": "Not Found"}
    assert "application/json" in r.headers["content-type"]


def test_other_statuses_keep_their_real_status_code_and_detail():
    r = client.post("/health")  # GET-only endpoint → 405
    assert r.status_code == 405
    assert r.json()["detail"]


def test_every_page_surface_tints_the_browser_chrome():
    for name in ("index.html", "gate.html", "login.html"):
        t = (REPO / "templates" / name).read_text(encoding="utf-8")
        assert 'name="theme-color"' in t, f"{name} lost its theme-color"
