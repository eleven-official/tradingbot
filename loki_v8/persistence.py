"""LOKI v8 — optional Supabase persistence layer.

A tiny, dependency-free PostgREST client for logging trades, signals, equity
snapshots, regime changes, and training reports to a Supabase project. It is
designed to be configured *later*:

    SUPABASE_URL=https://<project>.supabase.co
    SUPABASE_SERVICE_KEY=<service-role key>   # or SUPABASE_KEY

Properties:
  * **No-op when unconfigured**: every log_* call returns immediately when
    the environment variables are missing, so the trading loop never blocks
    or crashes.
  * **Never raises**: network/API errors are counted and reported through
    ``status()``/in the web UI, with a cooldown after repeated failures.
  * **Fire-and-forget**: writes happen on a small background thread pool; the
    trading loop is never slowed by a slow network.

Create the tables by running ``supabase_schema.sql`` in the Supabase SQL
editor once. See README "Supabase Data Vault" for instructions.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_SCHEMA_PATH = "supabase_schema.sql"
_FAIL_COOLDOWN_SECS = 300

# Env vars are read on every call, so credentials added to the environment
# (even without a restart in local dev) are picked up automatically.


def _load_dotenv_once() -> None:
    """Load a local .env file if python-dotenv is available (best effort)."""
    if getattr(_load_dotenv_once, "_done", False):
        return
    _load_dotenv_once._done = True  # type: ignore[attr-defined]
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv()
    except Exception:  # noqa: BLE001 — dot-env is optional
        pass


class SupabaseLogger:
    """Fire-and-forget persistence to Supabase (PostgREST) tables."""

    def __init__(self):
        self._pool: Optional[ThreadPoolExecutor] = None
        self._futures: List[Any] = []
        self._lock = threading.Lock()
        self._successes = 0
        self._failures = 0
        self._last_error: Optional[str] = None
        self._last_success_at: Optional[str] = None
        self._last_attempt_at: float = 0.0
        self._muted_until: float = 0.0

    # ------------------------------------------------------------------
    # Configuration (reads env on every access — late config friendly)
    # ------------------------------------------------------------------
    def url(self) -> str:
        _load_dotenv_once()
        return (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")

    def key(self) -> str:
        _load_dotenv_once()
        return (
            os.environ.get("SUPABASE_SERVICE_KEY")
            or os.environ.get("SUPABASE_KEY")
            or os.environ.get("SUPABASE_ANON_KEY")
            or ""
        ).strip()

    def configured(self) -> bool:
        return bool(self.url()) and bool(self.key())

    # ------------------------------------------------------------------
    # Core write path
    # ------------------------------------------------------------------
    def _post(self, table: str, row: Dict[str, Any], run_in_pool: bool = True) -> Dict[str, Any]:
        """Insert one row into ``table``. Returns a status dict; never raises."""
        if not self.configured():
            return {"ok": False, "reason": "not_configured"}

        now = time.monotonic()
        with self._lock:
            if now < self._muted_until and run_in_pool:
                return {"ok": False, "reason": "cooldown_after_failures"}

        def _perform() -> Dict[str, Any]:
            try:
                import requests  # local import: keeps yfinance-free envs safe

                resp = requests.post(
                    f"{self.url()}/rest/v1/{table}",
                    json=[row],
                    headers={
                        "apikey": self.key(),
                        "Authorization": f"Bearer {self.key()}",
                        "Content-Type": "application/json",
                        "Prefer": "return=minimal",
                    },
                    timeout=(2.0, 5.0),
                )
                ok = resp.status_code in (200, 201, 202, 204)
                with self._lock:
                    if ok:
                        self._successes += 1
                        self._last_success_at = datetime.now().isoformat(timespec="seconds")
                    else:
                        self._failures += 1
                        self._last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                        self._maybe_mute()
                return {"ok": ok, "error": None if ok else self._last_error}
            except Exception as exc:  # noqa: BLE001 — logging must never crash trading
                with self._lock:
                    self._failures += 1
                    self._last_error = f"{type(exc).__name__}: {exc}"
                    self._maybe_mute()
                return {"ok": False, "error": self._last_error}

        if run_in_pool:
            self._ensure_pool()
            try:
                fut = self._pool.submit(_perform)  # type: ignore[union-attr]
                self._futures.append(fut)
                return {"ok": True, "queued": True}
            except Exception:  # noqa: BLE001
                return _perform()
        return _perform()

    def _maybe_mute(self) -> None:
        """Pause background logging for a while after repeated failures."""
        if self._failures % 3 == 0:
            self._muted_until = time.monotonic() + _FAIL_COOLDOWN_SECS
            logger.warning(
                "supabase: muting logs for %ss after repeated failures: %s",
                _FAIL_COOLDOWN_SECS,
                self._last_error,
            )

    def _ensure_pool(self) -> None:
        if self._pool is None:
            self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="loki-supabase")

    def flush(self, timeout: float = 10.0) -> None:
        """Wait for queued background writes (tests / graceful shutdown)."""
        pending, self._futures = self._futures, []
        for fut in pending:
            try:
                fut.result(timeout=timeout)
            except Exception:  # noqa: BLE001 — result errors already counted
                pass

    # ------------------------------------------------------------------
    # Status / test
    # ------------------------------------------------------------------
    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "configured": self.configured(),
                "successes": self._successes,
                "failures": self._failures,
                "last_error": self._last_error,
                "last_success_at": self._last_success_at,
                "muted": time.monotonic() < self._muted_until,
                "schema_file": _SCHEMA_PATH,
                "env_vars": ["SUPABASE_URL", "SUPABASE_SERVICE_KEY (or SUPABASE_KEY)"],
            }

    def test_connection(self, table: str = "loki_events") -> Dict[str, Any]:
        """Synchronous write-and-verify used by the web UI's test button."""
        result = self._post(
            table,
            {
                "kind": "connection_test",
                "payload": {"at": datetime.now().isoformat(timespec="seconds")},
            },
            run_in_pool=False,
        )
        return result

    # ------------------------------------------------------------------
    # Domain helpers (all best-effort)
    # ------------------------------------------------------------------
    def log_trade(
        self,
        *,
        symbol: str = "",
        side: str = "",
        qty: float = 0.0,
        entry_price: float = 0.0,
        exit_price: float = 0.0,
        pnl: float = 0.0,
        pnl_pct: float = 0.0,
        exit_reason: str = "",
        mode: str = "paper",
        source: str = "engine",
        equity_at_trade: float = 0.0,
        opened_at: Optional[str] = None,
        closed_at: Optional[str] = None,
    ) -> None:
        self._post(
            "loki_trades",
            {
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "exit_reason": exit_reason,
                "mode": mode,
                "source": source,
                "equity_at_trade": equity_at_trade,
                "opened_at": opened_at,
                "closed_at": closed_at or _now_iso(),
            },
        )

    def log_signal(
        self,
        *,
        symbol: str = "",
        action: str = "",
        score: float = 0.0,
        confidence: float = 0.0,
        entry_price: float = 0.0,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        regime: str = "",
        timeframe: str = "",
    ) -> None:
        self._post(
            "loki_signals",
            {
                "symbol": symbol,
                "action": action,
                "score": score,
                "confidence": confidence,
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "regime": regime,
                "timeframe": timeframe,
            },
        )

    def log_equity_snapshot(
        self,
        *,
        equity: float = 0.0,
        cash: float = 0.0,
        open_positions: int = 0,
        mode: str = "paper",
    ) -> None:
        self._post(
            "loki_equity_snapshots",
            {
                "equity": equity,
                "cash": cash,
                "open_positions": open_positions,
                "mode": mode,
            },
        )

    def log_regime_event(
        self,
        *,
        symbol: str = "",
        from_state: str = "",
        to_state: str = "",
        confidence: float = 0.0,
    ) -> None:
        self._post(
            "loki_regime_events",
            {
                "symbol": symbol,
                "from_state": from_state,
                "to_state": to_state,
                "confidence": confidence,
            },
        )

    def log_training_report(self, *, period: str = "", payload: Any = None) -> None:
        self._post(
            "loki_training_reports",
            {
                "period": period,
                "payload": _jsonable(payload),
            },
        )


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _jsonable(value: Any) -> Any:
    try:
        import json

        return json.loads(json.dumps(value, default=str))
    except Exception:  # noqa: BLE001
        return {"unserializable": str(value)[:500]}


_logger: Optional[SupabaseLogger] = None


def get_logger() -> SupabaseLogger:
    global _logger
    if _logger is None:
        _logger = SupabaseLogger()
    return _logger


def status() -> Dict[str, Any]:
    return get_logger().status()
