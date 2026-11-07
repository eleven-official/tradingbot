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
- Access — display-name entry by default, with an optional operator-set code.
- Admin — a signed cookie carries privileges only after checking the configured
  operator secret as well as the operator name. Admin can teach facts (weighted)
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
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from loki.api import site_access
from pydantic import BaseModel, ConfigDict, Field

from loki.api.market_feed import MarketFeedError, fetch_quote, latest_headlines_for_query

logger = logging.getLogger(__name__)

_REQUEST_LOCK = threading.Lock()
_REQUEST_COUNTS: Dict[str, Tuple[float, int]] = {}


def limit_chat_requests(request: Request) -> None:
    if request.method != "POST":
        return
    key = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with _REQUEST_LOCK:
        start, count = _REQUEST_COUNTS.get(key, (now, 0))
        if now - start >= 60:
            start, count = now, 0
        if count >= 60:
            raise HTTPException(
                429, "Too many chat requests. Try again shortly.", headers={"Retry-After": "60"}
            )
        if key not in _REQUEST_COUNTS and len(_REQUEST_COUNTS) >= 4096:
            expired = [host for host, (stamp, _) in _REQUEST_COUNTS.items() if now - stamp >= 60]
            for host in expired:
                del _REQUEST_COUNTS[host]
            if len(_REQUEST_COUNTS) >= 4096:
                raise HTTPException(503, "Chat is busy. Try again shortly.")
        _REQUEST_COUNTS[key] = (start, count + 1)


router = APIRouter(
    prefix="/api/ai/chat", tags=["Research AI chat"], dependencies=[Depends(limit_chat_requests)]
)

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

# Locally saved public-data derivatives research (offline reports, never orders).
_DERIVATIVE_DIR = Path(__file__).resolve().parents[2] / "state" / "public_derivatives"

_COOKIE_SALT = b"loki-sentient-chat-v1"
_PROCESS_SECRET = secrets.token_bytes(32)
# Serverless hosts (Vercel) ship the code read-only; only the temp dir is
# writable. Memory there is per-instance, so the browser keeps its own copy
# of the conversation too (static/js/ai_chat.js).
_FALLBACK_DB_DIR = Path(tempfile.gettempdir()) / "loki_ai_chat"
if not _env_db and os.environ.get("VERCEL"):
    _DB_DIR = _FALLBACK_DB_DIR
    _DB_PATH = _DB_DIR / "memory.sqlite3"


def _session_secret() -> bytes:
    """Cookie signing key that survives cold starts and multiple instances.

    A random per-process key logged every visitor out whenever a serverless
    instance recycled. Prefer an explicit chat secret, then the site gate's
    stable secret material (never sent anywhere), and only then the
    per-process fallback.
    """
    explicit = os.environ.get("LOKI_CHAT_SESSION_SECRET", "").strip()
    if explicit:
        return explicit.encode()
    try:
        from loki.api import site_access

        # Only borrow the gate's key when an operator configured it; a local
        # dev constant must never sign chat cookies (admin claims ride them).
        if site_access.secret_is_configured():
            return hmac.new(site_access._secret(), b"loki-chat-session", hashlib.sha256).digest()
    except Exception:  # noqa: BLE001 - never block chat on gate config
        pass
    return _PROCESS_SECRET


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


def _open_db() -> sqlite3.Connection:
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, timeout=10)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        conn.close()
        raise
    return conn


def _connect() -> sqlite3.Connection:
    global _DB_DIR, _DB_PATH
    try:
        conn = _open_db()
    except (OSError, sqlite3.OperationalError) as exc:
        # Read-only deploy directory: fall back to the writable temp dir
        # instead of failing every chat request with a 500.
        if _DB_DIR == _FALLBACK_DB_DIR:
            raise
        logger.warning("chat memory dir not writable (%s); using temp dir", exc.__class__.__name__)
        _DB_DIR, _DB_PATH = _FALLBACK_DB_DIR, _FALLBACK_DB_DIR / "memory.sqlite3"
        conn = _open_db()
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    with _DB_LOCK:
        conn.executescript(_SCHEMA)
        if "session" not in {row[1] for row in conn.execute("PRAGMA table_info(turns)")}:
            conn.execute("ALTER TABLE turns ADD COLUMN session TEXT NOT NULL DEFAULT ''")
    return conn


# Schema runs inside _connect, so every handle (including after a test
# repoints _DB_PATH) opens with tables present; executescript is idempotent.


def _ensure_schema() -> None:
    with _DB_LOCK, _connect() as conn:
        conn.executescript(_SCHEMA)


_TURN_TEXT_MAX = _MESSAGE_MAX  # user bubbles stay single-message sized
_REPLY_MAX = _MESSAGE_MAX * 8  # two live AI reads plus headlines fit whole
_AI_TURN_TEXT_MAX = _REPLY_MAX  # AI replies are multi-line; keep them whole


def record_turn(role: str, name: str, text: str, session: str = "") -> None:
    cap = _AI_TURN_TEXT_MAX if role == "ai" else _TURN_TEXT_MAX
    with _DB_LOCK, _connect() as conn:
        conn.execute(
            "INSERT INTO turns (role, name, text, created_at, session) VALUES (?,?,?,?,?)",
            (role, name[:_NAME_MAX], text[:cap], time.time(), session),
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


def recall_turns(limit: int = 12, session: Optional[str] = None) -> List[Dict[str, Any]]:
    limit = max(1, min(limit, 40))
    with _DB_LOCK, _connect() as conn:
        rows = conn.execute(
            "SELECT role, name, text, created_at FROM turns "
            "WHERE (? IS NULL OR session = ?) ORDER BY created_at DESC LIMIT ?",
            (session, session, limit),
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
        _COOKIE_SALT + _session_secret(), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def encode_chat_cookie(name: str, admin: bool, session: str = "") -> str:
    payload = json.dumps(
        {
            "name": name,
            "admin": admin,
            "sid": session or secrets.token_hex(24),
            "iat": int(time.time()),
        },
        separators=(",", ":"),
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
    issued = data.get("iat")
    if not isinstance(issued, (int, float)) or not math.isfinite(issued):
        return None
    if not 0 <= time.time() - issued <= COOKIE_MAX_AGE:
        return None
    if not isinstance(data.get("sid"), str) or not data["sid"]:
        return None
    return {"name": data["name"][:_NAME_MAX], "admin": bool(data.get("admin")), "sid": data["sid"]}


def chat_identity(request: Request) -> Optional[Dict[str, Any]]:
    return decode_chat_cookie(request.cookies.get(COOKIE_NAME) or "")


def _normalize_name(value: str) -> str:
    return " ".join(str(value or "").split()).lower()[:_NAME_MAX]


# ---------------------------------------------------------------------------
# Internet access: public feeds only, learned facts carry their source link.
# ---------------------------------------------------------------------------
# Shouted at sentence start but still just words, not tickers.
_COMMON_SHOUTED_WORDS = {
    "WHAT",
    "WHY",
    "HOW",
    "WILL",
    "WHEN",
    "WHO",
    "WHICH",
    "SHOULD",
    "WHERE",
    "THIS",
    "THAT",
    "WITH",
    "FROM",
    "HAVE",
    "BEEN",
    "NEXT",
    "SHOW",
    "NAME",
    "PRICE",
    "PLEASE",
    "THANKS",
    "GOOD",
    "MORNING",
    "EVENING",
    "HELLO",
}
_TICKER_TOKEN = re.compile(r"\b([A-Z]{1,5})\b")
# Casual names still accepted when the writer skipped capitals.
_KNOWN_SYMBOLS = {
    "spx",
    "spy",
    "qqq",
    "iwm",
    "dia",
    "vix",
    "aapl",
    "msft",
    "nvda",
    "tsla",
    "meta",
    "amzn",
    "googl",
    "nflx",
    "amd",
    "mu",
    "nq",
    "es",
    "rt",
    "ym",
    "mes",
    "mnq",
    "btc",
    "eth",
    "sol",
    "xrp",
    "doge",
    "vxx",
    "uvxy",
    "gme",
}
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
    """First plausible ticker in a chat message, honest enough to fetch.

    A token counts when the writer actually typed it in capital letters
    (`VX`, `SPY`) or it is a well-known symbol typed casually (`spy`).
    Ordinary words like "What" cannot become tickers; that mistake used to
    send the internet sweep chasing the word WHAT as if it were a security.
    """
    shouted = set(re.findall(r"\b[A-Z][A-Z0-9.]{0,4}\b", message))
    for token in _TICKER_TOKEN.findall(message.upper()):
        if token in _SYMBOL_BLACKLIST or token in _COMMON_SHOUTED_WORDS:
            continue
        if len(token) == 1 and token not in {"T", "F"}:
            continue
        if token not in shouted and token.lower() not in _KNOWN_SYMBOLS:
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
    text: str = Field(min_length=1, max_length=_REPLY_MAX)
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
    words = set(re.findall(r"[a-z]+", text.lower()))
    if words.intersection(_TRADE_WORDS):
        return "trade"
    if words.intersection(_QUESTION_WORDS) or "?" in text:
        return "question"
    greeting_fillers = {"good", "there", "friend", "loki", "everyone"}
    if words.intersection(_GREETING_WORDS) and words <= set(_GREETING_WORDS) | greeting_fillers:
        return "greeting"
    return "chat"


def _derivatives_research_block(text: str) -> List[str]:
    """Quote the locally saved public-data research reports, honestly.

    Read-only derived answers from ``state/public_derivatives``; a missing or
    malformed report contributes nothing instead of an invented answer.
    """
    words = set(re.findall(r"[a-z0-9]+", text.lower()))
    if not words.intersection(("options", "option", "futures", "vx", "volatility", "derivatives")):
        return []
    lines: List[str] = []
    for instrument in ("SPY-options", "VX-futures"):
        path = _DERIVATIVE_DIR / f"{instrument}-report.json"
        if not path.is_file():
            continue
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        try:
            samples = report["sample_counts"]
            test = report["test"]
            status = re.sub(r"[^a-z0-9_-]", "", str(report["status"])).strip("-_")[:40]
            trained = int(samples["train"])
            validation = int(samples["validation"])
            heldout = int(samples["test"])
            trades = int(test["trades"])
            pnl = float(test["net_pnl_usd"])
        except (KeyError, TypeError, ValueError):
            continue
        lines.append(
            f"{instrument.replace('-', ' ')} research (offline, from public data): status "
            f"{status or 'unknown'}; trained {trained} / validation {validation} / holdout "
            f"{heldout} examples; heldout trades {trades}, net P&L ${pnl:.2f}."
        )
    if lines:
        lines.append(
            "These models do not trade or ship orders and do not prove profitability — "
            "research only, not advice."
        )
    return lines


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
    parts.extend(_derivatives_research_block(text))
    if intent == "trade":
        change = quote.get("change_pct") if isinstance(quote, dict) else None
        lean = (
            ("up" if change > 0 else "down" if change < 0 else "unchanged")
            if isinstance(change, (int, float)) and math.isfinite(change)
            else "unavailable"
        )
        parts.append(
            f"Quoted price direction: {lean}. A price change alone does not establish a trade setup — "
            "no promised outcomes. Research, not advice; no orders."
        )
    else:
        parts.append("Everything above: research, not advice; no orders.")
    if turns_used:
        parts.append(f"Context: {turns_used} recent turns from this browser session.")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Routes. Access first; every other route demands a signed cookie.
# ---------------------------------------------------------------------------
def _set_chat_cookie(
    response: Response, request: Request, name: str, admin: bool, fresh: bool = False
) -> None:
    response.set_cookie(
        COOKIE_NAME,
        encode_chat_cookie(
            name, admin, "" if fresh else (chat_identity(request) or {}).get("sid", "")
        ),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        secure=site_access.cookie_secure(request),
        samesite="lax",
        path="/",
    )


@router.post("/access")
async def chat_access(payload: AccessBody, response: Response, request: Request) -> Dict[str, Any]:
    """Open a fresh browser session; operator privileges require a secret."""
    submitted = " ".join(payload.code.split()).lower()
    code_required = chat_room_locked()
    admin_secret = os.environ.get("LOKI_CHAT_ADMIN_CODE", "")
    operator_code = bool(admin_secret) and hmac.compare_digest(payload.code, admin_secret)
    if code_required and not operator_code and not hmac.compare_digest(submitted, _chat_code()):
        raise HTTPException(403, "Wrong passcode — the door stays shut.")
    name = _normalize_name(payload.name)
    if not name:
        raise HTTPException(422, "Pick a name for the room (or use the admin one).")
    admin = name == ADMIN_NAME and operator_code
    _set_chat_cookie(response, request, name.title(), admin, fresh=True)
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
def chat_message(payload: MessageBody, request: Request, response: Response) -> Reply:
    identity = chat_identity(request)
    if not identity:
        raise HTTPException(401, "Unlock the room first — the passcode gates it.")
    name = str(identity.get("name") or "")
    is_admin = bool(identity.get("admin"))
    session = str(identity["sid"])
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
        record_turn("user", name, text, session)
        record_turn("ai", "Loki", reply_text, session)
        _set_chat_cookie(response, request, name, is_admin)
        return Reply(text=reply_text, admin=is_admin, name=name)

    from loki.api import loki_brain

    # The room keeps its own greeting (memory shelf stats) and headline
    # memory; Loki's brain adds the live AI read, market checks, the track
    # record and plain-English explanations.
    brain = loki_brain.answer(text, name, skip=("greeting",))
    if brain and brain["intent"] != "symbol":
        reply_text = brain["text"]
        record_turn("user", name, text, session)
        record_turn("ai", "Loki", reply_text, session)
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

    turns_used = recall_turns(10, session)
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
    if brain and brain["intent"] == "symbol":
        # Lead with what the AI engine actually sees; underneath, only the
        # headlines the room just learned or remembers for this name.
        from urllib.parse import urlsplit

        wanted = set()
        for sym in brain.get("symbols") or []:
            base = sym.split("-")[0].lower()
            wanted.add(base)
            wanted.update(k for k, v in loki_brain.NAMES.items() if v == sym and len(k) > 3)

        def _line(item: Dict[str, Any]) -> str:
            text_ = str(item.get("text") or item.get("title") or "")
            if not any(re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", text_.lower()) for w in wanted):
                return ""  # only headlines about the asked-about asset
            host = urlsplit(str(item.get("source") or item.get("link") or "")).hostname or ""
            return f"{text_} — {host.removeprefix('www.')}" if host else text_

        heard = [_line(item) for item in (sweep.get("learned") or []) if item.get("fresh")]
        heard += [_line(f) for f in relevant]
        heard = [h for i, h in enumerate(heard) if h and h not in heard[:i]][:3]
        reply_text = brain["text"]
        if heard:
            reply_text += "\n\nRecent headlines in my memory:\n" + "\n".join(f"• {h}" for h in heard)
    reply_text = reply_text[: _REPLY_MAX - 1].rstrip() if len(reply_text) >= _REPLY_MAX else reply_text
    record_turn("user", name, text, session)
    record_turn("ai", "Loki", reply_text, session)
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
        "turns": recall_turns(30, str(identity["sid"])),
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
