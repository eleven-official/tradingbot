"""The setup check must stay read-only and must never print provider secrets."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.setup_mirofish import SOURCE_PATHS, _satisfies, check_setup


def source_fixture(root: Path):
    for relative in SOURCE_PATHS:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("raise RuntimeError('UPSTREAM SOURCE MUST NOT BE EXECUTED')\n", encoding="utf-8")
    (root / "LICENSE").write_text("GNU AFFERO GENERAL PUBLIC LICENSE\nVersion 3\n", encoding="utf-8")
    (root / "backend/requirements.txt").write_text("flask>=3.0.0\nzep-cloud==3.25.0\n", encoding="utf-8")


class MiroFishSetupTests(unittest.TestCase):
    def test_missing_keys_are_real_blockers_without_importing_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_fixture(root)
            metadata = {"python_version": [3, 12, 10], "distributions": {"flask": "3.1.3", "zep-cloud": "3.25.0"}}
            with patch("scripts.setup_mirofish._installed_versions", return_value=metadata):
                report = check_setup(root, environment={})
            self.assertEqual(report["status"], "configuration_incomplete")
            self.assertTrue(any("LLM_API_KEY" in text for text in report["blockers"]))
            self.assertTrue(any("ZEP_API_KEY" in text for text in report["blockers"]))
            self.assertFalse(report["service_running_verified"])
            self.assertFalse(report["provider_access_verified"])

    def test_root_dotenv_precedence_placeholders_and_secrets_are_redacted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_fixture(root)
            (root / ".env").write_text('LLM_API_KEY="your_api_key_here" # example\nZEP_API_KEY="PRIVATE_SENTINEL"\nZEP_API_URL=http://127.0.0.1:9999\n', encoding="utf-8")
            metadata = {"python_version": [3, 12, 10], "distributions": {"flask": "3.1.3", "zep-cloud": "3.25.0"}}
            with patch("scripts.setup_mirofish._installed_versions", return_value=metadata):
                report = check_setup(root, environment={"LLM_API_KEY": "ENVIRONMENT_SENTINEL"})
            serialized = json.dumps(report)
            self.assertNotIn("PRIVATE_SENTINEL", serialized)
            self.assertNotIn("ENVIRONMENT_SENTINEL", serialized)
            self.assertFalse(report["credentials"]["LLM_API_KEY"]["configured"])
            self.assertTrue(report["credentials"]["ZEP_API_KEY"]["configured"])
            self.assertTrue(any("ZEP_API_URL" in text for text in report["blockers"]))

    def test_versions_and_python_range_do_not_report_false_readiness(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_fixture(root)
            metadata = {"python_version": [3, 13, 0], "distributions": {"flask": "3.1.3", "zep-cloud": "3.24.0"}}
            with patch("scripts.setup_mirofish._installed_versions", return_value=metadata):
                report = check_setup(root, environment={"LLM_API_KEY": "fixture_llm", "ZEP_API_KEY": "fixture_zep"})
            self.assertEqual(report["dependencies"][1]["status"], "version_mismatch")
            self.assertTrue(any("Python >=3.11,<3.13" in text for text in report["blockers"]))
            self.assertEqual(report["status"], "configuration_incomplete")

    def test_configured_does_not_mean_verified_or_permission_to_run_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_fixture(root)
            metadata = {"python_version": [3, 12, 10], "distributions": {"flask": "3.1.3", "zep-cloud": "3.25.0"}}
            with patch("scripts.setup_mirofish._installed_versions", return_value=metadata):
                report = check_setup(root, environment={"LLM_API_KEY": "fixture_llm", "ZEP_API_KEY": "fixture_zep"})
            self.assertEqual(report["status"], "ready_to_try_upstream_startup")
            self.assertFalse(report["service_running_verified"])
            self.assertFalse(report["provider_access_verified"])
            self.assertEqual(report["suggested_commands_not_executed"]["loki_environment"]["LOKI_MIROFISH_ALLOW_JOBS"], "0")
            self.assertNotIn("fixture_llm", json.dumps(report))

    def test_prerelease_or_unrecognized_versions_need_review(self):
        self.assertIsNone(_satisfies("3.0.0b1", ">=3.0.0"))
        self.assertTrue(_satisfies("3.25", "==3.25.0"))
        self.assertFalse(_satisfies("2.9.9", ">=3.0.0"))


if __name__ == "__main__":
    unittest.main()
