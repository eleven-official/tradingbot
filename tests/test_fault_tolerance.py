"""
Tests for core.fault_tolerance — exponential-backoff retries and crash-proof invocation.
"""
import pytest

from core.fault_tolerance import retry_with_backoff, run_safely, _compute_delay


class _Boom(Exception):
    pass


class _Special(Exception):
    pass


def test_retry_succeeds_after_transient_failure(monkeypatch):
    """A callable that fails once then succeeds should return its result."""
    calls = {"n": 0}

    @retry_with_backoff(max_attempts=3, base_delay=0.01, max_delay=0.01, jitter=False)
    def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise _Boom("transient")
        return "ok"

    monkeypatch.setattr("core.fault_tolerance.time.sleep", lambda s: None)
    assert flaky() == "ok"
    assert calls["n"] == 2


def test_retry_gives_up_after_max_attempts(monkeypatch):
    """After max_attempts failures the last exception should propagate."""
    @retry_with_backoff(max_attempts=3, base_delay=0.01, max_delay=0.01, jitter=False)
    def always_fails():
        raise _Boom("permanent")

    monkeypatch.setattr("core.fault_tolerance.time.sleep", lambda s: None)
    with pytest.raises(_Boom):
        always_fails()


def test_retry_does_not_retry_unlisted_exceptions(monkeypatch):
    """Exceptions not in retry_exceptions should propagate immediately."""
    calls = {"n": 0}

    @retry_with_backoff(max_attempts=5, retry_exceptions=(_Boom,))
    def raises_special():
        calls["n"] += 1
        raise _Special("not retried")

    monkeypatch.setattr("core.fault_tolerance.time.sleep", lambda s: None)
    with pytest.raises(_Special):
        raises_special()
    assert calls["n"] == 1


def test_run_safely_returns_default_on_error():
    def boom():
        raise ValueError("kaboom")

    assert run_safely(boom, default=42) == 42


def test_run_safely_returns_result_on_success():
    def ok(x):
        return x * 2

    assert run_safely(ok, 21) == 42


def test_delay_is_capped_at_max():
    assert _compute_delay(3, base_delay=1.0, max_delay=5.0, backoff_factor=10.0, jitter=False) == 5.0
    assert _compute_delay(2, base_delay=1.0, max_delay=5.0, backoff_factor=2.0, jitter=False) == 2.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
