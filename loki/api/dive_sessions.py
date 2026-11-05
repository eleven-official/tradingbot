"""Server-side engine and verified sessions for the Loki Dive daily.

The browser builds its own score and (until now) only the honour system stood
behind the leaderboard. This module adds the honest half:

- ``GET  /api/dive/challenge/order``   — the UTC-daily shared run: one prompt
  order per day, derived deterministically from the bank itself, the same
  seven prompts for every player on the planet.
- ``POST /api/dive/challenge/verify``  — replays a submitted round list
  through the *same* matching pipeline game.js uses (normalize → fold →
  length-aware Damerau tolerance) and returns round-by-round verified tiers
  and the exact total the client should have seen.
- ``POST /api/dive/challenge/publish`` — publishes a verified daily run to
  the shared board with the ``verified`` flag raised; self-reported rows stay
  plainly labelled.

The answer bank is read from the one file the browser plays
(``static/js/game_data.js`` — a single JSON literal now), so server and
client can never drift apart. The daily order derives from ``YYYYMMDD``
through the tiny mulberry32 PRNG; bank and seed are static, so anyone can
recompute the day's order — no secret, no trusting the browser.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date as _date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from loki.api import site_access
from loki.api.dive_board import MAX_SCORE, board_mode, local_write_verified
from loki.api.dive_board import _throttled, shared_write_verified
from loki.api.member_data import require_member

router = APIRouter(prefix="/api/dive", tags=["Dive daily challenge"])

ROUNDS_PER_DIVE = 7
ROUND_MS = 25000  # same starting clock as the browser
CLEAN_SWEEP_BONUS = 50  # all seven rounds found — matched to game.js
HOT_STREAK = 3  # consecutive finds before the combo pays
COMBO_BONUS = 5  # paid per find from the third in a row onward
MAX_SUBMIT_LEN = 64  # a longer answer cannot match anything; refuse it
_DAILY_SEED = 20261105  # derivation anchor; see daily_seed()

_BANK_PATH = Path(__file__).resolve().parents[2] / "static" / "js" / "game_data.js"


@lru_cache(maxsize=1)
def load_bank() -> Dict[str, Any]:
    """Parse the single JSON literal the browser plays. Fail loud on drift."""
    text = _BANK_PATH.read_text(encoding="utf-8")
    start = text.index("window.LokiDiveBank = ") + len("window.LokiDiveBank = ")
    end = text.rindex("}")  # the literal closes the file; nothing else follows
    data = json.loads(text[start : end + 1])
    tiers = data.get("tiers")
    prompts = data.get("prompts")
    if not isinstance(tiers, list) or len(tiers) != 6:
        raise HTTPException(503, "The dive bank file is unreadable on this server.")
    if not isinstance(prompts, list) or len(prompts) < 7:
        raise HTTPException(503, "The dive bank file is unreadable on this server.")
    return data


def _prompt_at(index: int) -> Dict[str, Any]:
    prompts = load_bank()["prompts"]
    if not 0 <= index < len(prompts):
        raise HTTPException(400, "That prompt index is not in the bank.")
    return prompts[index]


def tier_points(tier_index: int) -> int:
    return load_bank()["tiers"][tier_index]["points"]


def tier_name(tier_index: int) -> str:
    return load_bank()["tiers"][tier_index]["name"]


# ---------------------------------------------------------------------------
# Matching pipeline — ported 1:1 from static/js/game.js so a forged submission
# can never win points the browser would not also have awarded.
# ---------------------------------------------------------------------------

_PUNCT = re.compile(r"[^a-z0-9\s']")
_LEADING_ARTICLE = re.compile(r"^(a|an|the)\s+")


def normalize_answer(text: Any) -> str:
    """game.js normalize(): trim, lowercase, NFD-diacritics off, '&' to ' and',
    punctuation to spaces, apostrophes dropped, whitespace collapsed."""
    if not isinstance(text, str):
        return ""
    s = text.strip().lower()
    s = "".join(ch for ch in unicodedata.normalize("NFD", s) if not unicodedata.combining(ch))
    s = s.replace("&", " and ")
    s = _PUNCT.sub(" ", s)
    s = s.replace("'", "")
    return " ".join(s.split()).strip()


def fold_answer(text: Any) -> str:
    """game.js fold(): normalize, strip a leading article, then one trailing
    's' for words longer than three letters (never 'ss')."""
    s = normalize_answer(text)
    if not s:
        return ""
    s = _LEADING_ARTICLE.sub("", s).strip()
    if len(s) > 3 and s.endswith("s") and not s.endswith("ss"):
        s = s[:-1]
    return s


def tolerance_for(length: int) -> int:
    """Length-aware tolerance: short words exact, long ones forgive two."""
    if length <= 4:
        return 0
    if length <= 7:
        return 1
    return 2


def damerau_distance(a: str, b: str) -> int:
    """Optimal-string-alignment Damerau-Levenshtein, game.js algorithm."""
    m, n = len(a), len(b)
    if not m or not n:
        return m + n
    d = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        d[i][0] = i
    for j in range(n + 1):
        d[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            best = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                best = min(best, d[i - 2][j - 2] + 1)  # transposition
            d[i][j] = best
    return d[m][n]


@lru_cache(maxsize=2048)
def _prompt_index(prompt_index: int) -> Tuple[Tuple[str, str, int], ...]:
    """normalize-key -> (answer, tier), mirroring game.js buildIndex()."""
    prompt = _prompt_at(prompt_index)
    seen: Dict[str, Tuple[str, int]] = {}
    for answer, tier in prompt["a"]:
        key = normalize_answer(answer)
        if key and key not in seen:
            seen[key] = (answer, tier)
    return tuple((k, v[0], v[1]) for k, v in seen.items())


def match_answer(prompt_index: int, raw: Any) -> Optional[Dict[str, Any]]:
    """game.js findAnswer(): exact, then folded, then nearest in tolerance."""
    key = normalize_answer(raw)
    if not key:
        return None
    index = _prompt_index(prompt_index)
    exact = next((e for e in index if e[0] == key), None)
    if exact is not None:
        return {"answer": exact[1], "tier": exact[2], "fixed": False, "via": exact[0]}
    folded = fold_answer(raw)
    folded_hit = next((e for e in index if e[0] == folded and folded), None)
    if folded_hit is not None:
        return {
            "answer": folded_hit[1],
            "tier": folded_hit[2],
            "fixed": False,
            "via": folded_hit[0],
        }
    best: Optional[Tuple[str, str, int]] = None
    best_dist = 10**9
    for entry_key, answer, tier in index:
        candidates = [entry_key]
        alt = re.sub(r"^the\s+", "", entry_key)
        if alt != entry_key:
            candidates.append(alt)
        for cand in candidates:
            if cand == folded:
                continue  # already checked exactly
            dist = damerau_distance(folded, cand)
            tol = tolerance_for(max(len(folded), len(cand)))
            if dist <= tol and dist < best_dist:
                best_dist = dist
                best = (entry_key, answer, tier)
    if best is not None:
        return {"answer": best[1], "tier": best[2], "fixed": True, "via": best[0]}
    return None


# ---------------------------------------------------------------------------
# Shared daily order — mulberry32 over the bank, identical steps every day
# ---------------------------------------------------------------------------


def day_key(value: Optional[str]) -> str:
    """Validate (or derive today's) UTC daily key, ``YYYY-MM-DD``."""
    if not value:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise HTTPException(400, "date must look like YYYY-MM-DD.")
    try:
        _date.fromisoformat(value)
    except ValueError:
        raise HTTPException(400, "date must be a real calendar day.")
    return value


def daily_seed(day: str) -> int:
    """Stable, public derivation: YYYYMMDD folded into the 32-bit space.
    No secret — the order is meant to be recomputable by anyone."""
    return int(day.replace("-", ""), 10) & 0xFFFFFFFF


def _mulberry32(seed: int):
    """Bit-exact port of mulberry32 (the browser-standard PRNG, uint32 math)."""
    state = seed & 0xFFFFFFFF

    def _u32(x: int) -> int:
        return x & 0xFFFFFFFF

    def rnd() -> float:
        nonlocal state
        state = _u32(state + 0x6D2B79F5)
        t = state
        t = _u32((t ^ (t >> 15)) * (t | 1))
        t = _u32(t ^ _u32((t ^ _u32(t >> 7)) * (t | 61)))
        return _u32(t ^ (t >> 14)) / 4294967296.0

    return rnd


@lru_cache(maxsize=128)
def daily_order(day: str) -> Tuple[int, ...]:
    """Fisher-Yates over the whole bank driven by mulberry32; the first seven
    indexes are everyone's day. Same bank + same seed == same grace for all."""
    bank = load_bank()
    rng = _mulberry32(daily_seed(day))
    order = list(range(len(bank["prompts"])))
    for i in range(len(order) - 1, 0, -1):
        j = int(rng() * (i + 1))  # 0 <= r < 1, so floor keeps j <= i (as in JS)
        if j > i:
            j = i
        order[i], order[j] = order[j], order[i]
    return tuple(order[:ROUNDS_PER_DIVE])


class ChallengeOrderResponse(BaseModel):
    date: str
    rounds: int
    timer_ms: int
    order: List[int]
    prompts: List[Dict[str, Any]]


@router.get("/challenge/order")
async def challenge_order(date: Optional[str] = None) -> Dict[str, Any]:
    """The day's shared run: same prompts, same order, same clock for all."""
    key = day_key(date)
    order = list(daily_order(key))
    return {
        "date": key,
        "rounds": ROUNDS_PER_DIVE,
        "timer_ms": ROUND_MS,
        "order": order,
        "prompts": [
            {"i": i, "q": _prompt_at(i)["q"], "rules": _prompt_at(i)["rules"]} for i in order
        ],
        "note": "One shared order per UTC day — every player sees these same "
        "seven prompts in this same order.",
    }


# ---------------------------------------------------------------------------
# Verify + publish
# ---------------------------------------------------------------------------


class ChallengeVerifyBody(BaseModel):
    date: Optional[str] = Field(default=None, max_length=10)
    rounds: List[Dict[str, Any]] = Field(max_length=ROUNDS_PER_DIVE)


class ChallengeVerifyResponse(BaseModel):
    date: str
    verified: bool
    total_points: int
    base_points: int
    streak_bonus: int
    clean_sweep: int
    best_streak: int
    found_count: int
    rounds: List[Dict[str, Any]]
    missed: List[int]


def _run_scores(results: List[Optional[Dict[str, Any]]]) -> Tuple[int, int, int]:
    """Combo + clean sweep replay, identical to game.js's endRun payment."""
    streak = 0
    streak_bonus = 0
    best_streak = 0
    for r in results:
        if r is None:
            streak = 0
            continue
        streak += 1
        best_streak = max(best_streak, streak)
        if streak >= HOT_STREAK:
            streak_bonus += COMBO_BONUS
    clean_sweep = (
        CLEAN_SWEEP_BONUS
        if (len(results) == ROUNDS_PER_DIVE and all(r is not None for r in results))
        else 0
    )
    return streak_bonus, clean_sweep, best_streak


def replay_daily(date_key: str, rounds: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Replay a submitted round list against the day's shared order."""
    order = list(daily_order(date_key))
    if len(rounds) != len(order) or len(rounds) > ROUNDS_PER_DIVE:
        raise HTTPException(
            400,
            f"A daily run is exactly {ROUNDS_PER_DIVE} rounds in the shared "
            "order — this one cannot be verified.",
        )
    results: List[Optional[Dict[str, Any]]] = []
    for position, item in enumerate(order):
        submitted = rounds[position]
        claimed_index = submitted.get("i")
        if claimed_index is not None and int(claimed_index) != item:
            raise HTTPException(
                400,
                "The submitted round order does not match today's shared "
                "daily order — the run cannot be verified.",
            )
        raw = submitted.get("a", "")
        if not isinstance(raw, str) or len(raw) > MAX_SUBMIT_LEN:
            raise HTTPException(400, f"Answers are up to {MAX_SUBMIT_LEN} characters of text.")
        match = match_answer(item, raw)
        prompt = load_bank()["prompts"][item]
        if match:
            results.append(
                {
                    "i": item,
                    "q": prompt["q"],
                    "a": raw,
                    "matched": match["answer"],
                    "tier": match["tier"],
                    "tier_name": tier_name(match["tier"]),
                    "points": tier_points(match["tier"]),
                    "fixed": match["fixed"],
                }
            )
        else:
            results.append(None)
    streak_bonus, clean_sweep, best_streak = _run_scores(results)
    base = sum(r["points"] for r in results if r is not None)
    total = min(MAX_SCORE, base + streak_bonus + clean_sweep)
    found = [r for r in results if r is not None]
    return {
        "date": date_key,
        "verified": True,
        "total_points": total,
        "base_points": base,
        "streak_bonus": streak_bonus,
        "clean_sweep": clean_sweep,
        "best_streak": best_streak,
        "found_count": len(found),
        "rounds": found,
        "missed": [position for position, r in enumerate(results) if r is None],
    }


@router.post("/challenge/verify")
async def challenge_verify(body: ChallengeVerifyBody) -> ChallengeVerifyResponse:
    """Server-replayed scoring for a daily run; totals returned beat nothing —
    they are the same math the browser should have shown."""
    key = day_key(body.date)
    verdict = replay_daily(key, body.rounds)
    return ChallengeVerifyResponse(**verdict)


class ChallengePublishBody(BaseModel):
    nickname: str = Field(default="", max_length=32)
    date: Optional[str] = Field(default=None, max_length=10)
    rounds: List[Dict[str, Any]] = Field(max_length=ROUNDS_PER_DIVE)


@router.post("/challenge/publish", response_model=None)
def challenge_publish(request: Request, body: ChallengePublishBody) -> Dict[str, Any]:
    """Publish a daily run after the server replays it itself. Verified rows
    carry verified=true; self-reported rows stay plainly labelled. Sync def —
    the shared write rides FastAPI's threadpool, never the event loop."""
    key = day_key(body.date)
    verdict = replay_daily(key, body.rounds)
    if verdict["total_points"] <= 0:
        raise HTTPException(400, "Nothing verified in this run — the board only keeps real finds.")
    mode = board_mode()
    if mode == "shared":
        member = require_member(request)
        # cross-account tab guard, same guarantee the plain score route gives
        if request.headers.get("x-workspace-owner", member["uid"]) != member["uid"]:
            raise HTTPException(409, "Your signed-in account changed. Reload before publishing.")
        nickname = site_access.clean_nickname(member["nickname"])
        if not nickname:
            raise HTTPException(400, "Pick a board name (2-24 letters, numbers, spaces or dashes).")
        client_key = member["uid"]
    elif mode == "server-local":
        nickname = site_access.clean_nickname(body.nickname)
        if not nickname:
            raise HTTPException(400, "Pick a board name (2-24 letters, numbers, spaces or dashes).")
        client_key = request.client.host if request.client else "unknown"
    else:
        raise _HTTPException(
            503,
            "This deployment hosts no shared score store, so nothing was "
            "recorded — your best daily run still lives in this browser.",
        )
    # one verified publish per cooldown, same politeness as the plain score route
    if _throttled(client_key):
        raise HTTPException(429, "One publish per 20 seconds — give the board a breath.")
    if mode == "shared":
        row = shared_write_verified(member["uid"], nickname, verdict["total_points"])
    else:
        row = local_write_verified(nickname, verdict["total_points"])
    row["date"] = key
    row["verified"] = True
    return row
