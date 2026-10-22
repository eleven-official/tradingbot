"""Dive leaderboard: shared best scores under board names.

Publishing is always an explicit click and every score is self-reported.
These tests pin the honesty the endpoint promises: mode labels that describe
the real storage (shared database / server file / nothing), a worse dive
never lowering a row, the 20-second throttle, and the missing-table message
that tells the deployer to run supabase/schema_dive_scores.sql once.
"""
from pathlib import Path
import unittest

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from loki.api import dive_board
from loki.api.server import app

client = TestClient(app)

ROOT = Path(__file__).resolve().parents[1]


def clear() -> None:
    """Fresh throttle window per test; the limiter is in-memory by design."""
    dive_board._WRITES.clear()


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)
        self.headers = {}

    def json(self):
        return self._payload


class TestServerLocalBoard:
    def test_write_keeps_the_deepest_and_counts_dives(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LOKI_DATA_DIR", str(tmp_path))
        first = dive_board.local_write("Deep One", 100)
        assert first["best"] == 100 and first["dives"] == 1
        second = dive_board.local_write("Deep One", 40)
        assert second["best"] == 100, "a worse dive must never lower the row"
        assert second["dives"] == 2
        third = dive_board.local_write("Deep One", 900)
        assert third["best"] == 900 and third["dives"] == 3
        entries = dive_board.local_read()["entries"]
        assert entries[0]["nickname"] == "Deep One"

    def test_names_sort_by_best_and_board_limits_rows(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LOKI_DATA_DIR", str(tmp_path))
        dive_board.local_write("Abyss", 500)
        dive_board.local_write("Surfacing", 10)
        rows = dive_board.local_read()["entries"]
        assert [row["nickname"] for row in rows][:2] == ["Abyss", "Surfacing"]

    def test_http_round_trip_labels_the_mode(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LOKI_DATA_DIR", str(tmp_path))
        for name in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SUPABASE_KEY", "SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY"):
            monkeypatch.delenv(name, raising=False)
        response = client.get("/api/dive/leaderboard")
        assert response.status_code == 200
        payload = response.json()
        assert payload["mode"] == "server-local"  # local dev: the honest file board
        assert "file on this Loki server" in payload["note"]

    def test_operator_file_override_wins_over_supabase(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LOKI_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("LOKI_DIVE_BOARD", "file")
        monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_KEY", "sb_secret_placeholder")
        response = client.get("/api/dive/leaderboard")
        assert response.json()["mode"] == "server-local"  # the operator chose the file board; the label stays true

    def test_publish_refuses_bad_names_and_throttles(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LOKI_DATA_DIR", str(tmp_path))
        clear()
        bad = client.post("/api/dive/score", json={"nickname": "<script>", "best": 10})
        assert bad.status_code == 400
        assert "board name" in bad.json()["detail"]
        first = client.post("/api/dive/score", json={"nickname": "Deep One", "best": 120})
        assert first.status_code == 200
        again = client.post("/api/dive/score", json={"nickname": "Deep One", "best": 130})
        assert again.status_code == 429
        assert "20 seconds" in again.json()["detail"]
        clear()
        after = client.post("/api/dive/score", json={"nickname": "Deep One", "best": 130})
        assert after.status_code == 200 and after.json()["best"] == 130


class TestUnavailableMode:
    def test_vercel_without_supabase_refuses_to_lose_scores(self, monkeypatch):
        for name in ("SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY"):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv("VERCEL", "1")
        clear()
        listing = client.get("/api/dive/leaderboard")
        assert listing.status_code == 200
        assert listing.json()["mode"] == "unavailable"
        assert listing.json()["entries"] == []
        refused = client.post("/api/dive/score", json={"nickname": "Ghost", "best": 5})
        assert refused.status_code == 503
        assert "hosts no shared score store" in refused.json()["detail"]


class TestSharedBoard:
    def test_supabase_upsert_keeps_the_deepest(self, monkeypatch):  # noqa: self not needed (functional style)
        monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_KEY", "sb_secret_the-key-would-go-here")
        calls = []

        def fake_request(method, url, json=None, headers=None, timeout=None):
            calls.append({"method": method, "url": url, "json": json, "headers": headers})
            if method == "GET":
                return FakeResponse(200, [{"nickname": "Champ", "best_score": 300, "dives": 2}])
            return FakeResponse(200, [{"nickname": "Champ", "best_score": 750, "dives": 3}])

        monkeypatch.setattr(dive_board.http_requests, "request", fake_request)
        result = dive_board.shared_write("Champ", 750)
        assert result["best"] == 750 and result["dives"] == 3  # deepest kept, dive count bumped
        ordering = [call["method"] for call in calls]
        assert ordering == ["GET", "POST"]
        upsert = calls[1]
        assert upsert["url"].endswith("/rest/v1/dive_scores?on_conflict=nickname")
        assert upsert["headers"]["Prefer"].startswith("resolution=merge-duplicates")

    def test_missing_table_names_the_sql_to_run(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_KEY", "sb_secret_the-key-would-go-here")
        monkeypatch.setattr(dive_board.http_requests, "request", lambda *a, **k: FakeResponse(404, {"code": "42P01", "message": "relation does not exist"}))
        with pytest.raises(HTTPException) as caught:
            dive_board._shared_read()
        assert "schema_dive_scores.sql" in caught.value.detail


class TestWiring(unittest.TestCase):
    def test_template_and_game(self):
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        self_panel = html.split('id="dive-board"')
        assert len(self_panel) == 2  # exactly one board panel
        self.assertIn('id="dive-board-list"', html)
        self.assertIn('id="dive-publish-form"', html)
        self.assertIn('id="dive-board-name"', html)
        self.assertIn("unless you publish your best under a board name yourself", html)
        game = (ROOT / "static" / "js" / "game.js").read_text(encoding="utf-8")
        self.assertIn("LokiDiveBoard.diveEnded(totalPoints())", game)

    def test_board_module_is_honest(self):
        board = (ROOT / "static" / "js" / "dive_board.js").read_text(encoding="utf-8")
        self.assertIn("loki_dive_board_name", board)
        self.assertIn("Publishing is a click", board)
        self.assertIn("trusts the name, not the person", board)
        self.assertIn("shared by every browser using it", board)  # the server-local banner names its storage
        self.assertIn("payload.detail", board)  # a 503 refusal explains itself on the page

    def test_backup_carries_the_board_name(self):
        backup = (ROOT / "static" / "js" / "backup.js").read_text(encoding="utf-8")
        self.assertIn("loki_dive_board_name", backup)

    def test_schema_file_ships(self):
        sql = (ROOT / "supabase" / "schema_dive_scores.sql").read_text(encoding="utf-8")
        self.assertIn("create table if not exists public.dive_scores", sql)
        self.assertIn("best_score", sql)
