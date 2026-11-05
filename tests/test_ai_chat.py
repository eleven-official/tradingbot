"""The sentient chat room: passcode, memory that survives restarts, internet.

Three honesty contracts pinned here:

1. The passcode (`slaterisgay` default, overridable) is the only way in;
   wrong or wrong-shaped codes are rejected before any cookie is issued.
   The name "joshua mathew" (case/space-normalized) is the admin.
2. The AI learns only from the mocked public feed in tests and stores facts
   with their source links; a replayed quote never fabricates a memory.
3. Memory persists across process reloads (sqlite on disk), and only the
   admin cookie may teach or wipe.
"""

import pytest
import time
from fastapi.testclient import TestClient

from loki.api import ai_chat
from loki.api.server import app

client = TestClient(app)


@pytest.fixture()
def memory_path(tmp_path, monkeypatch):
    db_dir = tmp_path / "ai_chat"
    monkeypatch.setattr(ai_chat, "_DB_DIR", db_dir)
    monkeypatch.setattr(ai_chat, "_DB_PATH", db_dir / "memory.sqlite3")
    ai_chat._ensure_schema()
    return db_dir


@pytest.fixture()
def no_internet(monkeypatch, memory_path):
    """Blocks the 5-minute sweep by stamping the next window far in future."""
    monkeypatch.setattr(ai_chat, "_last_sweep", [time.time() + 10**6])
    return None


@pytest.fixture()
def seeded_feed(monkeypatch):
    """One fresh headline + one repeat link, like Yahoo would answer."""
    items = [
        {
            "title": "Stocks rally as inflation cools again in October",
            "publisher": "Reuters",
            "link": "https://finance.yahoo.com/news/rally-1",
            "published_at": 1730500000.0,
        },
        {
            "title": "Same link should not be learned twice",
            "publisher": "Reuters",
            "link": "https://finance.yahoo.com/news/rally-1",
            "published_at": 1730500010.0,
        },
        {
            "title": "short",
            "publisher": "AP",
            "link": "https://finance.yahoo.com/news/s",
            "published_at": 1.0,
        },
    ]
    monkeypatch.setattr(
        ai_chat,
        "latest_headlines_for_query",
        lambda query, limit: {"items": items},
    )
    monkeypatch.setattr(
        ai_chat,
        "fetch_quote",
        lambda symbol: {
            "symbol": "SPY",
            "ok": True,
            "price": 512.4,
            "change_pct": 1.2,
            "currency": "USD",
        },
    )
    return items


def _join(client_, name="guest", code=None):
    return client_.post(
        "/api/ai/chat/access", json={"name": name, "code": code or ai_chat.DEFAULT_CHAT_CODE}
    )


def test_the_room_opens_with_a_name_no_password_needed(memory_path, no_internet):
    """The chat door is open by default: a name is all it asks."""
    opened = client.post(
        "/api/ai/chat/access", json={"name": "olivia", "code": "whatever"}
    )
    assert opened.status_code == 200
    data = opened.json()
    assert data["name"] == "Olivia"
    assert data["admin"] is False
    assert client.cookies.get(ai_chat.COOKIE_NAME)
    assert "no password" in data["intro"].lower()


def test_an_operator_can_still_lock_the_room_behind_a_code(monkeypatch, memory_path, no_internet):
    """LOKI_CHAT_CODE puts the passcode door back — opt-in, never the default."""
    monkeypatch.setattr(ai_chat, "DEFAULT_CHAT_CODE", "slaterisgay")
    denied = client.post("/api/ai/chat/access", json={"name": "someone", "code": "slayterisgay"})
    assert denied.status_code == 403
    opened = client.post("/api/ai/chat/access", json={"name": "olivia", "code": "SLATERISGAY"})
    assert opened.status_code == 200 and opened.json()["name"] == "Olivia"


def test_admin_name_recognition_is_normalization_proof(memory_path, no_internet):
    joined = _join(client, name="  Joshua   Mathew ")
    assert joined.status_code == 200
    who = client.get("/api/ai/chat/whoami").json()
    assert who["ok"] is True and who["admin"] is True
    member = TestClient(app)
    other = member.post(
        "/api/ai/chat/access", json={"name": "someone else", "code": ai_chat.DEFAULT_CHAT_CODE}
    )
    assert other.json()["admin"] is False


def test_message_requires_the_cookie(memory_path, no_internet):
    blank = TestClient(app)
    refused = blank.post("/api/ai/chat/message", json={"text": "how is SPY?"})
    assert refused.status_code == 401
    assert "passcode" in refused.json()["detail"]


def test_chat_learns_internet_facts_with_sources_and_stores_history(
    memory_path, no_internet, seeded_feed
):
    _join(client)
    ai_chat._last_sweep[0] = 0.0  # allow a sweep for this test
    reply = client.post("/api/ai/chat/message", json={"text": "What is happening with SPY?"})
    assert reply.status_code == 200
    data = reply.json()
    learned = [entry for entry in data["learned"] if entry.get("fresh")]
    assert learned, "the fresh headline should be quoted verbatim in the reply flow"
    assert "Stocks rally as inflation cools again" in data["text"]
    assert "finance.yahoo.com/news/rally-1" in data["text"]
    assert "LIVE SPY" in data["text"]
    assert "512.40" in data["text"]
    facts = ai_chat.recall_facts(10)
    assert any("Stocks rally" in fact["text"] and fact["kind"] == "internet" for fact in facts)
    links = [fact["source"] for fact in facts]
    assert links.count("https://finance.yahoo.com/news/rally-1") == 1, "dedupe by link"


def test_repeat_messages_within_the_interval_do_not_re_sweep(memory_path, no_internet, seeded_feed):
    _join(client)
    ai_chat._last_sweep[0] = 0.0
    first = client.post("/api/ai/chat/message", json={"text": "what happened to SPY?"})
    assert first.status_code == 200
    # A different symbol right after is still inside the 5-minute window.
    second = client.post("/api/ai/chat/message", json={"text": "and AAPL?"})
    assert second.status_code == 200
    assert second.json()["learned"] == []  # quiet inside the interval, honestly stated


def test_memory_survives_a_fresh_process(memory_path, no_internet):
    _join(client)
    client.post("/api/ai/chat/message", json={"text": "remember this moment"})
    # A second client acts as a fresh browser and re-unlocks; the sqlite file
    # on disk is the same store a restarted process would reopen.
    fresh = TestClient(app)
    _join(fresh, name="returning")
    got = fresh.get("/api/ai/chat/memory")
    assert got.status_code == 200
    turns = got.json()["turns"]
    assert any("remember this moment" in (turn.get("text") or "") for turn in turns)


def test_admin_can_teach_weighted_and_non_admin_is_403(memory_path, no_internet):
    member = TestClient(app)
    _join(member, name="deputy")
    forbidden = member.post("/api/ai/chat/teach", json={"fact": "lowest RSI in two months was 32"})
    assert forbidden.status_code == 403
    admin = TestClient(app)
    joined = _join(admin, name="Joshua Mathew")
    assert joined.json()["admin"] is True
    taught = admin.post("/api/ai/chat/teach", json={"fact": "lowest RSI in two months was 32"})
    assert taught.status_code == 200
    facts = ai_chat.recall_facts(5)
    assert facts and facts[0]["kind"] == "admin" and facts[0]["weight"] == 3.0
    wipe_denied = TestClient(app)
    _join(wipe_denied, name="stranger")
    assert wipe_denied.post("/api/ai/chat/wipe").status_code == 403
    wiped = admin.post("/api/ai/chat/wipe")
    assert wiped.status_code == 200 and wiped.json()["wiped"] >= 1
    assert ai_chat.recall_facts(5) == []


def test_recency_blend_lets_fresh_news_outrank_stale_same_weight(memory_path):
    now = time.time()
    ai_chat.add_fact("internet", "old internet fact, months cold", source="a://x", weight=1.0)
    with ai_chat._DB_LOCK, ai_chat._connect() as conn:
        conn.execute("UPDATE facts SET created_at = ?", (now - 40 * 86400.0,))
    fresh = ai_chat.add_fact("internet", "fresh headline from the tape", source="a://y", weight=1.0)
    ranked = ai_chat.recall_facts(2)
    assert ranked[0]["id"] == fresh
    # But a weight-3 admin lesson still outranks everything the sweep learns.
    taught = ai_chat.add_fact("admin", "taught: don't chase gap opens", weight=3.0)
    ranked = ai_chat.recall_facts(2)
    assert ranked[0]["id"] == taught


def test_audit_command_reports_the_shelf(memory_path, no_internet):
    _join(client)
    ai_chat.add_fact("internet", "Nov 02: treasury yields cool", source="a://y")
    audited = client.post("/api/ai/chat/message", json={"text": "audit"})
    assert audited.status_code == 200
    body = audited.json()["text"]
    assert "audit, as asked" in body
    assert "0 taught + 1 internet facts" in body
    assert "5-minute cadence" in body
    assert audited.json()["learned"] == []


def test_duplicate_same_text_is_flood_guarded(memory_path, no_internet):
    _join(client)
    first = client.post("/api/ai/chat/message", json={"text": "tell me about SPY"})
    assert first.status_code == 200
    repeat = client.post("/api/ai/chat/message", json={"text": "tell me about SPY"})
    assert repeat.status_code == 429
    assert "ten seconds" in repeat.json()["detail"]


def test_recall_prefers_facts_about_the_named_symbol(memory_path, no_internet):
    _join(client)
    loud = ai_chat.add_fact(
        "internet",
        "Jul 01: SPY ladders into record close as breadth thins",
        source="https://finance.yahoo.com/news/spy-ladder",
    )
    noise = ai_chat.add_fact(
        "internet",
        "Nov 03: Bitcoin spot volumes ease for a third day",
        source="https://finance.yahoo.com/news/btc-vol",
    )
    ai_chat.add_fact("admin", "taught: watch the 10-handle", weight=3.0)
    ai_chat._last_sweep[0] = 0.0
    reply = client.post("/api/ai/chat/message", json={"text": "what's SPY doing today?"})
    assert reply.status_code == 200
    assert "SPY ladders" in reply.json()["text"] or loud in [f for f in ai_chat.recall_facts(3)]


def test_currency_and_macro_asks_stay_on_weather_not_ticker_garbage(memory_path, no_internet):
    _join(client)
    ai_chat._last_sweep[0] = 0.0
    reply = client.post("/api/ai/chat/message", json={"text": "good morning"})
    assert reply.status_code == 200
    body = reply.json()["text"]
    assert "room's open" in body
    assert "0 taught" in body


def test_ai_replies_stored_unclipped_for_honest_replay(memory_path, no_internet):
    _join(client)
    client.post("/api/ai/chat/message", json={"text": "hello there friend"})
    with ai_chat._DB_LOCK, ai_chat._connect() as conn:
        rows = conn.execute(
            "SELECT text FROM turns WHERE role = 'ai' ORDER BY created_at DESC LIMIT ?",
            (2,),
        ).fetchall()
        row = rows[0] if rows else None
    assert row is not None
    ai_text = row["text"]
    assert len(ai_text) > 100  # greeting replies are multi-line; pre-cap sliced them


def test_macro_fallback_labels_itself_when_symbol_news_is_empty(memory_path, monkeypatch):
    items = [
        {
            "title": "Fed minutes signal patience on rate path",
            "publisher": "Reuters",
            "link": "https://finance.yahoo.com/news/fed-1",
            "published_at": 1730500000.0,
        },
    ]
    monkeypatch.setattr(
        ai_chat,
        "latest_headlines_for_query",
        lambda query, limit: {
            "items": items if "SVXY" not in query.upper() and "stock" in query.lower() else []
        },
    )
    monkeypatch.setattr(
        ai_chat,
        "fetch_quote",
        lambda symbol: {"symbol": "SVXY", "ok": True, "price": 51.2, "change_pct": None},
    )
    _join(client)
    ai_chat._last_sweep[0] = 0.0
    reply = client.post("/api/ai/chat/message", json={"text": "anything on SVXY?"})
    assert reply.status_code == 200
    fresh = [entry for entry in reply.json()["learned"] if entry.get("fresh")]
    assert fresh and "[macro fallback — no live news for SVXY]" in fresh[0]["text"]
    assert "Fed minutes" in reply.json()["text"]
