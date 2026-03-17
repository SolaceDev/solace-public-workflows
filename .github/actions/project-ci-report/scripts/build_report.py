#!/usr/bin/env python3
"""Build a unified per-project CI report payload."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote


def _to_bool(raw: str | None) -> bool:
    if raw is None:
        return False
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _safe_int(raw: Any) -> int:
    try:
        return int(raw or 0)
    except Exception:
        return 0


def _read_json(path: str) -> dict[str, Any]:
    if not path:
        return {}
    report_path = Path(path)
    if not report_path.exists():
        return {}
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _write_output(name: str, value: str) -> None:
    output_path = os.getenv("GITHUB_OUTPUT", "")
    if not output_path:
        return
    with Path(output_path).open("a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


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
    tests_present = _to_bool(os.getenv("TESTS_PRESENT"))
    junit_exists = _to_bool(os.getenv("JUNIT_EXISTS"))
    coverage_exists = _to_bool(os.getenv("COVERAGE_EXISTS"))
    fossa_diff_mode = _to_bool(os.getenv("FOSSA_DIFF_MODE"))
    fossa_licensing_result = os.getenv("FOSSA_LICENSING_RESULT", "missing").strip()
    fossa_vulnerability_result = os.getenv("FOSSA_VULNERABILITY_RESULT", "missing").strip()
    output_file = os.getenv("OUTPUT_FILE", "").strip() or f"ci-project-result-{project}.json"

    fossa_licensing_report = _read_json(os.getenv("FOSSA_LICENSING_REPORT_PATH", ""))
    fossa_vulnerability_report = _read_json(os.getenv("FOSSA_VULNERABILITY_REPORT_PATH", ""))
    unit_test_report = _read_json(os.getenv("UNIT_TEST_REPORT_PATH", ""))

    fossa_project_id = f"{repo_owner}_{project}" if repo_owner and project else ""
    project_locator = quote(f"custom+48578/{fossa_project_id}", safe="") if fossa_project_id else ""
    encoded_branch = quote(branch, safe="")
    encoded_revision = quote(revision, safe="")
    fossa_report_url = (
        f"https://app.fossa.com/projects/{project_locator}/refs/branch/{encoded_branch}/{encoded_revision}"
        if fossa_project_id and branch and revision
        else ""
    )

    lic_summary = fossa_licensing_report.get("summary", {}) if isinstance(fossa_licensing_report, dict) else {}
    vul_summary = (
        fossa_vulnerability_report.get("summary", {}) if isinstance(fossa_vulnerability_report, dict) else {}
    )

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
        # Compatibility for existing plugin-based aggregators.
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
        "fossa_licensing_total_issues": _safe_int(lic_summary.get("total_issues")),
        "fossa_licensing_blocking_issues": _safe_int(lic_summary.get("blocking_issues")),
        "fossa_vulnerability_outcome": fossa_vulnerability_result,
        "fossa_vulnerability_total_issues": _safe_int(vul_summary.get("total_issues")),
        "fossa_vulnerability_blocking_issues": _safe_int(vul_summary.get("blocking_issues")),
    }

    Path(output_file).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_output("report_file", output_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
