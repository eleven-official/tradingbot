"""Revenue rails: the 30% profit-share ledger.

One purpose: keep the house's books honestly. When a recorded subject
(a desk, a strategy, a person the operator bills) turns a profit, an
operator records the figure here and the server computes the 30% cut.
Nothing on this page ever auto-charges anyone — this wave is the ledger,
not a billing collector. Figures exist only when a human recorded them;
an empty book says so out loud.

Hard honesty rules, mirroring the rest of Loki:

- The fee is computed ONLY here, server-side, with exact decimal math
  (3000 basis points of recorded gross, rounded half-up to the cent).
  No client, page, or game ever computes money.
- Every profit event carries provenance (``source``) and a period, so the
  books state where each figure came from. Negative events are allowed:
  a loss period or a correction must be able to pull the books down.
- Money data is private. The statement and the books export answer only
  to the operator key (``LOKI_REVENUE_KEY``); the public revenue page
  explains the model and shows the ledger mode, never the figures.
- Three storage modes, decided by what the deployment actually has,
  described the way the dive board describes its score store:
  ``shared`` (Supabase — run supabase/schema_revenue.sql once),
  ``server-local`` (a file beside the code), ``unavailable`` (ephemeral
  hosting with no database — nothing is accepted, and it says why).
"""
from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests as http_requests
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from loki.api import site_access

router = APIRouter(prefix="/api/revenue", tags=["Revenue ledger"])

HOUSE_CUT_BPS = 3000           # 30% of recorded profits, the one source of truth
CURRENCY = "USD"
MAX_GROSS = Decimal("1e12")    # no honest book hits this; rejects absurd junk
_PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_CENTS = Decimal("0.01")

_SAVE_LOCK = threading.Lock()

_TABLE_MISSING = (
    "The revenue ledger is not set up yet — run supabase/schema_revenue.sql "
    "once in the project database."
)


def ledger_mode() -> str:
    """Which store actually holds the books, honestly labeled."""
    if (os.environ.get("LOKI_REVENUE_STORE") or "").strip().lower() == "file":
        return "server-local"
    try:
        site_access._supabase_config()
        return "shared"
    except HTTPException:
        return "unavailable" if _on_vercel() else "server-local"


def _mode_note(mode: str) -> str:
    if mode == "shared":
        return "The books live in the project database: they survive deploys and are shared by this whole deployment."
    if mode == "server-local":
        return "The books live in a file on this Loki server: real bookkeeping for this deployment, gone if the files are."
    return (
        "This deployment keeps no durable ledger, so no profit event can be "
        "recorded here. Nothing about the fee model requires it to."
    )


def _on_vercel() -> bool:
    return bool(os.environ.get("VERCEL"))


def _data_dir() -> Path:
    override = (os.environ.get("LOKI_DATA_DIR") or "").strip()
    base = Path(override) if override else Path(__file__).resolve().parents[1] / "data"
    return base / "revenue_ledger.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def cut_for(gross: Decimal) -> Decimal:
    """The house cut: exactly HOUSE_CUT_BPS of gross, rounded half-up to cents."""
    return (gross * HOUSE_CUT_BPS / Decimal(10_000)).quantize(_CENTS, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Operator key — the only door to money figures
# ---------------------------------------------------------------------------

def require_operator(request: Request) -> None:
    expected = (os.environ.get("LOKI_REVENUE_KEY") or "").strip()
    if not expected:
        raise HTTPException(
            503,
            "The revenue ledger has no operator key configured on this "
            "deployment, so the books stay closed here.",
        )
    given = (request.headers.get("X-Operator-Key") or "").strip()
    if not given or not _key_matches(given, expected):
        raise HTTPException(403, "That operator key does not open the books.")


def _key_matches(given: str, expected: str) -> bool:
    import hmac

    return hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8"))


# ---------------------------------------------------------------------------
# Event validation — pure, so tests can hammer it without a server
# ---------------------------------------------------------------------------

def validate_event(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(422, "Send the profit event as JSON with a period, subject, and gross figure.")

    period = str(payload.get("period") or "").strip()
    if not _PERIOD_RE.match(period) or not (2000 <= int(period[:4]) <= 2100):
        raise HTTPException(422, "The period must be a real month like 2026-10 — books are kept by month.")

    subject = " ".join(str(payload.get("subject") or "").split())
    if not subject or len(subject) > 80:
        raise HTTPException(422, "Name who the profit belongs to (1-80 characters) — a ledger with 'unknown' rows is a guess.")

    gross = _money(payload.get("gross"), "the gross figure")
    if abs(gross) > MAX_GROSS:
        raise HTTPException(422, "That figure is beyond anything an honest book records.")

    currency = str(payload.get("currency") or CURRENCY).strip().upper() or CURRENCY
    if not _CURRENCY_RE.match(currency):
        raise HTTPException(422, "The currency must be a three-letter code like USD.")

    source = " ".join(str(payload.get("source") or "manual").split())
    if not source or len(source) > 40:
        raise HTTPException(422, "Say where the figure came from (1-40 characters) — provenance is the point.")

    note = " ".join(str(payload.get("note") or "").split())
    if len(note) > 240:
        raise HTTPException(422, "Keep the note under 240 characters.")

    return {
        "period": period,
        "subject": subject,
        "gross": gross,
        "currency": currency,
        "source": source,
        "note": note,
    }


def _money(value: Any, label: str) -> Decimal:
    if isinstance(value, bool) or value is None or value == "":
        raise HTTPException(422, f"{label.capitalize()} must be a number — money never arrives as a guess.")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise HTTPException(422, f"{label.capitalize()} must be a plain number, like 1234.56.")
    if not amount.is_finite():
        raise HTTPException(422, f"{label.capitalize()} must be a finite number — NaN and infinity are not money.")
    return amount


# ---------------------------------------------------------------------------
# Stores
# ---------------------------------------------------------------------------

def _supa_send(method: str, path: str, *, json_body: Optional[dict] = None) -> http_requests.Response:
    url, key = site_access._supabase_config()
    return http_requests.request(
        method, f"{url}{path}", json=json_body, headers=site_access._supa_headers(key), timeout=15
    )


def _guard(response: http_requests.Response) -> http_requests.Response:
    if response.status_code == 404:
        raise HTTPException(503, _TABLE_MISSING)
    if not 200 <= response.status_code < 300:
        raise HTTPException(503, "The ledger service had a hiccup; try again shortly.")
    return response


def record_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Append one profit event to the books and return the row as kept."""
    cut = cut_for(event["gross"])
    row = {
        "period": event["period"],
        "subject": event["subject"],
        "gross": _decimal_text(event["gross"]),
        "cut": _decimal_text(cut),
        "currency": event["currency"],
        "source": event["source"],
        "note": event["note"],
        "created_at": event["created_at"],
    }
    if ledger_mode() == "shared":
        sent = _supa_send("POST", "/rest/v1/revenue_ledger", json_body=row)
        if sent.status_code == 404:
            raise HTTPException(503, _TABLE_MISSING)
        if not 200 <= sent.status_code < 300:
            raise HTTPException(503, "The ledger service had a hiccup; try again shortly.")
        kept = sent.json()
        row["id"] = str(kept.get("id") or "") if isinstance(kept, dict) else ""
        return row
    if ledger_mode() == "unavailable":
        raise HTTPException(503, _mode_note("unavailable") + " No event was recorded.")
    return _file_append(row)


def _decimal_text(value: Decimal) -> str:
    """Plain cent-exact text so JSON never carries float fuzz about money."""
    return format(value.quantize(_CENTS, rounding=ROUND_HALF_UP), "f")


def _file_append(row: Dict[str, Any]) -> Dict[str, Any]:
    path = _data_dir()
    with _SAVE_LOCK:
        book: Dict[str, Any] = {"events": []}
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict) and isinstance(loaded.get("events"), list):
                    book = loaded
            except ValueError:
                book = {"events": []}
        row["id"] = str(uuid.uuid4())
        book["events"].append(row)
        book["saved_at"] = _now_iso()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(book, indent=2), encoding="utf-8")
    return row


def read_events() -> List[Dict[str, Any]]:
    """Every recorded event, oldest bookkeeping untouched, for statements/CSV."""
    if ledger_mode() == "shared":
        sent = _supa_send(
            "GET",
            "/rest/v1/revenue_ledger?select=period,subject,gross,cut,currency,source,note,created_at,id"
            "&order=created_at.asc&limit=10000",
        )
        _guard(sent)
        rows = sent.json() or []
    elif ledger_mode() == "unavailable":
        return []
    else:
        path = _data_dir()
        if not path.exists():
            return []
        try:
            book = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            return []
        rows = book.get("events") or []
    return [r for r in rows if isinstance(r, dict)]


# ---------------------------------------------------------------------------
# The books — pure aggregation
# ---------------------------------------------------------------------------

def build_statement(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Group by period and currency, exact decimal sums, honest empty case."""
    groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for row in events:
        key = (str(row.get("period") or ""), str(row.get("currency") or "").upper() or "???")
        groups.setdefault(key, []).append(row)
    periods: List[Dict[str, Any]] = []
    total_gross = Decimal("0")
    total_cut = Decimal("0")
    for (period, currency) in sorted(groups):
        rows = groups[(period, currency)]
        gross = sum((_as_decimal(r.get("gross")) for r in rows), Decimal("0"))
        cut = sum((_as_decimal(r.get("cut")) for r in rows), Decimal("0"))
        total_gross += gross
        total_cut += cut
        periods.append({
            "period": period,
            "currency": currency,
            "events": len(rows),
            "gross": _decimal_text(gross),
            "cut": _decimal_text(cut),
        })
    empty = not events
    return {
        "house_cut_bps": HOUSE_CUT_BPS,
        "periods": periods,
        "totals": {
            "gross": _decimal_text(total_gross),
            "cut": _decimal_text(total_cut),
        },
        "line": (
            "No profit events are recorded yet — the books show nothing "
            "because nothing has been recorded. Figures appear only when the "
            "operator records real ones."
            if empty else
            "Figures are server-computed: the house cut is exactly "
            f"30% of recorded profits, built from every event below."
        ),
    }


def _as_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def to_csv(events: List[Dict[str, Any]]) -> str:
    header = "period,subject,currency,gross,cut,source,created_at,note"
    lines = [header]
    for row in sorted(
        events,
        key=lambda r: (str(r.get("created_at") or ""), str(r.get("id") or "")),
    ):
        lines.append(",".join(_csv_cell(str(row.get(k) or "")) for k in
                              ("period", "subject", "currency", "gross", "cut",
                               "source", "created_at", "note")))
    return "\n".join(lines) + "\n"


def _csv_cell(value: str) -> str:
    if any(ch in value for ch in ",\"\n"):
        return '"' + value.replace('"', '""') + '"'
    return value


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------

class RevenueEventBody(BaseModel):
    period: str
    subject: str
    gross: Any
    currency: Optional[str] = None
    source: Optional[str] = None
    note: Optional[str] = None


@router.get("/info")
async def info() -> Dict[str, Any]:
    """Public: the fee model and the ledger mode. Never the figures."""
    mode = ledger_mode()
    return {
        "mode": mode,
        "note": _mode_note(mode),
        "house_cut_bps": HOUSE_CUT_BPS,
        "house_cut_percent": "30%",
        "billing": "Records the house cut on real recorded profits. Nothing auto-charges anyone.",
    }


@router.post("/events")
async def ingest(request: Request, body: RevenueEventBody) -> Dict[str, Any]:
    require_operator(request)
    event = validate_event(body.model_dump())
    event["created_at"] = _now_iso()
    await run_in_threadpool(record_event, event)
    return {"recorded": True, "cut": _decimal_text(cut_for(event["gross"])),
            "period": event["period"], "currency": event["currency"]}


@router.get("/statement")
async def statement(request: Request) -> Dict[str, Any]:
    require_operator(request)
    mode = ledger_mode()
    if mode == "unavailable":
        raise HTTPException(503, _mode_note(mode))
    events = await run_in_threadpool(read_events)
    books = build_statement(events)
    books["mode"] = mode
    books["note"] = _mode_note(mode)
    return books


@router.get("/export.csv")
async def export_csv(request: Request) -> Response:
    require_operator(request)
    mode = ledger_mode()
    if mode == "unavailable":
        raise HTTPException(503, _mode_note(mode))
    events = await run_in_threadpool(read_events)
    csv = await run_in_threadpool(to_csv, events)
    return Response(
        content=csv,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=loki_revenue_ledger.csv"},
    )
