"""Read completed native MiroFish artifacts through the retained original code.

No project HTTP API or cloud call. A host-selected data directory contains
MiroFish's report JSON. Browser input is an identifier, never a path. Scenario
opinions remain source material, not instructions or verified trading evidence.
"""

from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

COMPONENT = Path(__file__).resolve().parents[2] / "components" / "mirofish"


def data_directory():
    return (
        Path(os.environ.get("LOKI_MIROFISH_DATA_PATH") or COMPONENT / "upstream/backend/uploads")
        .expanduser()
        .resolve()
    )


def native_status():
    return {
        "engine": "bundled_mirofish_native",
        "source_bundled": (COMPONENT / "upstream/backend/app/services/report_agent.py").is_file(),
        "report_reader_ready": (COMPONENT / "report_bridge.py").is_file(),
        "data_directory_configured": bool(os.environ.get("LOKI_MIROFISH_DATA_PATH")),
        "reports_available": (data_directory() / "reports").is_dir(),
        "requires_project_api": False,
        "source_license": "AGPL-3.0",
        "simulation_provider_readiness": "not_checked",
    }


def load_report(report_id, symbol):
    if not isinstance(report_id, str) or not re.fullmatch(
        r"report_[A-Za-z0-9_-]{1,100}", report_id
    ):
        raise ValueError("Use a native MiroFish report_ identifier")
    base = (data_directory() / "reports").resolve()
    locations = [base / report_id / "meta.json", base / (report_id + ".json")]
    path = next((path for path in locations if path.is_file()), None)
    if path is None:
        raise ValueError(
            "No native MiroFish report with this ID exists in the configured local data directory"
        )
    path = path.resolve()
    if not path.is_relative_to(base) or path.stat().st_size > 1_500_000:
        raise ValueError("Native report path or size is invalid")
    raw = path.read_bytes()
    markdown = base / report_id / "full_report.md"
    if markdown.exists() and (
        not markdown.resolve().is_relative_to(base) or markdown.stat().st_size > 1_500_000
    ):
        raise ValueError("Native report markdown path or size is invalid")
    value = json.loads(raw)
    if (
        not isinstance(value, dict)
        or value.get("report_id") != report_id
        or value.get("status") != "completed"
        or value.get("error")
    ):
        raise ValueError(
            "Only a completed, nonfailed report with a matching native identity can enter the council"
        )
    for field in ("simulation_id", "graph_id"):
        if not isinstance(value.get(field), str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{1,128}", value[field]
        ):
            raise ValueError("Native report is missing its simulation/graph identity")
    if (
        not isinstance(value.get("simulation_requirement"), str)
        or len(value["simulation_requirement"]) > 20000
    ):
        raise ValueError("Native report needs its bounded simulation question")
    outline = value.get("outline")
    if (
        not isinstance(outline, dict)
        or not isinstance(outline.get("title"), str)
        or not isinstance(outline.get("summary"), str)
    ):
        raise ValueError("Native report requires its structured outline and summary")
    sections = outline.get("sections")
    if (
        not isinstance(sections, list)
        or not 1 <= len(sections) <= 50
        or any(
            not isinstance(section, dict)
            or not isinstance(section.get("title"), str)
            or not isinstance(section.get("content", ""), str)
            for section in sections
        )
    ):
        raise ValueError("Native report sections are invalid")
    environment = {
        name: os.environ[name] for name in ("SystemRoot", "WINDIR", "PATH") if name in os.environ
    }
    environment.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    result = subprocess.run(
        [sys.executable, "-I", str(COMPONENT / "report_bridge.py")],
        input=json.dumps({"report_id": report_id, "reports_directory": str(base)}).encode("utf-8"),
        capture_output=True,
        timeout=10,
        env=environment,
        cwd=COMPONENT,
        check=False,
    )
    if result.returncode or len(result.stdout) > 2_000_000:
        raise ValueError("The original MiroFish report classes could not normalize this artifact")
    normalized = json.loads(result.stdout)
    if (
        normalized.get("report", {}).get("status") != "completed"
        or normalized["report"].get("report_id") != report_id
    ):
        raise ValueError(
            "Native report changed identity or status while it was read; inspect it again"
        )
    return {
        "engine": "bundled_mirofish_native",
        "symbol": symbol,
        "report": normalized["report"],
        "native_classes_executed": normalized["native_classes"],
        "artifact_sha256": hashlib.sha256(
            json.dumps(normalized["report"], sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest(),
        "fingerprint_kind": "normalized_native_report",
        "metadata_sha256": hashlib.sha256(raw).hexdigest(),
        "data_kind": "hypothetical_agent_scenario",
        "project_api_called": False,
        "performance_evidence_eligible": False,
        "instrument_binding": "operator-selected council instrument; not independently authenticated",
        "timestamp_note": "Native report times may omit a timezone; freshness and point-in-time market availability are unverified.",
    }
