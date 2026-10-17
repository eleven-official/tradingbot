"""Local transport, real upstream wire contracts, and execution boundaries."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from threading import Thread

import pytest

from core.fusion.external import ExternalEngineError, FinceptAdapter, MiroFishAdapter


@contextmanager
def miro_server():
    calls = []
    responses = {
        "/health": (200, {"status": "ok", "service": "MiroFish Backend"}),
        "/api/graph/project/list": (200, {"success": True, "data": {"projects": []}}),
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            self.respond()

        def do_POST(self):
            self.respond()

        def respond(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            calls.append((self.command, self.path, body, self.headers.get("Content-Type")))
            status, result = responses.get(
                self.path, (200, {"success": True, "data": {"id": "example"}})
            )
            encoded = json.dumps(result).encode() if isinstance(result, dict) else result
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            if status == 302:
                self.send_header(
                    "Location", f"http://127.0.0.1:{self.server.server_port}/unexpected"
                )
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", calls, responses
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize(
    "origin",
    [
        "https://127.0.0.1:5001",
        "http://example.com:5001",
        "http://192.168.1.1:5001",
        "http://169.254.169.254:80",
        "http://0.0.0.0:5001",
        "http://127.0.0.1",
        "http://user:password@127.0.0.1:5001",
        "http://127.0.0.1:5001/other",
        "http://127.0.0.1:5001?target=external",
        "http://127.0.0.1:5001#fragment",
        "http://localhost.example.com:5001",
        "http://2130706433:5001",
    ],
)
def test_non_loopback_and_ambiguous_origins_are_rejected(origin):
    with pytest.raises(ValueError, match="loopback"):
        MiroFishAdapter(origin)


def test_default_engines_are_unconfigured_or_locked():
    miro = MiroFishAdapter.from_env({})
    assert miro.status()["state"] == "unconfigured"
    assert miro.status()["jobs_allowed"] is False
    with pytest.raises(ExternalEngineError, match="unconfigured"):
        miro.projects()
    fincept = FinceptAdapter.from_env({})
    assert fincept.status()["state"] == "license_required"
    assert fincept.status()["licensed"] is False
    with pytest.raises(ExternalEngineError, match="commercial license"):
        fincept.risk([0.01, -0.01] * 20)


def test_actual_mirofish_identity_and_project_route_required(monkeypatch):
    # An environment proxy must never receive local research documents.
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
    with miro_server() as (origin, calls, responses):
        adapter = MiroFishAdapter(origin)
        assert adapter.status()["state"] == "ready"
        assert [call[:2] for call in calls] == [
            ("GET", "/health"),
            ("GET", "/api/graph/project/list"),
        ]
        responses["/health"] = (200, {"status": "ok", "service": "Unrelated Service"})
        assert adapter.status()["state"] == "unavailable"


def test_mirofish_jobs_stay_disabled_until_operator_opt_in():
    with miro_server() as (origin, calls, _responses):
        adapter = MiroFishAdapter(origin)
        with pytest.raises(ExternalEngineError, match="jobs are disabled"):
            adapter.start_simulation("sim_example")
        with pytest.raises(ExternalEngineError, match="jobs are disabled"):
            adapter.create_project("Research", "A source document.", "Explore a scenario.")
        assert calls == []


def test_mirofish_configuration_status_does_not_probe_the_service():
    with miro_server() as (origin, calls, _responses):
        status = MiroFishAdapter(origin).status(probe=False)
        assert status["state"] == "configured"
        assert status["connection_verified"] is False
        assert calls == []


def test_serverless_environment_cannot_enable_desktop_engines():
    env = {
        "VERCEL": "1",
        "LOKI_MIROFISH_URL": "http://127.0.0.1:5001",
        "LOKI_MIROFISH_ALLOW_JOBS": "1",
        "LOKI_FINCEPT_PATH": ".",
        "LOKI_FINCEPT_LICENSE_CONFIRMED": "1",
        "LOKI_FINCEPT_ALLOW_ANALYTICS": "1",
    }
    assert MiroFishAdapter.from_env(env).status()["state"] == "unconfigured"
    assert FinceptAdapter.from_env(env).status()["jobs_allowed"] is False


def test_mirofish_real_multipart_project_contract_and_job_sequence():
    with miro_server() as (origin, calls, _responses):
        adapter = MiroFishAdapter(origin, allow_jobs=True)
        adapter.create_project(
            "Risk study", "Source text: inflation news.", "Compare agent reactions."
        )
        method, path, body, content_type = calls[-1]
        assert (method, path) == ("POST", "/api/graph/ontology/generate")
        assert content_type.startswith("multipart/form-data; boundary=")
        assert b'name="files"; filename="loki-research.txt"' in body
        assert b'name="project_name"' in body and b"Risk study" in body
        assert b'name="simulation_requirement"' in body and b"Compare agent reactions." in body
        adapter.build_graph("proj_test")
        assert json.loads(calls[-1][2]) == {"project_id": "proj_test", "force": False}
        adapter.create_simulation("proj_test", "graph_test")
        assert json.loads(calls[-1][2])["graph_id"] == "graph_test"
        adapter.prepare_simulation("sim_test")
        assert json.loads(calls[-1][2])["force_regenerate"] is False
        adapter.start_simulation("sim_test", 4)
        assert json.loads(calls[-1][2]) == {
            "simulation_id": "sim_test",
            "max_rounds": 4,
            "platform": "parallel",
            "enable_graph_memory_update": False,
            "force": False,
        }
        adapter.generate_report("sim_test")
        assert json.loads(calls[-1][2]) == {"simulation_id": "sim_test", "force_regenerate": False}
        adapter.chat("sim_test", "What are the strongest counterarguments?")
        assert calls[-1][1] == "/api/report/chat"


def test_mirofish_polling_uses_post_without_enabling_paid_jobs():
    with miro_server() as (origin, calls, _responses):
        adapter = MiroFishAdapter(origin)
        adapter.preparation_status("sim_test", "task_test")
        adapter.report_status("sim_test", "task_report")
        assert [call[:2] for call in calls] == [
            ("POST", "/api/simulation/prepare/status"),
            ("POST", "/api/report/generate/status"),
        ]
        assert json.loads(calls[0][2]) == {"simulation_id": "sim_test", "task_id": "task_test"}


def test_mirofish_rejects_identifier_path_injection_and_unbounded_rounds():
    with miro_server() as (origin, calls, _responses):
        adapter = MiroFishAdapter(origin, allow_jobs=True)
        for identifier in (
            "../../health",
            "sim_test?target=other",
            "sim_test#report",
            "sim/test",
            "",
        ):
            with pytest.raises(ValueError):
                adapter.simulation(identifier)
        for rounds in (True, 0, 101, 1.5, "10"):
            with pytest.raises(ValueError, match="max_rounds"):
                adapter.start_simulation("sim_test", rounds)
        assert calls == []


def test_mirofish_redirects_invalid_json_and_tracebacks_are_not_forwarded():
    with miro_server() as (origin, calls, responses):
        adapter = MiroFishAdapter(origin)
        responses["/api/graph/project/list"] = (302, {})
        with pytest.raises(ExternalEngineError, match="redirects are blocked"):
            adapter.projects()
        assert not any(call[1] == "/unexpected" for call in calls)
        responses["/api/graph/project/list"] = (
            500,
            {"error": "private-token", "traceback": "secret-path"},
        )
        with pytest.raises(ExternalEngineError) as exc:
            adapter.projects()
        assert "private-token" not in str(exc.value) and "secret-path" not in str(exc.value)
        responses["/api/graph/project/list"] = (200, b"not json")
        with pytest.raises(ExternalEngineError, match="invalid JSON"):
            adapter.projects()
        responses["/api/graph/project/list"] = (
            200,
            {"success": True, "data": [], "traceback": "secret-path"},
        )
        assert adapter.projects() == {"success": True, "data": []}


def test_mirofish_bounded_payload_and_response():
    with miro_server() as (origin, calls, responses):
        adapter = MiroFishAdapter(origin, allow_jobs=True)
        with pytest.raises(ValueError, match="document_text"):
            adapter.create_project("Test", "x" * 100_001, "A requirement")
        assert calls == []
        responses["/api/graph/project/list"] = (200, b" " * (adapter.max_response_bytes + 1))
        with pytest.raises(ExternalEngineError, match="response limit"):
            adapter.projects()


@pytest.fixture
def licensed_component(tmp_path):
    # A tiny independent test fixture, not a copy or substitute of Fincept.
    # It checks the fixed CLI transport without needing proprietary source in CI.
    directory = tmp_path / "fincept-qt/scripts/Analytics/portfolioManagement"
    directory.mkdir(parents=True)
    (directory / "config.py").write_text("# fixture", encoding="utf-8")
    (directory / "math_engine.py").write_text("# fixture", encoding="utf-8")
    (directory / "risk_management.py").write_text(
        "import sys,json\n"
        "assert sys.argv[1]=='comprehensive_risk_analysis'\n"
        "payload=json.loads(sys.argv[2])\n"
        "print(json.dumps({'basic_risk_metrics':{'test_value':payload['portfolio_value']},"
        "'echo_weights':payload['weights']}))\n",
        encoding="utf-8",
    )
    return FinceptAdapter(
        str(tmp_path),
        license_confirmed=True,
        allow_analytics=True,
        python_executable=sys.executable,
    )


def test_fincept_runs_only_fixed_external_cli_with_validated_data(licensed_component):
    result = licensed_component.risk(
        {"BTC": [0.01, -0.02] * 40, "ETH": [0.02, -0.01] * 40},
        weights=[0.6, 0.4],
        portfolio_value=12345,
    )
    assert result["data"]["basic_risk_metrics"]["test_value"] == 12345
    assert result["data"]["echo_weights"] == [0.6, 0.4]
    assert result["asset_count"] == 2 and result["observations"] == 80
    assert result["annualization_days"] == 252
    assert result["research_only"] is True
    assert result["source"] == "fincept_licensed_cli"


@pytest.mark.parametrize(
    "returns,weights",
    [
        ([0.1] * 19, None),
        ([0.1] * 20, None),
        ([float("nan"), 0.1] * 20, None),
        ([True, 0.1] * 20, None),
        ([-1.0, 0.1] * 20, None),
        ({"A": [0.1, -0.1] * 20, "B": [0.2, -0.2] * 21}, [0.5, 0.5]),
        ({"A": [0.1, -0.1] * 20, "B": [0.2, -0.2] * 20}, [1.0]),
        ({"A": [0.1, -0.1] * 20, "B": [0.2, -0.2] * 20}, [0.7, 0.4]),
        ({"A": [0.1, -0.1] * 20}, [float("inf")]),
        ({"../script": [0.1, -0.1] * 20}, None),
    ],
)
def test_fincept_rejects_invalid_series_weights_and_names(licensed_component, returns, weights):
    with pytest.raises(ValueError):
        licensed_component.risk(returns, weights=weights)


def test_fincept_cannot_run_before_license_and_host_execution_flags(licensed_component):
    licensed_component.allow_analytics = False
    assert licensed_component.status()["state"] == "disabled"
    with pytest.raises(ExternalEngineError, match="disabled"):
        licensed_component.risk([0.1, -0.1] * 20)
    licensed_component.allow_analytics = True
    licensed_component.license_confirmed = False
    with pytest.raises(ExternalEngineError, match="commercial license"):
        licensed_component.risk([0.1, -0.1] * 20)


def test_fincept_missing_installation_is_actionable():
    adapter = FinceptAdapter(license_confirmed=True)
    assert adapter.status()["state"] == "unconfigured"
    assert adapter.status()["jobs_allowed"] is False


def test_fincept_upstream_errors_are_not_exposed(licensed_component):
    script = licensed_component._script()
    script.write_text(
        "import json; print(json.dumps({'error':'secret','traceback':'private'}))", encoding="utf-8"
    )
    with pytest.raises(ExternalEngineError) as exc:
        licensed_component.risk([0.1, -0.1] * 20)
    assert "secret" not in str(exc.value) and "private" not in str(exc.value)


def test_fincept_relative_installation_path_is_normalized(licensed_component, monkeypatch):
    # Windows strict=False resolve may preserve '..' in a directory path.
    root = licensed_component.installation_path
    monkeypatch.chdir(root.parent)
    adapter = FinceptAdapter(
        f"{root.name}/../{root.name}", license_confirmed=True, allow_analytics=True
    )
    assert adapter.status()["state"] == "configured"
