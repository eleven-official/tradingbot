"""Explicit adapters to separately installed research engines.

No upstream implementation is imported, copied, started, or re-licensed here.
Configuration belongs to the host environment; browser requests cannot choose a
server, interpreter, filesystem path, or Python module. Research results never
become orders or assertions about future trade accuracy.
"""

from __future__ import annotations

import ipaddress
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
import uuid


class ExternalEngineError(RuntimeError):
    """A public, bounded error safe to display without upstream tracebacks."""


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


def _enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true"}


def _identifier(value: str, name: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        raise ValueError(f"{name} must contain only letters, numbers, underscores, or hyphens")
    return value


def _text(value: str, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must contain between 1 and {maximum} characters")
    return value.strip()


def _origin(value: str) -> str:
    """Resolve no DNS and admit only a literal loopback HTTP origin."""
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "http"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError
        hostname = parsed.hostname
        # Convert the familiar alias to a literal; never trust a DNS resolver.
        hostname = "127.0.0.1" if hostname.lower() == "localhost" else hostname
        address = ipaddress.ip_address(hostname)
        if not address.is_loopback:
            raise ValueError
        port = parsed.port
        if port is None or not 1 <= port <= 65535:
            raise ValueError
        host = f"[{address}]" if address.version == 6 else str(address)
        return f"http://{host}:{port}"
    except (ValueError, TypeError) as exc:
        raise ValueError(
            "MiroFish URL must be an HTTP loopback origin with an explicit port"
        ) from exc


class MiroFishAdapter:
    """Client for the uploaded MiroFish Flask REST contract.

    ``allow_jobs`` is an operator setting, not a browser request parameter.
    Graph, simulation, report, and chat jobs can consume the separately
    configured engine's LLM/Zep credits. They require explicit opt-in.
    """

    source_url = "https://github.com/666ghj/MiroFish"
    license_name = "AGPL-3.0"
    max_response_bytes = 2 * 1024 * 1024

    def __init__(
        self,
        base_url: str | None = None,
        *,
        allow_jobs: bool = False,
        timeout: float = 8.0,
    ) -> None:
        self.base_url = _origin(base_url) if base_url else None
        if not isinstance(allow_jobs, bool):
            raise ValueError("allow_jobs must be a boolean host setting")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise ValueError("timeout must be a number between 0.1 and 30 seconds")
        if not math.isfinite(timeout) or not 0.1 <= timeout <= 30:
            raise ValueError("timeout must be a number between 0.1 and 30 seconds")
        self.allow_jobs = allow_jobs
        self.timeout = float(timeout)
        self._http = build_opener(ProxyHandler({}), _NoRedirects())

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> MiroFishAdapter:
        env = os.environ if environ is None else environ
        if _enabled(env.get("VERCEL")):
            return cls()
        return cls(
            env.get("LOKI_MIROFISH_URL") or None,
            allow_jobs=_enabled(env.get("LOKI_MIROFISH_ALLOW_JOBS")),
        )

    def _require_jobs(self) -> None:
        if not self.allow_jobs:
            raise ExternalEngineError(
                "MiroFish jobs are disabled. The operator must set "
                "LOKI_MIROFISH_ALLOW_JOBS=1 after configuring provider budgets."
            )

    def _request(
        self,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        body: bytes | None = None,
        content_type: str = "application/json",
        job: bool = False,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        if not self.base_url:
            raise ExternalEngineError(
                "MiroFish is unconfigured. Set LOKI_MIROFISH_URL on the host."
            )
        if job:
            self._require_jobs()
        if (
            not path.startswith(("/api/graph/", "/api/simulation/", "/api/report/"))
            and path != "/health"
        ):
            raise ValueError("Unsupported MiroFish API path")
        if any(character in path for character in ("?", "#", "\\")) or "/../" in path:
            raise ValueError("Invalid MiroFish API path")
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = content_type
        request = Request(self.base_url + path, data=body, headers=headers)
        try:
            with self._http.open(
                request, timeout=self.timeout if timeout is None else timeout
            ) as response:
                if response.headers.get_content_type() != "application/json":
                    raise ExternalEngineError(
                        "MiroFish returned a non-JSON response; check its service version."
                    )
                encoded = response.read(self.max_response_bytes + 1)
                if len(encoded) > self.max_response_bytes:
                    raise ExternalEngineError(
                        "MiroFish response exceeds the 2 MiB research response limit."
                    )
        except HTTPError as exc:
            # Do not disclose upstream error bodies: these may contain provider
            # credentials, document contents, or debug tracebacks.
            if 300 <= exc.code < 400:
                raise ExternalEngineError(
                    "MiroFish redirects are blocked; configure its direct loopback origin."
                ) from None
            raise ExternalEngineError(
                f"MiroFish request failed (HTTP {exc.code}); inspect the local engine logs."
            ) from None
        except (URLError, TimeoutError, OSError):
            raise ExternalEngineError(
                "MiroFish is unreachable; start the separate local backend and check its port."
            ) from None
        try:
            result = json.loads(
                encoded, parse_constant=lambda _: (_ for _ in ()).throw(ValueError())
            )
        except (UnicodeDecodeError, ValueError):
            raise ExternalEngineError("MiroFish returned invalid JSON.") from None
        if not isinstance(result, dict):
            raise ExternalEngineError("MiroFish returned an unsupported response structure.")
        if result.get("success") is False:
            if result.get("pending") is True:
                raise ExternalEngineError(
                    "MiroFish stop is still pending. Poll the existing simulation's run status; "
                    "the process has not been confirmed stopped."
                )
            raise ExternalEngineError(
                "MiroFish rejected this research request; inspect the local engine logs."
            )
        if path != "/health" and (
            result.get("success") is not True or not isinstance(result.get("data"), (dict, list))
        ):
            raise ExternalEngineError(
                "MiroFish response does not match the supported API contract."
            )
        # Deliberately omit upstream tracebacks and arbitrary top-level fields.
        if path == "/health":
            return {"status": result.get("status"), "service": result.get("service")}
        return {"success": True, "data": result.get("data")}

    def status(self, probe: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": "mirofish",
            "name": "MiroFish",
            "state": "unconfigured",
            "configured": bool(self.base_url),
            "jobs_enabled": self.allow_jobs,
            "jobs_allowed": self.allow_jobs,
            "read_only": not self.allow_jobs,
            "license": self.license_name,
            "source_url": self.source_url,
            "integration": "Separate, independently installed AGPL research service",
            "capabilities": ["projects", "graphs", "simulations", "reports"],
            "message": "Set LOKI_MIROFISH_URL=http://127.0.0.1:5001 for your separately installed backend.",
            "prediction_is_trade_probability": False,
            "connection_verified": False,
        }
        if not self.base_url:
            return result
        if not probe:
            result.update(
                state="configured",
                message="Local MiroFish origin configured. Use Check connection to verify the running backend.",
            )
            return result
        try:
            health = self._request("/health", timeout=min(self.timeout, 1.0))
            if health != {"status": "ok", "service": "MiroFish Backend"}:
                raise ExternalEngineError(
                    "The configured service does not identify as MiroFish Backend."
                )
            # A generic /health can be shared by unrelated services. Confirm a
            # real read-only MiroFish route before advertising connectivity.
            self._request("/api/graph/project/list", timeout=min(self.timeout, 1.0))
            result.update(
                state="ready",
                connection_verified=True,
                message="Connected to local MiroFish; research results are scenarios, not price forecasts.",
            )
        except ExternalEngineError as exc:
            result.update(state="unavailable", message=str(exc))
        return result

    def projects(self) -> dict[str, Any]:
        return self._request("/api/graph/project/list")

    def simulations(self) -> dict[str, Any]:
        return self._request("/api/simulation/list")

    def reports(self) -> dict[str, Any]:
        return self._request("/api/report/list")

    def project(self, project_id: str) -> dict[str, Any]:
        return self._request(f"/api/graph/project/{_identifier(project_id, 'project_id')}")

    def graph(self, graph_id: str) -> dict[str, Any]:
        return self._request(f"/api/graph/data/{_identifier(graph_id, 'graph_id')}")

    def task(self, task_id: str) -> dict[str, Any]:
        return self._request(f"/api/graph/task/{_identifier(task_id, 'task_id')}")

    def simulation(self, simulation_id: str) -> dict[str, Any]:
        return self._request(f"/api/simulation/{_identifier(simulation_id, 'simulation_id')}")

    def run_status(self, simulation_id: str) -> dict[str, Any]:
        return self._request(
            f"/api/simulation/{_identifier(simulation_id, 'simulation_id')}/run-status"
        )

    def report(self, report_id: str) -> dict[str, Any]:
        return self._request(f"/api/report/{_identifier(report_id, 'report_id')}")

    def report_for_simulation(self, simulation_id: str) -> dict[str, Any]:
        return self._request(
            f"/api/report/by-simulation/{_identifier(simulation_id, 'simulation_id')}"
        )

    def preparation_status(self, simulation_id: str, task_id: str | None = None) -> dict[str, Any]:
        payload = {"simulation_id": _identifier(simulation_id, "simulation_id")}
        if task_id is not None:
            payload["task_id"] = _identifier(task_id, "task_id")
        # This is a POST in the upstream API, but performs a read only query.
        return self._request("/api/simulation/prepare/status", payload=payload)

    def report_status(self, simulation_id: str, task_id: str | None = None) -> dict[str, Any]:
        payload = {"simulation_id": _identifier(simulation_id, "simulation_id")}
        if task_id is not None:
            payload["task_id"] = _identifier(task_id, "task_id")
        return self._request("/api/report/generate/status", payload=payload)

    def create_project(self, name: str, document_text: str, requirement: str) -> dict[str, Any]:
        """Upload plain text through MiroFish's real multipart ontology endpoint."""
        self._require_jobs()
        values = {
            "project_name": _text(name, "name", 120),
            "simulation_requirement": _text(requirement, "requirement", 4000),
        }
        document = _text(document_text, "document_text", 100_000)
        boundary = "loki-" + uuid.uuid4().hex
        pieces: list[bytes] = []
        for key, value in values.items():
            pieces.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode(
                    "utf-8"
                )
            )
        pieces.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="loki-research.txt"\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n{document}\r\n--{boundary}--\r\n'.encode(
                "utf-8"
            )
        )
        return self._request(
            "/api/graph/ontology/generate",
            body=b"".join(pieces),
            content_type=f"multipart/form-data; boundary={boundary}",
            job=True,
        )

    def build_graph(self, project_id: str) -> dict[str, Any]:
        return self._request(
            "/api/graph/build",
            payload={"project_id": _identifier(project_id, "project_id"), "force": False},
            job=True,
        )

    def create_simulation(self, project_id: str, graph_id: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "project_id": _identifier(project_id, "project_id"),
            "enable_twitter": True,
            "enable_reddit": True,
        }
        if graph_id is not None:
            payload["graph_id"] = _identifier(graph_id, "graph_id")
        return self._request("/api/simulation/create", payload=payload, job=True)

    def prepare_simulation(self, simulation_id: str) -> dict[str, Any]:
        return self._request(
            "/api/simulation/prepare",
            payload={
                "simulation_id": _identifier(simulation_id, "simulation_id"),
                "use_llm_for_profiles": True,
                "parallel_profile_count": 1,
                "force_regenerate": False,
            },
            job=True,
        )

    def start_simulation(self, simulation_id: str, max_rounds: int = 10) -> dict[str, Any]:
        if (
            isinstance(max_rounds, bool)
            or not isinstance(max_rounds, int)
            or not 1 <= max_rounds <= 100
        ):
            raise ValueError("max_rounds must be an integer between 1 and 100")
        return self._request(
            "/api/simulation/start",
            payload={
                "simulation_id": _identifier(simulation_id, "simulation_id"),
                "platform": "parallel",
                "max_rounds": max_rounds,
                "enable_graph_memory_update": False,
                "force": False,
            },
            job=True,
        )

    def stop_simulation(self, simulation_id: str) -> dict[str, Any]:
        # Stopping work is available even after the operator disables new jobs.
        return self._request(
            "/api/simulation/stop",
            payload={"simulation_id": _identifier(simulation_id, "simulation_id")},
        )

    def generate_report(self, simulation_id: str) -> dict[str, Any]:
        return self._request(
            "/api/report/generate",
            payload={
                "simulation_id": _identifier(simulation_id, "simulation_id"),
                "force_regenerate": False,
            },
            job=True,
        )

    def chat(self, simulation_id: str, message: str) -> dict[str, Any]:
        return self._request(
            "/api/report/chat",
            payload={
                "simulation_id": _identifier(simulation_id, "simulation_id"),
                "message": _text(message, "message", 4000),
                "chat_history": [],
            },
            job=True,
        )


class FinceptAdapter:
    """Allowlisted JSON CLI adapter to an operator's licensed installation.

    The supplied archive requires a commercial license for internal business
    use. Loki ships no Fincept code and leaves this adapter locked by default.
    The operator must independently install the unmodified component and its
    dependencies, confirm rights, and explicitly enable analytics execution.
    """

    source_url = "https://github.com/Fincept-Corporation/FinceptTerminal"
    script_relative_path = Path(
        "fincept-qt/scripts/Analytics/portfolioManagement/risk_management.py"
    )
    actions = frozenset({"comprehensive_risk_analysis"})
    # A fixed launcher transports data through stdin, avoiding the Windows argv
    # size limit. Only the inspected upstream CLI's one risk command is called.
    # The installed Fincept implementation and notices stay untouched.
    _runner = (
        "import json,runpy,sys; from pathlib import Path; "
        "script=Path(sys.argv[1]); payload=json.load(sys.stdin); "
        "sys.path.insert(0,str(script.parent)); "
        "sys.argv=[str(script),'comprehensive_risk_analysis',json.dumps(payload)]; "
        "runpy.run_path(str(script),run_name='__main__')"
    )

    def __init__(
        self,
        installation_path: str | None = None,
        *,
        license_confirmed: bool = False,
        allow_analytics: bool = False,
        python_executable: str | None = None,
    ) -> None:
        if not isinstance(license_confirmed, bool) or not isinstance(allow_analytics, bool):
            raise ValueError("Fincept license and execution settings must be booleans")
        self.installation_path = (
            Path(os.path.abspath(installation_path)).resolve() if installation_path else None
        )
        self.license_confirmed = license_confirmed
        self.allow_analytics = allow_analytics
        self.python_executable = Path(
            os.path.abspath(python_executable or sys.executable)
        ).resolve()

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> FinceptAdapter:
        env = os.environ if environ is None else environ
        if _enabled(env.get("VERCEL")):
            return cls()
        return cls(
            env.get("LOKI_FINCEPT_PATH") or None,
            license_confirmed=_enabled(env.get("LOKI_FINCEPT_LICENSE_CONFIRMED")),
            allow_analytics=_enabled(env.get("LOKI_FINCEPT_ALLOW_ANALYTICS")),
            python_executable=env.get("LOKI_FINCEPT_PYTHON") or None,
        )

    def _script(self) -> Path | None:
        if self.installation_path is None:
            return None
        script = (self.installation_path / self.script_relative_path).resolve()
        if (
            not script.is_relative_to(self.installation_path)
            or not script.is_file()
            or any(not (script.parent / name).is_file() for name in ("config.py", "math_engine.py"))
        ):
            return None
        return script

    def status(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": "fincept",
            "name": "Fincept analytics",
            "state": "license_required",
            "configured": self.installation_path is not None,
            "license": "Separate Fincept commercial license required for business use",
            "license_confirmed": self.license_confirmed,
            "licensed": self.license_confirmed,
            "read_only": True,
            "jobs_enabled": False,
            "jobs_allowed": False,
            "source_url": self.source_url,
            "integration": "Separately licensed installation; allowlisted JSON CLI",
            "capabilities": [
                "portfolio_risk",
                "historical_var",
                "parametric_var",
                "expected_shortfall",
                "stress_tests",
            ],
            "supported_actions": sorted(self.actions),
            "annualization_days": 252,
            "message": "Business/internal use requires an executed Fincept commercial license. No Fincept code runs by default.",
        }
        if not self.license_confirmed:
            return result
        if self.installation_path is None:
            result.update(
                state="unconfigured",
                message="Set LOKI_FINCEPT_PATH to your separately licensed installation.",
            )
        elif self._script() is None or not self.python_executable.is_file():
            result.update(
                state="unavailable",
                message="The licensed installation or configured Python interpreter is missing.",
            )
        elif not self.allow_analytics:
            result.update(
                state="disabled",
                message="Licensed installation found. Set LOKI_FINCEPT_ALLOW_ANALYTICS=1 to enable research jobs.",
            )
        else:
            result.update(
                state="configured",
                jobs_enabled=True,
                jobs_allowed=True,
                message="Licensed analytics CLI configured. Dependencies and data access are checked when a report runs.",
            )
        return result

    def risk(
        self,
        returns_data: list[float] | Mapping[str, list[float]],
        *,
        weights: list[float] | None = None,
        portfolio_value: float = 100_000,
    ) -> dict[str, Any]:
        if not self.license_confirmed:
            raise ExternalEngineError(
                "Fincept business use is locked until the operator confirms an executed commercial license."
            )
        if not self.allow_analytics:
            raise ExternalEngineError("Fincept analytics execution is disabled on this host.")
        script = self._script()
        if script is None or not self.python_executable.is_file():
            raise ExternalEngineError(
                "The licensed Fincept installation or Python interpreter is unavailable."
            )

        def validated_series(values: Any) -> list[float]:
            if not isinstance(values, list) or not 20 <= len(values) <= 2000:
                raise ValueError(
                    "Each daily return series must contain between 20 and 2000 observations"
                )
            if any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not -1 < value <= 10
                for value in values
            ):
                raise ValueError(
                    "Daily returns must be finite fractions greater than -1 and at most 10"
                )
            if max(values) - min(values) < 1e-12:
                raise ValueError("Risk analysis requires a return series with measurable variation")
            return [float(value) for value in values]

        if isinstance(returns_data, Mapping):
            if not 1 <= len(returns_data) <= 20:
                raise ValueError("Supply between 1 and 20 assets")
            safe_returns: Any = {}
            for name, values in returns_data.items():
                _identifier(name, "asset name")
                safe_returns[name] = validated_series(values)
            if len({len(values) for values in safe_returns.values()}) != 1:
                raise ValueError(
                    "Asset daily return series must have equal lengths and aligned observation dates"
                )
            asset_count = len(safe_returns)
            observations = len(next(iter(safe_returns.values())))
        else:
            safe_returns = validated_series(returns_data)
            asset_count = 1
            observations = len(safe_returns)
        if weights is not None:
            if not isinstance(weights, list) or len(weights) != asset_count:
                raise ValueError("weights must contain one weight per asset, in the same order")
            if (
                any(
                    isinstance(weight, bool)
                    or not isinstance(weight, (float, int))
                    or not math.isfinite(weight)
                    or not 0 < weight <= 1
                    for weight in weights
                )
                or abs(sum(weights) - 1) > 0.001
            ):
                raise ValueError("Weights must be positive finite fractions and sum to 1")
        if (
            isinstance(portfolio_value, bool)
            or not isinstance(portfolio_value, (int, float))
            or not math.isfinite(portfolio_value)
            or not 0 < portfolio_value <= 1e12
        ):
            raise ValueError("portfolio_value must be between 0 and 1 trillion")
        payload = {
            "returns_data": safe_returns,
            "weights": weights,
            "portfolio_value": float(portfolio_value),
        }
        command = [
            str(self.python_executable),
            "-I",
            "-c",
            self._runner,
            str(script),
        ]
        # File-backed output prevents an unexpectedly noisy installed component
        # from consuming unbounded application memory. Never return its stderr.
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            try:
                completed = subprocess.run(
                    command,
                    cwd=str(script.parent),
                    input=json.dumps(payload, allow_nan=False).encode("utf-8"),
                    stdout=stdout,
                    stderr=stderr,
                    shell=False,
                    timeout=90,
                    env={
                        key: value
                        for key, value in os.environ.items()
                        if key.upper()
                        in {
                            "PATH",
                            "SYSTEMROOT",
                            "WINDIR",
                            "TEMP",
                            "TMP",
                            "TMPDIR",
                            "LANG",
                            "LC_ALL",
                            "USERPROFILE",
                            "HOME",
                        }
                    },
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    check=False,
                )
            except subprocess.TimeoutExpired:
                raise ExternalEngineError("Fincept analytics timed out after 90 seconds.") from None
            except OSError:
                raise ExternalEngineError(
                    "Cannot run the configured licensed Fincept Python installation."
                ) from None
            if completed.returncode != 0:
                raise ExternalEngineError(
                    "Fincept analytics failed; check the licensed installation's dependencies and data access."
                )
            stdout.seek(0)
            encoded = stdout.read(2 * 1024 * 1024 + 1)
        if len(encoded) > 2 * 1024 * 1024:
            raise ExternalEngineError("Fincept response exceeds the 2 MiB research response limit.")
        try:
            # Degenerate higher moments may be undefined in the upstream math.
            # Preserve these as unavailable (null), never fabricated zeroes.
            result = json.loads(encoded, parse_constant=lambda _: None)
        except (ValueError, UnicodeDecodeError):
            raise ExternalEngineError("Fincept analytics returned invalid JSON.") from None
        if (
            not isinstance(result, dict)
            or "error" in result
            or not isinstance(result.get("basic_risk_metrics"), dict)
        ):
            raise ExternalEngineError(
                "Fincept analytics could not produce this report; check the licensed engine logs."
            )
        return {
            "success": True,
            "source": "fincept_licensed_cli",
            "action": "comprehensive_risk_analysis",
            "data": result,
            "observations": observations,
            "asset_count": asset_count,
            "portfolio_value": float(portfolio_value),
            "annualization_days": 252,
            "input_frequency": "daily",
            "monte_carlo_is_estimate": True,
            "research_only": True,
        }
