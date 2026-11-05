
import pytest
from fastapi.testclient import TestClient

from core import loki_memory
from loki.api.server import app


@pytest.fixture
def vault(monkeypatch, tmp_path):
    monkeypatch.setenv("LOKI_MEMORY_DIR", str(tmp_path / "vault"))
    return tmp_path / "vault"


def test_notes_survive_new_reads_and_obsidian_edits(vault):
    name = loki_memory.remember("Review results weekly")
    assert loki_memory.recall("weekly")[0]["file"] == name
    (vault / name).write_text("# Revised note\nReview monthly", encoding="utf-8")
    assert not loki_memory.recall("weekly")
    assert "monthly" in loki_memory.recall("monthly")[0]["text"]


def test_recall_is_bounded_and_ignores_unrelated_or_oversized_files(vault):
    vault.mkdir()
    (vault / "private.md").write_text("not for Loki")
    (vault / "loki-note-big.md").write_text("x" * 9000)
    for i in range(8):
        loki_memory.remember(f"Review {i}")
    assert len(loki_memory.recall()) == 5
    assert not loki_memory.recall("not for Loki")


@pytest.mark.parametrize("text", ["", "x" * 2001, "password=example", "sb_secret_example"])
def test_invalid_or_credential_notes_are_not_saved(vault, text):
    with pytest.raises(ValueError):
        loki_memory.remember(text)
    assert not list(vault.glob("*.md"))


def test_chat_memory_requires_local_token(vault, monkeypatch):
    monkeypatch.setenv("LOKI_FUSION_LOCAL", "1")
    payload = {"message": "remember Review weekly", "context": {}}
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 1234)) as client:
        assert client.post("/api/copilot", json=payload).status_code == 403
        token = client.get("/api/fusion/capabilities").json()["local_token"]
        headers = {"X-Loki-Local-Token": token}
        saved = client.post("/api/copilot", json=payload, headers=headers)
        assert saved.status_code == 200
        assert saved.headers["cache-control"] == "private, no-store"
        recalled = client.post("/api/copilot", json={"message": "recall weekly"}, headers=headers)
        assert "Review weekly" in recalled.json()["text"]
        assert client.post("/api/copilot", json=payload,
                           headers={**headers, "Origin": "https://untrusted.test"}).status_code == 403


def test_normal_copilot_stays_stateless_and_public(vault):
    assert loki_memory.command("What is the market doing?") is None
    with TestClient(app) as client:
        assert client.post("/api/copilot", json={"message": "What is risk?"}).status_code == 200
    assert not vault.exists()
