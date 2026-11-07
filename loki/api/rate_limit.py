"""Per-client sliding-window rate limits for expensive or guessable endpoints.

In-memory and per-instance by design (no extra infrastructure): it caps
abuse from one client against one server instance — password guessing,
operator-key guessing, and hammering the heavy AI/market endpoints. Set
``LOKI_RATE_LIMITS=0`` to disable (the test suite does).
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Deque, Dict, Optional, Tuple

from fastapi import Request

_LOCK = threading.Lock()
_HITS: Dict[Tuple[str, str], Deque[float]] = {}
_MAX_KEYS = 20_000

# (method or "*", path prefix) -> (requests allowed, window seconds)
RULES: Tuple[Tuple[str, str, int, float], ...] = (
    ("POST", "/api/auth/login", 10, 300.0),
    ("POST", "/api/auth/sign-up", 5, 3600.0),
    ("POST", "/api/account/funded/login", 8, 300.0),
    ("POST", "/api/account/funded/connect", 8, 300.0),
    ("*", "/api/revenue/", 20, 600.0),
    ("POST", "/api/fusion/ai/step", 90, 60.0),
    ("GET", "/api/fusion/ai/portfolio", 30, 60.0),
    ("GET", "/api/fusion/ai/bars", 120, 60.0),
    ("*", "/api/markets/", 60, 60.0),
    ("POST", "/api/copilot", 60, 60.0),
    ("POST", "/api/desk/", 30, 60.0),
    ("POST", "/api/fusion/learn-history", 6, 60.0),
    ("POST", "/api/broker/alpaca/", 60, 60.0),
)


def enabled() -> bool:
    return os.environ.get("LOKI_RATE_LIMITS", "1") != "0"


def client_key(request: Request) -> str:
    """Client identity: the platform-set forwarded address on Vercel only.

    Elsewhere a client can write any X-Forwarded-For it likes, so the socket
    address is used instead.
    """
    if os.environ.get("VERCEL"):
        forwarded = request.headers.get("x-real-ip") or request.headers.get("x-forwarded-for", "")
        first = forwarded.split(",")[0].strip()
        if first:
            return first[:64]
    return (request.client.host if request.client else "unknown")[:64]


def rule_for(method: str, path: str) -> Optional[Tuple[str, int, float]]:
    for rule_method, prefix, limit, window in RULES:
        if (rule_method == "*" or rule_method == method) and path.startswith(prefix):
            return prefix, limit, window
    return None


def check(request: Request) -> Optional[int]:
    """Record a hit; return seconds to wait when the client is over its limit."""
    if not enabled():
        return None
    rule = rule_for(request.method, request.url.path)
    if rule is None:
        return None
    prefix, limit, window = rule
    key = (client_key(request), prefix)
    now = time.monotonic()
    with _LOCK:
        hits = _HITS.get(key)
        if hits is None:
            if len(_HITS) >= _MAX_KEYS:
                stale = [k for k, q in _HITS.items() if not q or now - q[-1] > 3600]
                for k in stale[: _MAX_KEYS // 2] or list(_HITS)[: _MAX_KEYS // 4]:
                    _HITS.pop(k, None)
            hits = _HITS[key] = deque()
        while hits and now - hits[0] > window:
            hits.popleft()
        if len(hits) >= limit:
            return max(1, int(window - (now - hits[0])) + 1)
        hits.append(now)
    return None


def reset() -> None:
    with _LOCK:
        _HITS.clear()
