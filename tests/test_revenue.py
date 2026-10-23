"""Revenue rails (2.21.0): the 30% profit-share ledger, honestly kept.

The fee is computed ONLY server-side (3000 basis points of the recorded
gross, exact decimal math, half-up to the cent); figures exist only when an
operator records real events; the books stay behind an operator key; the
public revenue page explains the model without leaking a number. Nothing
auto-charges anyone — this wave is the ledger, not a billing collector.
"""
import pathlib
import re
from decimal import Decimal

from fastapi.testclient import TestClient

from loki.api import revenue
from loki.api.server import app

REPO = pathlib.Path(__file__).resolve().parents[1]

client = TestClient(app)
client_nofollow = TestClient(app, follow_redirects=False)

OPERATOR_KEY = "op-test-key"


def _clean_money_envs(monkeypatch):
    """Force the honest file-ledger mode: no Supabase, no stale keys."""
    for name in revenue.site_access.SUPABASE_KEY_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("LOKI_REVENUE_STORE", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setenv("LOKI_DATA_DIR", "")


def _with_operator(monkeypatch, tmp_path):
    _clean_money_envs(monkeypatch)
    monkeypatch.setenv("LOKI_REVENUE_KEY", OPERATOR_KEY)
    monkeypatch.setenv("LOKI_DATA_DIR", str(tmp_path))
    return dict(headers={"X-Operator-Key": OPERATOR_KEY})


# ---------------------------------------------------------------------------
# The fee math is exact and only server-side
# ---------------------------------------------------------------------------

def test_house_cut_is_exactly_thirty_percent():
    assert revenue.HOUSE_CUT_BPS == 3000
    assert revenue.cut_for(Decimal("1234.56")) == Decimal("370.37")  # 370.368 → half-up
    assert revenue.cut_for(Decimal("100")) == Decimal("30.00")
    assert revenue.cut_for(Decimal("1")) == Decimal("0.30")
    assert revenue.cut_for(Decimal("0.10")) == Decimal("0.03")
    assert revenue.cut_for(Decimal("1000.005")) == Decimal("300.00")
    assert revenue.cut_for(Decimal("-500")) == Decimal("-150.00")  # clawbacks pull the books down


def test_the_statement_groups_by_period_and_currency_and_never_invents():
    books = revenue.build_statement([
        {"period": "2026-10", "currency": "USD", "gross": "1000.00", "cut": "300.00", "subject": "desk-1", "id": "2"},
        {"period": "2026-10", "currency": "USD", "gross": "-200.00", "cut": "-60.00", "subject": "desk-1", "id": "1"},
        {"period": "2026-09", "currency": "EUR", "gross": "10", "cut": "3.00", "subject": "alpha", "id": "3"},
    ])
    assert len(books["periods"]) == 2  # months stay distinct, currencies stay distinct
    assert books["totals"]["gross"] == "810.00"
    assert books["totals"]["cut"] == "243.00"
    assert books["periods"][0]["period"] == "2026-09"  # oldest month first
    empty = revenue.build_statement([])
    assert empty["periods"] == [] and empty["totals"]["gross"] == "0.00"
    assert "No profit events are recorded yet" in empty["line"]  # an empty book says so


def test_validation_rejects_junk_with_human_copy():
    import pytest
    from fastapi import HTTPException

    for bad_payload, message in (
        ({"period": "2026-13", "subject": "a", "gross": 1}, "period"),
        ({"period": "junk", "subject": "a", "gross": 1}, "period"),
        ({"period": "2026-10", "subject": "", "gross": 1}, "profit belongs"),
        ({"period": "2026-10", "subject": "x" * 81, "gross": 1}, "profit belongs"),
        ({"period": "2026-10", "subject": "a", "gross": "NaN"}, "number"),
        ({"period": "2026-10", "subject": "a", "gross": "inf"}, "number"),
        ({"period": "2026-10", "subject": "a", "gross": 1, "currency": "usdd"}, "currency"),
        ({"period": "2026-10", "subject": "a", "gross": 1, "source": "x" * 41}, "provenance"),
        ({"period": "2026-10", "subject": "a", "gross": 1, "note": "x" * 241}, "note"),
        ({"period": "2026-10", "subject": "a", "gross": 10**13}, "honest book"),
    ):
        with pytest.raises(HTTPException) as exc:
            revenue.validate_event(dict(bad_payload))
        assert message in str(exc.value.detail), bad_payload


# ---------------------------------------------------------------------------
# The operator key is the only door to money figures
# ---------------------------------------------------------------------------

def test_the_books_answer_only_to_the_operator_key(monkeypatch, tmp_path):
    opts = _with_operator(monkeypatch, tmp_path)

    closed = client.post("/api/revenue/events", json={
        "period": "2026-10", "subject": "desk-1", "gross": 1000, "source": "manual"
    })
    assert closed.status_code == 403  # no key, no books
    forced = client.post("/api/revenue/events", **{**opts, "json": {
        "period": "2026-10", "subject": "desk-1", "gross": 1000, "source": "manual",
    }})
    assert forced.status_code == 200 and forced.json()["recorded"] is True

    wrong = client.get("/api/revenue/statement", headers={"X-Operator-Key": "not-the-key"})
    assert wrong.status_code == 403

    monkeypatch.delenv("LOKI_REVENUE_KEY", raising=False)
    unset = client.get("/api/revenue/statement", headers={"X-Operator-Key": OPERATOR_KEY})
    assert unset.status_code == 503  # a deployment with no key keeps its books shut
    assert "operator key" in unset.json()["detail"]


def test_ingest_then_statement_keeps_the_math_server_side(monkeypatch, tmp_path):
    opts = _with_operator(monkeypatch, tmp_path)

    first = client.post("/api/revenue/events", **{**opts, "json": {
        "period": "2026-10", "subject": "desk-1", "gross": "1234.56",
        "currency": "usd", "source": "statement-import",
    }})
    assert first.status_code == 200
    assert first.json()["cut"] == "370.37"  # computed in the server, never the client

    books = client.get("/api/revenue/statement", **opts).json()
    row = [p for p in books["periods"] if p["period"] == "2026-10"][0]
    assert row["currency"] == "USD" and row["events"] == 1
    assert row["gross"] == "1234.56" and row["cut"] == "370.37"


def test_the_public_page_and_info_show_the_model_never_the_figures(monkeypatch, tmp_path):
    _with_operator(monkeypatch, tmp_path)

    info = client.get("/api/revenue/info")
    assert info.status_code == 200
    body = info.json()
    assert body["house_cut_percent"] == "30%" and body["house_cut_bps"] == 3000
    assert "figures" not in body and "periods" not in body and "totals" not in body  # no leak

    page = client.get("/revenue")
    assert page.status_code == 200
    html = page.text
    assert "30%" in html and "Draft" in html  # the model and its draft status stated plainly
    assert "0.00" not in html and "revenue_ledger.json" not in html  # no figures, no file paths


def test_the_csv_export_is_the_real_books(monkeypatch, tmp_path):
    opts = _with_operator(monkeypatch, tmp_path)

    for gross, month in (("100.00", "2026-10"), ("-40.00", "2026-10"), ("7.50", "2026-09")):
        sent = client.post("/api/revenue/events", **{**opts, "json": {
            "period": month, "subject": "desk-1", "gross": gross,
        }})
        assert sent.status_code == 200, sent.text

    csv = client.get("/api/revenue/export.csv", **opts)
    assert csv.status_code == 200
    assert "text/csv" in csv.headers["content-type"]
    rows = csv.text.strip().split("\n")
    assert rows[0] == "period,subject,currency,gross,cut,source,created_at,note"
    assert len(rows) == 4  # header + three events, exactly as recorded


# ---------------------------------------------------------------------------
# Honest modes and the run-once schema
# ---------------------------------------------------------------------------

def test_unavailable_mode_refuses_instead_of_inventing(monkeypatch):
    _clean_money_envs(monkeypatch)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("LOKI_REVENUE_KEY", OPERATOR_KEY)
    assert revenue.ledger_mode() == "unavailable"

    opts = {"headers": {"X-Operator-Key": OPERATOR_KEY}}
    assert client.get("/api/revenue/statement", **opts).status_code == 503
    assert client.get("/api/revenue/export.csv", **opts).status_code == 503
    refused = client.post("/api/revenue/events", **{**opts, "json": {
        "period": "2026-10", "subject": "desk-1", "gross": 1,
    }})
    assert refused.status_code == 503


def test_shared_mode_missing_table_says_run_the_schema(monkeypatch):
    _clean_money_envs(monkeypatch)
    monkeypatch.setenv("SUPABASE_URL", "https://vwtmfsrcqyteviyniiqj.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", OPERATOR_KEY)

    class Stub404:
        status_code = 404
        def json(self):
            return {}

    monkeypatch.setattr(revenue, "_supa_send", lambda *a, **k: Stub404())
    assert revenue.ledger_mode() == "shared"
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        revenue.read_events()
    assert "schema_revenue.sql" in str(exc.value.detail)


def test_the_schema_pins_the_shape_and_is_run_once():
    schema = (REPO / "supabase" / "schema_revenue.sql").read_text(encoding="utf-8")
    assert "ONCE" in schema  # tells the operator how it runs, exactly like the dive schema
    assert "create table if not exists public.revenue_ledger" in schema
    assert "check (abs(cut) <= abs(gross)" in schema  # a row can't out-earn its own gross
    assert "period ~ '^\\d{4}-(0[1-9]|1[0-2])$'" in schema  # real months only


def test_no_client_ever_computes_the_fee():
    game = (REPO / "static" / "js" / "game.js").read_text(encoding="utf-8")
    index = (REPO / "templates" / "index.html").read_text(encoding="utf-8")
    assert "HOUSE_CUT" not in game and "HOUSE_CUT" not in index
    assert "/api/revenue" not in game  # the dive game stays a game, never a biller
    page = (REPO / "templates" / "revenue.html").read_text(encoding="utf-8")
    assert "cut_for(" not in page and "house_cut_bps / " not in page  # the page renders, not computes


def test_the_revenue_router_is_mounted_and_the_footer_advertises_it():
    index = (REPO / "templates" / "index.html").read_text(encoding="utf-8")
    assert 'href="/revenue"' in index
    assert client_nofollow.get("/api/revenue/info").status_code == 200
