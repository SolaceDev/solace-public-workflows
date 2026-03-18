#!/usr/bin/env python3
"""Aggregate project CI payloads and publish a unified status report."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def _bootstrap_common_module() -> None:
    script_path = Path(__file__).resolve()
    for parent in script_path.parents:
        candidate = parent / "common" / "github_reporting.py"
        if candidate.exists():
            sys.path.insert(0, str(candidate.parent))
            return


_bootstrap_common_module()

from ci_payload import read_json_file, safe_int, to_bool  # type: ignore  # noqa: E402
from github_reporting import (  # type: ignore  # noqa: E402
    append_summary as append_job_summary,
    create_check_run,
    github_api,
    normalize_pr_number,
    resolve_check_run_id,
    resolve_pr_number_by_head,
    upsert_pr_comment,
    utc_now_iso,
    write_output,
)

SUPPORTED_CHECK_TYPES = {"sonarqube", "unit-tests"}
UNKNOWN_TEST_NAME = "<unknown-test>"
MAX_FAILED_TESTS_PER_PROJECT = 20
MAX_FAILURE_MESSAGE_LENGTH = 2000


def _normalize_projects(raw_projects: Any) -> list[str]:
    projects: list[str] = []
    if not isinstance(raw_projects, list):
        return projects
    for item in raw_projects:
        if isinstance(item, str):
            project = item.strip()
        elif isinstance(item, dict):
            project = str(item.get("project_directory") or item.get("plugin_directory") or "").strip()
        else:
            project = ""
        if project:
            projects.append(project)
    return projects


def _parse_projects(projects_json_raw: str) -> list[str]:
    try:
        parsed = json.loads(projects_json_raw or "[]")
    except Exception:
        parsed = []
    return _normalize_projects(parsed)


def _collect_result_payloads(results_dir: Path) -> dict[str, dict[str, Any]]:
    by_project: dict[str, dict[str, Any]] = {}
    if not results_dir.exists():
        return by_project
    for file_path in sorted(results_dir.rglob("*.json")):
        payload = read_json_file(file_path, {})
        if not isinstance(payload, dict):
            continue
        project = str(payload.get("project") or payload.get("plugin") or "").strip()
        if project:
            by_project[project] = payload
    return by_project


def _resolve_repository() -> tuple[str, str]:
    repository = os.getenv("GITHUB_REPOSITORY", "")
    if "/" not in repository:
        raise ValueError(f"Invalid GITHUB_REPOSITORY: {repository}")
    return repository.split("/", 1)


def _load_event_payload() -> dict[str, Any]:
    event_path = Path(os.getenv("GITHUB_EVENT_PATH", ""))
    payload = read_json_file(event_path, {})
    return payload if isinstance(payload, dict) else {}


def _resolve_pr_and_head_sha(
    *,
    owner: str,
    repo: str,
    event: dict[str, Any],
    token: str,
    explicit_pr_number: str,
) -> tuple[int, str]:
    pr_number = normalize_pr_number(event, explicit_value=explicit_pr_number)
    if pr_number <= 0:
        head_ref = str(event.get("pull_request", {}).get("head", {}).get("ref") or os.getenv("GITHUB_HEAD_REF", ""))
        pr_number = resolve_pr_number_by_head(owner, repo, token, head_ref)
    head_sha = str(event.get("pull_request", {}).get("head", {}).get("sha") or os.getenv("GITHUB_SHA", ""))
    return pr_number, head_sha


def _build_sonar_rows(
    *,
    projects: list[str],
    by_project: dict[str, dict[str, Any]],
    owner: str,
    pr_number: int,
    sonar_host_url: str,
) -> tuple[bool, list[dict[str, Any]]]:
    host = sonar_host_url.rstrip("/") + "/"
    rows: list[dict[str, Any]] = []
    for project in projects:
        payload = by_project.get(project, {})
        outcome = str(payload.get("sonar_outcome", "missing"))
        passed = outcome == "success"
        sonar_url = f"{host}dashboard?id={owner}_{project}"
        if pr_number > 0:
            sonar_url = f"{sonar_url}&pullRequest={pr_number}"
        rows.append(
            {
                "project": project,
                "status": "passed" if passed else "failed",
                "status_emoji": "✅" if passed else "❌",
                "outcome": outcome,
                "url": sonar_url,
                "has_issues": not passed,
            }
        )
    rows.sort(key=lambda row: (not row["has_issues"], row["project"]))
    return all(not row["has_issues"] for row in rows), rows


def _collapse_whitespace(value: str) -> str:
    return " ".join(value.split())


def _truncate(value: str, limit: int = MAX_FAILURE_MESSAGE_LENGTH) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}..."


def _normalize_failure_message(value: Any) -> str:
    message = str(value or "").replace("```", "'''").strip()
    if not message:
        return "No failure message available."
    return _truncate(message)


def _extract_ctrf_results(unit_test_report: Any) -> dict[str, Any]:
    if not isinstance(unit_test_report, dict):
        return {}
    nested_results = unit_test_report.get("results")
    if isinstance(nested_results, dict):
        return nested_results
    if isinstance(unit_test_report.get("summary"), dict) and isinstance(unit_test_report.get("tests"), list):
        return unit_test_report
    return {}


def _extract_ctrf_summary(unit_test_report: Any) -> dict[str, int]:
    ctrf_results = _extract_ctrf_results(unit_test_report)
    summary = ctrf_results.get("summary", {})
    if not isinstance(summary, dict):
        return {}
    tests = safe_int(summary.get("tests"), default=0)
    failed = safe_int(summary.get("failed"), default=0)
    skipped = safe_int(summary.get("skipped"), default=0)
    passed = safe_int(summary.get("passed"), default=max(tests - failed - skipped, 0))
    return {
        "tests": tests,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
    }


def _extract_ctrf_failed_tests(unit_test_report: Any) -> list[dict[str, str]]:
    ctrf_results = _extract_ctrf_results(unit_test_report)
    tests = ctrf_results.get("tests", [])
    if not isinstance(tests, list):
        return []

    failed_tests: list[dict[str, str]] = []
    for test in tests:
        if not isinstance(test, dict):
            continue
        status = str(test.get("status", "")).strip().lower()
        if status in {"passed", "skipped"}:
            continue
        name = str(test.get("name") or test.get("file_path") or UNKNOWN_TEST_NAME).strip()
        message = _normalize_failure_message(test.get("message") or test.get("trace") or test.get("raw_status"))
        failed_tests.append({"name": name, "message": message})
        if len(failed_tests) >= MAX_FAILED_TESTS_PER_PROJECT:
            break
    return failed_tests


def _extract_junit_report(payload: dict[str, Any]) -> dict[str, Any]:
    report = payload.get("unit_test_junit_report")
    return report if isinstance(report, dict) else {}


def _extract_junit_summary(payload: dict[str, Any]) -> dict[str, int]:
    junit_report = _extract_junit_report(payload)
    summary = junit_report.get("summary", {})
    if not isinstance(summary, dict):
        return {}
    tests = safe_int(summary.get("tests"), default=0)
    failed = safe_int(
        summary.get("failed"),
        default=safe_int(summary.get("failures"), default=0) + safe_int(summary.get("errors"), default=0),
    )
    skipped = safe_int(summary.get("skipped"), default=0)
    passed = safe_int(summary.get("passed"), default=max(tests - failed - skipped, 0))
    return {
        "tests": tests,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
    }


def _extract_junit_failed_tests(payload: dict[str, Any]) -> list[dict[str, str]]:
    junit_report = _extract_junit_report(payload)
    failed_tests_raw = junit_report.get("failed_tests", [])
    if not isinstance(failed_tests_raw, list):
        return []

    failed_tests: list[dict[str, str]] = []
    for entry in failed_tests_raw:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or UNKNOWN_TEST_NAME).strip()
        message = _normalize_failure_message(entry.get("message"))
        failed_tests.append({"name": name, "message": message})
        if len(failed_tests) >= MAX_FAILED_TESTS_PER_PROJECT:
            break
    return failed_tests


def _build_unit_status_label(status: str, summary: dict[str, int]) -> str:
    failed = summary.get("failed", 0)
    passed = summary.get("passed", 0)
    skipped = summary.get("skipped", 0)

    if failed > 0:
        return f"❌ {failed} failed"
    if passed > 0:
        return f"✅ {passed} passed"
    if skipped > 0:
        return f"⏭️ {skipped} skipped"
    if status == "passed":
        return "✅ Passed"
    if status == "skipped":
        return "⏭️ Skipped"
    if status == "missing":
        return "⚠️ Missing Result"
    return "❌ Failed"


def _build_unit_rows(
    *,
    projects: list[str],
    by_project: dict[str, dict[str, Any]],
) -> tuple[bool, list[dict[str, Any]], list[str], list[str]]:
    rows: list[dict[str, Any]] = []
    failing_projects: list[str] = []
    missing_projects: list[str] = []

    for project in projects:
        payload = by_project.get(project, {})
        status = str(payload.get("tests_status", "missing")).strip().lower()

        ctrf_summary = _extract_ctrf_summary(payload.get("unit_test_report"))
        junit_summary = _extract_junit_summary(payload)
        summary = ctrf_summary if ctrf_summary.get("tests", 0) > 0 else junit_summary

        failed_tests = _extract_ctrf_failed_tests(payload.get("unit_test_report"))
        if not failed_tests:
            failed_tests = _extract_junit_failed_tests(payload)

        failed_count = summary.get("failed", 0)
        if ctrf_summary.get("tests", 0) > 0:
            summary_source = "ctrf"
        elif junit_summary.get("tests", 0) > 0:
            summary_source = "junit"
        else:
            summary_source = "none"

        has_issues = status not in {"passed", "skipped"} or failed_count > 0
        if has_issues:
            failing_projects.append(project)
        if status == "missing":
            missing_projects.append(project)

        rows.append(
            {
                "project": project,
                "status": status,
                "status_label": _build_unit_status_label(status, summary),
                "tests_summary": summary,
                "test_outcome": str(payload.get("test_outcome", "missing")),
                "has_issues": has_issues,
                "failed_tests": failed_tests,
                "summary_source": summary_source,
            }
        )

    rows.sort(key=lambda row: (not row["has_issues"], row["project"]))
    return all(not row["has_issues"] for row in rows), rows, failing_projects, missing_projects


def _render_sonar_report(*, rows: list[dict[str, Any]], all_passed: bool) -> str:
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
    lines.extend(
        [
            "",
            "---",
            "*Quality gate checks run for each changed project.*",
        ]
    )
    return "\n".join(lines)


def _render_unit_report(
    *,
    rows: list[dict[str, Any]],
    all_passed: bool,
    failing_projects: list[str],
    missing_projects: list[str],
) -> str:
    header = "## ✅ Unit Tests - All Passed" if all_passed else "## ❌ Unit Tests - Issues Found"
    lines = [
        header,
        "",
        f"- Failing projects: {len(failing_projects)}",
        f"- Missing payloads: {len(missing_projects)}",
        "",
        "### Test Results",
        "",
        "| Project | Test Status |",
        "|---------|-------------|",
    ]
    for row in rows:
        lines.append(f"| `{row['project']}` | {row['status_label']} |")

    detailed_failures = [row for row in rows if row.get("has_issues") and row.get("failed_tests")]
    if detailed_failures:
        lines.extend(["", "### Failed Tests", ""])
        for row in detailed_failures:
            lines.append(f"#### `{row['project']}`")
            lines.append("```text")
            for failed_test in row["failed_tests"]:
                test_name = str(failed_test.get("name", UNKNOWN_TEST_NAME)).strip()
                message = _normalize_failure_message(failed_test.get("message"))
                lines.append(f"- {test_name}")
                for message_line in message.splitlines():
                    lines.append(f"  {message_line}")
            lines.append("```")
            lines.append("")
    elif failing_projects:
        lines.extend(
            [
                "",
                "### Failed Tests",
                "",
                "Detailed failed-test output is not available for the failing projects (no CTRF/JUnit details found).",
            ]
        )

    return "\n".join(lines)


def _default_check_metadata(check_type: str) -> tuple[str, str]:
    if check_type == "sonarqube":
        return "SonarQube Quality Gate", "SonarQube Quality Gate"
    return "Unit Tests", "Unit Tests - Issues Found"


def _build_check_summary(
    *,
    check_type: str,
    all_passed: bool,
    rows: list[dict[str, Any]],
    failing_projects: list[str],
) -> tuple[str, str]:
    if check_type == "sonarqube":
        title = "SonarQube Quality Gate Passed" if all_passed else "SonarQube Quality Gate Failed"
        failing_count = sum(1 for row in rows if row.get("has_issues"))
        summary = (
            f"All {len(rows)} project(s) passed SonarQube quality gate."
            if all_passed
            else f"{failing_count} of {len(rows)} project(s) have SonarQube quality-gate issues."
        )
        return title, summary

    title = "Unit Tests Passed" if all_passed else "Unit Tests Failed"
    summary = (
        f"All {len(rows)} project(s) passed unit tests."
        if all_passed
        else f"{len(failing_projects)} of {len(rows)} project(s) have unit-test issues."
    )
    return title, summary


def _update_pr_comment(
    *,
    enabled: bool,
    owner: str,
    repo: str,
    token: str,
    pr_number: int,
    marker: str,
    body: str,
    check_name: str,
) -> str | None:
    if not enabled:
        return None
    if pr_number <= 0:
        return f"comment_on_pr=true for {check_name}, but PR number could not be resolved."
    if not token:
        return f"comment_on_pr=true for {check_name}, but no github_token was provided."
    try:
        upsert_pr_comment(owner=owner, repo=repo, token=token, pr_number=pr_number, marker=marker, body=body)
        return None
    except Exception as err:
        return str(err)


def _update_check_details(
    *,
    enabled: bool,
    owner: str,
    repo: str,
    token: str,
    run_id: str,
    head_sha: str,
    check_name: str,
    title: str,
    summary: str,
    report_markdown: str,
    all_passed: bool,
) -> str | None:
    if not enabled:
        return None
    if not token:
        return f"update_check_details=true for {check_name}, but no github_token was provided."
    if not head_sha:
        return f"update_check_details=true for {check_name}, but no head SHA was available."
    try:
        created_check = False
        check_run_id = create_check_run(
            owner=owner,
            repo=repo,
            token=token,
            head_sha=head_sha,
            check_name=check_name,
            initial_summary=f"Generating {check_name} report...",
        )
        created_check = check_run_id is not None
        if not check_run_id:
            check_run_id = resolve_check_run_id(
                owner=owner,
                repo=repo,
                token=token,
                run_id=run_id,
                head_sha=head_sha,
                check_name=check_name,
            )
        if not check_run_id:
            raise RuntimeError(f"unable to create or resolve check run '{check_name}'")

        payload: dict[str, Any] = {
            "output": {
                "title": title,
                "summary": summary,
                "text": report_markdown,
            }
        }
        if created_check:
            payload.update(
                {
                    "status": "completed",
                    "conclusion": "success" if all_passed else "failure",
                    "completed_at": utc_now_iso(),
                }
            )
        check_url = f"https://api.github.com/repos/{owner}/{repo}/check-runs/{check_run_id}"
        github_api("PATCH", check_url, token, payload)
        return None
    except Exception as err:
        return str(err)


def main() -> int:
    check_type = os.getenv("CHECK_TYPE", "").strip().lower()
    if check_type not in SUPPORTED_CHECK_TYPES:
        print(f"Unsupported CHECK_TYPE: {check_type}", file=sys.stderr)
        return 2

    try:
        owner, repo = _resolve_repository()
    except ValueError as err:
        print(str(err), file=sys.stderr)
        return 2

    github_token = os.getenv("GITHUB_TOKEN", "").strip()
    sonar_host_url = os.getenv("SONARQUBE_HOST_URL", "https://sonarq.solace.com")
    projects = _parse_projects(os.getenv("PROJECTS_JSON", "[]"))
    results_dir = Path(os.getenv("RESULTS_DIR", "ci-plugin-results"))
    payloads_by_project = _collect_result_payloads(results_dir)
    print(f"Loaded {len(payloads_by_project)} project payload(s) from {results_dir}")

    event = _load_event_payload()
    pr_number, head_sha = _resolve_pr_and_head_sha(
        owner=owner,
        repo=repo,
        event=event,
        token=github_token,
        explicit_pr_number=os.getenv("PR_NUMBER", ""),
    )
    run_id = os.getenv("GITHUB_RUN_ID", "")

    all_passed = True
    rows: list[dict[str, Any]] = []
    failing_projects: list[str] = []
    missing_projects: list[str] = []

    if check_type == "sonarqube":
        all_passed, rows = _build_sonar_rows(
            projects=projects,
            by_project=payloads_by_project,
            owner=owner,
            pr_number=pr_number,
            sonar_host_url=sonar_host_url,
        )
        report_markdown = _render_sonar_report(rows=rows, all_passed=all_passed)
    else:
        all_passed, rows, failing_projects, missing_projects = _build_unit_rows(
            projects=projects,
            by_project=payloads_by_project,
        )
        report_markdown = _render_unit_report(
            rows=rows,
            all_passed=all_passed,
            failing_projects=failing_projects,
            missing_projects=missing_projects,
        )

    append_job_summary(report_markdown)
    default_check_name, default_comment_marker = _default_check_metadata(check_type)
    check_name = os.getenv("CHECK_NAME", "").strip() or default_check_name
    comment_marker = os.getenv("COMMENT_MARKER", "").strip() or default_comment_marker
    title, summary = _build_check_summary(
        check_type=check_type,
        all_passed=all_passed,
        rows=rows,
        failing_projects=failing_projects,
    )

    comment_error = _update_pr_comment(
        enabled=to_bool(os.getenv("COMMENT_ON_PR"), default=False),
        owner=owner,
        repo=repo,
        token=github_token,
        pr_number=pr_number,
        marker=comment_marker,
        body=report_markdown,
        check_name=check_name,
    )
    check_error = _update_check_details(
        enabled=to_bool(os.getenv("UPDATE_CHECK_DETAILS"), default=True),
        owner=owner,
        repo=repo,
        token=github_token,
        run_id=run_id,
        head_sha=head_sha,
        check_name=check_name,
        title=title,
        summary=summary,
        report_markdown=report_markdown,
        all_passed=all_passed,
    )

    write_output("all_passed", "true" if all_passed else "false")
    write_output("project_results", json.dumps(rows))
    write_output("failing_projects", json.dumps(failing_projects))
    write_output("missing_projects", json.dumps(missing_projects))
    write_output("report_markdown", report_markdown)

    if comment_error:
        print(f"Error: failed to publish PR comment for {check_name}: {comment_error}")
        return 2
    if check_error:
        print(f"Error: failed to publish check-run for {check_name}: {check_error}")
        return 2
    if to_bool(os.getenv("FAIL_ON_ISSUES"), default=True) and not all_passed:
        print(f"{check_name} found issues in one or more projects.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
