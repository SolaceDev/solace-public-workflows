#!/usr/bin/env python3
"""
Aggregate project check payloads and publish a formatted PR report.

Supported check types:
- sonarqube: aggregate `sonar_outcome` from CI result JSON files
- unit-tests: aggregate `tests_status` from CI result JSON files
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def _bootstrap_common_module() -> None:
    script_path = Path(__file__).resolve()
    for parent in script_path.parents:
        candidate = parent / ".github" / "scripts" / "common" / "github_reporting.py"
        if candidate.exists():
            sys.path.insert(0, str(candidate.parent))
            return


_bootstrap_common_module()

from github_reporting import (  # type: ignore  # noqa: E402
    append_summary as _append_summary,
    create_check_run as _create_check_run,
    github_api as _github_api,
    normalize_pr_number as _normalize_pr_number,
    resolve_check_run_id as _resolve_check_run_id,
    resolve_pr_number_by_head as _resolve_pr_number_by_head,
    to_bool as _to_bool,
    upsert_pr_comment as _upsert_pr_comment,
    utc_now_iso as _utc_now_iso,
    write_output as _write_output,
)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _collect_result_payloads(result_dir: Path) -> dict[str, dict[str, Any]]:
    by_project: dict[str, dict[str, Any]] = {}
    if not result_dir.exists():
        return by_project
    for file_path in result_dir.rglob("*.json"):
        payload = _read_json(file_path, {})
        project = payload.get("project") or payload.get("plugin")
        if isinstance(project, str) and project.strip():
            by_project[project.strip()] = payload
    return by_project


def _normalize_projects(raw_projects: Any) -> list[str]:
    projects: list[str] = []
    if not isinstance(raw_projects, list):
        return projects
    for item in raw_projects:
        if isinstance(item, str):
            project = item.strip()
            if project:
                projects.append(project)
        elif isinstance(item, dict):
            project = str(
                item.get("project_directory", "")
                or item.get("plugin_directory", "")
            ).strip()
            if project:
                projects.append(project)
    return projects


def _build_sonar_report(
    projects: list[str],
    by_project: dict[str, dict[str, Any]],
    owner: str,
    pr_number: int,
    sonar_host_url: str,
) -> tuple[bool, list[dict[str, Any]], str]:
    host = sonar_host_url.rstrip("/") + "/"
    all_passed = True
    rows: list[dict[str, Any]] = []
    for project in projects:
        payload = by_project.get(project, {})
        outcome = str(payload.get("sonar_outcome", "missing"))
        passed = outcome == "success"
        if not passed:
            all_passed = False
        status = "passed" if passed else "failed"
        status_emoji = "✅" if passed else "❌"
        sonar_url = f"{host}dashboard?id={owner}_{project}"
        if pr_number > 0:
            sonar_url = f"{sonar_url}&pullRequest={pr_number}"
        rows.append(
            {
                "project": project,
                "status": status,
                "status_emoji": status_emoji,
                "outcome": outcome,
                "url": sonar_url,
                "has_issues": not passed,
            }
        )
    rows.sort(key=lambda r: (not r["has_issues"], r["project"]))

    header = "## ✅ SonarQube Quality Gate - All Passed" if all_passed else "## ❌ SonarQube Quality Gate - Issues Found"
    lines = [
        header,
        "",
        "| Project | Quality Gate Status | Analysis |",
        "|---------|---------------------|----------|",
    ]
    for row in rows:
        status_text = "Passed" if row["status"] == "passed" else f"Failed ({row['outcome']})"
        lines.append(
            f"| `{row['project']}` | {row['status_emoji']} {status_text} | "
            f"[See analysis details on SonarQube]({row['url']}) |"
        )
    lines += [
        "",
        "---",
        "*Quality gate checks are run for each modified project. Click the SonarQube links above for detailed analysis.*",
    ]
    return all_passed, rows, "\n".join(lines)


def _build_unit_report(
    projects: list[str],
    by_project: dict[str, dict[str, Any]],
) -> tuple[bool, list[dict[str, Any]], list[str], list[str], str]:
    all_passed = True
    rows: list[dict[str, Any]] = []
    failing_projects: list[str] = []
    missing_projects: list[str] = []

    for project in projects:
        payload = by_project.get(project, {})
        status = str(payload.get("tests_status", "missing"))
        is_issue = status not in {"passed", "skipped"}
        if is_issue:
            all_passed = False
            failing_projects.append(project)
        if status == "missing":
            missing_projects.append(project)
        rows.append(
            {
                "project": project,
                "status": status,
                "junit_exists": payload.get("junit_exists") is True,
                "coverage_exists": payload.get("coverage_exists") is True,
                "test_outcome": str(payload.get("test_outcome", "missing")),
                "has_issues": is_issue,
            }
        )

    rows.sort(key=lambda r: (not r["has_issues"], r["project"]))

    header = "## ✅ Unit Tests - All Passed" if all_passed else "## ❌ Unit Tests - Issues Found"
    lines = [
        header,
        "",
        f"- Failing projects: {len(failing_projects)}",
        f"- Missing payloads: {len(missing_projects)}",
        "",
        "| Project | Test Status | Step Outcome | JUnit | Coverage |",
        "|---------|-------------|--------------|-------|----------|",
    ]
    for row in rows:
        if row["status"] == "passed":
            status_text = "✅ Passed"
        elif row["status"] == "skipped":
            status_text = "⏭️ Skipped"
        elif row["status"] == "missing":
            status_text = "⚠️ Missing Result"
        else:
            status_text = "❌ Failed"
        lines.append(
            f"| `{row['project']}` | {status_text} | {row['test_outcome']} | "
            f"{'Yes' if row['junit_exists'] else 'No'} | {'Yes' if row['coverage_exists'] else 'No'} |"
        )
    return all_passed, rows, failing_projects, missing_projects, "\n".join(lines)


def main() -> int:
    check_type = os.getenv("CHECK_TYPE", "").strip().lower()
    if check_type not in {"sonarqube", "unit-tests"}:
        print(f"Unsupported CHECK_TYPE: {check_type}", file=sys.stderr)
        return 2

    projects_json_raw = os.getenv("PROJECTS_JSON", "[]")
    results_dir = Path(os.getenv("RESULTS_DIR", "ci-plugin-results"))
    github_token = os.getenv("GITHUB_TOKEN", "").strip()
    sonar_host_url = os.getenv("SONARQUBE_HOST_URL", "https://sonarq.solace.com")
    comment_on_pr = _to_bool(os.getenv("COMMENT_ON_PR"), default=False)
    fail_on_issues = _to_bool(os.getenv("FAIL_ON_ISSUES"), default=True)
    update_check_details = _to_bool(os.getenv("UPDATE_CHECK_DETAILS"), default=True)
    check_name_input = os.getenv("CHECK_NAME", "").strip()
    marker_input = os.getenv("COMMENT_MARKER", "").strip()

    repository = os.getenv("GITHUB_REPOSITORY", "")
    if "/" not in repository:
        print(f"Invalid GITHUB_REPOSITORY: {repository}", file=sys.stderr)
        return 2
    owner, repo = repository.split("/", 1)
    run_id = os.getenv("GITHUB_RUN_ID", "")
    head_sha = os.getenv("GITHUB_SHA", "")

    event = _read_json(Path(os.getenv("GITHUB_EVENT_PATH", "")), {})
    pr_number = _normalize_pr_number(event)
    if pr_number <= 0:
        head_ref = str(event.get("pull_request", {}).get("head", {}).get("ref") or os.getenv("GITHUB_HEAD_REF", ""))
        pr_number = _resolve_pr_number_by_head(owner, repo, github_token, head_ref)
    event_head_sha = str(event.get("pull_request", {}).get("head", {}).get("sha") or "")
    if event_head_sha:
        # For pull_request workflows, use PR head SHA (not merge SHA) so check runs appear on the PR.
        head_sha = event_head_sha

    try:
        raw_projects = json.loads(projects_json_raw)
    except Exception:
        raw_projects = []
    projects = _normalize_projects(raw_projects)
    by_project = _collect_result_payloads(results_dir)
    print(f"Loaded {len(by_project)} project payload(s) from {results_dir}")

    if check_type == "sonarqube":
        check_name = check_name_input or "SonarQube Quality Gate"
        comment_marker = marker_input or "SonarQube Quality Gate"
        all_passed, rows, report_markdown = _build_sonar_report(
            projects=projects,
            by_project=by_project,
            owner=owner,
            pr_number=pr_number,
            sonar_host_url=sonar_host_url,
        )
        failing_projects: list[str] = []
        missing_projects: list[str] = []
        title = "SonarQube Quality Gate Passed" if all_passed else "SonarQube Quality Gate Failed"
        issue_count = sum(1 for row in rows if row.get("has_issues"))
        check_output_summary = (
            f"All {len(rows)} project(s) passed SonarQube quality gate."
            if all_passed
            else f"{issue_count} of {len(rows)} project(s) have SonarQube quality-gate issues."
        )
    else:
        check_name = check_name_input or "Unit Tests"
        comment_marker = marker_input or "Unit Tests - Issues Found"
        all_passed, rows, failing_projects, missing_projects, report_markdown = _build_unit_report(
            projects=projects,
            by_project=by_project,
        )
        title = "Unit Tests Passed" if all_passed else "Unit Tests Failed"
        check_output_summary = (
            f"All {len(rows)} project(s) passed unit tests."
            if all_passed
            else f"{len(failing_projects)} of {len(rows)} project(s) have unit-test issues."
        )

    _append_summary(report_markdown)

    comment_update_error: str | None = None
    if comment_on_pr:
        if pr_number <= 0:
            comment_update_error = (
                f"comment_on_pr=true for {check_name}, but PR number could not be resolved from event payload."
            )
        elif not github_token:
            comment_update_error = (
                f"comment_on_pr=true for {check_name}, but no github_token was provided."
            )
        else:
            try:
                _upsert_pr_comment(
                    owner=owner,
                    repo=repo,
                    token=github_token,
                    pr_number=pr_number,
                    marker=comment_marker,
                    body=report_markdown,
                )
            except Exception as err:
                comment_update_error = str(err)

    check_update_error: str | None = None
    if update_check_details:
        if not github_token:
            check_update_error = (
                f"update_check_details=true for {check_name}, but no github_token was provided."
            )
        elif not head_sha:
            check_update_error = (
                f"update_check_details=true for {check_name}, but no head SHA was available."
            )
        else:
            try:
                created_check_run = False
                check_run_id = _create_check_run(
                    owner=owner,
                    repo=repo,
                    token=github_token,
                    head_sha=head_sha,
                    check_name=check_name,
                    initial_summary=f"Generating {check_name} report...",
                )
                created_check_run = check_run_id is not None
                if not check_run_id:
                    check_run_id = _resolve_check_run_id(
                        owner=owner,
                        repo=repo,
                        token=github_token,
                        run_id=run_id,
                        head_sha=head_sha,
                        check_name=check_name,
                    )
                if not check_run_id:
                    raise RuntimeError(f"unable to create or resolve check run '{check_name}'")

                check_url = f"https://api.github.com/repos/{owner}/{repo}/check-runs/{check_run_id}"
                payload: dict[str, Any] = {
                    "output": {
                        "title": title,
                        "summary": check_output_summary,
                        "text": report_markdown,
                    }
                }
                if created_check_run:
                    payload.update(
                        {
                            "status": "completed",
                            "conclusion": "success" if all_passed else "failure",
                            "completed_at": _utc_now_iso(),
                        }
                    )
                _github_api("PATCH", check_url, github_token, payload)
                if created_check_run:
                    print(f"Created and completed dedicated check run {check_run_id} for {check_name}")
                else:
                    print(f"Updated existing check run {check_run_id} for {check_name}")
            except Exception as err:
                check_update_error = str(err)

    _write_output("all_passed", "true" if all_passed else "false")
    _write_output("project_results", json.dumps(rows))
    _write_output("failing_projects", json.dumps(failing_projects))
    _write_output("missing_projects", json.dumps(missing_projects))
    # Backward-compat outputs
    _write_output("plugin_results", json.dumps(rows))
    _write_output("failing_plugins", json.dumps(failing_projects))
    _write_output("missing_plugins", json.dumps(missing_projects))
    _write_output("report_markdown", report_markdown)

    if comment_update_error:
        print(f"Error: failed to publish PR comment for {check_name}: {comment_update_error}")
        return 2

    if check_update_error:
        print(f"Error: failed to publish check-run for {check_name}: {check_update_error}")
        return 2

    if fail_on_issues and not all_passed:
        print(f"{check_name} found issues in one or more projects.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
