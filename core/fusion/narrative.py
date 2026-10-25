"""Local narrative simulation engine, adapted from the bundled MiroFish architecture.

MiroFish's pipeline shape is source text -> knowledge relation graph ->
heterogeneous agent profiles -> multi-round simulation -> structured report.
The bundled upstream needs genuine LLM and Zep Cloud providers, so it cannot
run inside Loki by itself. This module implements that same pipeline shape
deterministically: stance lexicons instead of language models, fixed persona
families instead of generated profiles, and a hash-seeded order instead of
randomness. Everything is inspectable: every event that moves a stance is
listed in the report.

This is original code; no upstream file is copied. The MiroFish source bundle,
its manifest and its AGPL-3.0 license stay in components/mirofish/upstream/.
The produced report doubles as a native MiroFish-shaped report artifact, so
the existing council path (core.fusion.miro_native.load_report) can read it
without any change.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.fusion.miro_native import data_directory

PROVENANCE = {
    "project": "MiroFish",
    "license": "AGPL-3.0 (bundled upstream; license file in components/mirofish/upstream)",
    "archive_sha256": "89cbffbebb32228b99a5d022ca919cc83fb227b1a254d63d1d9695a89d51f524",
    "adaptation": (
        "Same pipeline shape (source text -> relation graph -> heterogeneous persona "
        "families -> simulation rounds -> structured report) implemented deterministically "
        "with stance lexicons and hash-seeded order. No LLM, no Zep Cloud, no OASIS, "
        "and no upstream source copied."
    ),
}

ENGINE = "loki_narrative_native"
MAX_TEXT = 100_000
MIN_ROUNDS = 2
MAX_ROUNDS = 12
MAX_AGENTS_PER_FAMILY = 3
EVENT_LIST_LIMIT = 12
MAX_QUESTION = 4000
MAX_TITLE = 120

# Fixed persona families. Priors are starting stances in [-100, 100];
# sensitivity scales how strongly each family reacts to parsed stance events.
FAMILIES: tuple[dict[str, Any], ...] = (
    {
        "family": "Momentum believer",
        "prior": 8.0,
        "sensitivity": 1.15,
        "role": "Follows repeated directional wording once it hardens.",
    },
    {
        "family": "Skeptic analyst",
        "prior": -4.0,
        "sensitivity": 0.9,
        "role": "Discounts hedged, unconfirmed and rumor-flagged claims.",
    },
    {
        "family": "Contrarian retail",
        "prior": -6.0,
        "sensitivity": 1.0,
        "role": "Fades whatever the aggregate of the other families believes.",
    },
    {
        "family": "Risk manager",
        "prior": -2.0,
        "sensitivity": 0.6,
        "role": "Reacts only to downside language; ignores bullish claims.",
    },
    {
        "family": "Institutional accumulator",
        "prior": 5.0,
        "sensitivity": 0.75,
        "role": "Rewards steady, repeated strength spread over rounds.",
    },
)

SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\u2018\u2019\"'])")
TICKER_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,5}(?:/[A-Z]{2,5})?)\b")
PERCENT_RE = re.compile(r"\b\d+(?:\.\d+)?\s?%\b")
PRICE_RE = re.compile(r"\$\s?\d{1,3}(?:[,\d]{0,12})(?:\.\d+)?")
DATE_RE = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
    r"Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\b|\bQ[1-4]\b|\b20\d{2}\b"
)
HEDGE_RE = re.compile(
    r"\b(may|might|could|rumoured|rumored|unconfirmed|unverified|reported|reportedly|"
    r"report suggests|expected|possible|watch|unclear)\b", re.I
)
BULLISH_RE = re.compile(
    r"\b(rallies|rally|rallied|surge[sd]?|soar[sd]?|jump[sd]?|leaps?|leapt|upgrades?|"
    r"upgraded|upbeat|beats|record high|record profit|inflows?|bullish|expands?|expanded|"
    r"expanding|raises?|raised|buybacks?|optimism|optimistic|gains?|gained|climbs?|climbed|"
    r"outperforms?|outperformed|strengthens?|strengthened|accelerates?|accelerated)\b", re.I
)
BEARISH_RE = re.compile(
    r"\b(slumps?|slumped|plunges?|plunged|tanks?|tanked|crashes|crashed|downgrades?|"
    r"downgraded|misses|outflows?|bearish|lawsuits?|probe[s]?|probes|investigates|investigated|"
    r"investigation|sinks?|sank|tumbles?|tumbled|warning|warns?|cuts|slashes?|slashed|"
    r"weakens?|weakened|layoffs?|fraud|defaults?|bankruptcy|halts?|halted|delays?|delayed)\b", re.I
)

# Common uppercase words a naive ticker regex would capture from news prose.
STOPWORDS = frozenset({
    "AND", "ALLY", "THE", "THIS", "THAT", "WITH", "FROM", "HAVE", "HAS", "WAS", "WERE",
    "NOT", "BUT", "FOR", "ALL", "ANY", "ARE", "OUT", "ITS", "INTO", "OVER", "AFTER",
    "BEFORE", "WHILE", "WILL", "DID", "DOES", "NEWS", "CEO", "SEC", "ETF", "GDP", "FED",
    "FOMC", "CPI", "EPS", "IPO", "COO", "CFO", "CTO", "APR", "AUG", "DEC", "FEB", "JAN",
    "JUL", "JUN", "MAR", "MAY", "NOV", "OCT", "SEP", "MON", "TUE", "WED", "THU", "FRI",
    "SAT", "SUN", "AM", "PM", "ET", "PT", "NOW", "SAYS", "SAID", "SAY", "TODAY", "NEW",
    "OLD", "BIG", "LOW", "TOP", "OFF", "WAY", "BUY", "SELL", "HOLD", "WAIT", "MISS",
    "BEAT", "FULL", "YEAR", "WEEK", "DAILY",
})


def _clamp(value: float, low: float = -100.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _round1(value: float) -> float:
    return round(value, 1)


def _preprocess(text: str) -> str:
    """Collapse whitespace the way a report pipeline expects before splitting."""
    return re.sub(r"\s+", " ", text).strip()


def _split_sentences(text: str) -> list[str]:
    normalized = _preprocess(text)
    if not normalized:
        return []
    return [part.strip() for part in SPLIT_RE.split(normalized) if part.strip()]


def _extract_tickers(sentence: str) -> list[str]:
    found: list[str] = []
    for match in TICKER_RE.finditer(sentence):
        token = match.group(1)
        base = token.split("/")[0]
        if base in STOPWORDS or len(base) < 2:
            continue
        if token not in found:
            found.append(token)
    return found


def _stance_of(sentence: str) -> tuple[int, float, bool]:
    """Direction, weight and hedge flag for one sentence.

    Direction: +1 bullish, -1 bearish, 0 no usable stance. Weight grows with
    repeated stance wording and explicit percentages, halves when hedged. A
    sentence claiming both directions is counted as parsed but ineffective
    rather than guessed into one side.
    """
    bullish = BULLISH_RE.search(sentence)
    bearish = BEARISH_RE.search(sentence)
    hedged = HEDGE_RE.search(sentence) is not None
    if bullish is None and bearish is None:
        return 0, 0.0, hedged
    if bullish is not None and bearish is not None:
        return 0, 0.0, hedged
    direction = 1 if bullish is not None else -1
    hits = len(BULLISH_RE.findall(sentence) if direction > 0 else BEARISH_RE.findall(sentence))
    weight = 1.0
    if PERCENT_RE.search(sentence) is not None:
        weight += 1.0
    if hits >= 2:
        weight += 1.0
    weight = min(weight, 3.0)
    if hedged:
        weight *= 0.5
    return direction, weight, hedged


def _events_from(text: str) -> tuple[list[dict[str, Any]], int]:
    events: list[dict[str, Any]] = []
    skipped = 0
    for sentence in _split_sentences(text):
        direction, weight, hedged = _stance_of(sentence)
        if direction == 0:
            skipped += 1
            continue
        events.append({
            "text": sentence if len(sentence) <= 240 else sentence[:237] + "...",
            "direction": direction,
            "weight": weight,
            "hedged": hedged,
            "tickers": _extract_tickers(sentence),
        })
    return events, skipped


def _relation_graph(events: list[dict[str, Any]]) -> dict[str, Any]:
    tickers: list[str] = []
    edges = 0
    previous: set[str] = set()
    for event in events:
        current = {item for item in event["tickers"]}
        tickers.extend(sorted(current - set(tickers)))
        edges += len(current & previous)
        previous = current
    return {
        "nodes": len(events) + len(tickers),
        "edges": edges,
        "tickers": tickers[:12],
        "note": "Events sharing a ticker are related; counts only, no invented relations.",
    }


def _agents(seed: str, agents_per_family: int) -> list[dict[str, Any]]:
    agents: list[dict[str, Any]] = []
    for family in FAMILIES:
        for unit in range(agents_per_family):
            digest = hashlib.sha256(f"{seed}|{family['family']}|{unit}".encode()).digest()
            jitter = ((digest[0] << 8 | digest[1]) / 65535.0 - 0.5) * 12.0
            starting = _clamp(float(family["prior"]) + jitter)
            agents.append({
                "name": f"{family['family']} {unit + 1}",
                "family": str(family["family"]),
                "prior": _round1(starting),
                "stance": _round1(starting),
            })
    return agents


def _shares(agents: list[dict[str, Any]]) -> dict[str, float]:
    total = float(len(agents))
    bullish = sum(1 for agent in agents if agent["stance"] > 12.0)
    bearish = sum(1 for agent in agents if agent["stance"] < -12.0)
    return {
        "bullish": _round1(bullish / total * 100.0),
        "neutral": _round1((total - bullish - bearish) / total * 100.0),
        "bearish": _round1(bearish / total * 100.0),
    }


def _family_of(name: str) -> dict[str, Any]:
    return next(family for family in FAMILIES if family["family"] == name)


def _trajectory(
    agents: list[dict[str, Any]], events: list[dict[str, Any]], rounds: int, seed: str
) -> list[dict[str, Any]]:
    """Advance every persona through the parsed events, round by round.

    Hash-seeded rotation stands in for MiroFish's sampled per-round message
    flow. The contrarian family fades the other families' aggregate instead of
    the raw events, which is what its role says.
    """
    trajectory: list[dict[str, Any]] = []
    order_digest = hashlib.sha256(f"{seed}|order".encode()).digest()
    for round_index in range(rounds):
        offset = order_digest[round_index % len(order_digest)] % max(len(events), 1)
        for position, _ in enumerate(events):
            event = events[(offset + position) % len(events)]
            influence = float(event["direction"]) * float(event["weight"]) * (0.86 ** round_index)
            for agent in agents:
                if agent["family"] == "Contrarian retail":
                    continue
                if agent["family"] == "Risk manager" and influence >= 0:
                    continue
                strength = influence * float(_family_of(agent["family"])["sensitivity"])
                agent["stance"] = _round1(_clamp(agent["stance"] + strength * 2.2))
        mean_stance = math.fsum(agent["stance"] for agent in agents) / len(agents)
        for agent in agents:
            if agent["family"] == "Contrarian retail":
                agent["stance"] = _round1(_clamp(agent["stance"] - 0.10 * mean_stance))
        trajectory.append({
            "round": round_index + 1,
            "stance": _round1(math.fsum(agent["stance"] for agent in agents) / len(agents)),
            "shares": _shares(agents),
        })
    return trajectory


def _lean_label(stance: float) -> str:
    if stance > 20.0:
        return "Bullish lean"
    if stance < -20.0:
        return "Bearish lean"
    return "Mixed / no lean"


def _limits() -> list[str]:
    return [
        "A deterministic stance simulation of the narrative — not a forecast, not a probability, not a price target.",
        "Stance comes from a fixed lexicon; negation, sarcasm and mixed half-breeds are not parsed.",
        "Persona families are static priors, not simulated people or model-backed agents.",
        "Hypothetical agent scenarios are not verified trading evidence and never qualify a 70% win-rate claim.",
    ]


def _change_notes(events: list[dict[str, Any]]) -> list[str]:
    text = " ".join(str(event["text"]) for event in events)
    hedged = sum(1 for event in events if event["hedged"])
    notes: list[str] = []
    if PRICE_RE.search(text) is None:
        notes.append(
            "No explicit price or level appears in the source; a stance priced in levels could overturn this lean."
        )
    if DATE_RE.search(text) is None:
        notes.append("No dated event is mentioned; timing risk stays unmeasured here.")
    if PERCENT_RE.search(text) is None:
        notes.append("No percentage figure is cited; growth or margin claims stay unquantified.")
    if hedged:
        notes.append(
            f"{hedged} of {len(events)} stance events are hedged; confirmation could shift the low-sensitivity families."
        )
    if len(events) <= 2:
        notes.append("Only a couple of stance sentences were parsed; one added quote could flip the aggregate.")
    if not notes:
        notes.append(
            "The source already carries priced, dated and quantified language; "
            "stronger counter-evidence is what could move this lean."
        )
    return notes


def _build_outline(
    *,
    title: str,
    question: str,
    rounds: int,
    agents: list[dict[str, Any]],
    events: list[dict[str, Any]],
    skipped: int,
    trajectory: list[dict[str, Any]],
    stance: float,
    lean: str,
    seed: str,
) -> dict[str, Any]:
    config_lines = [
        f"Question: {question}",
        f"Rounds: {rounds}",
        f"Agents: {len(agents)} persona agents across {len(FAMILIES)} fixed families "
        f"({MAX_AGENTS_PER_FAMILY} per family).",
        f"Seed fingerprint: {seed[:12]} (hash-seeded order; identical input reproduces this report).",
    ]
    if events:
        listed: list[str] = []
        for event in events[:EVENT_LIST_LIMIT]:
            marker = "+" if int(event["direction"]) > 0 else "-"
            hedge = " (hedged)" if event["hedged"] else ""
            ticker = f" [{', '.join(event['tickers'])}]" if event["tickers"] else ""
            listed.append(f"- {marker}{hedge}: {event['text']}{ticker}")
        more = len(events) - len(listed)
        if more > 0:
            listed.append(f"(+{more} parsed stance events not listed; all still count.)")
        event_content = "\n".join(listed)
        if skipped:
            event_content += (
                f"\n{skipped} sentence(s) had no directional language and were counted but not simulated."
            )
    else:
        event_content = (
            "No directional sentences were parsed. The engine reports no lean rather than "
            "inventing one; only explicit directional language produces stances."
        )
        if skipped:
            event_content += f"\n{skipped} sentence(s) had no directional language."
    family_lines = [
        f"- {family['family']} (prior {_round1(float(family['prior'])):+.1f}, "
        f"sensitivity {float(family['sensitivity']):.2f}): {family['role']}"
        for family in FAMILIES
    ]
    trajectory_lines = [
        f"- Round {item['round']}: aggregate stance {_round1(float(item['stance'])):+.1f} | "
        f"bullish {float(item['shares']['bullish']):.1f}% | "
        f"neutral {float(item['shares']['neutral']):.1f}% | "
        f"bearish {float(item['shares']['bearish']):.1f}%"
        for item in trajectory
    ] or ["No rounds were run."]
    change_lines = [f"- {note}" for note in _change_notes(events)]
    summary = (
        f"Aggregate stance {stance:+.1f} of a [-100, +100] band: {lean}. "
        f"{len(agents)} persona agents reacted to {len(events)} parsed stance events over {rounds} rounds."
    )
    return {
        "title": title,
        "summary": summary,
        "sections": [
            {"title": "Simulation configuration", "content": "\n".join(config_lines)},
            {"title": "Parsed narrative events", "content": event_content},
            {"title": "Persona families", "content": "\n".join(family_lines)},
            {"title": "Stance trajectory", "content": "\n".join(trajectory_lines)},
            {"title": "What would change this lean", "content": "\n".join(change_lines)},
            {"title": "Limits", "content": "\n".join(_limits())},
        ],
    }


def outline_markdown(outline: dict[str, Any]) -> str:
    """Render the outline the way the native ReportOutline.to_markdown does."""
    markdown = f"# {outline['title']}\n\n> {outline['summary']}\n\n"
    for section in outline["sections"]:
        markdown += f"## {section['title']}\n\n"
        if section["content"]:
            markdown += f"{section['content']}\n\n"
    return markdown


def analyze_narrative(
    seed_text: str,
    *,
    question: str | None = None,
    rounds: int = 6,
    agents_per_family: int = 3,
    title: str | None = None,
) -> dict[str, Any]:
    """Run the deterministic narrative pipeline and return a native-shaped report."""
    if not isinstance(seed_text, str) or not seed_text.strip():
        raise ValueError("Seed text is required for the narrative simulation")
    if len(seed_text) > MAX_TEXT:
        raise ValueError(f"Seed text is capped at {MAX_TEXT} characters")
    if not isinstance(rounds, int) or isinstance(rounds, bool) or not MIN_ROUNDS <= rounds <= MAX_ROUNDS:
        raise ValueError(f"Rounds must be an integer between {MIN_ROUNDS} and {MAX_ROUNDS}")
    if not isinstance(agents_per_family, int) or isinstance(agents_per_family, bool) or not (
        1 <= agents_per_family <= MAX_AGENTS_PER_FAMILY
    ):
        raise ValueError(f"Agents per family must be an integer from 1 to {MAX_AGENTS_PER_FAMILY}")
    question = question if question and str(question).strip() else (
        "Simulate how fixed persona families react to this market narrative."
    )
    if len(question) > MAX_QUESTION:
        raise ValueError(f"The simulation question is capped at {MAX_QUESTION} characters")
    heading = str(title or "").strip() or "Local narrative simulation"
    if len(heading) > MAX_TITLE:
        raise ValueError(f"The report title is capped at {MAX_TITLE} characters")

    source = _preprocess(seed_text)
    seed = hashlib.sha256((source + "\n" + question).encode()).hexdigest()
    events, skipped = _events_from(source)
    graph = _relation_graph(events)
    agents = _agents(seed, agents_per_family)
    trajectory = _trajectory(agents, events, rounds, seed)
    stance = _round1(math.fsum(agent["stance"] for agent in agents) / len(agents))
    lean = _lean_label(stance)
    outline = _build_outline(
        title=heading,
        question=question,
        rounds=rounds,
        agents=agents,
        events=events,
        skipped=skipped,
        trajectory=trajectory,
        stance=stance,
        lean=lean,
        seed=seed,
    )
    now = datetime.now(timezone.utc).isoformat()
    return {
        "report_id": f"report_narr{seed[:12]}",
        "simulation_id": f"sim{seed[:10]}",
        "graph_id": f"graph{seed[:10]}",
        "simulation_requirement": question,
        "status": "completed",
        "error": None,
        "outline": outline,
        "markdown_content": "",
        "created_at": now,
        "completed_at": now,
        "engine": ENGINE,
        "aggregate_stance": stance,
        "lean": lean,
        "trajectory": trajectory,
        "agents": [
            {"name": agent["name"], "family": agent["family"], "stance": agent["stance"]}
            for agent in agents
        ],
        "events": events,
        "events_skipped": skipped,
        "graph": graph,
        "provenance": PROVENANCE,
        "data_kind": "hypothetical_agent_scenario",
        "performance_evidence_eligible": False,
        "fingerprint": seed,
    }


def save_report(report: dict[str, Any]) -> Path:
    """Persist the report as a native MiroFish-shaped artifact.

    Writes reports/<report_id>/meta.json plus full_report.md in the configured
    data directory so core.fusion.miro_native.load_report can read it back and
    the existing council evidence path stays unchanged.
    """
    report_id = str(report.get("report_id") or "")
    if not re.fullmatch(r"report_[A-Za-z0-9_-]{1,100}", report_id):
        raise ValueError("The narrative report carries an unusable native identifier")
    base = (data_directory() / "reports").resolve()
    folder = (base / report_id).resolve()
    if not folder.is_relative_to(base):
        raise ValueError("The narrative report path escaped its data directory")
    folder.mkdir(parents=True, exist_ok=True)
    meta = {key: report.get(key) for key in (
        "report_id", "simulation_id", "graph_id", "simulation_requirement",
        "status", "error", "outline", "markdown_content", "created_at", "completed_at",
    )}
    meta["markdown_content"] = ""
    (folder / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (folder / "full_report.md").write_text(outline_markdown(report["outline"]), encoding="utf-8")
    return folder / "meta.json"


def list_reports(limit: int = 20) -> list[dict[str, Any]]:
    """Saved native narrative artifacts, newest first, as a small library.

    Reports exactly what meta.json carries (identifier, title, creation stamp,
    status, simulation requirement) for at most `limit` folders. A report
    whose meta.json is missing or unparsable is flagged unreadable rather than
    skipped silently — and exactly nothing is invented to fill its fields.
    """
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise ValueError("Limit must be an integer from 1 to 100")
    base = data_directory() / "reports"
    if not base.is_dir():
        return []
    folders = [
        path
        for path in base.iterdir()
        if path.is_dir() and re.fullmatch(r"report_[A-Za-z0-9_-]{1,100}", path.name)
    ]
    folders.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    rows: list[dict[str, Any]] = []
    for folder in folders[:limit]:
        meta_file = folder / "meta.json"
        meta: dict[str, Any] | None = None
        if meta_file.is_file():
            try:
                parsed = json.loads(meta_file.read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    meta = parsed
            except ValueError:
                meta = None
        if not isinstance(meta, dict):
            rows.append({"report_id": folder.name, "unreadable": True})
            continue
        outline = meta.get("outline")
        title = outline.get("title") if isinstance(outline, dict) else None
        rows.append(
            {
                "report_id": str(meta.get("report_id") or folder.name),
                "title": str(title) if title else "",
                "created_at": str(meta.get("created_at") or ""),
                "status": str(meta.get("status") or ""),
                "simulation_requirement": str(meta.get("simulation_requirement") or ""),
            }
        )
    return rows
