from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from loki.version import __version__
from core.copilot import LokiCopilot
from core.risk_preview import preview_position
from core.strategy_lab import evaluate_strategy
from loki.api import rate_limit, site_access
from loki.api.ai_chat import router as ai_chat_router
from loki.api.ai_paper import router as ai_paper_router
from loki.api.analogue import router as analogue_router
from loki.api.broker_alpaca import router as broker_alpaca_router
from loki.api.broker_workspace import router as broker_workspace_router
from loki.api.cloud_research import router as cloud_research_router
from loki.api.dive_board import router as dive_board_router
from loki.api.dive_sessions import router as dive_sessions_router
from loki.api.funded import router as funded_router
from loki.api.fusion import router as fusion_router
from loki.api.indicator_page import router as indicator_page_router
from loki.api.live_markets import router as live_markets_router
from loki.api.member_data import router as member_router
from loki.api.news_desk import router as news_desk_router
from loki.api.paper_tools import router as paper_tools_router
from loki.api.revenue import router as revenue_router
from loki.api.trading_desk import router as trading_desk_router
from loki.api.watchtower import router as watchtower_router

app = FastAPI(
    title="Loki Trading Platform",
    version=__version__,
    description="Loki research workspace and read-only trading copilot",
)
for _router in (
    fusion_router,
    broker_workspace_router,
    ai_paper_router,
    ai_chat_router,
    paper_tools_router,
    watchtower_router,
    live_markets_router,
    broker_alpaca_router,
    trading_desk_router,
    news_desk_router,
    dive_board_router,
    dive_sessions_router,
    revenue_router,
    member_router,
    cloud_research_router,
    funded_router,
    analogue_router,
    indicator_page_router,
):
    app.include_router(_router)


# Scripts only from this site (no inline scripts anywhere), so injected
# markup cannot run code; styles allow inline for the component styling and
# nothing may frame the site except itself.
CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "font-src 'self' data:",
        "img-src 'self' data: blob:",
        "connect-src 'self'",
        "frame-ancestors 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
    )
)


@app.middleware("http")
async def member_privacy_boundary(request: Request, call_next):
    private = request.url.path.startswith(("/api/auth/", "/api/account/", "/api/ai/chat/"))
    protected_write = private or request.url.path == "/api/dive/score"
    if protected_write and request.method not in {"GET", "HEAD", "OPTIONS"}:
        from urllib.parse import urlsplit

        origin = request.headers.get("origin")
        cross_site = request.headers.get("sec-fetch-site") == "cross-site"
        if origin:
            parsed = urlsplit(origin)
            cross_site = (
                cross_site
                or parsed.netloc != request.headers.get("host")
                or parsed.scheme not in {"http", "https"}
            )
        if cross_site:
            return JSONResponse(
                {"detail": "Use this website to change your account or publish a score."},
                status_code=403,
                headers={"Cache-Control": "no-store"},
            )
    wait = rate_limit.check(request)
    if wait is not None:
        return JSONResponse(
            {"detail": "Too many requests from this connection — wait a moment and try again."},
            status_code=429,
            headers={"Retry-After": str(wait), "Cache-Control": "no-store"},
        )
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    if site_access.cookie_secure(request):
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if private:
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Vary"] = "Cookie"
    return response


# Resolve assets independently of the process working directory.
repo_dir = Path(__file__).resolve().parents[2]
static_dir = repo_dir / "static"


class FreshStaticFiles(StaticFiles):
    """Static files that ask the browser to revalidate every time.

    Static-mount responses default to heuristic caching, which lets browsers
    serve stale JavaScript after a deploy; `no-cache` forces a cheap ETag
    revalidation so a refreshed site is always the current one.
    """

    def file_response(self, *args: Any, **kwargs: Any) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


if static_dir.exists():
    app.mount("/static", FreshStaticFiles(directory=str(static_dir)), name="static")

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
_GATED_PAGES = {"/", "/account", "/paper-tools", "/paper-tools/", "/indicator", "/ai-chat"}


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
    has_gate = site_access.verify_gate_cookie_value(request.cookies.get(site_access.GATE_COOKIE))
    has_terms = (
        site_access.read_terms_cookie_value(request.cookies.get(site_access.TERMS_COOKIE))
        >= site_access.TERMS_VERSION
    )
    if has_gate and has_terms:
        return await call_next(request)
    if request.method == "GET":
        return RedirectResponse("/gate", status_code=303)
    return JSONResponse(
        {"detail": "Enter the access code and tick the terms first."},
        status_code=403,
    )


@app.get("/gate", response_class=HTMLResponse, include_in_schema=False)
async def access_gate_page(request: Request):
    has_gate = site_access.verify_gate_cookie_value(request.cookies.get(site_access.GATE_COOKIE))
    has_terms = (
        site_access.read_terms_cookie_value(request.cookies.get(site_access.TERMS_COOKIE))
        >= site_access.TERMS_VERSION
    )
    if has_gate and has_terms:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="gate.html",
        context={"version": __version__, "terms_version": site_access.TERMS_VERSION},
    )


@app.get("/terms", response_class=HTMLResponse)
async def terms_page(request: Request):
    """The public Terms of Use a visitor must tick at the gate — readable before any acceptance."""
    return templates.TemplateResponse(
        request=request,
        name="terms.html",
        context={
            "version": __version__,
            "terms_version": site_access.TERMS_VERSION,
            "terms_updated": site_access.TERMS_UPDATED,
        },
    )


def _policy_context() -> Dict[str, Any]:
    return {
        "version": __version__,
        "terms_version": site_access.TERMS_VERSION,
        "terms_updated": site_access.TERMS_UPDATED,
        "minimum_age": site_access.MINIMUM_AGE,
        "operator_name": (os.environ.get("LOKI_OPERATOR_NAME") or "").strip(),
        "operator_email": (os.environ.get("LOKI_OPERATOR_EMAIL") or "").strip(),
    }


@app.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    """Privacy Policy — public, readable before entering."""
    return templates.TemplateResponse(request=request, name="privacy.html", context=_policy_context())


@app.get("/cookies", response_class=HTMLResponse)
async def cookies_page(request: Request):
    """Cookie Policy — public, readable before entering."""
    return templates.TemplateResponse(request=request, name="cookies.html", context=_policy_context())


@app.get("/transparency", response_class=HTMLResponse)
async def transparency_page(request: Request):
    """Who runs Loki, how to reach them, and the plain-language privacy/data summary."""
    import os

    name = (os.environ.get("LOKI_OPERATOR_NAME") or "").strip()
    email = (os.environ.get("LOKI_OPERATOR_EMAIL") or "").strip()
    since = (os.environ.get("LOKI_OPERATOR_SINCE") or "").strip()
    from loki.api.loki_wording import PRIVACY_SUMMARY, RETENTION_SUMMARY, revenue_status

    status = revenue_status()
    contact = (
        f'<a href="mailto:{email}">{email}</a>'
        if email
        else "set by this deployment's operator — configure the contact address when publishing"
    )
    subject = name or "The operator of this Loki deployment"
    operated_on = f"(operating since {since}) " if since else ""
    return templates.TemplateResponse(
        request=request,
        name="transparency.html",
        context={
            "version": __version__,
            "operator_name": subject,
            "operated_since": operated_on,
            "contact_line": contact,
            "privacy_summary": PRIVACY_SUMMARY,
            "retention_summary": RETENTION_SUMMARY,
            "revenue_status": status,
        },
    )


@app.get("/account", response_class=HTMLResponse)
async def account_page(request: Request):
    if not site_access.read_session_cookie_value(request.cookies.get(site_access.SESSION_COOKIE)):
        return RedirectResponse("/login", status_code=303)
    response = templates.TemplateResponse(
        request=request, name="account.html", context={"version": __version__}
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


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
    if not isinstance(body, dict):
        raise HTTPException(
            status_code=400, detail="Send an object with the access code and terms acceptance."
        )
    # The tick comes before the code matters. Refusing an unticked consent is
    # not a code failure, so it must never feed the anti-brute-force timer.
    if body.get("accepted_terms") is not True:
        raise HTTPException(
            status_code=403,
            detail="Tick the terms box — that is the agreement, not a formality.",
        )
    # Age is confirmed, never collected: only the yes travels, no birth date.
    if body.get("confirmed_age") is not True:
        raise HTTPException(
            status_code=403,
            detail=f"Loki is for adults: confirm you are {site_access.MINIMUM_AGE} or older to enter.",
        )
    if not site_access.code_matches(str(body.get("code") or "")):
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
        secure=site_access.cookie_secure(request),
    )
    response.set_cookie(
        site_access.TERMS_COOKIE,
        site_access.issue_terms_cookie_value(),
        max_age=site_access.GATE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=site_access.cookie_secure(request),
    )
    return response


@app.post("/api/gate/forget", include_in_schema=False)
async def gate_forget(response: Response):
    """Shared-computer eraser: makes this browser un-remember site access."""
    response.delete_cookie(site_access.GATE_COOKIE, path="/")
    response.delete_cookie(site_access.TERMS_COOKIE, path="/")
    return {"ok": True, "forgotten": True}


class AuthBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    nickname: Optional[str] = Field(default=None, max_length=24)
    age_confirmed: Optional[bool] = None


class NicknameBody(BaseModel):
    # The nickname-update route only ever receives a nickname; sharing AuthBody
    # here made every PUT 422 because email/password are required fields on it.
    model_config = ConfigDict(extra="forbid")
    nickname: str = Field(default="", max_length=24)


def _session_cookie(response: Response, uid: str, email: str, nickname: str) -> None:
    response.set_cookie(
        site_access.SESSION_COOKIE,
        site_access.issue_session_cookie_value(uid, email, nickname),
        max_age=site_access.SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=site_access.cookie_secure(),
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
    if body.age_confirmed is not True:
        raise HTTPException(
            status_code=400,
            detail=f"Accounts are for adults: confirm you are {site_access.MINIMUM_AGE} or older.",
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
async def auth_update_nickname(request: Request, body: NicknameBody, response: Response):
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
async def auth_session(request: Request, response: Response):
    session = site_access.read_session_cookie_value(request.cookies.get(site_access.SESSION_COOKIE))
    if not session:
        if site_access.accounts_available():
            # A session probe is a question, not a failure: the honest
            # "not signed in" answer rides inside a 200 like every other
            # read on this site, so the browser console stays as clean as
            # the page it serves.
            return {"enabled": True, "authenticated": False}
        return {"enabled": False}  # guest mode: local launcher without Supabase creds
    # Upgrade existing browser-readable cookies too, without extending the
    # signed session's original lifetime.
    response.set_cookie(
        site_access.SESSION_COOKIE,
        request.cookies[site_access.SESSION_COOKIE],
        max_age=max(0, int(site_access.SESSION_MAX_AGE - (time.time() - int(session["iat"])))),
        httponly=True,
        samesite="lax",
        secure=site_access.cookie_secure(request),
    )
    return {"enabled": True, "email": session.get("email"), "nickname": session.get("nickname")}


# ---------------------------------------------------------------------------
# Display-currency reference rate (USD -> AUD), server-side with caching so
# the browser never makes cross-origin FX requests (CORS noise / blocking).
# ---------------------------------------------------------------------------
_FX_CACHE: Dict[str, Tuple[float, float]] = {}
_FX_TTL_SECONDS = 1800.0
_FX_FALLBACK_RATE = 1.53  # AUD per 1 USD, used if the rate service is down
# frankfurter.app answers HTTP 403 to python's stock "Python-urllib/x.y"
# User-Agent; an identifying custom UA is accepted like every other public
# provider this workspace reads.
_FX_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; LokiWorkspace/2.0; read-only USD-AUD display rate)"
}


def _fetch_usd_aud_sync() -> float:
    try:
        url = "https://api.frankfurter.dev/v1/latest?from=USD&to=AUD"
        request = urllib.request.Request(url, headers=_FX_HEADERS)  # noqa: S310 - fixed https URL
        with urllib.request.urlopen(request, timeout=10) as res:
            data = json.loads(res.read().decode())
        rate = float(data["rates"]["AUD"])
    except Exception:  # noqa: BLE001 - second source below
        # Backup source: Yahoo's public USD/AUD quote (same feed as the board).
        from loki.api.market_feed import fetch_quote

        rate = float(fetch_quote("AUD=X")["price"])
    if not rate > 0:
        raise ValueError("Rate feed returned a non-positive USD/AUD rate.")
    return rate


@app.get("/api/fx/rate", include_in_schema=False)
async def fx_rate():
    now = time.time()
    cached = _FX_CACHE.get("usd_aud")
    if cached and now - cached[0] < _FX_TTL_SECONDS:
        return {"from": "USD", "to": "AUD", "rate": cached[1], "live": True}
    try:
        rate = await asyncio.to_thread(_fetch_usd_aud_sync)
    except Exception as error:
        # A degraded rate must be diagnosable, not silent: the deployment log
        # says exactly why the bar had to fall back.
        logging.getLogger(__name__).warning(
            "FX rate fetch failed (%s: %s); serving %s fallback",
            error.__class__.__name__,
            error,
            _FX_FALLBACK_RATE,
        )
        if cached:
            # Service blip: serve the last known rate, flagged not-live.
            return {"from": "USD", "to": "AUD", "rate": cached[1], "live": False}
        return {"from": "USD", "to": "AUD", "rate": _FX_FALLBACK_RATE, "live": False}
    _FX_CACHE["usd_aud"] = (now, rate)
    return {"from": "USD", "to": "AUD", "rate": rate, "live": True}


@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page(request: Request):
    return templates.TemplateResponse(
        request=request, name="login.html", context={"version": __version__}
    )


@app.get("/ai-chat", response_class=HTMLResponse, include_in_schema=False)
async def ai_chat_page(request: Request):
    """Loki's private room: its own passcode area, separate from the workspace gate."""
    return templates.TemplateResponse(
        request=request, name="ai_chat.html", context={"version": __version__}
    )


@app.get("/revenue", response_class=HTMLResponse)
async def revenue_page(request: Request):
    """Public explainer for the 30% profit-share model; figures stay behind the operator key."""
    from loki.api.revenue import HOUSE_CUT_BPS, ledger_mode, _mode_note

    mode = ledger_mode()
    context = {
        "request": request,
        "version": __version__,
        "house_cut_bps": HOUSE_CUT_BPS,
        "ledger_mode": mode,
        "ledger_note": _mode_note(mode),
    }
    return templates.TemplateResponse(request=request, name="revenue.html", context=context)


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bars: list[dict] = Field(min_length=161, max_length=5000)
    config: dict = Field(default_factory=dict)


class ProofRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(min_length=1, max_length=2000)
    symbol: str = Field(default="", max_length=15)
    interval: str = Field(default="1h", max_length=8)
    bars: int = Field(default=1000, ge=300, le=3000)
    starting_capital: float = Field(default=None, gt=0, le=1e9)
    risk_percent: float = Field(default=None, ge=0.05, le=5.0)
    max_holding_bars: int = Field(default=20, ge=1, le=100)


_PROOF_GATE = asyncio.Semaphore(2)
_PROOF_RUN_TIMEOUT_SECONDS = 90.0
# Dedicated pool for the fetch + three replays. Cancellation marks the future
# but cannot stop a running thread, so the work belongs to its own pool: when
# the deadline fires the client still gets a prompt 503, and the portal's
# default-executor drain never waits on proof work.
_PROOF_EXECUTOR: ThreadPoolExecutor | None = None


def _proof_executor() -> ThreadPoolExecutor:
    global _PROOF_EXECUTOR
    if _PROOF_EXECUTOR is None:
        _PROOF_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="loki-proof")
    return _PROOF_EXECUTOR


@app.post("/api/proof/assess")
async def proof_assess(requestable: Request, payload: ProofRequest):
    """The Proof Engine: plain English -> fixed rules -> falsification battery -> evidence report.

    Abuse protection is explicit: a per-identity run quota (in-process, or
    shared across instances via the configured Upstash store), a bounded
    two-slot concurrency gate, and a budget covering the *whole* job — the
    public-feed fetch and all three replays. The engine itself checks the
    budget at each seam between battery levels and stops cleanly (503)
    instead of finishing work abandoned by a cancelled client; the request
    timeout backs that up, and the two-slot gate still bounds any orphaned
    worker thread's runway.
    """
    from loki.api.binance_market_data import MarketDataError, get_binance_spot_history
    from loki.api.proof_engine import (
        ProofDeadlineExceeded,
        ProofError,
        compile_spec,
        rate_limited,
        safe_assess,
    )

    client_ip = requestable.client.host if requestable.client else "unknown"
    if rate_limited(f"proof:{client_ip}"):
        raise HTTPException(
            status_code=429,
            detail="Proof Engine is rate limited — the same description and dataset reproduce "
            "the same report, so wait a minute instead of re-running it.",
        )

    # Compile BEFORE touching the feed: a bad description is a text error and
    # must read as one even when public market data is unreachable.
    try:
        compile_spec(payload.description)
    except ProofError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    async def _bounded_proof_run():
        # One gate and one deadline around fetch AND compute: the report the
        # client waits for can never exceed this process's 90-second budget.
        # The clock starts when the run begins, and proof_engine also checks
        # it between battery levels so an abandoned job stops itself instead
        # of burning capacity nobody is waiting on. Work runs on the dedicated
        # proof pool so a retry can not wedge the request loop's executor.
        loop = asyncio.get_running_loop()
        deadline = time.monotonic() + _PROOF_RUN_TIMEOUT_SECONDS

        def fetch_candles():
            return get_binance_spot_history(
                payload.symbol or "BTCUSDT", payload.interval, payload.bars
            )

        def run_assessment():
            return safe_assess(
                candles,
                payload.description,
                symbol=payload.symbol,
                interval=payload.interval,
                risk_percent=payload.risk_percent,
                starting_capital=payload.starting_capital,
                max_holding_bars=payload.max_holding_bars,
                deadline=deadline,
            )

        async with _PROOF_GATE:
            candles = await loop.run_in_executor(_proof_executor(), fetch_candles)
            return await loop.run_in_executor(_proof_executor(), run_assessment)

    try:
        return await asyncio.wait_for(_bounded_proof_run(), timeout=_PROOF_RUN_TIMEOUT_SECONDS)
    except MarketDataError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except ProofDeadlineExceeded as error:
        # The budget ran out mid-battery and the run stopped at the next seam.
        raise HTTPException(
            status_code=503,
            detail=str(error),
        ) from error
    except ProofError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except asyncio.TimeoutError as error:
        raise HTTPException(
            status_code=503,
            detail="The proof run timed out — try fewer candles while the feed recovers.",
        ) from error


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
def copilot(payload: CopilotRequest, request: Request, response: Response):
    from core import loki_memory
    from loki.api.fusion import _require_local_action, _private_response, _call

    memory_command = loki_memory.command(payload.message)
    if memory_command:
        _require_local_action(request)
        _private_response(response)
        text = _call(loki_memory.respond, *memory_command)
        return {
            "text": text,
            "intent": "memory",
            "evidence": [],
            "suggestions": ["show memory"],
            "conversation": {"topics": ["memory"], "symbol": None},
        }
    # Questions about the visitor's own workspace (portfolio, research,
    # council) stay with the context-aware copilot; general questions —
    # tickers, the market, terms, the AI itself — go to Loki's brain, which
    # runs the live AI engine and real quotes.
    if not _PERSONAL.search(payload.message) or re.search(r"\bportfolio ai\b", payload.message, re.I):
        from loki.api import loki_brain

        brain = loki_brain.answer(payload.message)
        if brain:
            symbols = brain.get("symbols") or []
            return {
                "text": brain["text"],
                "intent": f"brain:{brain['intent']}",
                "evidence": [],
                "suggestions": ["How's the market?", "How did the AI do?", "What is a stop loss?"],
                "conversation": {"topics": [brain["intent"]], "symbol": symbols[0] if symbols else None},
            }
    return LokiCopilot().respond(payload.message, payload.context).as_dict()


_PERSONAL = re.compile(
    r"\b(my|mine|we|our|us|portfolio|account|council|dataset|journal|imported|lose|lost|doing|next)\b", re.I
)


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


# ---------------------------------------------------------------------------
# Honest 404s: people get a themed page, machines keep machine JSON.
# ---------------------------------------------------------------------------
@app.exception_handler(StarletteHTTPException)
async def honest_http_exception(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith("/api/") or "text/html" not in (
        request.headers.get("accept") or ""
    ):
        # The original contract: machine-readable detail, real status codes.
        return JSONResponse(
            {"detail": exc.detail if exc.detail else "Not Found"},
            status_code=exc.status_code,
            headers=exc.headers,
        )
    if exc.status_code == 404:
        page = templates.TemplateResponse(
            request=request,
            name="404.html",
            context={"version": __version__},
        )
        page.status_code = 404
        return page
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)
