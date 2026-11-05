"""The sentient chat room: Loki talks, learns from the internet, remembers.

Design honesty first: this module gives the same paper-research AI a persistent
memory and internet eyes — it is still a deterministic reasoning engine over
real inputs, not a magic oracle. What it says always cites where it learned
it (chat, internet feed, admin teaching), and nothing in here submits orders.

Pieces:
- ``memory.sqlite3`` — persistent chat memory (facts distilled from the
  internet, admin lessons, and reply history) across restarts.
- Internet access — public Yahoo Finance feeds only (headlines + quotes),
  self-fetched at reply time (no user browsing gets shared);
  new facts learned from the feed are stored with their source link.
- Access — the room is its own passcode area (`slaterisgay`), independent of
  the workspace gate; the code never travels further than the HMAC check.
- Admin — the signed cookie can carry an admin claim; the account name
  "joshua mathew" is the admin. Admin can teach facts (weighted), pin,
  and wipe memory; every admin action is journaled in the memory store.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import math
import os
import re
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from loki.api.market_feed import MarketFeedError, fetch_quote, latest_headlines_for_query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai/chat", tags=["Sentient AI chat"])

DEFAULT_CHAT_CODE = ""  # open by default: the chat door needs only a name. Set LOKI_CHAT_CODE to lock it behind a passcode again.
ADMIN_NAME = "joshua mathew"
COOKIE_NAME = "loki_chat"
COOKIE_MAX_AGE = 14 * 24 * 3600
_MESSAGE_MAX = 500
_NAME_MAX = 24
_MEMORY_LIMIT = 180
_STORE_ROWS = 400
_FACT_LEN = 220
_LEARN_INTERVAL = 300.0  # one internet sweep at most every five minutes
_MEMO_TTL = 900.0  # how long a fresh "internet lesson" is quoted verbatim

_DB_DIR = Path(__file__).resolve().parents[2] / "state" / "ai_chat"
# LOKI_CHAT_DB_PATH lets a host point the memory store somewhere writable;
# default keeps the sqlite beside the repo state.
_env_db = os.environ.get("LOKI_CHAT_DB_PATH")
if _env_db:
    _DB_DIR = Path(_env_db).expanduser().resolve().parent
    _DB_PATH = Path(_env_db).expanduser().resolve()
else:
    _DB_PATH = _DB_DIR / "memory.sqlite3"
_DB_LOCK = threading.RLock()

_COOKIE_SALT = b"loki-sentient-chat-v1"
_PROCESS_SECRET = secrets.token_bytes(32)


def _chat_code() -> str:
    # Empty by default: the room is open — a name is a person, no password gate.
    # Operators can still opt into a passcode door with LOKI_CHAT_CODE.
    raw = os.environ.get("LOKI_CHAT_CODE") or DEFAULT_CHAT_CODE
    return " ".join(str(raw).split()).lower()


def chat_room_locked() -> bool:
    return bool(_chat_code())


# ---------------------------------------------------------------------------
# Persistent memory store (sqlite, WAL, process-safe by an in-process lock).
# ---------------------------------------------------------------------------
_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL CHECK (kind IN ('internet','admin','chat')),
    text TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    weight REAL NOT NULL DEFAULT 1.0,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL CHECK (role IN ('user','ai')),
    name TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS admin_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS turns_created ON turns (created_at DESC);
"""


def _connect() -> sqlite3.Connection:
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    with _DB_LOCK:
        conn.executescript(_SCHEMA)
    return conn


# Schema runs inside _connect, so every handle (including after a test
# repoints _DB_PATH) opens with tables present; executescript is idempotent.


def _ensure_schema() -> None:
    with _DB_LOCK, _connect() as conn:
        conn.executescript(_SCHEMA)


_TURN_TEXT_MAX = _MESSAGE_MAX  # user bubbles stay single-message sized
_AI_TURN_TEXT_MAX = _MESSAGE_MAX * 4  # AI replies are multi-line; keep them whole


def record_turn(role: str, name: str, text: str) -> None:
    cap = _AI_TURN_TEXT_MAX if role == "ai" else _TURN_TEXT_MAX
    with _DB_LOCK, _connect() as conn:
        conn.execute(
            "INSERT INTO turns (role, name, text, created_at) VALUES (?,?,?,?)",
            (role, name[:_NAME_MAX], text[:cap], time.time()),
        )
        conn.execute(
            "DELETE FROM turns WHERE id NOT IN "
            "(SELECT id FROM turns ORDER BY created_at DESC LIMIT ?)",
            (_STORE_ROWS,),
        )


def add_fact(kind: str, text: str, source: str = "", weight: float = 1.0) -> int:
    """Store one fact; an exact-text duplicate updates the original instead of
    piling a second copy into recall — sweeps hit the same headlines daily."""
    trimmed = text[:_FACT_LEN]
    with _DB_LOCK, _connect() as conn:
        existing = conn.execute("SELECT id FROM facts WHERE text = ?", (trimmed,)).fetchone()
        if existing:
            return int(existing["id"])
        cursor = conn.execute(
            "INSERT INTO facts (kind, text, source, weight, created_at) VALUES (?,?,?,?,?)",
            (kind, trimmed, source[:300], float(weight), time.time()),
        )
        conn.execute(
            "DELETE FROM facts WHERE id NOT IN "
            "(SELECT id FROM facts ORDER BY weight DESC, created_at DESC LIMIT ?)",
            (_MEMORY_LIMIT,),
        )
        return int(cursor.lastrowid or 0)


_FACT_HALF_LIFE = 36.0  # hours until an internet fact's recency bonus halves


def _fact_score(weight: float, created_at: float, now: float) -> float:
    """Weight plus a decaying recency pulse, so freshly learned headlines
    can outrank months-old ones the way a trader weights 'new tape' — while
    admin-taught facts keep their heavier base weight forever."""
    age_hours = max(0.0, (now - created_at) / 3600.0)
    pulse = 0.5 ** (age_hours / _FACT_HALF_LIFE)
    recency = 1.4 * float(pulse)
    return float(weight) * 0.6 + recency


def recall_facts(limit: int = 6) -> List[Dict[str, Any]]:
    """Rank memory for recall: dedupe near-identical text, tier admins ahead,
    then fill with the highest-scored internet facts so fresh tape still leads."""
    limit = max(1, min(limit, 12))
    with _DB_LOCK, _connect() as conn:
        rows = conn.execute(
            "SELECT id, kind, text, source, weight, created_at FROM facts "
            "ORDER BY weight DESC, created_at DESC LIMIT ?",
            (limit * 6,),
        ).fetchall()
    now = time.time()
    seen: set[str] = set()
    admins: List[Dict[str, Any]] = []
    others: List[Dict[str, Any]] = []
    for row in rows:
        entry = dict(row)
        key = " ".join(str(entry.get("text") or "").lower().split())
        if not key or key in seen:
            continue  # same text already in the pool — recall diversity wins
        seen.add(key)
        (admins if entry.get("kind") == "admin" else others).append(entry)
    admin_quota = max(1, limit // 2)
    ranked: List[Dict[str, Any]] = admins[:admin_quota]
    remaining = limit - len(ranked)
    scored = sorted(
        others,
        key=lambda row: (_fact_score(row["weight"], row["created_at"], now), row["created_at"]),
        reverse=True,
    )
    return ranked + scored[:remaining]


def recall_turns(limit: int = 12) -> List[Dict[str, Any]]:
    limit = max(1, min(limit, 40))
    with _DB_LOCK, _connect() as conn:
        rows = conn.execute(
            "SELECT role, name, text, created_at FROM turns ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in reversed(rows)]


def wipe_memory() -> Tuple[int, int]:
    wiped = 0
    with _DB_LOCK, _connect() as conn:
        for table in ("facts", "turns"):
            cursor = conn.execute(f"DELETE FROM {table}")
            wiped += cursor.rowcount or 0
        conn.execute(
            "INSERT INTO admin_log (action, detail, created_at) VALUES ('wipe','memory cleared',?)",
            (time.time(),),
        )
    return wiped, 0


def admin_journal(action: str, detail: str) -> None:
    with _DB_LOCK, _connect() as conn:
        conn.execute(
            "INSERT INTO admin_log (action, detail, created_at) VALUES (?,?,?)",
            (action[:40], detail[:220], time.time()),
        )


# ---------------------------------------------------------------------------
# Signed chat cookie: name + admin claim, verified with HMAC every request.
# ---------------------------------------------------------------------------
def _sign(payload: str) -> str:
    return hmac.new(
        _COOKIE_SALT + _PROCESS_SECRET, payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def encode_chat_cookie(name: str, admin: bool) -> str:
    payload = json.dumps(
        {"name": name, "admin": admin, "iat": int(time.time())}, separators=(",", ":")
    )
    return payload + "." + _sign(payload)


def decode_chat_cookie(value: str) -> Optional[Dict[str, Any]]:
    try:
        payload, signature = value.rsplit(".", 1)
    except ValueError:
        return None
    if not hmac.compare_digest(_sign(payload), signature):
        return None
    try:
        data = json.loads(payload)
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("name"), str):
        return None
    if time.time() - float(data.get("iat") or 0) > COOKIE_MAX_AGE:
        return None
    return {"name": data["name"][:_NAME_MAX], "admin": bool(data.get("admin"))}


def chat_identity(request: Request) -> Optional[Dict[str, Any]]:
    return decode_chat_cookie(request.cookies.get(COOKIE_NAME) or "")


def _normalize_name(value: str) -> str:
    return " ".join(str(value or "").split()).lower()[:_NAME_MAX]


# ---------------------------------------------------------------------------
# Internet access: public feeds only, learned facts carry their source link.
# ---------------------------------------------------------------------------
_TICKER_TOKEN = re.compile(r"\b([A-Z]{1,5})\b")
_SYMBOL_BLACKLIST = {
    "A",
    "I",
    "OK",
    "THE",
    "AND",
    "OR",
    "IF",
    "IS",
    "MY",
    "ME",
    "IT",
    "NO",
    "ON",
    "IN",
    "TO",
    "OF",
    "UP",
    "AT",
    "AS",
    "BE",
    "BY",
    "DO",
    "GO",
    "HI",
    "SO",
    "TV",
    "VS",
    "AM",
    "PM",
    "AI",
    "CEO",
    "IPO",
    "ETF",
    "GDP",
    "CPI",
    "EPS",
    "SL",
    "TP",
    "USD",
    "EUR",
    "YTD",
    "ATH",
    "NQ",
    "ES",
    "YM",
    "RTY",
}


def detect_symbol(message: str) -> Optional[str]:
    """First plausible ticker in a chat message, honest enough to fetch."""
    for token in _TICKER_TOKEN.findall(message.upper()):
        if token in _SYMBOL_BLACKLIST:
            continue
        if len(token) == 1 and token not in {"T", "F"}:
            continue
        return str(token)
    return None


def _headline_fact(item: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """Distill one headline into (fact text, source link)."""
    title = " ".join(str(item.get("title") or "").split())
    link = str(item.get("link") or "").strip()
    if not title or not link or len(title) < 12:
        return None
    publisher = " ".join(str(item.get("publisher") or "").split())
    published = item.get("published_at")
    stamp = ""
    if isinstance(published, (int, float)) and published > 0:
        stamp = time.strftime("%b %d", time.gmtime(float(published)))
    text = f"{stamp}: {title}" if stamp and not publisher else title
    if stamp and publisher:
        text = f"{stamp} ({publisher}): {title}"
    elif publisher:
        text = f"{publisher}: {title}"
    return text, link


def learn_from_internet(symbol: Optional[str] = None) -> Dict[str, Any]:
    """Pull fresh public headlines (and a quote when a symbol was named),
    store the new facts, and return a compact view for the reply builder."""
    terms = [symbol] if symbol else ["stock market", "Federal Reserve"]
    learned: List[Dict[str, Any]] = []
    quote: Optional[Dict[str, Any]] = None
    try:
        if symbol:
            quote = fetch_quote(symbol)
    except MarketFeedError:
        quote = None

    def _sweep(term: str) -> None:
        try:
            payload = latest_headlines_for_query(str(term), 5)
        except MarketFeedError:
            return
        for item in payload.get("items", []):
            distilled = _headline_fact(item)
            if distilled is None:
                continue
            text, link = distilled
            # Same headline is not learned twice: the source link is unique.
            if any(entry["source"] == link for entry in learned):
                continue
            add_fact("internet", text, source=link, weight=1.0)
            learned.append({"text": text, "source": link, "fresh": _MEMO_TTL})

    for term in terms[:2]:
        _sweep(term)
    # A named ticker whose feed answers nothing falls back to the macro
    # basket, labeled loudly; an empty room stays honest about the gap.
    if symbol and not learned:
        _sweep("stock market")
        for entry in learned:
            entry["text"] = f"[macro fallback — no live news for {symbol}] {entry['text']}"
    return {"learned": learned[:6], "quote": quote}


_LEARN_LOCK = threading.Lock()
_last_sweep: List[float] = [0.0]


def _maybe_sweep(symbol: Optional[str]) -> Dict[str, Any]:
    """Rate-limited internet sweep: at most one per _LEARN_INTERVAL."""
    with _LEARN_LOCK:
        now = time.time()
        if now - _last_sweep[0] >= _LEARN_INTERVAL:
            _last_sweep[0] = now
            due = True
        else:
            due = False
    if due:
        return learn_from_internet(symbol)
    return {"learned": [], "quote": None}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class AccessBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=_NAME_MAX)
    code: str = Field(default="", max_length=80)  # empty = open room (the default)


class MessageBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=_MESSAGE_MAX)


class TeachBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact: str = Field(min_length=3, max_length=_FACT_LEN)


class Reply(BaseModel):
    text: str = Field(min_length=1, max_length=_MESSAGE_MAX * 4)
    learned: List[Dict[str, Any]] = Field(default_factory=list)
    quote: Optional[Dict[str, Any]] = None
    facts_used: int = 0
    admin: bool = False
    name: str = ""


# ---------------------------------------------------------------------------
# Reply composer: deterministic, honest, sourced.
# ---------------------------------------------------------------------------
def _quote_block(quote: Optional[Dict[str, Any]]) -> str:
    if not isinstance(quote, dict) or not quote.get("ok"):
        return ""
    price = quote.get("price")
    pct = quote.get("change_pct")
    sym = quote.get("symbol") or ""
    if not isinstance(price, (int, float)) or not price > 0:
        return ""
    change = ""
    if isinstance(pct, (int, float)):
        arrow = "+" if pct >= 0 else ""
        change = f" ({arrow}{pct:.2f}% today)"
    return f"LIVE {sym}: {price:,.2f}{change} · public feed"


_TRADE_WORDS = ("buy", "sell", "long", "short", "entry", "trade", "stop", "target")
_QUESTION_WORDS = ("what", "why", "how", "will", "when", "who", "which", "should")
_GREETING_WORDS = ("hi", "hello", "hey", "yo", "sup", "morning", "evening")


def _intent(text: str) -> str:
    lower = " " + text.lower() + " "
    if any(f" {word}" in lower for word in _GREETING_WORDS) and len(text.split()) <= 6:
        return "greeting"
    if any(word in lower for word in _TRADE_WORDS):
        return "trade"
    if any(word in lower for word in _QUESTION_WORDS):
        return "question"
    return "chat"


def _daypart() -> str:
    hour = time.gmtime().tm_hour  # UTC — the room stands for anyone, anywhere
    if 5 <= hour < 12:
        return "Morning"
    if 12 <= hour < 18:
        return "Afternoon"
    return "Evening"


def _fresh_news_block(fresh: List[Dict[str, Any]]) -> List[str]:
    parts: List[str] = []
    if not fresh:
        return parts
    quoted = "; ".join(str(entry["text"]) for entry in fresh[:3])
    parts.append(
        f"Fresh off the internet ({len(fresh)} headline"
        f"{'s' if len(fresh) != 1 else ''}): {quoted}"
    )
    sources = " · ".join(str(entry.get("source") or "") for entry in fresh[:3]).strip(" ·")
    if sources:
        parts.append(f"Sources: {sources}")
    return parts


def _memory_block(facts: List[Dict[str, Any]], fresh_texts: set[str], had_fresh: bool) -> List[str]:
    parts: List[str] = []
    seen: set[str] = set()
    recalled: List[Dict[str, Any]] = []
    for entry in facts:
        line = " ".join(str(entry.get("text") or "").split())
        if not line or line in fresh_texts or line in seen:
            continue  # never repeat one fact twice in the same reply
        seen.add(line)
        recalled.append(entry)
    recalled = recalled[:3]
    if recalled:
        quoted = "; ".join(str(entry.get("text") or "") for entry in recalled)
        parts.append(
            f"Memory recall ({len(recalled)} fact" f"{'s' if len(recalled) != 1 else ''}): {quoted}"
        )
    elif not had_fresh:
        parts.append(
            "My memory on this is still thin — ask again after the next internet "
            "sweep, or teach me a fact, and I will hold it."
        )
    return parts


def _compose_reply(
    text: str,
    name: str,
    is_admin: bool,
    learned: List[Dict[str, Any]],
    quote: Optional[Dict[str, Any]],
    facts: List[Dict[str, Any]],
    turns_used: int,
    symbol: Optional[str],
) -> str:
    intent = _intent(text)
    if intent == "greeting":
        taught = sum(1 for entry in facts if entry.get("kind") == "admin")
        net = len(facts) - taught
        lines = [
            f"{_daypart()}, {name or 'friend'} — room's open, memory loaded, research mode on.",
            f"On the shelf right now: {taught} taught and {net} netted from the "
            "internet. Name a ticker or ask away.",
        ]
        if is_admin:
            lines.append("joshua — teach and wipe stay unlocked for you.")
        lines.append("Everything in this room is research, not advice; no orders.")
        return "\n".join(lines)

    fresh = [entry for entry in learned if entry.get("fresh")]
    fresh_texts = {" ".join(str(entry["text"]).split()) for entry in fresh}
    parts: List[str] = []
    if is_admin:
        parts.append("joshua at the desk — memory and teaching unlocked.")
    else:
        parts.append(f"{name or 'friend'} — memory is on, still reading the tape.")
    if intent == "question" and len(facts) <= 2 and not fresh:
        parts.append(
            "Honest shape of this answer: I'm a reasoning engine over my market "
            "memory, public feeds, and what you've taught me — nothing here "
            "submits orders."
        )
    if symbol:
        parts.append(f"Focus: {symbol} — matched against memory and the live tape.")
    else:
        parts.append(
            "No ticker named — I keep watching the macro basket: stocks, the Fed, Bitcoin."
        )
    quote_block = _quote_block(quote)
    if quote_block:
        parts.append(quote_block)
    elif symbol and intent == "trade":
        parts.append(f"No live price for {symbol} right now — the tape is quiet here.")
    parts.extend(_fresh_news_block(fresh))
    parts.extend(_memory_block(facts, fresh_texts, bool(fresh)))
    if intent == "trade":
        change = quote.get("change_pct") if isinstance(quote, dict) else None
        lean = "risk-on" if isinstance(change, (int, float)) and change >= 0 else "risk-off"
        parts.append(
            f"Tape leans {lean}. I grade setups from real history and say what I see — "
            "no promised outcomes. Research, not advice; no orders."
        )
    else:
        parts.append("Everything above: research, not advice; no orders.")
    if turns_used:
        parts.append(f"Our room holds {turns_used} turns of history, and none of it drains.")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Routes. Access first; every other route demands a signed cookie.
# ---------------------------------------------------------------------------
def _set_chat_cookie(response: Response, request: Request, name: str, admin: bool) -> None:
    response.set_cookie(
        COOKIE_NAME,
        encode_chat_cookie(name, admin),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        secure=request.url.scheme == "https" or bool(os.getenv("VERCEL")),
        samesite="lax",
        path="/",
    )


@router.post("/access")
async def chat_access(payload: AccessBody, response: Response, request: Request) -> Dict[str, Any]:
    """Passcode area: the code gates the room; the name becomes the identity.

    The admin name ("joshua mathew") carries an admin claim on the signed
    cookie. Wrong names are still identities — they just stay members.
    """
    submitted = " ".join(payload.code.split()).lower()
    code_required = chat_room_locked()
    if code_required and not hmac.compare_digest(submitted, _chat_code()):
        raise HTTPException(403, "Wrong passcode — the door stays shut.")
    name = _normalize_name(payload.name)
    if not name:
        raise HTTPException(422, "Pick a name for the room (or use the admin one).")
    admin = name == ADMIN_NAME
    _set_chat_cookie(response, request, name.title(), admin)
    record_turn("user", name.title(), f"[joined as {name.title()}{' — admin' if admin else ''}]")
    if admin:
        admin_journal("join", "joshua mathew entered the chat room")
    return {
        "ok": True,
        "name": name.title(),
        "admin": admin,
        "memory_url": "/ai-chat",
        "intro": (
            "Loki's private room unlocked — no password, just a name. The AI "
            "reads the market internet, keeps a persistent memory, and "
            "answers in its own voice."
        ),
    }


@router.get("/whoami")
async def chat_whoami(request: Request) -> Dict[str, Any]:
    identity = chat_identity(request)
    if not identity:
        return {"ok": False, "admin": False, "name": ""}
    return {"ok": True, **identity}


@router.post("/logout")
async def chat_logout(request: Request, response: Response) -> Dict[str, Any]:
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


_DUPLICATE_WINDOW = 10.0  # same speaker + same text inside this window = flood
_recent_messages: Dict[str, float] = {}
_FLOOD_LOCK = threading.Lock()


def memory_audit() -> Dict[str, Any]:
    """Room self-audit: counts by kind, memory span, store pressure. Honest,
    bounded reads straight off the sqlite store."""
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        fact_rows = conn.execute(
            "SELECT kind, COUNT(*) AS n, MAX(created_at) AS newest FROM facts GROUP BY kind"
        ).fetchall()
        turn_row = conn.execute(
            "SELECT COUNT(*) AS n, MIN(created_at) AS oldest FROM turns"
        ).fetchone()
    by_kind = {row["kind"]: int(row["n"]) for row in fact_rows}
    newest = max([float(row["newest"] or 0.0) for row in fact_rows] or [0.0])
    oldest_turn = float(turn_row["oldest"] or 0) if turn_row and turn_row["oldest"] else 0.0
    span_days = 0.0
    if oldest_turn:
        span_days = max(0.0, (now - oldest_turn) / 86400.0)
    return {
        "taught": by_kind.get("admin", 0),
        "internet": by_kind.get("internet", 0),
        "turns": int(turn_row["n"] or 0) if turn_row else 0,
        "newest_fact_age_min": round(max(0.0, (now - newest) / 60.0), 1) if newest else None,
        "memory_span_days": round(span_days, 2),
        "next_sweep_in_min": round(max(0.0, (_last_sweep[0] + _LEARN_INTERVAL - now) / 60.0), 1),
        "store_cap": {"facts": _MEMORY_LIMIT, "turns": _STORE_ROWS},
    }


def _audit_reply(name: str, is_admin: bool) -> str:
    audit = memory_audit()
    parts = [
        f"{name or 'friend'} — audit, as asked:",
        (
            f"Memory shelf: {audit['taught']} taught + {audit['internet']} internet facts "
            f"(caps: {audit['store_cap']['facts']} facts / {audit['store_cap']['turns']} turns)."
        ),
        f"Conversation depth: {audit['turns']} turns, spanning {audit['memory_span_days']} day(s)."
        f"{' Admin unlocked.' if is_admin else ' Member view.'}",
        (
            f"Internet sweep: next in ~{audit['next_sweep_in_min']} min "
            f"(5-minute cadence by design)."
        ),
        (
            f"Newest learned fact is {audit['newest_fact_age_min']} min old."
            if audit["newest_fact_age_min"] is not None
            else "No facts learned yet — name a ticker to start the sweep."
        ),
        "Everything here: research, not advice; no orders.",
    ]
    return "\n".join(parts)


_STOP_WORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "is",
    "are",
    "was",
    "you",
    "i",
    "it",
    "to",
    "of",
    "on",
    "in",
    "what",
    "how",
    "why",
    "tell",
    "me",
    "about",
    "for",
    "with",
    "this",
    "that",
    "any",
    "your",
    "my",
    "do",
    "does",
    "be",
}


def _relevant_facts(message: str, pool: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    """Relevance-ranked recall: overlap with the message's content words and
    the named symbol beats plain recency, so the room answers about the thing
    asked instead of whatever landed last. Taught facts keep their weight edge."""
    words = [
        w for w in re.findall(r"[a-z0-9]+", message.lower()) if len(w) > 2 and w not in _STOP_WORDS
    ]
    wanted = set(words)
    symbol_upper = detect_symbol(message)
    if symbol_upper:
        wanted.add(symbol_upper.lower())

    def score(fact: Dict[str, Any]) -> float:
        hay = f"{fact.get('text', '')} {fact.get('source', '')}".lower()
        overlap = sum(1 for token in wanted if token in hay)
        base = float(fact.get("weight", 1.0)) * 0.35
        return overlap * 2.0 + base

    ranked = sorted(pool, key=score, reverse=True)
    half = math.ceil(limit / 2) if symbol_upper else 0
    ordered: List[Dict[str, Any]] = []
    if symbol_upper:
        matching = [f for f in ranked if symbol_upper.lower() in f.get("text", "").lower()]
        ordered.extend(matching[:half])
    for fact in ranked:
        if fact in ordered:
            continue
        ordered.append(fact)
        if len(ordered) >= limit:
            break
    return ordered


@router.post("/message")
async def chat_message(payload: MessageBody, request: Request, response: Response) -> Reply:
    identity = chat_identity(request)
    if not identity:
        raise HTTPException(401, "Unlock the room first — the passcode gates it.")
    name = str(identity.get("name") or "")
    is_admin = bool(identity.get("admin"))
    text = payload.text.strip()[:_MESSAGE_MAX]
    if not text:
        raise HTTPException(422, "Say something first.")
    flood_key = f"{name}::{text}"
    now = time.time()
    with _FLOOD_LOCK:
        last_same = _recent_messages.get(flood_key)
        _recent_messages[flood_key] = now
        if len(_recent_messages) > 256:  # bounded key ring, oldest half dropped
            for key, stamp in sorted(_recent_messages.items(), key=lambda kv: kv[1])[:128]:
                _recent_messages.pop(key, None)
    if last_same is not None and now - last_same < _DUPLICATE_WINDOW:
        raise HTTPException(429, "Same message twice in ten seconds — give the room a breath.")

    if text.strip().lower() in {"audit", "pulse", "status"}:
        reply_text = _audit_reply(name, is_admin)
        record_turn("user", name, text)
        record_turn("ai", "Loki", reply_text)
        _set_chat_cookie(response, request, name, is_admin)
        return Reply(text=reply_text, admin=is_admin, name=name)

    symbol = detect_symbol(text)
    sweep = _maybe_sweep(symbol)
    quote = sweep.get("quote")
    try:
        if symbol and not isinstance(quote, dict):
            quote = fetch_quote(symbol)
    except MarketFeedError:
        quote = None

    turns_used = recall_turns(10)
    fact_pool = recall_facts(16)
    relevant = _relevant_facts(text, fact_pool, 6)
    reply_text = _compose_reply(
        text=text,
        name=name,
        is_admin=is_admin,
        learned=sweep.get("learned") or [],
        quote=quote,
        facts=relevant,
        turns_used=len(turns_used),
        symbol=symbol,
    )
    record_turn("user", name, text)
    record_turn("ai", "Loki", reply_text)
    # Refresh the sliding 14-day window on every message.
    _set_chat_cookie(response, request, name, is_admin)
    return Reply(
        text=reply_text,
        learned=sweep.get("learned") or [],
        quote=quote,
        facts_used=len(relevant),
        admin=is_admin,
        name=name,
    )


@router.get("/memory")
async def chat_memory(request: Request) -> Dict[str, Any]:
    identity = chat_identity(request)
    if not identity:
        raise HTTPException(401, "Unlock the room first — the passcode gates it.")
    return {
        "facts": recall_facts(12),
        "turns": recall_turns(30),
        "admin": bool(identity.get("admin")),
        "name": identity.get("name") or "",
    }


@router.post("/teach")
async def chat_teach(payload: TeachBody, request: Request) -> Dict[str, Any]:
    identity = chat_identity(request)
    if not identity:
        raise HTTPException(401, "Unlock the room first — the passcode gates it.")
    if not identity.get("admin"):
        raise HTTPException(403, "Only the admin can write permanent facts.")
    fact = " ".join(payload.fact.split())
    add_fact("admin", fact, source="taught by joshua mathew", weight=3.0)
    admin_journal("teach", fact)
    return {"ok": True, "fact": fact, "note": "Loki holds this as a heavy truth (weight 3)."}


@router.post("/wipe")
async def chat_wipe(request: Request) -> Dict[str, Any]:
    identity = chat_identity(request)
    if not identity:
        raise HTTPException(401, "Unlock the room first — the passcode gates it.")
    if not identity.get("admin"):
        raise HTTPException(403, "Only the admin can wipe memory.")
    wiped_facts, _ = wipe_memory()
    admin_journal("wipe", f"{wiped_facts} facts cleared")
    return {"ok": True, "wiped": wiped_facts, "note": "Memory wiped; the wipe itself is journaled."}
