#!/usr/bin/env python3

import importlib.util
import os
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest.mock import patch


def _load_module():
    script_path = Path(__file__).resolve().parent.parent / "scripts" / "release_readiness_report.py"
    spec = importlib.util.spec_from_file_location("release_readiness_report", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


report = _load_module()

SOURCE = {"label": "Source", "project": "SolaceDev_app", "branch": "main", "revision": "1.0.0-rc.1", "result": "success"}
CONTAINER = {"label": "Container", "project": "app-container", "branch": "main", "revision": "1.0.0-rc.1", "result": "failure"}

ISSUES = {
    "custom+48578/SolaceDev_app": [{"type": "policy_flag"}, {"type": "policy_flag"}],
    "custom+48578/app-container": [
        {"type": "policy_conflict"},
        {"type": "unlicensed_dependency"},
        {"type": "unlicensed_dependency"},
        {"type": "unconcluded_dependency"},
        {"type": "policy_flag"},
    ],
}
POLICIES = {
    "custom+48578/SolaceDev_app": "Solace-Distributed-Standard",
    "custom+48578/app-container": "Solace-OS-Container-with-Application",
}

GATE = {
    "results": [
        {
            "repository": "app",
            "vulnerabilities": [
                {
                    "cve_id": "CVE-1",
                    "component_name": "openssl",
                    "component_version": "3.0.2",
                    "severity": "Critical",
                    "fix_versions": ["3.0.3"],
                    "jira_key": "DATAGO-1",
                    "scanners": ["prisma"],
                }
            ],
            "vulnerabilities_pending": [
                {
                    "cve_id": "CVE-2",
                    "component_name": "netty",
                    "component_version": "4.1.1",
                    "severity": "High",
                    "fix_versions": ["4.1.2"],
                    "jira_key": "DATAGO-2",
                    "days_until_blocking": 5,
                    "scanners": ["prisma"],
                }
            ],
        }
    ]
}


def fake_fetch(method, url, token, body=None):
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc == "app.fossa.com":
        if parsed.path == "/api/v2/issues":
            query = urllib.parse.parse_qs(parsed.query)
            return {"issues": ISSUES[query["scope[id]"][0]]}
        project = urllib.parse.unquote(parsed.path.rsplit("/", 1)[-1])
        return {"policy": {"title": POLICIES[project]}}
    if parsed.path == "/api/v1/vulnerability_gate":
        return GATE
    if parsed.path == "/api/v1/configs/squads":
        return {"squads": [{"name": "squad-a", "products": [{"name": "app"}]}]}
    if parsed.path == "/api/v1/vulnerabilities":
        return {"vulnerabilities": []}
    raise AssertionError(f"unexpected request {method} {url}")


class ReportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.summary = Path(self.tmp.name) / "summary.md"
        self.output = Path(self.tmp.name) / "output"
        self.env = {
            "RUNNER_TEMP": self.tmp.name,
            "GITHUB_STEP_SUMMARY": str(self.summary),
            "GITHUB_OUTPUT": str(self.output),
            "TITLE": "Release readiness: `1.0.0-rc.1`",
            "STATUS": "blocked",
            "REASONS": "FOSSA container licensing: failure",
            "CONTEXT": "Image `app:1.0.0-rc.1`",
            "FOSSA_API_KEY": "fossa-key",
            "FOSSA_PROJECTS": report.json.dumps([SOURCE, CONTAINER]),
            "GUARDIAN_URL": "https://guardian.example",
            "GUARDIAN_KEY": "guardian-key",
            "GUARDIAN_PRODUCT_NAME": "app",
            "GUARDIAN_PRODUCT_VERSION": "main",
            "GUARDIAN_FULL_VERSION": "1.0.0-rc.1",
            "GUARDIAN_DASHBOARD_URL": "https://guardian.example",
            "JIRA_BASE_URL": "https://jira.example",
            "SHOW_DETAILS": "true",
        }

    def run_report(self, **overrides):
        values = {**self.env, **overrides}
        with patch.dict(os.environ, values, clear=True), patch.object(
            report.guardian_report, "fetch_json", side_effect=fake_fetch
        ):
            self.assertEqual(report.main(), 0)
        outputs = dict(line.split("=", 1) for line in self.output.read_text().splitlines())
        text = Path(outputs["report_path"]).read_text()
        return text, outputs

    def test_verdict_and_reasons(self):
        text, _ = self.run_report()
        self.assertTrue(text.startswith("## ❌ Release readiness: `1.0.0-rc.1` — blocked"))
        self.assertIn("- Image `app:1.0.0-rc.1`", text)
        self.assertIn("**Blocked by:**\n\n- FOSSA container licensing: failure", text)

    def test_ready_verdict_has_no_reasons(self):
        text, _ = self.run_report(STATUS="ready", REASONS="")
        self.assertTrue(text.startswith("## ✅ Release readiness: `1.0.0-rc.1` — ready"))
        self.assertNotIn("Blocked by", text)

    def test_licensing_counts_only_block_on_types_as_blocking(self):
        text, outputs = self.run_report()
        self.assertEqual(outputs["licensing_blocking"], "3")
        self.assertIn(
            "| Source | [SolaceDev_app](https://app.fossa.com/projects/custom%2B48578%2FSolaceDev_app"
            "/refs/branch/main/1.0.0-rc.1/issues/licensing) | `1.0.0-rc.1` "
            "| Solace-Distributed-Standard | ✅ passed | 0 | 2 flagged |",
            text,
        )
        self.assertIn("| ❌ failed | **1 denied by policy, 2 unlicensed** | 1 unconcluded, 1 flagged |", text)

    def test_licensing_lists_no_individual_issues_but_recommends_per_blocking_type(self):
        text, _ = self.run_report()
        self.assertIn("**Denied by policy.**", text)
        self.assertIn("**Unlicensed.**", text)
        self.assertNotIn("**Flagged.**", text)
        self.assertIn("Resolving License Compliance Issues in FOSSA", text)

    def test_block_on_is_configurable(self):
        text, outputs = self.run_report(FOSSA_BLOCK_ON="policy_conflict")
        self.assertEqual(outputs["licensing_blocking"], "1")
        self.assertIn("**1 denied by policy** | 2 unlicensed, 1 unconcluded, 1 flagged |", text)

    def test_fossa_pages_are_followed(self):
        pages = {1: [{"type": "policy_flag"}] * report.FOSSA_PAGE_SIZE, 2: [{"type": "policy_conflict"}]}

        def paged(method, url, token, body=None):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            return {"issues": pages[int(query["page"][0])]}

        with patch.object(report.guardian_report, "fetch_json", side_effect=paged):
            counts = report.fossa_issue_counts("key", "custom+48578/app", "1.0.0")
        self.assertEqual(counts, {"policy_flag": report.FOSSA_PAGE_SIZE, "policy_conflict": 1})

    def test_fossa_error_is_reported_not_raised(self):
        def failing(method, url, token, body=None):
            if "app.fossa.com" in url:
                raise OSError("boom")
            return fake_fetch(method, url, token, body)

        with patch.dict(os.environ, self.env, clear=True), patch.object(
            report.guardian_report, "fetch_json", side_effect=failing
        ), patch("builtins.print") as printed:
            self.assertEqual(report.main(), 0)
        text = self.summary.read_text()
        self.assertIn("| — | could not be read |", text)
        self.assertTrue(any("Could not read FOSSA issues" in str(c) for c in printed.call_args_list))

    def test_guardian_section_matches_guardian_report(self):
        text, outputs = self.run_report()
        self.assertEqual(outputs["guardian_blocking"], "1")
        self.assertIn("### 🛡️ Guardian", text)
        self.assertNotIn("Guardian Scan Overview", text)
        self.assertIn("| 🚨 Past SLA | 1 | 0 | 0 | 0 | 0 | 1 |", text)
        self.assertIn("[DATAGO-1](https://jira.example/browse/DATAGO-1)", text)
        self.assertIn("https://guardian.example/squads/squad-a/products/app/main", text)

    def test_guardian_details_hidden_without_show_details(self):
        text, _ = self.run_report(SHOW_DETAILS="false")
        self.assertIn("| ⏳ Within SLA | 0 | 1 | 0 | 0 | 0 | 1 |", text)
        self.assertNotIn("DATAGO-1", text)
        self.assertIn("Per-issue details are hidden", text)

    def test_sections_are_omitted_without_inputs(self):
        text, outputs = self.run_report(FOSSA_PROJECTS="", GUARDIAN_URL="")
        self.assertNotIn("Licensing", text)
        self.assertNotIn("Guardian", text)
        self.assertEqual(outputs["licensing_blocking"], "")

    def test_summary_can_be_suppressed(self):
        text, _ = self.run_report(WRITE_STEP_SUMMARY="false")
        self.assertFalse(self.summary.exists())
        self.assertIn("### 📜 Licensing (FOSSA)", text)

    def test_summary_is_the_report(self):
        text, _ = self.run_report()
        self.assertEqual(self.summary.read_text(), text)


if __name__ == "__main__":
    unittest.main()
