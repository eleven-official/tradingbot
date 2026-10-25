"""Site access control: fun-but-real gate code, sessions, and accounts.

The public deployment asks visitors for an access code before the workspace
opens, and then for an email/password account so the experience can greet the
user by their chosen nickname. Supabase stores the accounts; the browser never
talks to Supabase directly — everything is proxied through this server, so no
key ever reaches the client and only a signed first-party cookie is set.

Activation rules:
- The gate engages only for remote deployments (``VERCEL`` set) or when the
  launcher explicitly turns it on (``LOKI_SITE_GATE=1``). The local desktop
  launcher experience stays open, as designed by the fusion workspace.
- The access code defaults to a surprise value and stays configurable via
  ``LOKI_SITE_CODE`` so it can be changed without a deploy.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import time
import unicodedata
from typing import Any, Dict, Optional

import requests
from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)

GATE_COOKIE = "loki_gate"
SESSION_COOKIE = "loki_session"
TERMS_COOKIE = "loki_terms"
GATE_MAX_AGE = 30 * 24 * 3600
SESSION_MAX_AGE = 14 * 24 * 3600
_DEFAULT_CODE = "flathead"

# The Terms of Use a visitor ticks before the door opens. Version stamps every
# acceptance cookie: bump TERMS_VERSION whenever the document changes, and every
# browser re-gates once to accept the new words.
TERMS_VERSION = 3
TERMS_UPDATED = "2026-10-25"

_COOKIE_SALT = b"loki-site-access-v1"
_PROCESS_SECRET = secrets.token_bytes(32)

# Every environment name a deployment might put the Supabase service credential
# under — hand-set SUPABASE_SERVICE_KEY / SUPABASE_KEY, or the Supabase–Vercel
# integration's SUPABASE_SECRET_KEY / SUPABASE_SERVICE_ROLE_KEY. The tests use
# this list to wipe all of them, so guest-mode assertions stay honest.
SUPABASE_KEY_ENV_NAMES = (
    "SUPABASE_SERVICE_KEY",
    "SUPABASE_KEY",
    "SUPABASE_SECRET_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
)


def gate_enabled() -> bool:
    """True when the access gate should guard the website."""
    return bool(os.environ.get("VERCEL")) or os.environ.get("LOKI_SITE_GATE") == "1"


def expected_code() -> str:
    raw = os.environ.get("LOKI_SITE_CODE") or _DEFAULT_CODE
    return _normalize_code(raw)


_PUNCTUATION = set(".,!?'\";:-_~`@#$%^&*()+={}[]|\\/<>\u00b7")


def _normalize_code(value: str) -> str:
    """Lowercase, drop punctuation/padding, and collapse inner space runs."""
    value = unicodedata.normalize("NFKC", value or "").strip().lower()
    value = "".join(ch for ch in value if ch not in _PUNCTUATION)
    return " ".join(value.split())


def code_matches(candidate: str) -> bool:
    guess = _normalize_code(candidate or "")
    if not guess:
        return False
    target = expected_code()
    squash = lambda s: s.replace(" ", "")  # noqa: E731 - tiny local normalizer
    return hmac.compare_digest(guess, target) or hmac.compare_digest(squash(guess), squash(target))


_NICKNAME_ALLOWED = set("abcdefghijklmnopqrstuvwxyz0123456789 -_")


def clean_nickname(value: str) -> str:
    """Validate a display name: 2-24 characters of letters/digits/space/-/_."""
    value = unicodedata.normalize("NFKC", value or "").strip()
    value = " ".join(value.split())
    if not 2 <= len(value) <= 24 or any(ch not in _NICKNAME_ALLOWED for ch in value.lower()):
        return ""
    return value


# ---------------------------------------------------------------------------
# Gate brute-force throttle: best-effort, in-memory, per client IP.
# ---------------------------------------------------------------------------
_GATE_ATTEMPTS: Dict[str, list] = {}
_GATE_ATTEMPT_LOCK = threading.Lock()
_GATE_ATTEMPT_WINDOW = 300.0
_GATE_ATTEMPT_LIMIT = 10


def _prune(stamps: list, now: float) -> list:
    return [t for t in stamps if now - t < _GATE_ATTEMPT_WINDOW]


def gate_rate_limited(client_ip: str) -> bool:
    now = time.time()
    with _GATE_ATTEMPT_LOCK:
        stamps = _prune(_GATE_ATTEMPTS.get(client_ip, []), now)
        _GATE_ATTEMPTS[client_ip] = stamps
        return len(stamps) >= _GATE_ATTEMPT_LIMIT


def record_gate_failure(client_ip: str) -> None:
    now = time.time()
    with _GATE_ATTEMPT_LOCK:
        stamps = _prune(_GATE_ATTEMPTS.get(client_ip, []), now)
        stamps.append(now)
        _GATE_ATTEMPTS[client_ip] = stamps


def clear_gate_failures(client_ip: str) -> None:
    with _GATE_ATTEMPT_LOCK:
        _GATE_ATTEMPTS.pop(client_ip, None)


def _secret() -> bytes:
    explicit = (os.environ.get("LOKI_GATE_SECRET") or "").strip()
    if explicit:
        return hashlib.sha256(_COOKIE_SALT + explicit.encode()).digest()
    material = f"{os.environ.get('SUPABASE_URL') or ''}\0{_supabase_key()}"
    if _supabase_key():
        return hashlib.sha256(_COOKIE_SALT + material.encode()).digest()
    if os.environ.get("VERCEL"):
        # A URL is public and cannot be signing material. Fail closed across
        # instances until an operator supplies a real secret.
        return _PROCESS_SECRET
    # Local/dev deployments: stable-but-throwaway secret keeps cookies verifiable.
    return hashlib.sha256(_COOKIE_SALT + b"loki-local-dev-gate").digest()


def _sign(payload: str) -> str:
    return hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def issue_gate_cookie_value() -> str:
    payload = str(int(time.time()) + GATE_MAX_AGE)
    return f"{payload}.{_sign(payload)}"


def verify_gate_cookie_value(value: Optional[str]) -> bool:
    if not value or "." not in value:
        return False
    payload, signature = value.rsplit(".", 1)
    if not hmac.compare_digest(_sign(payload).encode("ascii"), signature.encode("utf-8")):
        return False
    try:
        return float(payload) >= time.time()
    except ValueError:
        return False


def issue_terms_cookie_value() -> str:
    """A signed acceptance record: which terms version, accepted when.

    The payload is plain digits (``version.timestamp``) — cookie jars along the
    way wrap fancy characters in extra quotes, and a signature checked over a
    mis-quoted blob would silently fail. Dots and digits survive every jar.
    """
    payload = f"{TERMS_VERSION}.{int(time.time())}"
    return f"{payload}.{_sign(payload)}"


def read_terms_cookie_value(value: Optional[str]) -> int:
    """The accepted terms version, or 0 when nothing valid was accepted."""
    if not value:
        return 0
    cleaned = value.strip().strip('"')  # some cookie jars quote values defensively
    if "." not in cleaned:
        return 0
    payload, signature = cleaned.rsplit(".", 1)
    if not hmac.compare_digest(_sign(payload).encode("ascii"), signature.encode("utf-8")):
        return 0
    parts = payload.split(".")
    if len(parts) != 2:
        return 0
    try:
        version = int(parts[0])
    except ValueError:
        return 0
    return version if version > 0 else 0


def issue_session_cookie_value(uid: str, email: str, nickname: str) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps(
            {"uid": uid, "email": email, "nickname": nickname, "iat": int(time.time())},
            separators=(",", ":"),
        ).encode("utf-8")
    ).decode("ascii")
    return f"{payload}.{_sign(payload)}"


def read_session_cookie_value(value: Optional[str]) -> Optional[Dict[str, Any]]:
    if value:
        value = value.strip('"')
    if not value or "." not in value:
        return None
    payload, signature = value.rsplit(".", 1)
    if not hmac.compare_digest(_sign(payload).encode("ascii"), signature.encode("utf-8")):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        issued = int(data.get("iat") or 0)
    except (ValueError, TypeError, OverflowError):
        return None
    if not 0 <= time.time() - issued <= SESSION_MAX_AGE:
        return None
    if not all(isinstance(data.get(key), str) and data[key] for key in ("uid", "email", "nickname")):
        return None
    return data


# ---------------------------------------------------------------------------
# Supabase account proxy — the browser never sees any key or Supabase cookie.
# ---------------------------------------------------------------------------
def accounts_available() -> bool:
    try:
        _supabase_config()
        return True
    except HTTPException:
        return False


def _supabase_key() -> str:
    """The project's service credential, under whatever name the deployment used.

    Deployments wire accounts two ways: an explicit SUPABASE_SERVICE_KEY or
    SUPABASE_KEY set by hand, or the Supabase–Vercel integration, which injects
    SUPABASE_SECRET_KEY / SUPABASE_SERVICE_ROLE_KEY. One fixed lookup order —
    and _secret() must derive from this same resolution, so signing material
    stays stable within a deployment.
    """
    for name in SUPABASE_KEY_ENV_NAMES:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def _supabase_config() -> tuple[str, str]:
    url = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    key = _supabase_key()
    if not url or not key or not url.endswith(".supabase.co"):
        raise HTTPException(
            503,
            "Accounts are not configured on this deployment; the workspace still works as a guest.",
        )
    return url, key


def _supa_headers(key: str) -> Dict[str, str]:
    headers = {"apikey": key, "Content-Type": "application/json"}
    # Opaque server secrets use just the apikey header; legacy JWTs need Bearer.
    if not key.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _supa_request(method: str, path: str, *, json_body: Optional[dict] = None) -> Dict[str, Any]:
    url, key = _supabase_config()
    try:
        response = requests.request(
            method,
            f"{url}{path}",
            json=json_body,
            headers=_supa_headers(key),
            timeout=15,
        )
    except requests.RequestException as exc:
        logger.warning("Supabase auth network failure: %s", exc.__class__.__name__)
        raise HTTPException(503, "The account service is unreachable; try again shortly.") from exc
    if 200 <= response.status_code < 300:
        try:
            return response.json() or {}
        except ValueError:
            return {}
    if response.status_code == 422 or response.status_code == 400:
        detail = "That email or password was not accepted (passwords need 8+ characters)."
        try:
            body = response.json()
            ident = str(body.get("msg") or body.get("error_description") or body.get("error") or "")
            if "invalid login credentials" in ident.lower() or "invalid credentials" in ident.lower():
                # Supabase answers 400 (not 401) for a wrong password; without
                # this mapping the visitor got told about password length.
                raise HTTPException(401, "Wrong email or password.")
            if "already" in ident.lower():
                detail = "That email already has an account — try signing in instead."
            elif "capacity" in ident.lower() or "signed up" in ident.lower():
                detail = "Sign-ups are temporarily limited; try again shortly."
        except ValueError:
            pass
        raise HTTPException(400, detail)
    if response.status_code == 401:
        raise HTTPException(401, "Wrong email or password.")
    logger.warning("Supabase auth %s %s -> %s", method, response.status_code, response.text[:120])
    raise HTTPException(503, "The account service had a hiccup; try again shortly.")


async def create_account(email: str, password: str, nickname: str) -> Dict[str, Any]:
    """Create a confirmed account with the nickname in user_metadata."""
    user = await run_in_threadpool(
        _supa_request,
        "POST",
        "/auth/v1/admin/users",
        json_body={
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"nickname": nickname},
        },
    )
    return user


async def sign_in_with_password(email: str, password: str) -> Dict[str, Any]:
    """Password grant; returns the Supabase user object (session stays server-side)."""
    grant = await run_in_threadpool(
        _supa_request,
        "POST",
        "/auth/v1/token?grant_type=password",
        json_body={"email": email, "password": password},
    )
    return grant.get("user") or {}


async def update_nickname(uid: str, nickname: str) -> Dict[str, Any]:
    # Supabase's admin update endpoint answers 405 to PATCH (verified live):
    # it takes PUT /auth/v1/admin/users/{uid}.
    return await run_in_threadpool(
        _supa_request,
        "PUT",
        f"/auth/v1/admin/users/{uid}",
        json_body={"user_metadata": {"nickname": nickname}},
    )
