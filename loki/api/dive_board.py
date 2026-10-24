"""Shared best-dive leaderboard for the Bored? game.

Account-owned public rankings in Supabase. Publishing is an explicit click;
scores remain self-reported. The server takes identity from the signed session
and the database atomically preserves each account's highest score. The local
development file board remains nickname-based and is labeled separately.

Three honest storage modes, decided by what the deployment actually has:

- ``shared`` — Supabase is configured (the same credentials the accounts
   feature uses). One global board held by the ``member_dive_scores`` table that
  survives deploys. If the table itself is missing, the board says to run
   ``supabase/schema_member_data.sql`` once instead of pretending.
- ``server-local`` — no Supabase, but a long-lived server (a person running
  Loki on their machine). A JSON file beside the code is genuinely shared by
  every browser pointing at that server, and the board describes itself
  exactly that way.
- ``unavailable`` — ephemeral hosting (Vercel) with no Supabase. A file
  written there would evaporate between requests, so nothing is accepted
  and the endpoint says why rather than accepting scores it would lose.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests as http_requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from loki.api import site_access
from loki.api.member_data import database, require_member

router = APIRouter(prefix="/api/dive", tags=["Dive leaderboard"])

MAX_ROWS = 500            # server-local cap; the shallowest names lose their seat
BOARD_LIMIT = 25          # rows served to a browser
WRITE_COOLDOWN = 20.0     # per-client-IP seconds between accepted publishes
MAX_SCORE = 1_000_000     # no honest dive reaches this; rejects absurd junk

_SAVE_LOCK = threading.Lock()
_WRITES: Dict[str, List[float]] = {}
_WRITE_LOCK = threading.Lock()


def _data_dir() -> Path:
    override = (os.environ.get("LOKI_DATA_DIR") or "").strip()
    base = Path(override) if override else Path(__file__).resolve().parents[1] / "data"
    return base / "dive_board.json"


def _on_vercel() -> bool:
    return bool(os.environ.get("VERCEL"))


def board_mode() -> str:
    # Operator override: LOKI_DIVE_BOARD=file deliberately chooses the local
    # file board even where Supabase exists (accounts keep using Supabase).
    # The mode label still describes the real storage, so this stays honest.
    if (os.environ.get("LOKI_DIVE_BOARD") or "").strip().lower() == "file":
        return "server-local"
    try:
        site_access._supabase_config()
        return "shared"
    except HTTPException:
        return "unavailable" if _on_vercel() else "server-local"


def _mode_note(mode: str) -> str:
    if mode == "shared":
        return "Shared board held by the project database — it survives deploys and every browser sees the same rows."
    if mode == "server-local":
        return "Scores are kept in a file on this Loki server: shared across every browser using it, tied to this deployment."
    return "This deployment hosts no shared score store, so nothing can be published here. Your best dive stays in your browser only."


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Supabase (shared) board
# ---------------------------------------------------------------------------

_TABLE_MISSING = "The account leaderboard is not set up yet — run supabase/schema_member_data.sql in the project database."


def _supa_quote(value: str) -> str:
    return value.replace(" ", "%20").replace(",", "%2C").replace('"', "%22")


def _supa_send(method: str, path: str, *, json_body: Optional[dict] = None, headers: Optional[dict] = None) -> http_requests.Response:
    url, key = site_access._supabase_config()
    base_headers = site_access._supa_headers(key)
    if headers:
        base_headers.update(headers)
    try:
        return http_requests.request(method, f"{url}{path}", json=json_body, headers=base_headers, timeout=15)
    except http_requests.RequestException as exc:
        raise HTTPException(503, "The shared board is unreachable; try again shortly.") from exc


def _guard(response: http_requests.Response) -> None:
    if response.status_code == 404:
        raise HTTPException(503, _TABLE_MISSING)
    if not 200 <= response.status_code < 300:
        raise HTTPException(503, "The shared board service had a hiccup; try again shortly.")


def _shared_read() -> Dict[str, Any]:
    response = _supa_send(
        "GET",
        f"/rest/v1/member_dive_scores?select=nickname,best_score,dives,updated_at&order=best_score.desc,updated_at.asc,user_id.asc&limit={BOARD_LIMIT}",
    )
    _guard(response)
    entries: List[Dict[str, Any]] = []
    for row in response.json() or []:
        entries.append({
            "nickname": str(row.get("nickname") or "?"),
            "best": int(row.get("best_score") or 0),
            "dives": int(row.get("dives") or 0),
            "updated_at": str(row.get("updated_at") or ""),
        })
    return {"mode": "shared", "note": _mode_note("shared"), "entries": entries}


def shared_write(uid: str, nickname: str, best: int) -> Dict[str, Any]:
    """Atomic maximum and count, keyed by the verified account, not its label."""
    rows = database("POST", "/rest/v1/rpc/publish_member_dive", {"p_user_id": uid, "p_nickname": nickname, "p_best": best})
    row = rows[0]
    return {"mode": "shared", "note": _mode_note("shared"), "nickname": nickname, "best": row["best_score"], "dives": row["dives"]}


# ---------------------------------------------------------------------------
# Server-local (file) board
# ---------------------------------------------------------------------------

def _file_load() -> Dict[str, Any]:
    path = _data_dir()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (ValueError, OSError):
        return {}


def _file_save(board: Dict[str, Any]) -> None:
    path = _data_dir()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(board, sort_keys=True), encoding="utf-8")


def _file_entries() -> List[Dict[str, Any]]:
    rows = [{"nickname": nick, **row} for nick, row in _file_load().items()]
    rows.sort(key=lambda row: row.get("best", 0), reverse=True)
    return rows[:BOARD_LIMIT]


def local_write(nickname: str, best: int) -> Dict[str, Any]:
    with _SAVE_LOCK:
        board = _file_load()
        previous = board.get(nickname) or {}
        kept_best = max(best, int(previous.get("best") or 0))
        board[nickname] = {"best": kept_best, "dives": int(previous.get("dives") or 0) + 1, "updated_at": _now_iso()}
        if len(board) > MAX_ROWS:
            keep = sorted(board.items(), key=lambda item: item[1].get("best", 0), reverse=True)[:MAX_ROWS]
            board = dict(keep)  # strictly the deepest names stay; no tie-unsafe deletion
        _file_save(board)
        row = board[nickname]
    return {"mode": "server-local", "note": _mode_note("server-local"), "nickname": nickname, "best": row["best"], "dives": row["dives"]}


def local_read() -> Dict[str, Any]:
    return {"mode": "server-local", "note": _mode_note("server-local"), "entries": _file_entries()}


# ---------------------------------------------------------------------------
# Throttle + routes
# ---------------------------------------------------------------------------

def _throttled(client_ip: str) -> bool:
    now = time.time()
    with _WRITE_LOCK:
        stamps = [t for t in _WRITES.get(client_ip, []) if now - t < WRITE_COOLDOWN]
        _WRITES[client_ip] = stamps
        if stamps:
            return True
        stamps.append(now)
        return False


class DiveScoreBody(BaseModel):
    nickname: str = Field(default="", max_length=32)
    best: int = Field(ge=0, le=MAX_SCORE)
    dives: Optional[int] = Field(default=None, ge=0, le=1_000_000)  # accepted for API shape; the server counts its own


@router.get("/leaderboard")
async def leaderboard() -> Dict[str, Any]:
    mode = board_mode()
    if mode == "shared":
        return await run_in_threadpool(_shared_read)
    if mode == "server-local":
        return await run_in_threadpool(local_read)
    return {"mode": "unavailable", "note": _mode_note("unavailable"), "entries": []}


@router.post("/score")
async def publish(request: Request, body: DiveScoreBody) -> Dict[str, Any]:
    # Validate before throttling: a rejected publish is not traffic worth
    # cooling down, so honest mistakes never cost the browser its slot.
    mode = board_mode()
    member = require_member(request) if mode == "shared" else None
    if member and request.headers.get("x-workspace-owner", member["uid"]) != member["uid"]:
        raise HTTPException(409, "Your signed-in account changed. Reload before publishing.")
    nickname = site_access.clean_nickname(member["nickname"] if member else body.nickname)
    if not nickname:
        raise HTTPException(400, "Pick a board name (2-24 letters, numbers, spaces or dashes).")
    best = int(body.best)
    if best < 0 or best > MAX_SCORE:
        raise HTTPException(400, f"Scores are whole numbers from 0 to {MAX_SCORE} points.")
    client_ip = request.client.host if request.client else "unknown"
    if _throttled(member["uid"] if member else client_ip):
        raise HTTPException(429, "One publish per 20 seconds — give the board a breath.")
    if mode == "shared":
        assert member is not None
        return await run_in_threadpool(shared_write, member["uid"], nickname, best)
    if mode == "server-local":
        return await run_in_threadpool(local_write, nickname, best)
    raise HTTPException(
        503,
        "This deployment hosts no shared score store, so nothing was recorded — your best dive still lives in this browser.",
    )
