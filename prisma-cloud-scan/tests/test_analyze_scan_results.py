#!/usr/bin/env python3

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def _load_module():
    script_path = Path(__file__).resolve().parent.parent / "scripts" / "analyze_scan_results.py"
    spec = importlib.util.spec_from_file_location("analyze_scan_results", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


analyze_scan_results = _load_module()


class TestAnalyzeScanResults(unittest.TestCase):
    def _read_outputs(self, output_path: Path) -> dict[str, str]:
        outputs: dict[str, str] = {}
        if not output_path.exists():
            return outputs
        for line in output_path.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                outputs[key] = value
        return outputs

    def test_parse_string_date_to_epoch(self):
        value = analyze_scan_results.parse_string_date_to_epoch("2026-03-10T10:11:12Z")
        self.assertIsInstance(value, int)
        self.assertIsNotNone(value)
        self.assertIsNone(analyze_scan_results.parse_string_date_to_epoch("not-a-date"))

    def test_compute_blocking_count_falls_back_on_bad_data(self):
        vulnerabilities = [
            {"severity": "high", "publishedDate": "bad-date"},
            {"severity": "high", "publishedDate": "2026-01-01"},
        ]
        # Should fall back because one date is invalid.
        count = analyze_scan_results.compute_blocking_vulnerability_count(
            vulnerabilities=vulnerabilities,
            severity="high",
            threshold_epoch=0,
            fallback_count=5,
        )
        self.assertEqual(count, 5)

    def test_main_non_blocking_scan_writes_outputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            results = {
                "results": [
                    {
                        "vulnerabilities": [
                            {"severity": "low", "publishedDate": "2026-01-01"},
                        ],
                        "compliances": [],
                        "vulnerabilityDistribution": {
                            "critical": 0,
                            "high": 0,
                            "medium": 0,
                            "low": 1,
                        },
                        "complianceDistribution": {
                            "critical": 0,
                            "high": 0,
                            "medium": 0,
                            "low": 0,
                        },
                    }
                ]
            }
            (root / "pcc_scan_results.json").write_text(json.dumps(results), encoding="utf-8")
            output_file = root / "github_output.txt"

            env = {
                "GITHUB_OUTPUT": str(output_file),
                "BLOCK_ON_COMPLIANCE": "false",
                "GRACE_PERIOD_DAYS": "7",
                "CONSOLE_LINK": "https://example.prisma/scan",
            }

            cwd = os.getcwd()
            os.chdir(root)
            try:
                with patch.dict(os.environ, env, clear=False):
                    rc = analyze_scan_results.main()
            finally:
                os.chdir(cwd)

            self.assertEqual(rc, 0)
            outputs = self._read_outputs(output_file)
            self.assertEqual(outputs.get("scan_passed"), "true")
            self.assertEqual(outputs.get("vuln_low"), "1")
            self.assertEqual(outputs.get("blocking_total"), "0")

            analysis = json.loads((root / "pcc_scan_analysis.json").read_text(encoding="utf-8"))
            self.assertTrue(analysis["scan_passed"])
            self.assertEqual(analysis["vuln_low"], 1)

    def test_main_blocks_on_high_with_zero_grace(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            results = {
                "results": [
                    {
                        "vulnerabilities": [
                            {"severity": "high", "publishedDate": "2026-01-01"},
                        ],
                        "compliances": [],
                    }
                ]
            }
            (root / "pcc_scan_results.json").write_text(json.dumps(results), encoding="utf-8")
            output_file = root / "github_output.txt"

            env = {
                "GITHUB_OUTPUT": str(output_file),
                "BLOCK_ON_COMPLIANCE": "false",
                "GRACE_PERIOD_DAYS": "0",
                "PCC_CONSOLE_URL": "https://example.prisma",
            }

            cwd = os.getcwd()
            os.chdir(root)
            try:
                with patch.dict(os.environ, env, clear=False):
                    rc = analyze_scan_results.main()
            finally:
                os.chdir(cwd)

            self.assertEqual(rc, 1)
            outputs = self._read_outputs(output_file)
            self.assertEqual(outputs.get("scan_passed"), "false")
            self.assertEqual(outputs.get("vuln_high"), "1")
            self.assertEqual(outputs.get("blocking_vuln_high"), "1")


if __name__ == "__main__":
    unittest.main()
