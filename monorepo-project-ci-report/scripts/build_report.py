#!/usr/bin/env python3
"""Build a normalized per-project CI report payload."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote
import xml.etree.ElementTree as ET


def _bootstrap_common_module() -> None:
    script_path = Path(__file__).resolve()
    for parent in script_path.parents:
        candidate = parent / "common" / "ci_payload.py"
        if candidate.exists():
            sys.path.insert(0, str(candidate.parent))
            return


_bootstrap_common_module()

from ci_payload import read_json_file, safe_int, to_bool  # type: ignore  # noqa: E402
from github_reporting import write_output as write_github_output  # type: ignore  # noqa: E402


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _collapse_whitespace(value: str) -> str:
    return " ".join(value.split())


def _truncate(value: str, limit: int = 2000) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}..."


def _read_junit_report(path: str) -> dict[str, Any]:
    if not path:
        return {}
    report_path = Path(path)
    if not report_path.exists():
        return {}

    try:
        root = ET.parse(report_path).getroot()
    except Exception:
        return {}

    cases = list(root.iter("testcase"))
    summary_tests = safe_int(root.attrib.get("tests"), default=len(cases)) if hasattr(root, "attrib") else len(cases)

    failed_tests: list[dict[str, str]] = []
    failures = 0
    errors = 0
    skipped = 0

    for case in cases:
        failure_node = case.find("failure")
        error_node = case.find("error")
        skipped_node = case.find("skipped")

        if skipped_node is not None:
            skipped += 1
            continue

        if failure_node is None and error_node is None:
            continue

        node = failure_node if failure_node is not None else error_node
        if failure_node is not None:
            failures += 1
        if error_node is not None:
            errors += 1

        testcase_name = str(case.attrib.get("name", "")).strip() or "<unknown-test>"
        class_name = str(case.attrib.get("classname", "")).strip()
        full_name = f"{class_name}::{testcase_name}" if class_name else testcase_name

        message_attr = str(node.attrib.get("message", "")).strip() if node is not None else ""
        message_text = (node.text or "").strip() if node is not None else ""
        if message_attr and message_text:
            message = f"{message_attr}\n{message_text}"
        else:
            message = message_attr or message_text or "No failure message available."

        failed_tests.append(
            {
                "name": full_name,
                "message": _truncate(_collapse_whitespace(message), limit=2500),
            }
        )

    failed_count = failures + errors
    passed = max(summary_tests - failed_count - skipped, 0)
    return {
        "summary": {
            "tests": summary_tests,
            "passed": passed,
            "failed": failed_count,
            "skipped": skipped,
            "failures": failures,
            "errors": errors,
        },
        "failed_tests": failed_tests,
    }


def main() -> int:
    project = os.getenv("PROJECT_NAME", "").strip()
    project_path = os.getenv("PROJECT_PATH", "").strip() or project
    repo_owner = os.getenv("REPO_OWNER", "").strip()
    branch = os.getenv("BRANCH", "").strip()
    revision = os.getenv("REVISION", "").strip()
    sha = os.getenv("SHA", "").strip()
    github_event = os.getenv("GITHUB_EVENT", "").strip()
    sonarqube_result = os.getenv("SONARQUBE_RESULT", "missing").strip()
    unit_test_result = os.getenv("UNIT_TEST_RESULT", "missing").strip()
    unit_test_outcome = os.getenv("UNIT_TEST_OUTCOME", "missing").strip()
    tests_present = to_bool(os.getenv("TESTS_PRESENT"))
    junit_exists = to_bool(os.getenv("JUNIT_EXISTS"))
    coverage_exists = to_bool(os.getenv("COVERAGE_EXISTS"))
    fossa_diff_mode = to_bool(os.getenv("FOSSA_DIFF_MODE"))
    fossa_licensing_result = os.getenv("FOSSA_LICENSING_RESULT", "missing").strip()
    fossa_vulnerability_result = os.getenv("FOSSA_VULNERABILITY_RESULT", "missing").strip()
    output_file = os.getenv("OUTPUT_FILE", "").strip() or f"ci-project-result-{project}.json"

    fossa_licensing_report = _as_dict(read_json_file(os.getenv("FOSSA_LICENSING_REPORT_PATH", ""), {}))
    fossa_vulnerability_report = _as_dict(read_json_file(os.getenv("FOSSA_VULNERABILITY_REPORT_PATH", ""), {}))
    unit_test_report = _as_dict(read_json_file(os.getenv("UNIT_TEST_REPORT_PATH", ""), {}))
    unit_test_junit_report = _as_dict(_read_junit_report(os.getenv("UNIT_TEST_JUNIT_REPORT_PATH", "")))

    fossa_project_id = f"{repo_owner}_{project}" if repo_owner and project else ""
    project_locator = quote(f"custom+48578/{fossa_project_id}", safe="") if fossa_project_id else ""
    encoded_branch = quote(branch, safe="")
    encoded_revision = quote(revision, safe="")
    fossa_report_url = (
        f"https://app.fossa.com/projects/{project_locator}/refs/branch/{encoded_branch}/{encoded_revision}"
        if fossa_project_id and branch and revision
        else ""
    )

    licensing_summary = _as_dict(fossa_licensing_report.get("summary", {}))
    vulnerability_summary = _as_dict(fossa_vulnerability_report.get("summary", {}))

    # Keep both project and plugin keys so downstream aggregators can stay generic.
    payload: dict[str, Any] = {
        "project": project,
        "project_path": project_path,
        "branch": branch,
        "sha": sha,
        "github_event": github_event,
        "sonarqube_result": sonarqube_result,
        "fossa_vulnerability_report": fossa_vulnerability_report,
        "fossa_licensing_report": fossa_licensing_report,
        "unit_test_result": unit_test_result,
        "unit_test_report": unit_test_report,
        "unit_test_junit_report": unit_test_junit_report,
        "plugin": project,
        "tests_status": unit_test_result,
        "tests_present": tests_present,
        "test_outcome": unit_test_outcome,
        "junit_exists": junit_exists,
        "coverage_exists": coverage_exists,
        "sonar_outcome": sonarqube_result,
        "fossa_project_id": fossa_project_id,
        "fossa_branch": branch,
        "fossa_revision": revision,
        "fossa_diff_mode": fossa_diff_mode,
        "fossa_report_url": fossa_report_url,
        "fossa_licensing_outcome": fossa_licensing_result,
        "fossa_licensing_total_issues": safe_int(licensing_summary.get("total_issues")),
        "fossa_licensing_blocking_issues": safe_int(licensing_summary.get("blocking_issues")),
        "fossa_vulnerability_outcome": fossa_vulnerability_result,
        "fossa_vulnerability_total_issues": safe_int(vulnerability_summary.get("total_issues")),
        "fossa_vulnerability_blocking_issues": safe_int(vulnerability_summary.get("blocking_issues")),
    }

    Path(output_file).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_github_output("report_file", output_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
