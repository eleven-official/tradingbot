"""Guard the Vercel FastAPI deployment entrypoint against invalid runtimes."""
import json
import re
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DeploymentConfigTests(unittest.TestCase):
    def test_vercel_uses_the_supported_fastapi_framework_preset(self):
        config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        self.assertEqual(config["framework"], "fastapi")
        self.assertEqual(config["$schema"], "https://openapi.vercel.sh/vercel.json")

    def test_vercel_does_not_declare_an_invalid_custom_python_runtime(self):
        config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        self.assertNotIn("functions", config)
        self.assertNotIn("routes", config)

    def test_fastapi_app_entrypoint_is_explicit(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(project["tool"]["vercel"]["entrypoint"], "main:app")
        self.assertIn("fastapi>=0.110.0", project["project"]["dependencies"])

    def test_pyproject_runtime_dependencies_cover_requirements_file(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        declared = {
            re.split(r"[<>=!~\\[]", item, maxsplit=1)[0].lower()
            for item in project["project"]["dependencies"]
        }
        required = {
            re.split(r"[<>=!~\\[]", line.strip(), maxsplit=1)[0].lower()
            for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        self.assertEqual(declared, required)


if __name__ == "__main__":
    unittest.main()
