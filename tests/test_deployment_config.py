"""Guard the Vercel FastAPI deployment entrypoint against invalid runtimes."""
import ast
import json
import re
import tomllib
import unittest
from pathlib import Path
from html.parser import HTMLParser


ROOT = Path(__file__).resolve().parents[1]


class LandingPageContract(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []
        self.inputs = []
        self.scripts = []
        self.stylesheets = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "form":
            self.forms.append(values)
        elif tag == "input":
            self.inputs.append(values)
        elif tag == "script" and values.get("src"):
            self.scripts.append(values["src"])
        elif tag == "link" and values.get("rel") == "stylesheet":
            self.stylesheets.append(values.get("href"))

    def handle_data(self, data):
        self.text.append(data)


class DeploymentConfigTests(unittest.TestCase):
    def test_vercel_uses_the_supported_fastapi_framework_preset(self):
        config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        self.assertEqual(config["framework"], "fastapi")
        self.assertEqual(config["$schema"], "https://openapi.vercel.sh/vercel.json")

    def test_vercel_does_not_declare_an_invalid_custom_python_runtime(self):
        config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        function = config["functions"]["main.py"]
        self.assertEqual(function["includeFiles"], "{templates/**,static/**}")
        self.assertNotIn("runtime", function)
        self.assertNotIn("routes", config)

    def test_fastapi_app_entrypoint_is_explicit(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(project["tool"]["vercel"]["entrypoint"], "main:app")
        dependencies = project["project"]["dependencies"]
        self.assertTrue(any(item.lower().startswith("fastapi") for item in dependencies))

    def test_pyproject_runtime_dependencies_cover_requirements_file(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        declared = {
            re.split(r"[<>=!~\[]", item, maxsplit=1)[0].lower()
            for item in project["project"]["dependencies"]
        }
        required = {
            re.split(r"[<>=!~\[]", line.strip(), maxsplit=1)[0].lower()
            for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        self.assertEqual(declared, required)

    def test_landing_route_uses_current_starlette_template_response_order(self):
        source = (ROOT / "loki" / "api" / "server.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "TemplateResponse"
        ]
        self.assertEqual(len(calls), 1)
        self.assertEqual([arg.id if isinstance(arg, ast.Name) else getattr(arg, "value", None)
                          for arg in calls[0].args], ["request", "index.html", "context"])

    def test_landing_assets_are_included_in_the_deployment_bundle(self):
        config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        included = config["functions"]["main.py"]["includeFiles"]
        self.assertIn("templates/**", included)
        self.assertIn("static/**", included)
        self.assertTrue((ROOT / "templates" / "index.html").is_file())
        self.assertTrue((ROOT / "static" / "css" / "style.css").is_file())
        self.assertTrue((ROOT / "static" / "js" / "profile.js").is_file())
        self.assertTrue((ROOT / "static" / "js" / "strategy-lab.js").is_file())
        self.assertTrue((ROOT / "static" / "js" / "workspace.js").is_file())

    def test_landing_page_has_required_labelled_personal_profile_fields(self):
        source = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        page = LandingPageContract()
        page.feed(source)
        inputs = {item.get("id"): item for item in page.inputs}
        self.assertIn("profileForm", [form.get("id") for form in page.forms])
        self.assertEqual(inputs["profileNickname"].get("autocomplete"), "nickname")
        self.assertEqual(inputs["profileEmail"].get("type"), "email")
        self.assertEqual(inputs["profileEmail"].get("autocomplete"), "email")
        self.assertIn("/static/js/profile.js", page.scripts)
        self.assertIn("/static/css/style.css", page.stylesheets)
        self.assertIn("does not send your details to the server", " ".join(page.text))

    def test_workspace_has_navigable_research_views_and_no_github_promotion(self):
        source = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        for view in ("overview", "strategy", "paper", "journal", "council"):
            self.assertIn(f'data-view="{view}"', source)
            self.assertIn(f'id="view-{view}"', source)
        self.assertIn('id="csvUpload"', source)
        self.assertIn("REAL MODE", source)
        self.assertIn("Live execution is not connected", source)
        self.assertNotIn("github.com/eleven-official", source)

    def test_profile_code_persists_locally_without_sending_contact_details(self):
        source = (ROOT / "static" / "js" / "profile.js").read_text(encoding="utf-8")
        self.assertIn("localStorage.setItem", source)
        self.assertIn("localStorage.removeItem", source)
        self.assertNotRegex(source, r"\bfetch\s*\(|XMLHttpRequest|navigator\.sendBeacon")

    def test_server_resolves_template_and_static_paths_from_repository_root(self):
        source = (ROOT / "loki" / "api" / "server.py").read_text(encoding="utf-8")
        self.assertIn("Path(__file__).resolve().parents[2]", source)
        self.assertIn('project_root / "static"', source)
        self.assertIn('project_root / "templates"', source)


if __name__ == "__main__":
    unittest.main()

