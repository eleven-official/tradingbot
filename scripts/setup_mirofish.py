"""Inspect a separate MiroFish installation without importing it or contacting providers.

This is a readiness check, not an installer or alternate server. It never writes
credentials, substitutes keys, starts MiroFish, or submits a provider job.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Mapping

SOURCE_PATHS = (
    "LICENSE", "backend/run.py", "backend/app/__init__.py", "backend/app/config.py",
    "backend/requirements.txt", "backend/pyproject.toml",
)
CONFIG_NAMES = {"LLM_API_KEY", "ZEP_API_KEY", "ZEP_API_URL", "FLASK_DEBUG", "FLASK_HOST"}
PLACEHOLDERS = {"your_api_key", "your_api_key_here", "your_zep_api_key", "your_zep_api_key_here", "changeme", "replace_me"}
METADATA_PROBE = """
import importlib.metadata,json,sys
names=json.loads(sys.argv[1])
result={}
for name in names:
    try: result[name]=importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError: result[name]=None
print(json.dumps({'python_version':list(sys.version_info[:3]),'distributions':result}))
"""


def _dotenv_settings(path: Path) -> dict[str, str]:
    """Read only relevant config assignments; never expose secret values."""
    if not path.is_file():
        return {}
    if path.stat().st_size > 64_000:
        raise ValueError("MiroFish .env is unexpectedly large; inspect it locally")
    settings = {}
    text = path.read_text(encoding="utf-8-sig")
    for line in text.splitlines():
        match = re.match(r"^\s*(?:export\s+)?([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$", line)
        if not match or match[1] not in CONFIG_NAMES:
            continue
        value = match[2].strip()
        if value.startswith(("'", '"')):
            quote = value[0]
            end = next((index for index in range(1, len(value))
                        if value[index] == quote and (quote == "'" or value[index - 1] != "\\")), None)
            if end is None or (value[end + 1:].strip() and not value[end + 1:].lstrip().startswith("#")):
                raise ValueError("MiroFish .env uses multiline or complex quoted settings; review them locally")
            value = value[1:end]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        settings[match[1]] = value
    return settings


def _configured(value: str | None) -> bool:
    return bool(value and value.strip() and value.strip().lower() not in PLACEHOLDERS and "${" not in value)


def _requirements(path: Path) -> list[tuple[str, str]]:
    requirements = []
    for index, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9_.-]*)(?:(==|>=|<=|>|<)([0-9]+(?:\.[0-9]+)*))?", line)
        if not match:
            raise ValueError(f"Dependency syntax needs manual review at requirements line {index}")
        requirements.append((match[1], (match[2] or "") + (match[3] or "")))
    return requirements


def _satisfies(installed: str, specifier: str) -> bool | None:
    if not specifier:
        return True
    version_match = re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", installed)
    specification = re.fullmatch(r"(==|>=|<=|>|<)([0-9]+(?:\.[0-9]+)*)", specifier)
    if not version_match or not specification:
        return None
    left = tuple(map(int, installed.split(".")))
    right = tuple(map(int, specification[2].split(".")))
    width = max(len(left), len(right))
    left, right = left + (0,) * (width - len(left)), right + (0,) * (width - len(right))
    return {"==": left == right, ">=": left >= right, "<=": left <= right,
            ">": left > right, "<": left < right}[specification[1]]


def _installed_versions(python: Path, names: list[str]) -> dict:
    environment = dict(os.environ)
    # Package metadata needs no credentials, source imports or provider clients.
    for name in ("LLM_API_KEY", "ZEP_API_KEY", "OPENAI_API_KEY"):
        environment.pop(name, None)
    result = subprocess.run([str(python), "-I", "-c", METADATA_PROBE, json.dumps(names)],
                            cwd=python.parent, env=environment, capture_output=True,
                            text=True, encoding="utf-8", timeout=20, check=False)
    if result.returncode or len(result.stdout) > 64_000:
        raise ValueError("The selected Python interpreter could not inspect installed package metadata")
    try:
        response = json.loads(result.stdout)
        if not isinstance(response["distributions"], dict) or not isinstance(response["python_version"], list):
            raise ValueError
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("The selected Python interpreter returned invalid dependency metadata") from exc
    return response


def check_setup(source: Path, python: Path | None = None, *, environment: Mapping[str, str] | None = None) -> dict:
    source = Path(os.path.abspath(source.expanduser())).resolve()
    python = Path(os.path.abspath((python or Path(sys.executable)).expanduser())).resolve()
    if not source.is_dir() or any(not (source / relative).is_file() for relative in SOURCE_PATHS):
        raise ValueError("Select the MiroFish root containing LICENSE and backend/run.py, app/config.py, requirements.txt and pyproject.toml")
    if not python.is_file():
        raise ValueError("Select an existing Python executable for the separate MiroFish environment")
    license_text = (source / "LICENSE").read_text(encoding="utf-8-sig")
    if "GNU AFFERO GENERAL PUBLIC LICENSE" not in license_text:
        raise ValueError("The selected source does not have the expected MiroFish AGPL license; review it manually")
    requirements = _requirements(source / "backend/requirements.txt")
    installed = _installed_versions(python, [name for name, _ in requirements])
    dependency_rows = []
    for name, specifier in requirements:
        version = installed["distributions"].get(name)
        acceptable = _satisfies(version, specifier) if isinstance(version, str) else False
        dependency_rows.append({"distribution": name, "required": specifier or "present", "installed": version,
                                "status": "present" if acceptable else "missing" if version is None else "version_unverified" if acceptable is None else "version_mismatch"})
    settings = {name: str(value) for name, value in (environment if environment is not None else os.environ).items() if name in CONFIG_NAMES}
    env_path = source / ".env"
    # Mirrors the inspected Config's explicit root .env override precedence.
    settings.update(_dotenv_settings(env_path))
    credentials = {name: {"configured": _configured(settings.get(name)), "value": "not displayed"}
                   for name in ("LLM_API_KEY", "ZEP_API_KEY")}
    blockers = []
    version = installed["python_version"]
    if len(version) < 2 or not (3, 11) <= tuple(version[:2]) < (3, 13):
        blockers.append("The inspected backend requires Python >=3.11,<3.13.")
    missing_dependencies = [row["distribution"] for row in dependency_rows if row["status"] != "present"]
    if missing_dependencies:
        blockers.append("Missing or incompatible dependencies: " + ", ".join(missing_dependencies) + ".")
    for name, evidence in credentials.items():
        if not evidence["configured"]:
            blockers.append(f"{name} is missing, a template placeholder or an unresolved variable; upstream run.py refuses startup.")
    if settings.get("ZEP_API_URL"):
        blockers.append("ZEP_API_URL is unsupported by this archive; its implementation requires Zep Cloud.")
    if settings.get("FLASK_HOST") and settings["FLASK_HOST"] not in {"127.0.0.1", "localhost", "::1"}:
        blockers.append("The source .env/environment sets a non-loopback FLASK_HOST; set 127.0.0.1 before local startup.")
    warnings = ["Credential presence is not authentication, account-credit verification or permission to submit jobs.",
                "Package metadata does not prove imports and native dependencies will succeed.",
                "The upstream run.py requires both provider keys even when you only intend to inspect /health.",
                "The app factory imports graph/simulation/report routes and provider SDKs before serving health.",
                "This check does not import upstream modules, execute its config, install dependencies, start services or call any provider."]
    if not env_path.is_file():
        warnings.append("No source-root .env exists. Upstream load_dotenv fallback can discover parent files; create an explicit root .env for unambiguous configuration.")
    if settings.get("FLASK_DEBUG", "").lower() == "true":
        warnings.append("FLASK_DEBUG is true; set false for a shared or business service.")
    environment_python = source / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return {"source_root": str(source), "python": str(python), "python_version": version,
            "status": "configuration_incomplete" if blockers else "ready_to_try_upstream_startup",
            "service_running_verified": False, "provider_access_verified": False,
            "credentials": credentials, "dependencies": dependency_rows, "blockers": blockers, "warnings": warnings,
            "source_sha256": {relative: hashlib.sha256((source / relative).read_bytes()).hexdigest() for relative in SOURCE_PATHS},
            "license": {"identifier": "AGPL-3.0", "source_license": str(source / "LICENSE"),
                        "note": "Keep upstream notices and source available as applicable; an HTTP boundary alone is not a guarantee of license compliance."},
            "suggested_commands_not_executed": {
                "create_separate_environment": [str(python), "-m", "venv", str(source / ".venv")],
                "install_dependencies": [str(environment_python), "-m", "pip", "install", "-r", str(source / "backend/requirements.txt")],
                "recheck": [str(environment_python), str(Path(__file__).resolve()), "--source", str(source), "--python", str(environment_python)],
                "start_upstream_after_configuration": [str(environment_python), str(source / "backend/run.py")],
                "startup_environment": {"FLASK_HOST": "127.0.0.1", "FLASK_PORT": "5001", "FLASK_DEBUG": "false"},
                "loki_environment": {"LOKI_MIROFISH_URL": "http://127.0.0.1:5001", "LOKI_MIROFISH_ALLOW_JOBS": "0"}}}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Separately installed MiroFish source root")
    parser.add_argument("--python", type=Path, default=Path(sys.executable), help="Python interpreter whose installed dependencies should be checked")
    args = parser.parse_args(argv)
    try:
        report = check_setup(args.source, args.python)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        # Never forward child stderr or a parsed secret into a diagnostic.
        parser.exit(2, f"MiroFish setup check could not complete: {exc}\n")
    print(json.dumps(report, indent=2))
    return 1 if report["blockers"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
