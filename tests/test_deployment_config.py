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
        self.assertEqual(
            function["includeFiles"],
            "{templates/**,static/**,loki_v8/training_report_snapshot.json}",
        )
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
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "TemplateResponse"
        ]
        self.assertGreaterEqual(len(calls), 1)
        for call in calls:
            self.assertEqual(
                {item.arg for item in call.keywords},
                {"request", "name", "context"},
                f"TemplateResponse at line {call.lineno} must keep the keyword form.",
            )

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
        source = (ROOT / "templates" / "research_desk.html").read_text(encoding="utf-8")
        page = LandingPageContract()
        page.feed(source)
        inputs = {item.get("id"): item for item in page.inputs}
        self.assertIn("profileForm", [form.get("id") for form in page.forms])
        self.assertEqual(inputs["profileNickname"].get("autocomplete"), "nickname")
        self.assertEqual(inputs["profileEmail"].get("type"), "email")
        self.assertEqual(inputs["profileEmail"].get("autocomplete"), "email")
        self.assertIn("/static/js/profile.js", page.scripts)
        self.assertIn("/static/css/research_desk.css", page.stylesheets)
        self.assertIn("does not send your details to the server", " ".join(page.text))

    def test_workspace_has_navigable_research_views_and_no_github_promotion(self):
        source = (ROOT / "templates" / "research_desk.html").read_text(encoding="utf-8")
        for view in ("overview", "strategy", "paper", "journal", "council"):
            self.assertIn(f'data-view="{view}"', source)
            self.assertIn(f'id="view-{view}"', source)
        self.assertIn('id="csvUpload"', source)
        self.assertIn("REAL MODE", source)
        self.assertIn("Live execution is not connected", source)
        self.assertNotIn("github.com/eleven-official", source)

    def test_landing_has_loki_dive_arcade_wiring(self):
        source = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-view="game"', source)  # nav item, last in the bar
        self.assertIn("Bored?</a>", source)  # the tab reads "Bored?"
        self.assertIn('<section id="game"', source)  # arcade view exists
        self.assertIn("/static/js/game_data.js", source)  # answer bank loaded
        self.assertIn("/static/js/game.js", source)  # loader present
        self.assertIn("/static/js/visit_note.js", source)  # "since last visit" diff
        self.assertIn('id="dive-start-btn"', source)  # button ids intact
        self.assertIn('id="dive-challenge"', source)  # daily challenge stat line
        self.assertIn('id="dive-wait-chip"', source)  # play-while-scans-run prompt
        self.assertIn('id="ai-next-tick"', source)  # next-check countdown slot
        self.assertIn('id="visit-note"', source)  # what-changed-since-last-visit slot
        self.assertLess(
            source.index('data-view="integrations"'),
            source.index('data-view="game"'),
            "Bored? should sit at the very bottom of the navigation bar",
        )

    def test_workspace_responsive_nav_next_steps_and_backup(self):
        source = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        # Nav: Overview / Quant lab / Paper portfolio stay visible; the rest is grouped under "More".
        group_start = source.index('id="nav-more-group"')
        for visible in ('data-view="overview"', 'data-view="strategy-lab"', 'data-view="portfolio"'):
            self.assertLess(source.index(visible), group_start)
        self.assertIn('id="nav-more-toggle"', source)
        for grouped in ("agent-council", "simulated-market", "ai-trading", "real-market",
                        "scenarios", "copilot", "advanced-terminal", "paper-planner", "integrations", "game"):
            self.assertGreater(source.index(f'data-view="{grouped}"'), group_start, grouped)
        # Account pill mounts into the topbar instead of floating over content.
        auth_js = (ROOT / "static" / "js" / "loki_auth.js").read_text(encoding="utf-8")
        self.assertIn(".topbar-status", auth_js)
        # Next-steps panel with markers written at the moment each action succeeds.
        self.assertIn('id="next-steps-panel"', source)
        self.assertIn('id="data-context-line"', source)
        workspace = (ROOT / "static" / "js" / "workspace.js").read_text(encoding="utf-8")
        for marker in ("loki_steps_data", "loki_steps_run", "loki_steps_council"):
            self.assertIn(marker, workspace)
        self.assertIn("loki_steps_journal", (ROOT / "static" / "js" / "planner.js").read_text(encoding="utf-8"))
        # CSV preview before a replay.
        self.assertIn('id="quant-csv-preview"', source)
        self.assertIn('id="preview-apply"', source)
        self.assertIn("function previewCsv", workspace)
        # AI heartbeat, FX note, evidence links, backup/restore.
        self.assertIn('id="ai-heartbeat"', source)
        self.assertIn("loki-fx-note", (ROOT / "static" / "js" / "currency.js").read_text(encoding="utf-8"))
        self.assertIn("EVIDENCE", workspace)
        self.assertIn('id="backup-export"', source)
        backup = (ROOT / "static" / "js" / "backup.js").read_text(encoding="utf-8")
        self.assertIn("loki-fusion-paper-v1", backup)
        self.assertIn("browser-backup", backup)
        self.assertIn('id="terminal-offline-note"', source)
        self.assertIn("/static/js/next_steps.js", source)
        self.assertIn("/static/js/backup.js", source)

    def test_regime_breakdown_shocks_freshness_and_practice_wiring(self):
        source = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="regime-panel"', source)
        self.assertIn('id="regime-note"', source)
        self.assertIn('id="regime-table"', source)
        self.assertIn('id="scenario-compare"', source)
        self.assertIn('id="scenario-compare-out"', source)
        self.assertIn('class="panel practice-panel"', source)
        self.assertIn('data-practice="ride-trend"', source)
        self.assertIn('data-practice="range-trap"', source)
        self.assertIn('data-practice="crash-drill"', source)
        self.assertIn("/static/js/practice.js", source)
        workspace = (ROOT / "static" / "js" / "workspace.js").read_text(encoding="utf-8")
        self.assertIn("report.regime_metrics", workspace)
        self.assertIn("mark_updated_at", workspace)
        self.assertIn("opened_at", workspace)
        self.assertIn("council-disagree", workspace)
        self.assertIn("#scenario-compare", workspace)
        practice = (ROOT / "static" / "js" / "practice.js").read_text(encoding="utf-8")
        for key in ("ride-trend", "range-trap", "crash-drill"):
            self.assertIn(key, practice)
        self.assertIn("lokiSimulatedMarket", practice)
        lab = Path(__file__).resolve().parents[1] / "core" / "strategy_lab.py"
        lab_source = lab.read_text(encoding="utf-8")
        self.assertIn("_regime_analysis", lab_source)
        self.assertIn("Trending up", lab_source)
        portfolio = (Path(__file__).resolve().parents[1] / "core" / "fusion" / "portfolio.py").read_text(encoding="utf-8")
        self.assertIn('"mark_source"', portfolio)
        self.assertIn("manual mark", portfolio)
        self.assertIn("entry fill", portfolio)

    def test_results_read_note_research_links_and_backup_coverage(self):
        source = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="research-read-note"', source)  # how-to-read framing on the results page
        # the regime table sits between the headline metrics and the cost grid
        self.assertLess(
            source.index('id="regime-panel"'),
            source.index('id="evidence-list"'),
            "regime breakdown should read before evidence/limitations",
        )
        workspace = (ROOT / "static" / "js" / "workspace.js").read_text(encoding="utf-8")
        self.assertIn("Research link", workspace)  # ledger ties fills back to runs
        self.assertIn("report_fingerprint", workspace)
        backup = (ROOT / "static" / "js" / "backup.js").read_text(encoding="utf-8")
        self.assertIn("loki-synthetic-market-v1", backup)  # saved practice sessions travel in backups
        simulated = (Path(__file__).resolve().parents[1] / "core" / "fusion" / "simulated_market.py").read_text(encoding="utf-8")
        self.assertIn("generated close", simulated)  # synthetic marks never claim to be manual

    def test_command_palette_shortcut_sheet_and_pinned_run_compare(self):
        source = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        # palette + cheat sheet overlays exist as real accessible dialogs
        self.assertIn('id="command-palette"', source)
        self.assertIn('id="palette-input"', source)
        self.assertIn('id="palette-list"', source)
        self.assertIn('id="shortcut-sheet"', source)
        self.assertIn('aria-label="Command palette"', source)
        self.assertIn('aria-label="Keyboard cheat sheet"', source)
        self.assertIn('id="open-palette"', source)  # topbar chip opens it
        self.assertIn("/static/js/palette.js", source)  # and the module is loaded
        self.assertIn('id="pinned-strip"', source)  # pinned compare anchors exist
        self.assertIn('id="pin-report"', source)
        palette = (ROOT / "static" / "js" / "palette.js").read_text(encoding="utf-8")
        self.assertIn("a[data-view]", palette)  # palette entries come from the real nav
        self.assertIn("data-practice", palette)  # drills are one command away
        self.assertIn("will not pretend", palette)  # actions refuse to fake success
        self.assertIn("Ctrl K", palette)  # non-Mac users see the real binding
        self.assertIn("Escape", palette)
        workspace = (ROOT / "static" / "js" / "workspace.js").read_text(encoding="utf-8")
        self.assertIn("loki_pinned_report_v1", workspace)  # pinned runs survive reloads
        self.assertIn("ppDeltaCell", workspace)  # honest change arithmetic
        self.assertIn("it does not forecast anything", workspace)  # delta honesty line
        self.assertIn("Compare with the pinned run ↓", workspace)  # compare is discoverable from the top
        self.assertIn("same fingerprint as the pinned run", workspace)  # disabled state explains itself
        self.assertIn("✓ Selected:", workspace)  # upload zone shows the chosen file
        backup = (ROOT / "static" / "js" / "backup.js").read_text(encoding="utf-8")
        self.assertIn("loki_pinned_report_v1", backup)  # pins ride in backups too
        styles = (ROOT / "static" / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn(".palette-overlay", styles)
        self.assertIn(".pinned-strip", styles)
        self.assertIn(".pin-flash", styles)  # compare jump highlights the strip
        self.assertIn("topbar-status{flex-wrap:wrap", styles)  # crowded bar wraps on phones

    def test_display_currency_switch_rerenders_the_paper_portfolio(self):
        # The switcher toggles A$/US$ display; every money surface must follow.
        currency = (ROOT / "static" / "js" / "currency.js").read_text(encoding="utf-8")
        self.assertIn("roundedMagnitude", currency)  # sub-cent outflows show US$0.00, never "-US$0.00"
        self.assertIn("Decide the sign AFTER rounding", currency)  # honesty note on the edge case
        workspace = (ROOT / "static" / "js" / "workspace.js").read_text(encoding="utf-8")
        self.assertIn("loki:currency", workspace)  # paper portfolio re-renders on switch
        self.assertIn("displayMoney", workspace)  # metric cards and ledger follow
        self.assertIn("window.LokiCurrency", workspace)  # via the shared formatter
        ai = (ROOT / "static" / "js" / "ai_trading.js").read_text(encoding="utf-8")
        self.assertIn("loki:currency", ai)  # AI panel already followed; keep it so
        planner = (ROOT / "static" / "js" / "planner.js").read_text(encoding="utf-8")
        self.assertIn("no decision to save yet", planner)  # empty-save tells the user, never silently no-ops

    def test_run_summary_evidence_card_and_practice_streak(self):
        source = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="run-summary"', source)         # plain-English paragraph from real numbers
        self.assertIn('id="copy-run-summary"', source)    # honest shareable evidence card
        self.assertIn('id="practice-streak"', source)     # habit strip on the Bored? page
        workspace = (ROOT / "static" / "js" / "workspace.js").read_text(encoding="utf-8")
        self.assertIn("renderRunSummary", workspace)
        self.assertIn("walk-forward fold", workspace)     # written from real report fields
        self.assertIn("not a forecast of what happens next", workspace)
        self.assertIn("Cleared as a paper candidate.", workspace)
        self.assertIn("blocked the clipboard", workspace)  # copy failures are told, never faked
        practice = (ROOT / "static" / "js" / "practice.js").read_text(encoding="utf-8")
        self.assertIn("loki_practice_stats_v1", practice)
        self.assertIn("bumpDrill", practice)              # bumps only at real drill completion
        self.assertIn("never grades skill", practice)
        backup = (ROOT / "static" / "js" / "backup.js").read_text(encoding="utf-8")
        self.assertIn("loki_practice_stats_v1", backup)   # streak survives backups too

    def test_gate_page_recovery_explanations_and_preview(self):
        source = (ROOT / "templates" / "gate.html").read_text(encoding="utf-8")
        self.assertIn('id="need-help"', source)  # "Need help getting in?" affordance
        self.assertIn('id="help-block"', source)  # inline recovery guidance
        self.assertIn('id="forget-device"', source)  # shared-computer eraser
        self.assertIn("30 days", source)  # the 30-day unlock is explained
        self.assertIn("five-minute break", source)  # lockout recovery copy
        self.assertIn("peek-card", source)  # workspace preview cards
        self.assertIn("paper mode", source)  # privacy promise states what is real
        self.assertIn("/api/gate/forget", source)  # eraser hits the server endpoint
        server_src = (ROOT / "loki" / "api" / "server.py").read_text(encoding="utf-8")
        self.assertIn('"/api/gate/forget"', server_src)  # and the endpoint exists
        self.assertIn("delete_cookie(site_access.GATE_COOKIE", server_src)  # clears the httponly gate cookie

    def test_no_github_links_in_any_public_template(self):
        for template in sorted((ROOT / "templates").glob("*.html")):
            text = template.read_text(encoding="utf-8")
            self.assertNotIn("github.com/eleven-official", text, str(template))

    def test_rule_version_labels_match_replay_engine(self):
        html = (ROOT / "templates" / "research_desk.html").read_text(encoding="utf-8")
        engine = (ROOT / "static" / "js" / "strategy-lab.js").read_text(encoding="utf-8")
        match = re.search(r'const RULE_VERSION = "([^"]+)";', engine)
        self.assertIsNotNone(match)
        version = match.group(1)
        self.assertIn(f"RULE SET · VERSION {version}", html)
        self.assertIn(f'class="versionValue">{version}</strong>', html)
        self.assertIn(f"REVIEWING RULE SET {version}", html)
        self.assertIn("matched-cost buy-and-hold baseline", html)
        agent_match = re.search(r'const AGENT_VERSION = "([^"]+)";', engine)
        self.assertIsNotNone(agent_match)
        self.assertIn(f"ADAPTIVE PAPER AGENT · VERSION {agent_match.group(1)}", html)
        workspace = (ROOT / "static" / "js" / "research_desk.js").read_text(encoding="utf-8")
        self.assertIn("trainingBenchmarkReturnPct", workspace)
        self.assertIn("latestAgentPaper.agentVersion !== LAB.AGENT_VERSION", workspace)

    def test_profile_code_persists_locally_without_sending_contact_details(self):
        source = (ROOT / "static" / "js" / "profile.js").read_text(encoding="utf-8")
        self.assertIn("localStorage.setItem", source)
        self.assertIn("localStorage.removeItem", source)
        self.assertNotRegex(source, r"\bfetch\s*\(|XMLHttpRequest|navigator\.sendBeacon")

    def test_server_resolves_template_and_static_paths_from_repository_root(self):
        source = (ROOT / "loki" / "api" / "server.py").read_text(encoding="utf-8")
        self.assertIn("Path(__file__).resolve().parents[2]", source)
        self.assertIn('repo_dir / "static"', source)
        self.assertIn('repo_dir / "templates"', source)


if __name__ == "__main__":
    unittest.main()
