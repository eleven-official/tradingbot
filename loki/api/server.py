from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from loki.version import __version__
from core.copilot import LokiCopilot
from core.risk_preview import preview_position
from core.strategy_lab import evaluate_strategy
from loki.api import site_access
from loki.api.ai_paper import router as ai_paper_router
from loki.api.fusion import router as fusion_router
from loki.api.broker_workspace import router as broker_workspace_router

app = FastAPI(
    title="Loki Trading Platform",
    version=__version__,
    description="Loki research workspace and read-only trading copilot",
)
app.include_router(fusion_router)
app.include_router(broker_workspace_router)
app.include_router(ai_paper_router)
from loki.api.paper_tools import router as paper_tools_router

app.include_router(paper_tools_router)


# Load the larger optional strategy engine only for terminal requests.
class AdvancedTerminal:
    def __init__(self):
        self.application = None

    async def __call__(self, scope, receive, send):
        if self.application is None:
            from loki.api.terminal_v8 import app as terminal_app

            self.application = terminal_app
        await self.application(scope, receive, send)


app.mount("/terminal", AdvancedTerminal(), name="advanced-terminal")

# Resolve assets independently of the process working directory.
repo_dir = Path(__file__).resolve().parents[2]
static_dir = repo_dir / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Templates dir
templates_dir = repo_dir / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Render the workspace; real orders use separately gated local routes."""
    context = {"request": request, "version": __version__}
    return templates.TemplateResponse(request=request, name="index.html", context=context)


# ---------------------------------------------------------------------------
# Site access: code gate + Supabase-backed personalized accounts (additive).
# The gate engages only on remote deployments (VERCEL) or when the launcher
# asks for it (LOKI_SITE_GATE=1); the local desktop experience stays open.
# ---------------------------------------------------------------------------
_GATED_PAGES = {"/", "/terminal", "/terminal/", "/paper-tools", "/paper-tools/"}


@app.middleware("http")
async def site_access_gate(request: Request, call_next):
    if not site_access.gate_enabled():
        return await call_next(request)
    path = request.scope.get("path", "")
    prefix = request.scope.get("root_path", "")
    if prefix and path.startswith(prefix):
        path = path[len(prefix) :] or "/"
    low = path.lower().rstrip("/") or "/"
    if (
        low == "/gate"
        or low.startswith("/static")
        or low.startswith("/api/auth")
        or low
        in (
            "/api/gate",
            "/health",
            "/api/health",
            "/favicon.ico",
            "/favicon.png",
        )
    ):
        return await call_next(request)
    needs_gate = low == "/login" or low in _GATED_PAGES
    if not needs_gate:
        return await call_next(request)
    if site_access.verify_gate_cookie_value(request.cookies.get(site_access.GATE_COOKIE)):
        return await call_next(request)
    if request.method == "GET":
        return RedirectResponse("/gate", status_code=303)
    return JSONResponse({"detail": "Enter the access code first."}, status_code=403)


@app.get("/gate", response_class=HTMLResponse, include_in_schema=False)
async def access_gate_page(request: Request):
    if site_access.verify_gate_cookie_value(request.cookies.get(site_access.GATE_COOKIE)):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request=request, name="gate.html", context={"version": __version__}
    )


@app.post("/api/gate", include_in_schema=False)
async def access_gate_submit(request: Request):
    client_ip = request.client.host if request.client else "unknown"
    if site_access.gate_rate_limited(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Too many tries — wait a few minutes.",
        )
    try:
        body = await request.json()
    except ValueError:
        body = {}
    if not site_access.code_matches(str((body or {}).get("code") or "")):
        site_access.record_gate_failure(client_ip)
        raise HTTPException(status_code=403, detail="That is not the code.")
    site_access.clear_gate_failures(client_ip)
    response = JSONResponse({"ok": True})
    response.set_cookie(
        site_access.GATE_COOKIE,
        site_access.issue_gate_cookie_value(),
        max_age=site_access.GATE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=bool(os.environ.get("VERCEL")),
    )
    return response


class AuthBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    nickname: Optional[str] = Field(default=None, max_length=24)


def _session_cookie(response: Response, uid: str, email: str, nickname: str) -> None:
    response.set_cookie(
        site_access.SESSION_COOKIE,
        site_access.issue_session_cookie_value(uid, email, nickname),
        max_age=site_access.SESSION_MAX_AGE,
        httponly=False,
        samesite="lax",
        secure=bool(os.environ.get("VERCEL")),
    )


@app.post("/api/auth/sign-up", include_in_schema=False)
async def auth_sign_up(body: AuthBody, response: Response):
    email = (body.email or "").strip().lower()
    nickname = site_access.clean_nickname(body.nickname or "")
    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        raise HTTPException(status_code=400, detail="Enter a valid email address.")
    if not nickname:
        raise HTTPException(
            status_code=400, detail="Pick a nickname (2-24 letters, numbers or dashes)."
        )
    user = await site_access.create_account(email, body.password, nickname)
    uid = str(user.get("id") or "")
    if not uid:
        raise HTTPException(
            status_code=503, detail="The account service did not confirm; try again."
        )
    _session_cookie(response, uid, email, nickname)
    return {"email": email, "nickname": nickname}


@app.post("/api/auth/login", include_in_schema=False)
async def auth_login(body: AuthBody, response: Response):
    email = (body.email or "").strip().lower()
    user = await site_access.sign_in_with_password(email, body.password)
    uid = str(user.get("id") or "")
    if not uid:
        raise HTTPException(
            status_code=503, detail="The account service did not confirm; try again."
        )
    metadata = user.get("user_metadata") or {}
    nickname = (
        site_access.clean_nickname(str(metadata.get("nickname") or "")) or email.split("@")[0][:24]
    )
    _session_cookie(response, uid, email, nickname)
    return {"email": email, "nickname": nickname}


@app.put("/api/auth/nickname", include_in_schema=False)
async def auth_update_nickname(request: Request, body: AuthBody, response: Response):
    session = site_access.read_session_cookie_value(request.cookies.get(site_access.SESSION_COOKIE))
    if not session or not session.get("uid"):
        raise HTTPException(status_code=401, detail="Sign in first.")
    nickname = site_access.clean_nickname(body.nickname or "")
    if not nickname:
        raise HTTPException(
            status_code=400, detail="Pick a nickname (2-24 letters, numbers or dashes)."
        )
    await site_access.update_nickname(str(session["uid"]), nickname)
    _session_cookie(response, str(session["uid"]), str(session["email"]), nickname)
    return {"email": session["email"], "nickname": nickname}


@app.post("/api/auth/logout", include_in_schema=False)
async def auth_logout(response: Response):
    response.delete_cookie(site_access.SESSION_COOKIE)
    return {"ok": True}


@app.get("/api/auth/session", include_in_schema=False)
async def auth_session(request: Request):
    session = site_access.read_session_cookie_value(request.cookies.get(site_access.SESSION_COOKIE))
    if not session:
        if site_access.accounts_available():
            raise HTTPException(status_code=401, detail="Not signed in.")
        return {"enabled": False}  # guest mode: local launcher without Supabase creds
    return {"enabled": True, "email": session.get("email"), "nickname": session.get("nickname")}


@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page(request: Request):
    return templates.TemplateResponse(
        request=request, name="login.html", context={"version": __version__}
    )


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bars: list[dict] = Field(min_length=161, max_length=5000)
    config: dict = Field(default_factory=dict)


@app.post("/api/research/evaluate")
def research(payload: ResearchRequest):
    try:
        return evaluate_strategy(payload.bars, payload.config)
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class CopilotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=2000)
    context: dict = Field(default_factory=dict)


@app.post("/api/copilot")
def copilot(payload: CopilotRequest):
    return LokiCopilot().respond(payload.message, payload.context).as_dict()


class SizingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)
    equity: float = Field(gt=0, le=1e12)
    entry: float = Field(gt=0, le=1e12)
    stop: float = Field(gt=0, le=1e12)
    risk_pct: float = Field(default=0.5, gt=0, le=5)
    max_exposure_pct: float = Field(default=20, gt=0, le=100)
    fee_bps: float = Field(default=10, ge=0, le=1000)
    slippage_bps: float = Field(default=5, ge=0, le=1000)


@app.post("/api/risk/preview")
def risk_preview(payload: SizingRequest):
    try:
        return preview_position(**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok", "service": "loki", "version": __version__})


@app.get("/favicon.ico", include_in_schema=False)
async def favicon_ico():
    # Prefer static/favicon.ico if present, fallback to repo root loki.ico if available.
    static_fav = static_dir / "favicon.ico"
    if static_fav.exists():
        return FileResponse(static_fav)
    root_fav = repo_dir / "loki.ico"
    if root_fav.exists():
        return FileResponse(root_fav)
    return Response(status_code=204)


@app.get("/favicon.png", include_in_schema=False)
async def favicon_png():
    static_fav = static_dir / "favicon.png"
    if static_fav.exists():
        return FileResponse(static_fav)
    return Response(status_code=204)
