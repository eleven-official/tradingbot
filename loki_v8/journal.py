"""LOKI v8 — trade journaling, annotations, and decision logging."""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

STATE_DIR = Path("state") / "journal"
STATE_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = STATE_DIR / "journal.db"


@dataclass
class TradeNote:
    """A single trade note/annotation."""
    id: Optional[int] = None
    trade_id: str = ""  # Links to a specific trade
    symbol: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    note_type: str = "observation"  # observation, hypothesis, mistake, lesson, decision
    title: str = ""
    content: str = ""
    tags: List[str] = field(default_factory=list)
    confidence: int = 5  # 1-10
    related_trade_ids: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


@dataclass
class DecisionLog:
    """A logged trading decision with rationale."""
    id: Optional[int] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    symbol: str = ""
    decision: str = ""  # enter, exit, skip, size_up, size_down, hold
    rationale: str = ""
    factors_considered: List[str] = field(default_factory=list)
    regime: str = ""
    signal_strength: float = 0.0
    expected_outcome: str = ""  # what you expect to happen
    actual_outcome: str = ""  # filled after the fact
    pnl: Optional[float] = None
    tags: List[str] = field(default_factory=list)
    confidence: int = 5  # 1-10
    review_date: Optional[str] = None  # When to review this decision
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


@dataclass
class ReviewSession:
    """A periodic review of decisions and performance."""
    id: Optional[int] = None
    start_date: str = ""
    end_date: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    decisions_reviewed: int = 0
    correct_decisions: int = 0
    incorrect_decisions: int = 0
    lessons_learned: List[str] = field(default_factory=list)
    action_items: List[str] = field(default_factory=list)
    overall_rating: int = 5  # 1-10
    notes: str = ""


def init_db() -> sqlite3.Connection:
    """Initialize the journal database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trade_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            note_type TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            tags TEXT DEFAULT '[]',
            confidence INTEGER DEFAULT 5,
            related_trade_ids TEXT DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS decision_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            symbol TEXT NOT NULL,
            decision TEXT NOT NULL,
            rationale TEXT NOT NULL,
            factors_considered TEXT DEFAULT '[]',
            regime TEXT DEFAULT '',
            signal_strength REAL DEFAULT 0.0,
            expected_outcome TEXT DEFAULT '',
            actual_outcome TEXT DEFAULT '',
            pnl REAL,
            tags TEXT DEFAULT '[]',
            confidence INTEGER DEFAULT 5,
            review_date TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS review_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            decisions_reviewed INTEGER DEFAULT 0,
            correct_decisions INTEGER DEFAULT 0,
            incorrect_decisions INTEGER DEFAULT 0,
            lessons_learned TEXT DEFAULT '[]',
            action_items TEXT DEFAULT '[]',
            overall_rating INTEGER DEFAULT 5,
            notes TEXT DEFAULT ''
        )
    """)

    # Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notes_trade_id ON trade_notes(trade_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notes_symbol ON trade_notes(symbol)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_decisions_symbol ON decision_logs(symbol)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_decisions_timestamp ON decision_logs(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_decisions_review ON decision_logs(review_date)")

    conn.commit()
    return conn


def get_conn() -> sqlite3.Connection:
    """Get a database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# --- Trade Notes ---

def add_note(note: TradeNote) -> int:
    """Add a trade note."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO trade_notes (trade_id, symbol, timestamp, note_type, title, content, tags, confidence, related_trade_ids, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        note.trade_id, note.symbol, note.timestamp, note.note_type, note.title,
        note.content, json.dumps(note.tags), note.confidence,
        json.dumps(note.related_trade_ids), note.created_at, note.updated_at
    ))
    conn.commit()
    note_id = cursor.lastrowid
    conn.close()
    return note_id


def get_notes(
    trade_id: Optional[str] = None,
    symbol: Optional[str] = None,
    note_type: Optional[str] = None,
    limit: int = 100,
) -> List[TradeNote]:
    """Query trade notes."""
    conn = get_conn()
    cursor = conn.cursor()
    query = "SELECT * FROM trade_notes WHERE 1=1"
    params = []
    if trade_id:
        query += " AND trade_id = ?"
        params.append(trade_id)
    if symbol:
        query += " AND symbol = ?"
        params.append(symbol)
    if note_type:
        query += " AND note_type = ?"
        params.append(note_type)
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    notes = []
    for row in rows:
        notes.append(TradeNote(
            id=row["id"],
            trade_id=row["trade_id"],
            symbol=row["symbol"],
            timestamp=row["timestamp"],
            note_type=row["note_type"],
            title=row["title"],
            content=row["content"],
            tags=json.loads(row["tags"]),
            confidence=row["confidence"],
            related_trade_ids=json.loads(row["related_trade_ids"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        ))
    return notes


def update_note(note_id: int, **kwargs) -> bool:
    """Update a trade note."""
    allowed = {"title", "content", "tags", "confidence", "related_trade_ids", "note_type"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    updates["updated_at"] = datetime.now().isoformat(timespec="seconds")
    if "tags" in updates:
        updates["tags"] = json.dumps(updates["tags"])
    if "related_trade_ids" in updates:
        updates["related_trade_ids"] = json.dumps(updates["related_trade_ids"])

    conn = get_conn()
    cursor = conn.cursor()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [note_id]
    cursor.execute(f"UPDATE trade_notes SET {set_clause} WHERE id = ?", params)
    conn.commit()
    changed = cursor.rowcount > 0
    conn.close()
    return changed


def delete_note(note_id: int) -> bool:
    """Delete a trade note."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM trade_notes WHERE id = ?", (note_id,))
    conn.commit()
    changed = cursor.rowcount > 0
    conn.close()
    return changed


# --- Decision Logs ---

def log_decision(decision: DecisionLog) -> int:
    """Log a trading decision."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO decision_logs (timestamp, symbol, decision, rationale, factors_considered,
            regime, signal_strength, expected_outcome, actual_outcome, pnl, tags, confidence, review_date, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        decision.timestamp, decision.symbol, decision.decision, decision.rationale,
        json.dumps(decision.factors_considered), decision.regime, decision.signal_strength,
        decision.expected_outcome, decision.actual_outcome, decision.pnl,
        json.dumps(decision.tags), decision.confidence, decision.review_date,
        decision.created_at, decision.updated_at
    ))
    conn.commit()
    decision_id = cursor.lastrowid
    conn.close()
    return decision_id


def get_decisions(
    symbol: Optional[str] = None,
    decision: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    needs_review: bool = False,
    limit: int = 100,
) -> List[DecisionLog]:
    """Query decision logs."""
    conn = get_conn()
    cursor = conn.cursor()
    query = "SELECT * FROM decision_logs WHERE 1=1"
    params = []
    if symbol:
        query += " AND symbol = ?"
        params.append(symbol)
    if decision:
        query += " AND decision = ?"
        params.append(decision)
    if start_date:
        query += " AND timestamp >= ?"
        params.append(start_date)
    if end_date:
        query += " AND timestamp <= ?"
        params.append(end_date)
    if needs_review:
        query += " AND review_date IS NOT NULL AND review_date <= ?"
        params.append(datetime.now().isoformat(timespec="seconds"))
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    decisions = []
    for row in rows:
        decisions.append(DecisionLog(
            id=row["id"],
            timestamp=row["timestamp"],
            symbol=row["symbol"],
            decision=row["decision"],
            rationale=row["rationale"],
            factors_considered=json.loads(row["factors_considered"]),
            regime=row["regime"],
            signal_strength=row["signal_strength"],
            expected_outcome=row["expected_outcome"],
            actual_outcome=row["actual_outcome"],
            pnl=row["pnl"],
            tags=json.loads(row["tags"]),
            confidence=row["confidence"],
            review_date=row["review_date"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        ))
    return decisions


def update_decision_outcome(decision_id: int, actual_outcome: str, pnl: Optional[float] = None) -> bool:
    """Update a decision with its actual outcome."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE decision_logs SET actual_outcome = ?, pnl = ?, updated_at = ? WHERE id = ?
    """, (actual_outcome, pnl, datetime.now().isoformat(timespec="seconds"), decision_id))
    conn.commit()
    changed = cursor.rowcount > 0
    conn.close()
    return changed


def get_decisions_for_review() -> List[DecisionLog]:
    """Get all decisions that need review."""
    return get_decisions(needs_review=True)


# --- Review Sessions ---

def create_review_session(session: ReviewSession) -> int:
    """Create a review session."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO review_sessions (start_date, end_date, timestamp, decisions_reviewed,
            correct_decisions, incorrect_decisions, lessons_learned, action_items, overall_rating, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session.start_date, session.end_date, session.timestamp, session.decisions_reviewed,
        session.correct_decisions, session.incorrect_decisions,
        json.dumps(session.lessons_learned), json.dumps(session.action_items),
        session.overall_rating, session.notes
    ))
    conn.commit()
    session_id = cursor.lastrowid
    conn.close()
    return session_id


def get_review_sessions(limit: int = 20) -> List[ReviewSession]:
    """Get past review sessions."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM review_sessions ORDER BY timestamp DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()

    sessions = []
    for row in rows:
        sessions.append(ReviewSession(
            id=row["id"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            timestamp=row["timestamp"],
            decisions_reviewed=row["decisions_reviewed"],
            correct_decisions=row["correct_decisions"],
            incorrect_decisions=row["incorrect_decisions"],
            lessons_learned=json.loads(row["lessons_learned"]),
            action_items=json.loads(row["action_items"]),
            overall_rating=row["overall_rating"],
            notes=row["notes"],
        ))
    return sessions


# --- Analytics ---

def decision_accuracy(symbol: Optional[str] = None) -> Dict[str, Any]:
    """Compute decision accuracy stats."""
    decisions = get_decisions(symbol=symbol, limit=1000)
    reviewed = [d for d in decisions if d.actual_outcome]
    if not reviewed:
        return {"total": 0, "reviewed": 0, "accuracy": 0.0}

    correct = sum(1 for d in reviewed if d.actual_outcome.lower() in d.expected_outcome.lower())
    return {
        "total": len(decisions),
        "reviewed": len(reviewed),
        "correct": correct,
        "incorrect": len(reviewed) - correct,
        "accuracy": correct / len(reviewed),
    }


def note_frequency_by_type() -> Dict[str, int]:
    """Count notes by type."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT note_type, COUNT(*) as cnt FROM trade_notes GROUP BY note_type")
    rows = cursor.fetchall()
    conn.close()
    return {row["note_type"]: row["cnt"] for row in rows}


def tags_analysis() -> Dict[str, int]:
    """Analyze tag usage across notes and decisions."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT tags FROM trade_notes")
    note_rows = cursor.fetchall()
    cursor.execute("SELECT tags FROM decision_logs")
    decision_rows = cursor.fetchall()
    conn.close()

    tag_counts = {}
    for row in note_rows + decision_rows:
        try:
            tags = json.loads(row["tags"])
            for tag in tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        except json.JSONDecodeError:
            continue
    return dict(sorted(tag_counts.items(), key=lambda x: -x[1]))


def export_journal(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    path: Optional[Path] = None,
) -> Path:
    """Export journal to JSON."""
    if path is None:
        path = STATE_DIR / f"journal_export_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"

    notes = get_notes(limit=10000)
    decisions = get_decisions(limit=10000)
    reviews = get_review_sessions(limit=1000)

    if start_date:
        notes = [n for n in notes if n.timestamp >= start_date]
        decisions = [d for d in decisions if d.timestamp >= start_date]
    if end_date:
        notes = [n for n in notes if n.timestamp <= end_date]
        decisions = [d for d in decisions if d.timestamp <= end_date]

    data = {
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "notes": [asdict(n) for n in notes],
        "decisions": [asdict(d) for d in decisions],
        "reviews": [asdict(r) for r in reviews],
        "analytics": {
            "decision_accuracy": decision_accuracy(),
            "note_frequency": note_frequency_by_type(),
            "tag_analysis": tags_analysis(),
        },
    }
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return path


def print_note(note: TradeNote) -> None:
    """Pretty-print a trade note."""
    tags = " ".join(f"#{t}" for t in note.tags)
    print(f"\n[{note.timestamp}] {note.symbol} — {note.note_type.upper()}")
    print(f"  {note.title}")
    if tags:
        print(f"  Tags: {tags}")
    print(f"  {note.content}")
    print(f"  Confidence: {note.confidence}/10")


def print_decision(d: DecisionLog) -> None:
    """Pretty-print a decision log."""
    pnl_str = f" P&L: ${d.pnl:.2f}" if d.pnl is not None else ""
    review_str = f" | REVIEW BY: {d.review_date}" if d.review_date else ""
    print(f"\n[{d.timestamp}] {d.symbol} — {d.decision.upper()}{pnl_str}{review_str}")
    print(f"  Rationale: {d.rationale}")
    if d.factors_considered:
        print(f"  Factors: {', '.join(d.factors_considered)}")
    if d.regime:
        print(f"  Regime: {d.regime} | Signal: {d.signal_strength:.3f}")
    print(f"  Expected: {d.expected_outcome}")
    if d.actual_outcome:
        print(f"  Actual:   {d.actual_outcome}")
    print(f"  Confidence: {d.confidence}/10")