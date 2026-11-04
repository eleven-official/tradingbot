"""Where the Proof Engine's per-identity run quota lives.

Serverless platforms run several instances of the same app, so an
in-process counter only caps the work seen by one instance (a floor, not
a wall). The two backends here:

* ``MemoryStore`` — the original bounded in-process sliding window. Always
  present; also the fail-over when a shared store is unreachable.
* ``UpstashStore`` — a fixed-window INCR counter via Upstash's Redis REST
  endpoint, honoured by every instance of the deployment. No new runtime
  dependency: configuration is two environment variables
  (``UPSTASH_REDIS_REST_URL`` + ``UPSTASH_REDIS_REST_TOKEN``). If either
  is missing, or the store flakes, ``hit`` falls back to the memory store
  so the door still shuts locally instead of standing open.

Both implement ``hit(key, now=None) -> bool`` (True = over quota) and
``reset()``. The deployment chooses the backend once per process.
"""

from __future__ import annotations

import json
import os
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

PROOF_RATE_WINDOW_SECONDS = 60.0
PROOF_RATE_MAX_PER_WINDOW = 8
_MEMORY_KEYS_MAX = 512

_UPSTASH_ENV_URL = "UPSTASH_REDIS_REST_URL"
_UPSTASH_ENV_TOKEN = "UPSTASH_REDIS_REST_TOKEN"
_UPSTASH_HTTP_TIMEOUT = 3.0


class MemoryStore:
    """Bounded sliding-window counter, per process.

    Exact and immediate, but only sees the identity's requests that landed
    on this instance — on a multi-instance deployment it is the floor
    under the shared store, not the whole wall.
    """

    def __init__(self, keys_max: int = _MEMORY_KEYS_MAX) -> None:
        self._keys_max = keys_max
        self._lock = threading.Lock()
        self._hits: dict[str, list[float]] = {}

    @property
    def degraded(self) -> bool:
        """Always False: the local counter never degrades, it is the floor."""
        return False

    def hit(self, key: str, now: float | None = None) -> bool:
        stamp = time.monotonic() if now is None else float(now)
        window = PROOF_RATE_WINDOW_SECONDS
        limit = PROOF_RATE_MAX_PER_WINDOW
        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                if len(self._hits) >= self._keys_max:
                    # Bounded key shelf: drop the oldest keys, never grow forever.
                    oldest = sorted(self._hits, key=lambda k: min(self._hits[k]))
                    for doomed in oldest[: self._keys_max // 4]:
                        self._hits.pop(doomed, None)
                hits = []
                self._hits[key] = hits
            window_hits = [hit for hit in hits if stamp - hit < window]
            if len(window_hits) >= limit:
                self._hits[key] = window_hits
                return True
            window_hits.append(stamp)
            self._hits[key] = window_hits
            return False

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


class UpstashStore:
    """Fixed-window INCR counters in a shared Upstash Redis, via REST.

    Every deployment instance reads and writes the same counters, so the
    per-identity quota is real across the platform, not per instance.
    On any store error the in-process memory store keeps counting, so an
    outage degrades to the floor instead of disabling the cap. The
    ``degraded`` property reports that state so callers (and tests) can
    see the limiter is running on its floor, not on the shared wall.
    """

    def __init__(self, url: str, token: str) -> None:
        self._url = url.rstrip("/")
        self._token = token
        self._fallback = MemoryStore()
        self._degraded = False

    @property
    def degraded(self) -> bool:
        """True once a store error pushed the counter onto the local floor.

        Cleared on the first successful shared-store exchange — the flag
        tracks the limiter's health, not a permanent verdict on the store.
        """
        return self._degraded

    def _rest(self, path: str) -> int:
        request = Request(
            f"{self._url}{path}",
            method="POST",
            headers={"Authorization": f"Bearer {self._token}"},
        )
        with urlopen(request, timeout=_UPSTASH_HTTP_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
        result = payload.get("result")
        if isinstance(result, bool) or not isinstance(result, (int, float)):
            raise ValueError("Upstash rate store returned a non-integer counter")
        return int(result)

    def hit(self, key: str, now: float | None = None) -> bool:
        stamp = time.time() if now is None else float(now)
        bucket = int(stamp // PROOF_RATE_WINDOW_SECONDS)
        encoded = quote(f"proof:r:{bucket}:{key}", safe="")
        try:
            count = self._rest(f"/incr/{encoded}")
            if count == 1:
                # First hit in the bucket arms the window's expiry.
                self._rest(f"/pexpire/{encoded}/{int(PROOF_RATE_WINDOW_SECONDS * 1000)}")
            self._degraded = False
            return count > PROOF_RATE_MAX_PER_WINDOW
        except (OSError, URLError, HTTPError, ValueError, KeyError, TypeError):
            # Shared store unreachable or unreadable: the local counter still
            # enforces the same quota for requests that land on this instance.
            self._degraded = True
            return self._fallback.hit(key, stamp)

    def reset(self) -> None:
        self._fallback.reset()


def select_backend() -> MemoryStore | UpstashStore:
    """Pick the deployment's store: Upstash when configured, memory otherwise.

    Configuration is read at process start; a Vercel/Upstash integration
    sets the environment variables once, and both long-running and
    serverless instances share the counters from then on.
    """
    url = os.environ.get(_UPSTASH_ENV_URL)
    token = os.environ.get(_UPSTASH_ENV_TOKEN)
    if url and token:
        return UpstashStore(url, token)
    return MemoryStore()
