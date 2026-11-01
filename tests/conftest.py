"""Offline tests must never discover the operator's real Supabase credentials."""
import pytest


@pytest.fixture(autouse=True)
def isolate_supabase_configuration(monkeypatch):
    from loki_v8 import persistence

    monkeypatch.setattr(persistence._load_dotenv_once, "_done", True, raising=False)
    for name in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SUPABASE_KEY",
                 "SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ANON_KEY"):
        monkeypatch.delenv(name, raising=False)
