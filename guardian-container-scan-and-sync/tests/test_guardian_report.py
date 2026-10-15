#!/usr/bin/env python3

import importlib.util
import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch


def _load_module():
    script_path = Path(__file__).resolve().parent.parent / "scripts" / "guardian_report.py"
    spec = importlib.util.spec_from_file_location("guardian_report", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


report = _load_module()


def _hit(cve, component, version, severity, fixes, jira=None, days=None, scanners=("prisma",)):
    return {
        "cve_id": cve,
        "component_name": component,
        "component_version": version,
        "severity": severity,
        "fix_versions": list(fixes),
        "jira_key": jira,
        "days_until_blocking": days,
        "scanners": list(scanners),
    }


GATE = {
    "overall_blocked": True,
    "results": [
        {
            "repository": "my-product",
            "vulnerabilities": [
                _hit("CVE-1", "spring-core", "6.2.19", "Critical", ["7.0.8.1", "6.2.20", "6.1.29"], "DATAGO-1", scanners=("prisma", "trivy")),
                _hit("CVE-2", "spring-core", "6.2.19", "High", ["6.2.21"], "DATAGO-1"),
            ],
            "vulnerabilities_pending": [
                _hit("CVE-3", "jq", "1.6", "Medium", ["1.7"], "DATAGO-2", days=3, scanners=("trivy",)),
                _hit("CVE-4", "jq", "1.6", "Low", ["1.7"], "DATAGO-2", days=9, scanners=("trivy",)),
                _hit("CVE-5", "zlib", "1.2", "High", ["1.3"], None, days=1),
            ],
            "vulnerabilities_excluded": [_hit("CVE-6", "x", "1", "High", ["2"])],
            "vulnerabilities_parent_owned": [],
        }
    ],
}

DESCRIPTIONS = {
    "vulnerabilities": [
        {"cve_id": "CVE-1", "component_name": "spring-core", "component_version": "6.2.19",
         "description": "Header predicate bypass | in pre-flight.", "cvss_score": 9.8},
        {"cve_id": "CVE-2", "component_name": "spring-core", "component_version": "6.2.19",
         "description": "Other.", "cvss_score": 7.5},
    ]
}

SQUADS = {"squads": [{"name": "cicd", "products": [{"name": "my-product"}]}]}


class TestVersions(unittest.TestCase):
    def test_earliest_fix_prefers_lowest_version_above_installed(self):
        self.assertEqual(report.earliest_fix("6.2.19", ["7.0.8.1", "6.2.20", "6.1.29"]), "6.2.20")
        self.assertEqual(report.earliest_fix("10.40-6.el9", ["10.40-7.el9_8"]), "10.40-7.el9_8")
        # Nothing above the installed version: fall back to the lowest.
        self.assertEqual(report.earliest_fix("9.0", ["1.0", "2.0"]), "1.0")
        self.assertIsNone(report.earliest_fix("1.0", []))


class TestRendering(unittest.TestCase):
    def test_plain_description_drops_markdown(self):
        text = "### Impact\nIf the **Unpacker** is used `twice`, it crashes."
        self.assertEqual(
            report.truncate(report.plain_description(text), 140),
            "Impact If the Unpacker is used twice, it crashes.",
        )


class TestGrouping(unittest.TestCase):
    def setUp(self):
        result = GATE["results"][0]
        details = {
            (r["cve_id"], r["component_name"], r["component_version"]): {
                "description": r["description"], "cvss": r["cvss_score"]}
            for r in DESCRIPTIONS["vulnerabilities"]
        }
        self.rows = report.group_issues(result["vulnerabilities"], result["vulnerabilities_pending"], details)
        self.by_key = {r["jira_key"] or r["component"]: r for r in self.rows}

    def test_one_row_per_jira_issue(self):
        self.assertEqual(len(self.rows), 3)
        self.assertEqual(self.by_key["DATAGO-1"]["cves"], ["CVE-1", "CVE-2"])

    def test_row_fix_clears_every_cve(self):
        # CVE-1 needs 6.2.20, CVE-2 needs 6.2.21: the issue is fixed by 6.2.21.
        self.assertEqual(self.by_key["DATAGO-1"]["fix"], "6.2.21")

    def test_row_fields(self):
        row = self.by_key["DATAGO-1"]
        self.assertTrue(row["blocking"])
        self.assertEqual(row["severity"], "Critical")
        self.assertEqual(row["cvss"], 9.8)
        self.assertEqual(row["scanners"], ["prisma", "trivy"])
        self.assertIn("Header predicate bypass", row["description"])
        pending = self.by_key["DATAGO-2"]
        self.assertFalse(pending["blocking"])
        self.assertEqual(pending["days_until_blocking"], 3)

    def test_findings_without_jira_group_by_component(self):
        self.assertIsNone(self.by_key["zlib"]["jira_key"])

    def test_order_blocking_then_soonest_due(self):
        self.assertEqual([r["jira_key"] for r in self.rows], ["DATAGO-1", None, "DATAGO-2"])


class TestMain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.output = self.dir / "output.txt"
        self.summary = self.dir / "summary.md"
        self.posted = []

    def tearDown(self):
        self.tmp.cleanup()

    def _fetch(self, method, url, token, body=None):
        if url.endswith("/api/v1/vulnerability_gate"):
            self.assertEqual(body["repositories"], [{"product": "my-product", "version": "1.2.3"}])
            return GATE
        if "/api/v1/vulnerabilities?" in url:
            return DESCRIPTIONS
        if url.endswith("/api/v1/configs/squads"):
            return SQUADS
        raise AssertionError(url)

    def _run(self, fetch=None, post=None, **overrides):
        env = {
            "GUARDIAN_URL": "https://guardian.example/",
            "GUARDIAN_KEY": "k",
            "PRODUCT_NAME": "my-product",
            "PRODUCT_VERSION": "develop",
            "FULL_VERSION": "1.2.3",
            "UNIFIERS": "prisma,trivy",
            "TRIVY_STATUS": "success",
            "SYNC_RESPONSE": json.dumps({"db_synch": {"summary": {"new": 1, "resolved": 2, "resurfaced": 0}},
                                         "jira_close": {"closed": 1}}),
            "SHOW_DETAILS": "true",
            "DASHBOARD_URL": "https://dash.example",
            "JIRA_BASE_URL": "https://jira.example",
            "GITHUB_OUTPUT": str(self.output),
            "GITHUB_STEP_SUMMARY": str(self.summary),
            "GITHUB_TOKEN": "t",
            "GITHUB_REPOSITORY": "org/repo",
            "TARGET_SHA": "abc",
        }
        env.update(overrides)

        def default_post(payload):
            self.posted.append(payload)
            return "https://github.example/check/1"

        with patch.dict(os.environ, env, clear=False), \
                patch.object(report, "fetch_json", side_effect=fetch or self._fetch), \
                patch.object(report, "post_check_run", side_effect=post or default_post), \
                patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(report.main(), 0)
        outputs = dict(l.split("=", 1) for l in self.output.read_text().splitlines())
        summary = self.summary.read_text() if self.summary.exists() else ""
        return outputs, summary, out.getvalue()

    def test_private_report_has_issue_table_and_links(self):
        outputs, summary, _ = self._run()
        self.assertEqual(outputs["report_status"], "ok")
        self.assertEqual(outputs["blocking_count"], "2")
        self.assertEqual(outputs["pending_count"], "3")
        self.assertEqual(outputs["blocking_issues"], "1")
        self.assertIn("1 new · 2 resolved · 0 resurfaced · Jira closed: 1", summary)
        self.assertIn("| 🚨 Past SLA | 1 | 1 | 0 | 0 | 0 | 2 |", summary)
        self.assertIn("Not counted above: 1 excluded.", summary)
        self.assertIn("[DATAGO-1](https://jira.example/browse/DATAGO-1)", summary)
        self.assertIn(
            "[CVE-1](https://dash.example/vulnerabilities/CVE-1?from=%2Fsquads%2Fcicd%2Fproducts%2Fmy-product%2Fdevelop)",
            summary,
        )
        self.assertIn("fixed in 6.2.21", summary)
        self.assertIn("Header predicate bypass \\| in pre-flight.", summary)
        payload = self.posted[0]
        self.assertEqual(payload["name"], "Guardian Scan")
        self.assertEqual(payload["head_sha"], "abc")
        self.assertEqual(payload["conclusion"], "neutral")
        self.assertIn("1 Jira issue(s) past SLA", payload["output"]["title"])
        self.assertEqual(payload["details_url"], "https://dash.example/squads/cicd/products/my-product/develop")
        self.assertIn("DATAGO-1", payload["output"]["text"])

    def test_public_report_is_counts_only(self):
        calls = []

        def fetch(method, url, token, body=None):
            calls.append(url)
            return self._fetch(method, url, token, body)

        _, summary, _ = self._run(fetch=fetch, SHOW_DETAILS="false")
        self.assertIn("Past SLA", summary)
        self.assertIn("Per-issue details are hidden", summary)
        self.assertNotIn("DATAGO-1", summary)
        self.assertNotIn("dash.example", summary)
        self.assertNotIn("Header predicate", summary)
        # No description or squad lookups when details are hidden.
        self.assertEqual(len(calls), 1)
        self.assertNotIn("DATAGO-1", self.posted[0]["output"]["text"])

    def test_no_blocking_is_success(self):
        clean = {"results": [{"repository": "my-product", "vulnerabilities": [],
                              "vulnerabilities_pending": []}]}
        _, summary, _ = self._run(
            fetch=lambda m, u, t, b=None: clean if u.endswith("vulnerability_gate") else self._fetch(m, u, t, b)
        )
        self.assertEqual(self.posted[0]["conclusion"], "success")
        self.assertIn("No open findings with a fix", summary)

    def test_gate_failure_degrades_without_failing(self):
        def fetch(method, url, token, body=None):
            raise urllib.error.URLError("down")

        outputs, summary, out = self._run(fetch=fetch)
        self.assertEqual(outputs["report_status"], "unavailable")
        self.assertIn("could not be retrieved", summary)
        self.assertIn("::warning::", out)
        self.assertEqual(self.posted[0]["conclusion"], "neutral")

    def test_check_run_can_be_disabled(self):
        self._run(CREATE_CHECK="false")
        self.assertEqual(self.posted, [])

    def test_trivy_failure_is_called_out(self):
        _, summary, _ = self._run(UNIFIERS="prisma", TRIVY_STATUS="failure")
        self.assertIn("prisma (Trivy not synced)", summary)

    def test_prisma_failure_is_called_out(self):
        _, summary, _ = self._run(UNIFIERS="trivy", PRISMA_STATUS="failure")
        self.assertIn("trivy (Prisma not synced)", summary)


class TestPostCheckRun(unittest.TestCase):
    def test_missing_checks_permission_is_skipped(self):
        body = b'{"message": "Resource not accessible by integration"}'
        error = urllib.error.HTTPError("u", 403, "Forbidden", {}, io.BytesIO(body))
        with patch.dict(os.environ, {"GITHUB_TOKEN": "t", "GITHUB_REPOSITORY": "o/r"}), \
                patch("urllib.request.urlopen", side_effect=error), \
                patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertIsNone(report.post_check_run({"name": "x"}))
        self.assertIn("HTTP 403: Resource not accessible by integration", out.getvalue())
        self.assertIn("checks: write", out.getvalue())

    def test_skip_notice_without_body(self):
        error = urllib.error.HTTPError("u", 404, "Not Found", {}, io.BytesIO(b"not json"))
        with patch.dict(os.environ, {"GITHUB_TOKEN": "t", "GITHUB_REPOSITORY": "o/r"}), \
                patch("urllib.request.urlopen", side_effect=error), \
                patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertIsNone(report.post_check_run({"name": "x"}))
        self.assertIn("(HTTP 404)", out.getvalue())

    def test_other_errors_propagate(self):
        error = urllib.error.HTTPError("u", 500, "Boom", {}, io.BytesIO(b"{}"))
        with patch.dict(os.environ, {"GITHUB_TOKEN": "t", "GITHUB_REPOSITORY": "o/r"}), \
                patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(urllib.error.HTTPError):
                report.post_check_run({"name": "x"})


if __name__ == "__main__":
    unittest.main()
