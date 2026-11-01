"""Explicit local-operator notes for Loki chat, stored as Obsidian Markdown.

Notes are data, never instructions, broker state or trading-model inputs.
No automatic transcript collection or network synchronization.
"""
from datetime import datetime, timezone
from itertools import islice
import os
from pathlib import Path
import re
import threading
from uuid import uuid4

_lock = threading.Lock()
MAX_NOTES = 1000
MAX_BYTES = 8192


def vault_path():
    configured = os.environ.get("LOKI_MEMORY_DIR")
    return Path(configured).expanduser().resolve() if configured else Path(__file__).resolve().parents[1] / "state/loki_memory"


def command(message):
    text = message.strip()
    if re.match(r"^remember(?:\s|:)", text, re.I):
        return "save", re.sub(r"^remember\s*:?\s*", "", text, flags=re.I)
    if re.match(r"^recall(?:\s|$)", text, re.I):
        return "recall", re.sub(r"^recall\s*:?\s*", "", text, flags=re.I)
    if text.casefold() in {"memory", "memory status", "show memory"}:
        return "recall", ""
    return None


def _files(root):
    return list(islice(root.glob("loki-note-*.md"), MAX_NOTES + 1)) if root.exists() else []


def remember(text):
    text = text.strip()
    if not text or len(text) > 2000:
        raise ValueError("Memory notes must contain 1–2000 characters")
    if re.search(r"sb_secret_|(?:AK|PK)[A-Z0-9]{18,}|eyJ[A-Za-z0-9_-]+\.|api[_ -]?(?:key|secret)\s*[:=]|password\s*[:=]|token\s*[:=]", text, re.I):
        raise ValueError("Do not store credentials in memory")
    root = vault_path()
    with _lock:
        root.mkdir(parents=True, exist_ok=True)
        if len(_files(root)) >= MAX_NOTES:
            raise ValueError("Memory note limit reached; archive notes in Obsidian first")
        name = "loki-note-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex + ".md"
        body = "# Loki memory note\n\nRecorded UTC: " + datetime.now(timezone.utc).isoformat() + "\n\n" + text + "\n"
        with (root / name).open("x", encoding="utf-8") as stream:
            stream.write(body)
    return name


def recall(query=""):
    root = vault_path()
    terms = re.findall(r"\w+", query.casefold())[:20]
    matches = []
    for path in sorted(_files(root), reverse=True)[:MAX_NOTES]:
        if path.is_symlink() or not path.is_file():
            continue
        try:
            with path.open("rb") as stream:
                raw = stream.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                continue
            text = raw.decode("utf-8")
        except (OSError, UnicodeError):
            continue
        if terms and not all(term in text.casefold() for term in terms):
            continue
        matches.append({"file": path.name, "text": text[:2400]})
        if len(matches) == 5:
            break
    return matches


def respond(action, text):
    if action == "save":
        name = remember(text)
        return f"Saved to Loki memory: {name}. This is a note, not a trading instruction or verified market fact."
    matches = recall(text)
    if not matches:
        return "No matching Loki memory notes. Use ‘remember your note’ to save one."
    return "Saved Loki notes (historical, not live account data):\n\n" + "\n\n".join(item["text"] for item in matches)
