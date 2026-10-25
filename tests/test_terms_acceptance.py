"""Terms gate (2.22.0): a ticked agreement before the door opens.

The gate now demands two honest things: the access code AND a ticked
box agreeing to the Terms of Use — the plain-words promise that Loki is
research-only, nothing here is advice, no profits are promised, and the
operator's liability stops where the law says it must. The server never
trusts the checkbox alone: a POST without an explicit accepted tick is
refused, and the acceptance cookie carries a signed version stamp so a
future terms change re-gates every browser exactly once.
"""
import pathlib
import time

from fastapi.testclient import TestClient

from loki.api import site_access
from loki.api.server import app

REPO = pathlib.Path(__file__).resolve().parents[1]

client = TestClient(app)
client_nofollow = TestClient(app, follow_redirects=False)


def _page_lockdown(monkeypatch):
    """Gate middleware engaged, exactly like on a remote deployment, and a clean throttle."""
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setattr(site_access, "_GATE_ATTEMPTS", {})
    client.cookies.clear()
    client_nofollow.cookies.clear()


def test_the_gate_refuses_a_body_without_a_tick_and_never_charges_the_timer(monkeypatch):
    _page_lockdown(monkeypatch)
    unticked = client.post("/api/gate", json={"code": "flathead"})
    assert unticked.status_code == 403
    assert "Tick the terms" in unticked.json()["detail"]

    # skipping the tick is not punished: nine silent skips still leave the
    # anti-brute-force budget for a real wrong-code probe
    for _ in range(9):
        client.post("/api/gate", json={"code": "flathead"})
    wrong_code = client.post("/api/gate", json={"code": "chocolate", "accepted_terms": True})
    assert wrong_code.status_code == 403
    assert "not the code" in wrong_code.json()["detail"]


def test_non_object_gate_payloads_are_bad_requests(monkeypatch):
    _page_lockdown(monkeypatch)
    for body in ([], ["code"], "flathead", 42, True):
        response = client.post("/api/gate", json=body)
        assert response.status_code == 400
        assert "object" in response.json()["detail"]
    assert not site_access._GATE_ATTEMPTS.get("testclient")


def test_a_ticked_correct_code_opens_with_both_cookies(monkeypatch):
    _page_lockdown(monkeypatch)
    opened = client.post("/api/gate", json={"code": "flaTHEAD", "accepted_terms": True})
    assert opened.status_code == 200
    gate = opened.cookies.get(site_access.GATE_COOKIE)
    terms = opened.cookies.get(site_access.TERMS_COOKIE)
    assert gate and site_access.verify_gate_cookie_value(gate)
    assert terms and site_access.read_terms_cookie_value(terms) == site_access.TERMS_VERSION
    assert site_access.read_terms_cookie_value(terms) >= 1  # the badge records WHICH words


def test_gated_pages_demand_both_cookies(monkeypatch):
    _page_lockdown(monkeypatch)
    client_nofollow.cookies.set(
        site_access.GATE_COOKIE, site_access.issue_gate_cookie_value()
    )
    gate_only_home = client_nofollow.get("/")
    assert gate_only_home.status_code == 303
    assert gate_only_home.headers["location"] == "/gate"

    client_nofollow.cookies.clear()
    client_nofollow.cookies.set(
        site_access.TERMS_COOKIE, site_access.issue_terms_cookie_value()
    )
    terms_only = client_nofollow.get("/")
    assert terms_only.status_code == 303
    assert terms_only.headers["location"] == "/gate"  # terms alone does not unlatch


def test_the_gate_page_opens_only_when_both_are_set(monkeypatch):
    _page_lockdown(monkeypatch)
    fresh = client_nofollow.get("/gate")
    assert fresh.status_code == 200
    assert 'id="terms-ok"' in fresh.text

    client_nofollow.cookies.set(
        site_access.GATE_COOKIE, site_access.issue_gate_cookie_value()
    )
    half_in = client_nofollow.get("/gate")
    assert half_in.status_code == 200  # an unlocked browser with no tick sees the form again

    client_nofollow.cookies.set(
        site_access.TERMS_COOKIE, site_access.issue_terms_cookie_value()
    )
    both = client_nofollow.get("/gate")
    assert both.status_code == 303 and both.headers["location"] == "/"


def test_the_eraser_clears_both_cookies():
    client.cookies.clear()
    client.cookies.set(site_access.GATE_COOKIE, site_access.issue_gate_cookie_value())
    client.cookies.set(site_access.TERMS_COOKIE, site_access.issue_terms_cookie_value())
    forgotten = client.post("/api/gate/forget")
    assert forgotten.status_code == 200
    header = "; ".join(forgotten.headers.get_list("set-cookie"))
    assert f"{site_access.GATE_COOKIE}=" in header
    assert f"{site_access.TERMS_COOKIE}=" in header  # both memories are erased


def test_the_terms_page_is_public_and_honest():
    page = client.get("/terms")
    assert page.status_code == 200  # readable BEFORE any tick: that is the point
    html = page.text
    assert "No profits are promised" in html or "no profits are promised" in html
    assert "Not advice" in html
    assert "To the maximum extent permitted by applicable law" in html
    assert "strict paper mode" in html
    assert "Version" in html and "Updated" in html
    assert "free to use" in html and "30% of recorded profits" in html
    assert "/revenue" in html  # the fee model's public home is one click away


def test_a_badge_baked_under_old_words_stops_opening_the_door(monkeypatch):
    # today's words are v1; a badge is baked as v1
    monkeypatch.setattr(site_access, "TERMS_VERSION", 1)
    old_badge = site_access.issue_terms_cookie_value()
    assert site_access.read_terms_cookie_value(old_badge) == 1
    # tomorrow the words change to v2: the same badge is now stale, and only
    # the comparison gate keeps it from unlatching pages
    monkeypatch.setattr(site_access, "TERMS_VERSION", 2)
    assert site_access.read_terms_cookie_value(old_badge) < site_access.TERMS_VERSION


def test_the_gate_script_posts_the_real_checkbox_state():
    gate_html = (REPO / "templates" / "gate.html").read_text(encoding="utf-8")
    assert "accepted_terms: termsEl.checked" in gate_html
    assert "Tick the terms box first" in gate_html  # client blocks quietly; server still verifies
    assert 'novalidate' in gate_html  # native required bubbles swallow the submit event — our words replace them
    assert "Type the access code first" in gate_html  # the code field keeps its own honest prompt
    assert 'document.cookie = \'loki_terms=; Max-Age=0; path=/\';' in gate_html  # eraser parity


def test_the_terms_are_advertised_and_stamped():
    index = (REPO / "templates" / "index.html").read_text(encoding="utf-8")
    assert 'href="/terms"' in index
    assert site_access.TERMS_VERSION >= 1 and site_access.TERMS_UPDATED


def test_free_to_use_is_stated_at_every_door():
    """The price policy in the user's own words, on each public surface.

    Free to use — the only ask is the house's 30% fee of recorded profits,
    and nothing is charged automatically. Each wording keeps the honest
    qualifiers (recorded profits, no auto-charging) instead of a bare 30%.
    """
    gate = (REPO / "templates" / "gate.html").read_text(encoding="utf-8")
    assert "free to use" in gate and "30% fee of recorded profits" in gate
    assert "nothing is charged automatically" in gate

    login = (REPO / "templates" / "login.html").read_text(encoding="utf-8")
    assert "free to use" in login and "30% fee of recorded profits" in login

    index_footer = (REPO / "templates" / "index.html").read_text(encoding="utf-8")
    assert "Free to use — the house's only ask is a 30% fee of recorded profits" in index_footer

    # A version bump is the re-tick mechanism: words changed → ask again.
    assert site_access.TERMS_VERSION >= 3
