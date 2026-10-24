"""Native narrative-engine pins: deterministic, honest, and council-compatible.

The engine adapts the bundled MiroFish pipeline shape without LLM/Zep/OASIS.
These tests pin what it may never do: invent a lean from neutral text, invent
prices or probabilities, or produce a report the existing native council path
cannot read back.
"""

import json
import re
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from core.fusion import narrative as narrative_module
from core.fusion.miro_native import load_report
from loki.api.fusion import router

BULLISH_TEXT = (
    "NVDA rallies as datacenter demand accelerates. Analysts upgrade the stock after it "
    "climbs to record high margins. Institutional inflows keep expanding."
)
BEARISH_TEXT = (
    "NVDA plunges after guidance misses expectations. Lawsuits probe the datacenter deal, "
    "and investors warn of outflows."
)
MIXED_TEXT = (
    "NVDA rallies as inflows expand. NVDA plunges as investors warn of outflows."
)
NEUTRAL_TEXT = (
    "The company publishes a quarterly note about governance meetings. Rows of the annual "
    "report describe committee structures."
)
HEDGED_TEXT = "Analysts may upgrade the stock after record inflows."
UNHEDGED_TEXT = "Analysts upgrade the stock after record inflows."


@pytest.fixture
def data_path(tmp_path, monkeypatch):
    monkeypatch.setenv("LOKI_MIROFISH_DATA_PATH", str(tmp_path))
    return tmp_path


@pytest.fixture
def app(monkeypatch):
    for key in ("LOKI_FUSION_LOCAL", "VERCEL", "LOKI_MIROFISH_URL"):
        monkeypatch.delenv(key, raising=False)
    application = FastAPI()
    application.include_router(router)
    return application


@pytest.fixture
def local_client(app, monkeypatch):
    monkeypatch.setenv("LOKI_FUSION_LOCAL", "1")
    with TestClient(app, base_url="http://127.0.0.1:8765", client=("127.0.0.1", 12345)) as client:
        yield client


def local_token(local_client):
    response = local_client.get("/api/fusion/capabilities")
    assert response.status_code == 200
    return {"X-Loki-Local-Token": response.json()["local_token"]}


def stable_report(report):
    """A timestamp-free copy for determinism comparisons."""
    return {key: value for key, value in report.items() if key not in ("created_at", "completed_at")}


def test_bullish_narrative_moves_stance_positive(data_path):
    report = narrative_module.analyze_narrative(BULLISH_TEXT)
    assert report["aggregate_stance"] > 20.0
    assert report["lean"] == "Bullish lean"
    assert report["events"], "bullish text must parse stance events"


def test_bearish_narrative_moves_stance_negative(data_path):
    report = narrative_module.analyze_narrative(BEARISH_TEXT)
    assert report["aggregate_stance"] < -20.0
    assert report["lean"] == "Bearish lean"


def test_balanced_text_stays_near_middle(data_path):
    report = narrative_module.analyze_narrative(MIXED_TEXT)
    assert abs(report["aggregate_stance"]) < 25.0
    bullish_events = [event for event in report["events"] if event["direction"] > 0]
    bearish_events = [event for event in report["events"] if event["direction"] < 0]
    assert bullish_events and bearish_events


def test_neutral_text_reports_no_invented_lean(data_path):
    report = narrative_module.analyze_narrative(NEUTRAL_TEXT)
    assert report["events"] == []
    assert report["events_skipped"] >= 1
    assert abs(report["aggregate_stance"]) <= 20.0
    assert report["lean"] == "Mixed / no lean"
    events_section = next(
        section for section in report["outline"]["sections"]
        if section["title"] == "Parsed narrative events"
    )
    assert "No directional sentences were parsed" in events_section["content"]


def test_identical_input_reproduces_the_report(data_path):
    first = stable_report(narrative_module.analyze_narrative(BULLISH_TEXT))
    second = stable_report(narrative_module.analyze_narrative(BULLISH_TEXT))
    assert first == second


def test_hedged_claims_weigh_half(data_path):
    hedged = narrative_module.analyze_narrative(HEDGED_TEXT)["events"]
    unhedged = narrative_module.analyze_narrative(UNHEDGED_TEXT)["events"]
    assert hedged and unhedged
    assert hedged[0]["hedged"] is True and unhedged[0]["hedged"] is False
    assert hedged[0]["weight"] * 2 == unhedged[0]["weight"]


def test_trajectory_and_agents_stay_bounded(data_path):
    report = narrative_module.analyze_narrative(BULLISH_TEXT, rounds=6)
    agents = report["agents"]
    assert len(agents) == len(narrative_module.FAMILIES) * 3
    for agent in agents:
        assert -100.0 <= agent["stance"] <= 100.0
    for item in report["trajectory"]:
        assert -100.0 <= item["stance"] <= 100.0
        shares = item["shares"]
        assert abs(shares["bullish"] + shares["neutral"] + shares["bearish"] - 100.0) < 0.3


def test_report_matches_the_native_contract_and_round_trips(data_path):
    report = narrative_module.analyze_narrative(
        BULLISH_TEXT, title="Loki market scenario", question="Will the rally hold?"
    )
    assert re.fullmatch(r"report_[A-Za-z0-9_-]{1,100}", report["report_id"])
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,128}", report["simulation_id"])
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,128}", report["graph_id"])
    assert report["status"] == "completed" and not report["error"]
    assert len(report["simulation_requirement"]) <= 20000
    outline = report["outline"]
    assert isinstance(outline["title"], str) and isinstance(outline["summary"], str)
    assert 1 <= len(outline["sections"]) <= 50
    for section in outline["sections"]:
        assert isinstance(section["title"], str)
        assert isinstance(section["content"], str)
    saved = narrative_module.save_report(report)
    assert (Path(saved)).is_file()
    artifact = json.loads(Path(saved).read_text(encoding="utf-8"))
    assert artifact["report_id"] == report["report_id"]
    assert artifact["status"] == "completed"
    loaded = load_report(report["report_id"], "NVDA")
    assert loaded["engine"] == "bundled_mirofish_native"
    assert loaded["data_kind"] == "hypothetical_agent_scenario"
    assert loaded["report"]["status"] == "completed"
    assert loaded["report"]["outline"]["title"] == "Loki market scenario"
    assert len(loaded["artifact_sha256"]) == 64


def test_outline_never_invents_prices_or_probabilities(data_path):
    report = narrative_module.analyze_narrative(BULLISH_TEXT + " Target $40 and 5% upside claims.")
    summary = report["outline"]["summary"]
    assert "$" not in summary
    markdown = narrative_module.outline_markdown(report["outline"])
    assert "not a forecast" in markdown
    for title in ("Limits", "What would change this lean"):
        section = next(
            item for item in report["outline"]["sections"] if item["title"] == title
        )
        assert "$" not in section["content"]
    limits = next(
        section for section in report["outline"]["sections"] if section["title"] == "Limits"
    )
    assert "not a probability" in limits["content"]
    assert "not verified trading evidence" in limits["content"]


def test_what_would_change_honesty(data_path):
    report = narrative_module.analyze_narrative(HEDGED_TEXT)
    change = next(
        section for section in report["outline"]["sections"]
        if section["title"] == "What would change this lean"
    )
    notes = change["content"]
    assert "No explicit price or level" in notes
    assert "1 of 1 stance events are hedged" in notes


def test_engine_rejects_junk_input(data_path):
    with pytest.raises(ValueError):
        narrative_module.analyze_narrative("   ")
    with pytest.raises(ValueError):
        narrative_module.analyze_narrative("NVDA rallies.", rounds=1)
    with pytest.raises(ValueError):
        narrative_module.analyze_narrative("NVDA rallies.", rounds=13)
    with pytest.raises(ValueError):
        narrative_module.analyze_narrative("NVDA rallies.", agents_per_family=0)
    with pytest.raises(ValueError):
        narrative_module.analyze_narrative("NVDA rallies." * 1, question="x" * 4001)
    bad = narrative_module.analyze_narrative("NVDA rallies.")
    del bad["report_id"]
    with pytest.raises(ValueError):
        narrative_module.save_report(bad)


def test_compute_stays_public_but_save_needs_the_launcher(local_client):
    response = local_client.post("/api/fusion/narrative", json={"seed_text": BULLISH_TEXT, "save": False})
    assert response.status_code == 200
    assert response.json()["saved"] is None
    assert response.json()["lean"] == "Bullish lean"

    refused = local_client.post("/api/fusion/narrative", json={"seed_text": BULLISH_TEXT, "save": True})
    assert refused.status_code == 403
    assert "launcher" in refused.json()["detail"]


def test_local_launcher_saves_and_list_reports(local_client, data_path):
    headers = local_token(local_client)
    response = local_client.post(
        "/api/fusion/narrative",
        json={"seed_text": BULLISH_TEXT, "title": "Council candidate", "save": True},
        headers=headers,
    )
    assert response.status_code == 200
    saved = response.json()["saved"]
    assert isinstance(saved["report_id"], str)
    report_id = saved["report_id"]
    assert re.fullmatch(r"report_[A-Za-z0-9_-]{1,100}", report_id)
    loaded = load_report(report_id, "NVDA")
    assert loaded["report"]["outline"]["title"] == "Council candidate"


def test_endpoint_validates_input_as_human_copy(local_client, data_path):
    response = local_client.post("/api/fusion/narrative", json={"seed_text": "   "})
    assert response.status_code == 422
    oversized = local_client.post("/api/fusion/narrative", json={"seed_text": "NVDA rallies. " * 12000})
    assert oversized.status_code == 422
