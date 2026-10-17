"""Local configuration validation must not partly enable native components."""

import json
import os
from pathlib import Path

import pytest

from launch_loki_fusion import configure


@pytest.fixture(autouse=True)
def clean_engine_environment(monkeypatch):
    for name in (
        "LOKI_FUSION_LOCAL",
        "LOKI_FINCEPT_PATH",
        "LOKI_FINCEPT_PYTHON",
        "LOKI_FINCEPT_LICENSE_CONFIRMED",
        "LOKI_FINCEPT_ALLOW_ANALYTICS",
        "LOKI_MIROFISH_URL",
        "LOKI_MIROFISH_ALLOW_JOBS",
        "VERCEL",
    ):
        monkeypatch.delenv(name, raising=False)


def write_config(tmp_path, value):
    path = tmp_path / "fusion.config.local.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_invalid_license_flag_leaves_all_host_settings_unchanged(tmp_path):
    path = write_config(
        tmp_path, {"fincept_path": "private-install", "fincept_license_confirmed": "yes"}
    )
    before = dict(os.environ)
    with pytest.raises(ValueError, match="true or false"):
        configure(path)
    assert dict(os.environ) == before


def test_remote_mirofish_origin_cannot_partly_enable_jobs(tmp_path):
    path = write_config(
        tmp_path, {"mirofish_url": "http://public.example:5001", "mirofish_allow_jobs": True}
    )
    before = dict(os.environ)
    with pytest.raises(ValueError, match="loopback"):
        configure(path)
    assert dict(os.environ) == before


def test_relative_component_paths_resolve_from_configuration_directory(tmp_path, monkeypatch):
    path = write_config(
        tmp_path,
        {
            "fincept_path": "components/fincept",
            "fincept_python": "runtime/python.exe",
            "fincept_license_confirmed": True,
            "fincept_allow_analytics": False,
            "mirofish_url": "http://127.0.0.1:5001",
            "mirofish_allow_jobs": False,
        },
    )
    unrelated = tmp_path / "different-working-directory"
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)
    configure(path)
    assert Path(os.environ["LOKI_FINCEPT_PATH"]) == tmp_path / "components/fincept"
    assert Path(os.environ["LOKI_FINCEPT_PYTHON"]) == tmp_path / "runtime/python.exe"
    assert os.environ["LOKI_FINCEPT_ALLOW_ANALYTICS"] == "0"
    assert os.environ["LOKI_MIROFISH_ALLOW_JOBS"] == "0"
    assert os.environ["LOKI_FUSION_LOCAL"] == "1"


def test_host_configuration_cannot_choose_shell_commands_or_undefined_settings(tmp_path):
    path = write_config(tmp_path, {"shell_command": "run anything"})
    with pytest.raises(ValueError, match="Unknown"):
        configure(path)
    assert "LOKI_FUSION_LOCAL" not in os.environ
