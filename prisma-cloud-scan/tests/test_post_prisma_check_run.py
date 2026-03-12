#!/usr/bin/env python3

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def _load_module():
    script_path = Path(__file__).resolve().parent.parent / "scripts" / "post_prisma_check_run.py"
    spec = importlib.util.spec_from_file_location("post_prisma_check_run", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


post_prisma_check_run = _load_module()


class TestPostPrismaCheckRun(unittest.TestCase):
    def test_parse_datetime_to_epoch(self):
        self.assertIsInstance(post_prisma_check_run.parse_datetime_to_epoch("2026-03-10"), int)
        self.assertEqual(post_prisma_check_run.parse_datetime_to_epoch(""), None)
        self.assertEqual(post_prisma_check_run.parse_datetime_to_epoch(None), None)

    def test_resolve_target_sha_prefers_pull_request_head(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            event_path = Path(tmpdir) / "event.json"
            event_path.write_text(
                json.dumps({"pull_request": {"head": {"sha": "pr-head-sha-456"}}}),
                encoding="utf-8",
            )
            env = {
                "GITHUB_EVENT_PATH": str(event_path),
                "TARGET_SHA": "merge-sha-111",
                "PR_HEAD_SHA": "pr-head-sha-222",
                "GITHUB_SHA": "github-sha-333",
            }
            with patch.dict(os.environ, env, clear=False):
                self.assertEqual(post_prisma_check_run.resolve_target_sha(), "pr-head-sha-456")

    def test_resolve_target_sha_falls_back_when_event_missing(self):
        env = {
            "GITHUB_EVENT_PATH": "/tmp/does-not-exist-event-path.json",
            "TARGET_SHA": "merge-sha-111",
            "PR_HEAD_SHA": "pr-head-sha-222",
            "GITHUB_SHA": "github-sha-333",
        }
        with patch.dict(os.environ, env, clear=False):
            self.assertEqual(post_prisma_check_run.resolve_target_sha(), "merge-sha-111")

    def test_build_detailed_text_hidden_mode(self):
        details = post_prisma_check_run.build_detailed_text(
            detailed_tables_enabled=False,
            repo_visibility="public",
            show_detailed_logs=False,
            target_url="https://example.prisma/scan",
            grace_days=7,
            block_on_compliance=False,
        )
        self.assertIn("Detailed issue rows are hidden.", details)
        self.assertIn("Repository visibility is `public`", details)

    def test_main_posts_check_from_analysis(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            analysis = {
                "scan_passed": True,
                "vuln_critical": 0,
                "vuln_high": 0,
                "vuln_medium": 1,
                "vuln_low": 2,
                "compliance_critical": 0,
                "compliance_high": 0,
                "compliance_medium": 0,
                "compliance_low": 0,
                "blocking_vuln_critical": 0,
                "blocking_vuln_high": 0,
                "blocking_compliance_critical": 0,
                "blocking_compliance_high": 0,
                "blocking_total": 0,
                "grace_days": 7,
                "block_on_compliance": False,
            }
            (root / "pcc_scan_analysis.json").write_text(json.dumps(analysis), encoding="utf-8")
            (root / "event.json").write_text(
                json.dumps({"pull_request": {"head": {"sha": "pr-head-sha-123"}}}),
                encoding="utf-8",
            )

            env = {
                "GITHUB_TOKEN": "token",
                "GITHUB_REPOSITORY": "owner/repo",
                "RUNNER_OS": "Linux",
                "RUNNER_ARCH": "X64",
                "TARGET_SHA": "abc123",
                "GITHUB_EVENT_PATH": str(root / "event.json"),
                "SCAN_EXIT_CODE": "0",
                "IMAGE_NAME": "repo/image:tag",
                "REPO_VISIBILITY": "private",
                "SHOW_DETAILED_LOGS": "false",
                "CONSOLE_LINK": "https://example.prisma/scan",
                "PCC_CONSOLE_URL": "https://example.prisma",
                "FALLBACK_IMAGE": "repo/image:fallback",
            }

            captured: dict[str, object] = {}

            def fake_post(payload):
                captured["payload"] = payload

            cwd = os.getcwd()
            os.chdir(root)
            try:
                with patch.dict(os.environ, env, clear=False):
                    with patch.object(post_prisma_check_run, "post_check_run", side_effect=fake_post):
                        rc = post_prisma_check_run.main()
            finally:
                os.chdir(cwd)

            self.assertEqual(rc, 0)
            payload = captured["payload"]
            self.assertEqual(payload["head_sha"], "pr-head-sha-123")
            self.assertEqual(payload["conclusion"], "success")
            self.assertIn("Prisma Image Scan (Linux/X64)", payload["name"])
            self.assertIn("Prisma Image Scan Overview", payload["output"]["summary"])

    def test_main_detailed_mode_renders_issue_tables(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            analysis = {
                "scan_passed": False,
                "vuln_critical": 0,
                "vuln_high": 1,
                "vuln_medium": 0,
                "vuln_low": 0,
                "compliance_critical": 0,
                "compliance_high": 1,
                "compliance_medium": 0,
                "compliance_low": 0,
                "blocking_vuln_critical": 0,
                "blocking_vuln_high": 1,
                "blocking_compliance_critical": 0,
                "blocking_compliance_high": 1,
                "blocking_total": 2,
                "grace_days": 7,
                "block_on_compliance": True,
            }
            results = {
                "results": [
                    {
                        "vulnerabilities": [
                            {
                                "id": "CVE-2026-0001",
                                "severity": "high",
                                "cvss": 8.1,
                                "packageName": "tar",
                                "packageVersion": "7.5.7",
                                "status": "fixed in 7.5.11",
                                "publishedDate": "2026-03-01",
                                "discoveredDate": "2026-03-10",
                                "description": "Example vulnerability",
                            }
                        ],
                        "compliances": [
                            {
                                "id": "42",
                                "title": "Sensitive information provided in environment variables",
                                "severity": "high",
                                "description": "Example compliance issue",
                            }
                        ],
                    }
                ]
            }
            (root / "pcc_scan_analysis.json").write_text(json.dumps(analysis), encoding="utf-8")
            (root / "pcc_scan_results.json").write_text(json.dumps(results), encoding="utf-8")

            env = {
                "GITHUB_TOKEN": "token",
                "GITHUB_REPOSITORY": "owner/repo",
                "RUNNER_OS": "Linux",
                "RUNNER_ARCH": "ARM64",
                "TARGET_SHA": "def456",
                "SCAN_EXIT_CODE": "1",
                "IMAGE_NAME": "repo/image:tag",
                "REPO_VISIBILITY": "private",
                "SHOW_DETAILED_LOGS": "true",
                "CONSOLE_LINK": "https://example.prisma/scan",
                "PCC_CONSOLE_URL": "https://example.prisma",
                "FALLBACK_IMAGE": "repo/image:fallback",
            }

            captured: dict[str, object] = {}

            def fake_post(payload):
                captured["payload"] = payload

            cwd = os.getcwd()
            os.chdir(root)
            try:
                with patch.dict(os.environ, env, clear=False):
                    with patch.object(post_prisma_check_run, "post_check_run", side_effect=fake_post):
                        rc = post_prisma_check_run.main()
            finally:
                os.chdir(cwd)

            self.assertEqual(rc, 0)
            text = captured["payload"]["output"]["text"]
            self.assertIn("### Vulnerability Issues (quick view)", text)
            self.assertIn("CVE-2026-0001", text)
            self.assertIn("### Compliance Issues (quick view)", text)

    def test_main_returns_failure_when_post_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            analysis = {
                "scan_passed": True,
                "vuln_critical": 0,
                "vuln_high": 0,
                "vuln_medium": 0,
                "vuln_low": 0,
                "compliance_critical": 0,
                "compliance_high": 0,
                "compliance_medium": 0,
                "compliance_low": 0,
                "blocking_vuln_critical": 0,
                "blocking_vuln_high": 0,
                "blocking_compliance_critical": 0,
                "blocking_compliance_high": 0,
                "blocking_total": 0,
                "grace_days": 7,
                "block_on_compliance": False,
            }
            (root / "pcc_scan_analysis.json").write_text(json.dumps(analysis), encoding="utf-8")

            env = {
                "GITHUB_TOKEN": "token",
                "GITHUB_REPOSITORY": "owner/repo",
                "TARGET_SHA": "sha999",
                "PCC_CONSOLE_URL": "https://example.prisma",
                "FALLBACK_IMAGE": "repo/image:fallback",
            }

            cwd = os.getcwd()
            os.chdir(root)
            try:
                with patch.dict(os.environ, env, clear=False):
                    with patch.object(
                        post_prisma_check_run, "post_check_run", side_effect=RuntimeError("boom")
                    ):
                        rc = post_prisma_check_run.main()
            finally:
                os.chdir(cwd)

            self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
