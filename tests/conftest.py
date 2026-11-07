"""Offline tests must never discover the operator's real Supabase credentials."""
import pytest


@pytest.fixture(autouse=True)
def isolate_supabase_configuration(monkeypatch):
    for name in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SUPABASE_KEY",
                 "SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ANON_KEY"):
        monkeypatch.delenv(name, raising=False)
