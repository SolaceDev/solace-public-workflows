#!/usr/bin/env python3
"""Build a normalized per-project CI report payload."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote


def _bootstrap_common_module() -> None:
    script_path = Path(__file__).resolve()
    for parent in script_path.parents:
        candidate = parent / ".github" / "scripts" / "common" / "ci_payload.py"
        if candidate.exists():
            sys.path.insert(0, str(candidate.parent))
            return


_bootstrap_common_module()

from ci_payload import read_json_file, safe_int, to_bool  # type: ignore  # noqa: E402
from github_reporting import write_output as write_github_output  # type: ignore  # noqa: E402


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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
