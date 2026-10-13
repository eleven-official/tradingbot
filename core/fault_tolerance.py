"""
Fault-tolerance utilities for the Loki trading bot.

This module fills the gap between the structured exceptions in
``core.exceptions`` and the health monitoring in ``core.self_healing`` by
providing reusable, dependency-free primitives for:

* ``retry_with_backoff`` — exponential-backoff retries for flaky API/network
  calls (with jitter to avoid synchronised retry storms).
* ``run_safely`` — invoke any callable and swallow/log failures so an
  unhandled exception can never crash the main event loop during a live
  paper-trading session.

Both helpers use only the Python standard library so they can be dropped into
any module (sync or threaded) without adding dependencies.
"""
from __future__ import annotations

import logging
import random
import time
from functools import wraps
from typing import Any, Callable, Optional, Tuple, Type, TypeVar

logger = logging.getLogger(__name__)

# Generic return type for the decorator/helpers.
T = TypeVar("T")


def _compute_delay(
    attempt: int,
    base_delay: float,
    max_delay: float,
    backoff_factor: float,
    jitter: bool,
) -> float:
    """Compute the sleep duration for a given retry attempt.

    Args:
        attempt: One-based attempt number (attempt 1 is the first retry).
        base_delay: Initial delay in seconds.
        max_delay: Upper bound on the returned delay.
        backoff_factor: Multiplicative growth per attempt.
        jitter: If True, apply +/-20% random jitter.

    Returns:
        The delay in seconds, always clamped to ``[0, max_delay]``.
    """
    delay = base_delay * (backoff_factor ** (attempt - 1))
    if jitter:
        delay *= random.uniform(0.8, 1.2)
    return max(0.0, min(delay, max_delay))


def retry_with_backoff(
    *,
    max_attempts: int = 4,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    retry_exceptions: Tuple[Type[BaseException], ...] = (Exception,),
    on_retry: Optional[Callable[[BaseException, int, float], None]] = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Return a decorator that retries a callable with exponential backoff.

    The wrapped callable is attempted at most ``max_attempts`` times. If it
    raises an exception listed in ``retry_exceptions`` and attempts remain,
    the wrapper sleeps for an exponentially-growing delay and retries. Any
    exception *not* listed in ``retry_exceptions`` propagates immediately.

    Args:
        max_attempts: Total attempts (1 means no retry). Must be >= 1.
        base_delay: Delay in seconds before the first retry.
        max_delay: Cap on the delay between consecutive attempts.
        backoff_factor: Multiplier applied to the delay after each failure.
        jitter: Add +/-20% random jitter to the delay.
        retry_exceptions: Tuple of exception types that trigger a retry.
        on_retry: Optional callback invoked before each retry with
            ``(exception, attempt_number, delay_seconds)``.

    Returns:
        A decorator that wraps the target callable.

    Example:
        @retry_with_backoff(max_attempts=5, base_delay=0.5, retry_exceptions=(ConnectionError, TimeoutError))
        def fetch_quote(symbol: str) -> float: ...
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            attempt = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except retry_exceptions as exc:
                    attempt += 1
                    if attempt >= max_attempts:
                        raise
                    delay = _compute_delay(
                        attempt, base_delay, max_delay, backoff_factor, jitter
                    )
                    if on_retry is not None:
                        on_retry(exc, attempt, delay)
                    logger.warning(
                        "%s failed with %s — attempt %d/%d, retrying in %.2fs",
                        getattr(func, "__qualname__", func.__name__),
                        type(exc).__name__,
                        attempt,
                        max_attempts,
                        delay,
                    )
                    time.sleep(delay)

        return wrapper

    return decorator


def run_safely(
    func: Callable[..., T],
    *args: Any,
    default: Optional[T] = None,
    log_level: int = logging.ERROR,
    message: str = "",
    **kwargs: Any,
) -> Optional[T]:
    """Invoke ``func(*args, **kwargs)`` and never let an exception escape.

    This is the "graceful degradation" primitive: any raised exception is
    logged and ``default`` is returned, so a failing sub-system (data feed,
    notifier, analytics) cannot bring down the main loop.

    Args:
        func: The callable to invoke.
        *args: Positional arguments forwarded to ``func``.
        default: Value returned when ``func`` raises.
        log_level: Logging level used to report the failure.
        message: Optional human-readable label for the failing operation.
        **kwargs: Keyword arguments forwarded to ``func``.

    Returns:
        The callable's result, or ``default`` if it raised.
    """
    label = message or getattr(func, "__qualname__", func.__name__)
    try:
        return func(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - deliberate crash-proofing
        detail = f": {exc}" if str(exc) else ""
        logger.log(log_level, "%s failed with %s%s", label, type(exc).__name__, detail)
        return default
