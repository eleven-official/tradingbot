"""Protect private native research while keeping pure paper tools public."""

from datetime import datetime, timedelta, timezone
import math

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from core.fusion.external import ExternalEngineError, FinceptAdapter, MiroFishAdapter
from loki.api.fusion import router


@pytest.fixture
def app(monkeypatch):
    for key in ("LOKI_FUSION_LOCAL", "VERCEL", "LOKI_FINCEPT_PATH", "LOKI_MIROFISH_URL"):
        monkeypatch.delenv(key, raising=False)
    application = FastAPI()
    application.include_router(router)
    return application


@pytest.fixture
def local_client(app, monkeypatch):
    monkeypatch.setenv("LOKI_FUSION_LOCAL", "1")
    with TestClient(app, base_url="http://127.0.0.1:8765", client=("127.0.0.1", 12345)) as client:
        yield client


def native_headers(client):
    response = client.get("/api/fusion/capabilities")
    assert response.status_code == 200
    return {"X-Loki-Local-Token": response.json()["local_token"]}


@pytest.mark.parametrize(
    "path",
    [
        "/api/fusion/mirofish/status",
        "/api/fusion/fincept/status",
        "/api/fusion/mirofish/projects",
        "/api/fusion/mirofish/simulations",
        "/api/fusion/mirofish/reports",
        "/api/fusion/mirofish/project/proj_private",
        "/api/fusion/mirofish/graph/graph_private",
        "/api/fusion/mirofish/report/report_private",
        "/api/fusion/mirofish/simulation/sim_private",
        "/api/fusion/mirofish/task/task_private",
    ],
)
def test_private_native_reads_require_local_session_token(local_client, path):
    assert local_client.get(path).status_code == 403


def test_remote_clients_never_receive_local_token_or_native_data(app, monkeypatch):
    monkeypatch.setenv("LOKI_FUSION_LOCAL", "1")
    with TestClient(
        app, base_url="http://127.0.0.1:8765", client=("203.0.113.10", 12345)
    ) as client:
        capabilities = client.get("/api/fusion/capabilities").json()
        assert capabilities["local_actions_enabled"] is False
        assert "local_token" not in capabilities
        assert client.get("/api/fusion/mirofish/projects").status_code == 403


@pytest.mark.parametrize(
    "headers",
    [
        {"Host": "public.example"},
        {"Host": "localhost:invalid"},
        {"Host": "127.0.0.1:0"},
        {"Host": "user@127.0.0.1:8765"},
        {"Origin": "https://external.example"},
        {"Origin": "http://127.0.0.1:8766"},
        {"Origin": "http://127.0.0.1:8765/path"},
        {"Origin": "null"},
        {"X-Forwarded-For": "203.0.113.1"},
        {"X-Forwarded-Host": "public.example"},
        {"X-Forwarded-Proto": "https"},
        {"Forwarded": "for=203.0.113.1"},
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
    ],
)
def test_native_token_cannot_be_obtained_via_rebinding_proxy_or_foreign_origin(
    local_client, headers
):
    response = local_client.get("/api/fusion/capabilities", headers=headers)
    assert response.status_code == 200
    assert "local_token" not in response.json()
    assert response.json()["local_actions_enabled"] is False


def test_local_launcher_flag_and_vercel_disable_token_issuance(local_client, monkeypatch):
    monkeypatch.delenv("LOKI_FUSION_LOCAL")
    assert "local_token" not in local_client.get("/api/fusion/capabilities").json()
    monkeypatch.setenv("LOKI_FUSION_LOCAL", "1")
    monkeypatch.setenv("VERCEL", "1")
    assert "local_token" not in local_client.get("/api/fusion/capabilities").json()


def test_same_origin_default_port_is_compared_correctly(app, monkeypatch):
    monkeypatch.setenv("LOKI_FUSION_LOCAL", "1")
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 12345)) as client:
        response = client.get("/api/fusion/capabilities", headers={"Origin": "http://localhost:80"})
        assert response.json()["local_actions_enabled"] is True


def test_private_data_and_tokens_are_not_cacheable(local_client, monkeypatch):
    capabilities = local_client.get("/api/fusion/capabilities")
    assert "no-store" in capabilities.headers["cache-control"]
    headers = {"X-Loki-Local-Token": capabilities.json()["local_token"]}
    monkeypatch.setattr(
        MiroFishAdapter,
        "projects",
        lambda self: {"success": True, "data": [{"name": "private research"}]},
    )
    response = local_client.get("/api/fusion/mirofish/projects", headers=headers)
    assert response.status_code == 200
    assert response.json()["data"][0]["name"] == "private research"
    assert "private" in response.headers["cache-control"]
    assert "no-store" in response.headers["cache-control"]


def test_valid_token_is_still_rejected_for_foreign_origin(local_client, monkeypatch):
    headers = native_headers(local_client)
    headers["Origin"] = "http://evil.example"
    monkeypatch.setattr(
        MiroFishAdapter, "projects", lambda self: pytest.fail("private engine must not be touched")
    )
    assert local_client.get("/api/fusion/mirofish/projects", headers=headers).status_code == 403


def test_valid_token_cannot_be_reused_from_a_remote_client(local_client, app):
    headers = native_headers(local_client)
    with TestClient(
        app, base_url="http://127.0.0.1:8765", client=("203.0.113.10", 12345)
    ) as remote:
        assert remote.get("/api/fusion/mirofish/projects", headers=headers).status_code == 403


def test_configured_capabilities_do_not_probe_native_service(local_client, monkeypatch):
    monkeypatch.setenv("LOKI_MIROFISH_URL", "http://127.0.0.1:5001")
    monkeypatch.setattr(
        MiroFishAdapter,
        "_request",
        lambda *args, **kwargs: pytest.fail("capability discovery must not call MiroFish"),
    )
    response = local_client.get("/api/fusion/capabilities")
    assert response.status_code == 200
    miro = next(item for item in response.json()["components"] if item["id"] == "mirofish")
    assert miro["status"] == "configured" and miro["connection_verified"] is False


def test_real_mirofish_preparation_and_report_polling_keep_task_ids(local_client, monkeypatch):
    headers = native_headers(local_client)
    calls = []

    def preparation(self, simulation_id, task_id=None):
        calls.append((simulation_id, task_id))
        return {"success": True, "data": {"status": "processing", "task_id": task_id}}

    monkeypatch.setattr(MiroFishAdapter, "preparation_status", preparation)
    monkeypatch.setattr(MiroFishAdapter, "report_status", preparation)
    for kind in ("preparation-status", "report-status"):
        response = local_client.get(
            f"/api/fusion/mirofish/{kind}/sim_private?task_id=task_actual", headers=headers
        )
        assert response.status_code == 200
        assert response.json()["data"]["task_id"] == "task_actual"
    assert calls == [("sim_private", "task_actual")] * 2


def test_native_jobs_use_real_project_stop_and_chat_contracts(local_client, monkeypatch):
    headers = native_headers(local_client)
    calls = []

    def create(self, name, document_text, requirement):
        calls.append(("create_project", name, document_text, requirement))
        return {"success": True, "data": {"project_id": "proj_created"}}

    def stop(self, simulation_id):
        calls.append(("stop_simulation", simulation_id))
        return {"success": True, "data": {"runner_status": "stopping"}}

    def chat(self, simulation_id, message):
        calls.append(("chat", simulation_id, message))
        return {"success": True, "data": {"response": "A sourced scenario answer."}}

    monkeypatch.setattr(MiroFishAdapter, "create_project", create)
    monkeypatch.setattr(MiroFishAdapter, "stop_simulation", stop)
    monkeypatch.setattr(MiroFishAdapter, "chat", chat)
    cases = [
        {
            "action": "create_project",
            "title": "Study",
            "seed_text": "Source facts",
            "requirements": "Compare reactions",
        },
        {"action": "stop_simulation", "simulation_id": "sim_private"},
        {"action": "chat", "simulation_id": "sim_private", "message": "Explain uncertainty"},
    ]
    for payload in cases:
        response = local_client.post("/api/fusion/mirofish/jobs", json=payload, headers=headers)
        assert response.status_code == 200
    assert calls == [
        ("create_project", "Study", "Source facts", "Compare reactions"),
        ("stop_simulation", "sim_private"),
        ("chat", "sim_private", "Explain uncertainty"),
    ]


def test_fincept_multi_asset_matrix_maps_to_ordered_source_contract(local_client, monkeypatch):
    headers = native_headers(local_client)
    captured = {}

    def risk(self, returns_data, *, weights=None, portfolio_value=100000):
        captured.update(returns_data=returns_data, weights=weights, portfolio_value=portfolio_value)
        return {"success": True, "data": {"basic_risk_metrics": {"volatility_daily": 0.01}}}

    monkeypatch.setattr(FinceptAdapter, "risk", risk)
    returns = [[0.01, -0.02] * 20, [0.02, -0.01] * 20]
    response = local_client.post(
        "/api/fusion/fincept/analyze",
        json={"returns": returns, "weights": [0.6, 0.4], "portfolio_value": 12345},
        headers=headers,
    )
    assert response.status_code == 200
    assert captured == {
        "returns_data": {"asset_1": returns[0], "asset_2": returns[1]},
        "weights": [0.6, 0.4],
        "portfolio_value": 12345.0,
    }


def test_fincept_single_asset_and_fixed_confidence_contract(local_client, monkeypatch):
    headers = native_headers(local_client)

    def risk(self, returns_data, **kwargs):
        assert isinstance(returns_data, list)
        assert kwargs["weights"] == [1.0]
        return {"success": True, "data": {"basic_risk_metrics": {}}}

    monkeypatch.setattr(FinceptAdapter, "risk", risk)
    payload = {"returns": [[0.01, -0.02] * 20], "weights": [1.0]}
    assert (
        local_client.post("/api/fusion/fincept/analyze", json=payload, headers=headers).status_code
        == 200
    )
    payload["confidence"] = 0.90
    assert (
        local_client.post("/api/fusion/fincept/analyze", json=payload, headers=headers).status_code
        == 422
    )


def test_engine_failures_are_actionable_503_and_input_failures_422(local_client, monkeypatch):
    headers = native_headers(local_client)

    def unavailable(self):
        raise ExternalEngineError("MiroFish is unconfigured. Set LOKI_MIROFISH_URL on the host.")

    monkeypatch.setattr(MiroFishAdapter, "projects", unavailable)
    response = local_client.get("/api/fusion/mirofish/projects", headers=headers)
    assert response.status_code == 503 and "unconfigured" in response.json()["detail"]

    def invalid(self, simulation_id):
        raise ValueError("Invalid simulation identifier")

    monkeypatch.setattr(MiroFishAdapter, "simulation", invalid)
    assert (
        local_client.get("/api/fusion/mirofish/simulation/sim_bad", headers=headers).status_code
        == 422
    )


def test_native_request_schema_blocks_arbitrary_code_paths_and_oversized_series(local_client):
    headers = native_headers(local_client)
    payload = {"returns": [[0.01, -0.01] * 20], "weights": [1.0], "script_path": "arbitrary.py"}
    assert (
        local_client.post("/api/fusion/fincept/analyze", json=payload, headers=headers).status_code
        == 422
    )
    assert (
        local_client.post(
            "/api/fusion/fincept/analyze",
            json={"returns": [[0.01, -0.01] * 1001], "weights": [1.0]},
            headers=headers,
        ).status_code
        == 422
    )
    assert (
        local_client.post(
            "/api/fusion/mirofish/jobs",
            json={"action": "execute_python", "script": "arbitrary.py"},
            headers=headers,
        ).status_code
        == 422
    )


def test_public_paper_research_tools_remain_available_without_native_token(app):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars, previous = [], 100.0
    for index in range(90):
        close = 100 * math.exp(0.0009 * index + 0.06 * math.sin(index / 8))
        bars.append(
            {
                "timestamp": (start + timedelta(days=index)).isoformat(),
                "open": previous,
                "high": max(previous, close) * 1.007,
                "low": min(previous, close) * 0.993,
                "close": close,
                "volume": 100_000.0,
            }
        )
        previous = close
    with TestClient(app, client=("203.0.113.10", 12345)) as client:
        assert client.get("/api/fusion/portfolio").status_code == 200
        assert client.post("/api/fusion/portfolio", json={"action": "snapshot"}).status_code == 200
        assert client.post("/api/fusion/scenario", json={"shock_pct": -10}).status_code == 200
        quant = client.post("/api/fusion/quant", json={"bars": bars})
        assert quant.status_code == 200
        assert "replay" in quant.json() and "analysis" in quant.json()
        assert client.post("/api/fusion/council", json={"bars": bars}).status_code == 200
