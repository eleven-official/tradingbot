"""Offline tests must never discover the operator's real Supabase credentials."""
import pytest


@pytest.fixture(autouse=True)
def isolate_supabase_configuration(monkeypatch):
    for name in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SUPABASE_KEY",
                 "SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ANON_KEY"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def offline_brain(monkeypatch, request):
    """Loki's brain reads live data; the suite stays offline unless a test opts in."""
    if request.node.get_closest_marker("brain_data"):
        return
    from loki.api import loki_brain

    monkeypatch.setattr(loki_brain, "_ai_read", lambda symbol: None)
    monkeypatch.setattr(loki_brain, "_quotes", lambda symbols: [])
    monkeypatch.setattr(loki_brain, "_portfolio", lambda: None)
