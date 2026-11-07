"""Phase 1 of the external audit: honest revenue copy, a transparency page,
and the paper/live separation the terms promise — pinned, not vibes.

The wording lives in loki.api.loki_wording so templates cannot drift apart;
these tests pin the constants and the rendered pages.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from loki.api import site_access
from loki.api.loki_wording import (
    DISPUTE_PROCESS,
    LOSS_TREATMENT,
    PROFIT_DEFINITION,
    REPORTING_PERIOD,
    REVENUE_BANNER,
    revenue_status,
)
from loki.api.server import app

client = TestClient(app)


def test_profit_wording_constants_carry_the_definitions():
    assert "net realised profit" in PROFIT_DEFINITION.lower() or PROFIT_DEFINITION.startswith(
        "Net realised"
    )
    for needle in (
        "closed",
        "unrealised",
        "paper",
        "simulated",
    ):
        assert needle in PROFIT_DEFINITION.lower()
    assert "negative event" in LOSS_TREATMENT
    assert "calendar months" in REPORTING_PERIOD
    for needle in ("30 days", "withheld"):
        assert needle in DISPUTE_PROCESS


def test_revenue_status_defaults_proposed_and_env_can_promote(monkeypatch):
    monkeypatch.delenv("LOKI_REVENUE_STATUS", raising=False)
    assert revenue_status() == "proposed"
    monkeypatch.setenv("LOKI_REVENUE_STATUS", "finalized")
    assert revenue_status() == "finalized"
    assert "formal agreement" in REVENUE_BANNER


def test_transparency_page_is_public_and_names_the_operator():
    reply = client.get("/transparency")
    assert reply.status_code == 200
    body = reply.text
    assert "Who is behind" in body
    assert "Joshua Mathew" in body and "joshuajestin2010@gmail.com" in body  # named operator default
    assert "proposed" in body  # revenue status echoed
    assert "Retention" in body


def test_operator_env_overrides_show_on_transparency(monkeypatch):
    monkeypatch.setenv("LOKI_OPERATOR_NAME", "Slater Trading Co")
    monkeypatch.setenv("LOKI_OPERATOR_EMAIL", "ops@example.com")
    reply = client.get("/transparency")
    assert reply.status_code == 200
    body = reply.text
    assert "Slater Trading Co" in body
    assert "mailto:ops@example.com" in body


def test_revenue_page_marks_the_model_proposed_and_defines_profit():
    reply = client.get("/revenue")
    assert reply.status_code == 200
    body = reply.text
    assert "PROPOSED" in body
    assert "No invoice is issued" in body
    assert "Net realised profit" in body
    assert "Disputes" in body
    assert "calendar months" in body
    # Implementation notes stay out of the customer page (audit fix).
    assert "schema_revenue.sql" not in body
    assert "revenue_ledger" not in body
    assert "{{" not in body  # no unrendered template leaks


def test_terms_page_carries_the_bumped_version_and_paper_live_line():
    assert site_access.TERMS_VERSION >= 5  # new words force a re-tick
    reply = client.get("/terms")
    assert reply.status_code == 200
    body = reply.text
    assert "never closes existing broker positions" in body
    assert "net realised profit" in body
    assert "/transparency" in body
