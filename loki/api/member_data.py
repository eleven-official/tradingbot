"""Owner-scoped cloud workspace and game records; no client-supplied owner."""
import json
from typing import Any, Dict, Optional
from datetime import datetime, timezone
from uuid import UUID

import requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from loki.api import site_access

router = APIRouter(prefix="/api/account", tags=["My account"])
WORKSPACE_KEYS = frozenset({
    "loki-fusion-paper-v1", "loki_ai_paper_v1", "loki.paper-journal.v1",
    "loki.daily-risk-limit.v1", "loki_dive_best", "loki_dive_dives",
    "loki_dive_challenge", "loki_dive_recent", "loki_dive_history",
    "loki_currency", "loki_visit_snapshot", "loki_steps_data", "loki_steps_run",
    "loki_steps_council", "loki_steps_journal", "loki-synthetic-market-v1",
    "loki_practice_stats_v1", "loki_watchlist_v1", "loki_pinned_report_v1",
    "loki_council_history_v1", "loki_news_seen_v1", "loki_dive_badges",
    "loki_dive_streak", "loki_dive_challenge_wins",
})


def require_member(request: Request) -> dict:
    session = site_access.read_session_cookie_value(request.cookies.get(site_access.SESSION_COOKIE))
    if not session:
        raise HTTPException(401, "Sign in to access your saved information.")
    try:
        session["uid"] = str(UUID(session["uid"]))
    except (ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(401, "Sign in again to access your saved information.")
    return session


def database(method: str, path: str, body: Optional[dict] = None, prefer: Optional[str] = None) -> Any:
    url, key = site_access._supabase_config()
    headers = site_access._supa_headers(key)
    if prefer:
        headers["Prefer"] = prefer
    try:
        response = requests.request(method, url + path, json=body, headers=headers, timeout=15)
        if response.status_code == 404:
            raise HTTPException(503, "Account storage needs setup: run supabase/schema_member_data.sql in the project database.")
        if not 200 <= response.status_code < 300:
            raise HTTPException(503, "Account storage is unavailable. Please try again shortly.")
        return response.json() if response.content else []
    except (requests.RequestException, ValueError) as exc:
        raise HTTPException(503, "Account storage could not be reached. Please try again shortly.") from exc


class WorkspaceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: Dict[str, str] = Field(max_length=30)


@router.get("/storage-context.js")
async def storage_context(request: Request) -> Response:
    session = site_access.read_session_cookie_value(request.cookies.get(site_access.SESSION_COOKIE))
    owner = session["uid"] if session else "guest"
    return Response("window.LokiStorageOwner=" + json.dumps(owner) + ";", media_type="application/javascript", headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/me")
async def my_account(request: Request) -> dict:
    member = require_member(request)
    rows = await run_in_threadpool(database, "GET", f"/rest/v1/member_dive_scores?user_id=eq.{member['uid']}&select=best_score,dives,updated_at&limit=1")
    return {"email": member["email"], "nickname": member["nickname"], "dive": rows[0] if rows else None}


@router.get("/workspace")
async def load_workspace(request: Request) -> dict:
    member = require_member(request)
    if request.headers.get("x-workspace-owner", member["uid"]) != member["uid"]:
        raise HTTPException(409, "Your signed-in account changed. Reload before restoring your workspace.")
    rows = await run_in_threadpool(database, "GET", f"/rest/v1/member_workspace?user_id=eq.{member['uid']}&select=items,updated_at&limit=1")
    return rows[0] if rows else {"items": {}, "updated_at": None}


@router.put("/workspace")
async def save_workspace(request: Request, body: WorkspaceBody) -> dict:
    member = require_member(request)
    if request.headers.get("x-workspace-owner") != member["uid"]:
        raise HTTPException(409, "Your signed-in account changed. Reload before saving this workspace.")
    if set(body.items) - WORKSPACE_KEYS:
        raise HTTPException(400, "Only workspace journals and game progress can be saved; credentials are excluded.")
    if len(json.dumps(body.items).encode()) > 500_000:
        raise HTTPException(413, "This workspace is too large for cloud save (500 KB). Export a local backup instead.")
    rows = await run_in_threadpool(
        database, "POST", "/rest/v1/member_workspace?on_conflict=user_id",
        {"user_id": member["uid"], "items": body.items, "updated_at": datetime.now(timezone.utc).isoformat()},
        "resolution=merge-duplicates,return=representation",
    )
    return {"saved": True, "updated_at": rows[0]["updated_at"]}
