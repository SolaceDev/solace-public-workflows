#!/usr/bin/env python3

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def _load_module():
    script_path = (
        Path(__file__).resolve().parent.parent / "scripts" / "summarize_trivy_results.py"
    )
    spec = importlib.util.spec_from_file_location("summarize_trivy_results", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


summarize = _load_module()


def _vuln(vuln_id, severity, pkg="pkg", installed="1.0", fixed="1.1"):
    return {
        "VulnerabilityID": vuln_id,
        "Severity": severity,
        "PkgName": pkg,
        "InstalledVersion": installed,
        "FixedVersion": fixed,
    }


REPORT = {
    "Results": [
        {
            "Target": "image (os)",
            "Vulnerabilities": [
                _vuln("CVE-1", "CRITICAL", pkg="a"),
                _vuln("CVE-2", "HIGH", pkg="b"),
                _vuln("CVE-3", "low", pkg="c"),
                _vuln("CVE-4", "WEIRD", pkg="d"),
            ],
        },
        {
            "Target": "app/requirements.txt",
            "Vulnerabilities": [
                # Same finding reported for a second target: counted once.
                _vuln("CVE-2", "HIGH", pkg="b"),
                _vuln("CVE-5", "MEDIUM", pkg="pipe|name"),
            ],
        },
        {"Target": "no-vulns", "Vulnerabilities": None},
    ]
}


class TestSummarizeTrivyResults(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.output = self.dir / "output.txt"
        self.summary = self.dir / "summary.md"

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, report=REPORT, **env):
        report_path = self.dir / "trivy_scan.json"
        if report is not None:
            report_path.write_text(
                report if isinstance(report, str) else json.dumps(report),
                encoding="utf-8",
            )
        base = {
            "TRIVY_FILE": str(report_path),
            "GITHUB_OUTPUT": str(self.output),
            "GITHUB_STEP_SUMMARY": str(self.summary),
            "IMAGE_DISPLAY": "repo:1.2.3",
            "TRIVY_VERSION": "v0.69.2",
            "REPO_VISIBILITY": "public",
            "SHOW_DETAILS": "false",
        }
        base.update(env)
        with patch.dict(os.environ, base, clear=False):
            self.assertEqual(summarize.main(), 0)
        outputs = {}
        for line in self.output.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            outputs[key] = value
        summary = self.summary.read_text(encoding="utf-8") if self.summary.exists() else ""
        return outputs, summary

    def test_counts_dedupe_and_normalize_severity(self):
        outputs, _ = self._run()
        self.assertEqual(outputs["scan_ok"], "true")
        self.assertEqual(outputs["vuln_critical"], "1")
        self.assertEqual(outputs["vuln_high"], "1")
        self.assertEqual(outputs["vuln_medium"], "1")
        self.assertEqual(outputs["vuln_low"], "1")
        self.assertEqual(outputs["vuln_unknown"], "1")
        self.assertEqual(outputs["vuln_total"], "5")

    def test_details_hidden_by_default(self):
        _, summary = self._run()
        self.assertIn("Trivy Image Scan Overview", summary)
        self.assertIn("| Vulnerabilities | 1 | 1 | 1 | 1 | 1 | 5 |", summary)
        self.assertIn("Detailed findings are hidden", summary)
        self.assertNotIn("CVE-1", summary)

    def test_details_shown_when_enabled(self):
        _, summary = self._run(SHOW_DETAILS="true", REPO_VISIBILITY="private")
        self.assertIn("<details>", summary)
        self.assertIn("| CVE-1 | CRITICAL | a | 1.0 | 1.1 |", summary)
        self.assertIn("pipe\\|name", summary)
        self.assertNotIn("Detailed findings are hidden", summary)
        # Ordered by severity: critical before low.
        self.assertLess(summary.index("CVE-1"), summary.index("CVE-3"))

    def test_details_truncated_to_max_rows(self):
        _, summary = self._run(SHOW_DETAILS="true", MAX_ROWS="2")
        self.assertIn("_Showing the first 2 of 5 findings._", summary)
        self.assertNotIn("CVE-3", summary)

    def test_missing_report_is_reported_not_raised(self):
        outputs, summary = self._run(report=None)
        self.assertEqual(outputs["scan_ok"], "false")
        self.assertEqual(outputs["vuln_total"], "0")
        self.assertIn("did not produce a readable report", summary)

    def test_invalid_json_is_reported_not_raised(self):
        outputs, _ = self._run(report="{not json")
        self.assertEqual(outputs["scan_ok"], "false")

    def test_step_summary_can_be_disabled(self):
        _, summary = self._run(WRITE_STEP_SUMMARY="false")
        self.assertEqual(summary, "")


if __name__ == "__main__":
    unittest.main()
