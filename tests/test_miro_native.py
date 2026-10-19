"""Exercise the actual retained MiroFish report reader, not an HTTP mock."""

import ast
import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from core.fusion.council import build_council_report
from core.fusion.miro_native import COMPONENT, load_report, native_status
from loki.api.server import app
from tests.test_fusion_quant import sample_bars


def native_fixture(tmp_path, monkeypatch, **changes):
    monkeypatch.setenv("LOKI_MIROFISH_DATA_PATH", str(tmp_path))
    path = tmp_path / "reports/report_fixture"
    path.mkdir(parents=True, exist_ok=True)
    value = {
        "report_id": "report_fixture",
        "simulation_id": "sim_fixture",
        "graph_id": "graph_fixture",
        "simulation_requirement": "Synthetic native-contract fixture for BTC/USDT; not a real agent run.",
        "status": "completed",
        "outline": {
            "title": "Fixture liquidity scenario",
            "summary": "A hypothetical shock creates uncertainty.",
            "sections": [
                {
                    "title": "Counterargument",
                    "content": "A thin market could invalidate the price signal.",
                }
            ],
        },
        "markdown_content": "",
        "created_at": "2026-10-17T00:00:00",
        "completed_at": "2026-10-17T00:02:00",
        "error": None,
        **changes,
    }
    (path / "meta.json").write_text(json.dumps(value), encoding="utf-8")
    (path / "full_report.md").write_text("# Native fixture\nHypothetical only.", encoding="utf-8")
    return path, value


def test_all_upstream_files_and_license_match_the_supplied_archive_manifest():
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    assert len(manifest["files"]) == 128
    for name, expected in manifest["files"].items():
        assert (
            hashlib.sha256((COMPONENT / "upstream" / name).read_bytes()).hexdigest() == expected
        ), name
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in (COMPONENT / "upstream/LICENSE").read_text()
    assert (
        hashlib.sha256((COMPONENT / "report_contracts.py").read_bytes()).hexdigest()
        == manifest["report_contracts"]["sha256"]
    )


def test_executed_report_classes_and_reader_are_actual_unchanged_native_code():
    def classes(path):
        return {
            node.name: node
            for node in ast.parse(path.read_text(encoding="utf-8")).body
            if isinstance(node, ast.ClassDef)
        }

    original = classes(COMPONENT / "upstream/backend/app/services/report_agent.py")
    retained = classes(COMPONENT / "report_contracts.py")
    for name in ("Report", "ReportOutline", "ReportSection", "ReportStatus"):
        assert ast.dump(original[name]) == ast.dump(retained[name])
    methods = {
        node.name: node
        for node in original["ReportManager"].body
        if isinstance(node, ast.FunctionDef)
    }
    for node in retained["ReportManager"].body:
        if isinstance(node, ast.FunctionDef):
            assert ast.dump(node) == ast.dump(methods[node.name])


def test_native_reader_executes_and_loads_actual_meta_and_markdown_layout(tmp_path, monkeypatch):
    path, _ = native_fixture(tmp_path, monkeypatch)
    (path / "full_report.md").write_text(
        "# Native fixture — 原生模拟\nHypothetical only.", encoding="utf-8"
    )
    packet = load_report("report_fixture", "BTC/USDT")
    assert "ReportManager" in packet["native_classes_executed"]
    assert packet["report"]["markdown_content"].startswith("# Native fixture")
    assert "— 原生模拟" in packet["report"]["markdown_content"]
    assert packet["report"]["outline"]["sections"][0]["title"] == "Counterargument"
    assert packet["project_api_called"] is False
    assert packet["performance_evidence_eligible"] is False
    assert len(packet["artifact_sha256"]) == 64
    assert native_status()["source_bundled"] is True


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "generating"},
        {"error": "provider failed"},
        {"report_id": "report_other"},
        {"outline": None},
    ],
)
def test_incomplete_failed_or_mismatched_reports_never_enter_the_council(
    tmp_path, monkeypatch, changes
):
    native_fixture(tmp_path, monkeypatch, **changes)
    with pytest.raises(ValueError):
        load_report("report_fixture", "BTC/USDT")


def test_native_scenario_changes_the_review_and_adds_a_gate_without_overriding_performance(
    tmp_path, monkeypatch
):
    native_fixture(tmp_path, monkeypatch)
    packet = load_report("report_fixture", "BTC/USDT")
    report = build_council_report(sample_bars(), miro_research=packet)
    assert report["analysts"][1]["status"] == "scenario_needs_review"
    assert "Counterargument" in str(report["analysts"][1]["evidence"])
    assert "MiroFish scenario reviewed" in report["director"]["blocked_by"]
    reviewed = build_council_report(sample_bars(), miro_research=packet, miro_reviewed=True)
    assert "MiroFish scenario reviewed" not in reviewed["director"]["blocked_by"]
    assert reviewed["performance_target"]["supported"] is False
    assert reviewed["director"]["decision"] == "wait"
    assert reviewed["live_trading_enabled"] is False


def test_native_artifacts_are_private_and_tokens_are_needed_for_both_preview_and_council(
    tmp_path, monkeypatch
):
    native_fixture(tmp_path, monkeypatch)
    monkeypatch.setenv("LOKI_FUSION_LOCAL", "1")
    with TestClient(app, base_url="http://127.0.0.1:8765", client=("127.0.0.1", 1234)) as client:
        payload = {"bars": sample_bars(), "miro_report_id": "report_fixture"}
        assert client.post("/api/fusion/council", json=payload).status_code == 403
        assert client.get("/api/fusion/native-mirofish/report/report_fixture").status_code == 403
        headers = {
            "X-Loki-Local-Token": client.get("/api/fusion/capabilities").json()["local_token"]
        }
        preview = client.get("/api/fusion/native-mirofish/report/report_fixture", headers=headers)
        assert preview.status_code == 200, preview.text
        result = client.post("/api/fusion/council", json=payload, headers=headers)
        assert result.status_code == 200, result.text
        assert result.headers["cache-control"] == "private, no-store"
        assert result.json()["miro_research"]["engine"] == "bundled_mirofish_native"
        assert "MiroFish scenario reviewed" in result.json()["director"]["blocked_by"]
