#!/usr/bin/env python3
"""
Aggregate plugin check payloads and publish a formatted PR report.

Supported check types:
- sonarqube: aggregate `sonar_outcome` from ci-plugin-result JSON files
- unit-tests: aggregate `tests_status` from ci-plugin-result JSON files
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _github_api(
    method: str,
    url: str,
    token: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any] | list[Any]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "solace-public-workflows/pr-plugin-check-report",
    }
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, method=method.upper(), headers=headers, data=body)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            if not raw:
                return {}
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {method} {url} failed: {err.code} {detail}") from err


def _write_output(name: str, value: str) -> None:
    output_path = os.getenv("GITHUB_OUTPUT")
    if not output_path:
        return
    path = Path(output_path)
    with path.open("a", encoding="utf-8") as handle:
        if "\n" in value:
            marker = f"EOF_{name}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
            handle.write(f"{name}<<{marker}\n")
            handle.write(value)
            if not value.endswith("\n"):
                handle.write("\n")
            handle.write(f"{marker}\n")
        else:
            handle.write(f"{name}={value}\n")


def _append_summary(markdown: str) -> None:
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    with Path(summary_path).open("a", encoding="utf-8") as handle:
        handle.write(markdown)
        if not markdown.endswith("\n"):
            handle.write("\n")


def _collect_result_payloads(result_dir: Path) -> dict[str, dict[str, Any]]:
    by_plugin: dict[str, dict[str, Any]] = {}
    if not result_dir.exists():
        return by_plugin
    for file_path in result_dir.rglob("*.json"):
        payload = _read_json(file_path, {})
        plugin = payload.get("plugin")
        if isinstance(plugin, str) and plugin.strip():
            by_plugin[plugin.strip()] = payload
    return by_plugin


def _normalize_plugins(raw_plugins: Any) -> list[str]:
    plugins: list[str] = []
    if not isinstance(raw_plugins, list):
        return plugins
    for item in raw_plugins:
        if isinstance(item, str):
            plugin = item.strip()
            if plugin:
                plugins.append(plugin)
        elif isinstance(item, dict):
            plugin = str(item.get("plugin_directory", "")).strip()
            if plugin:
                plugins.append(plugin)
    return plugins


def _normalize_pr_number(event: dict[str, Any]) -> int:
    candidates = [
        event.get("pull_request", {}).get("number"),
        event.get("number"),
        os.getenv("PR_NUMBER"),
    ]
    for raw in candidates:
        try:
            if raw is None:
                continue
            value = str(raw).strip()
            if value:
                return int(value)
        except Exception:
            continue
    return 0


def _resolve_check_run_id(
    owner: str,
    repo: str,
    token: str,
    run_id: str,
    head_sha: str,
    check_name: str,
) -> int | None:
    # Primary: derive from current workflow run jobs
    try:
        jobs_url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/jobs?per_page=100"
        jobs_resp = _github_api("GET", jobs_url, token)
        jobs = jobs_resp.get("jobs", []) if isinstance(jobs_resp, dict) else []
        target_name = check_name.lower()
        for job in jobs:
            job_name = str(job.get("name", "")).lower()
            if job_name == target_name or target_name in job_name or job_name in target_name:
                check_url = str(job.get("check_run_url", ""))
                match = re.search(r"/check-runs/(\d+)$", check_url)
                if match:
                    return int(match.group(1))
    except Exception:
        pass

    # Fallback: find check run by commit SHA
    try:
        checks_url = f"https://api.github.com/repos/{owner}/{repo}/commits/{head_sha}/check-runs?per_page=100"
        checks_resp = _github_api("GET", checks_url, token)
        runs = checks_resp.get("check_runs", []) if isinstance(checks_resp, dict) else []
        target_name = check_name.lower()

        def _score(run: dict[str, Any]) -> tuple[int, str]:
            started = str(run.get("started_at") or run.get("created_at") or "")
            name = str(run.get("name", "")).lower()
            score = 0
            if name == target_name:
                score += 3
            elif target_name in name or name in target_name:
                score += 1
            details = str(run.get("details_url", ""))
            if f"/actions/runs/{run_id}" in details:
                score += 2
            return (score, started)

        candidates = [r for r in runs if _score(r)[0] > 0]
        if not candidates:
            return None
        candidates.sort(key=_score, reverse=True)
        return int(candidates[0]["id"])
    except Exception:
        return None


def _create_check_run(
    owner: str,
    repo: str,
    token: str,
    head_sha: str,
    check_name: str,
    initial_summary: str,
) -> int | None:
    if not token or not head_sha:
        return None
    try:
        url = f"https://api.github.com/repos/{owner}/{repo}/check-runs"
        payload = {
            "name": check_name,
            "head_sha": head_sha,
            "status": "in_progress",
            "started_at": _utc_now_iso(),
            "output": {
                "title": check_name,
                "summary": initial_summary,
            },
        }
        created = _github_api("POST", url, token, payload)
        return int(created.get("id"))
    except Exception as err:
        print(f"Warning: failed to create check-run {check_name}: {err}")
        return None


def _upsert_pr_comment(
    owner: str,
    repo: str,
    token: str,
    pr_number: int,
    marker: str,
    body: str,
) -> None:
    if pr_number <= 0:
        return
    list_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments?per_page=100"
    comments_resp = _github_api("GET", list_url, token)
    comments = comments_resp if isinstance(comments_resp, list) else []
    existing_id = None
    for comment in comments:
        comment_body = str(comment.get("body", ""))
        if marker in comment_body and comment.get("user", {}).get("type") == "Bot":
            existing_id = int(comment["id"])
            break

    if existing_id:
        patch_url = f"https://api.github.com/repos/{owner}/{repo}/issues/comments/{existing_id}"
        _github_api("PATCH", patch_url, token, {"body": body})
        return

    create_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
    _github_api("POST", create_url, token, {"body": body})


def _build_sonar_report(
    plugins: list[str],
    by_plugin: dict[str, dict[str, Any]],
    owner: str,
    pr_number: int,
    sonar_host_url: str,
) -> tuple[bool, list[dict[str, Any]], str]:
    host = sonar_host_url.rstrip("/") + "/"
    all_passed = True
    rows: list[dict[str, Any]] = []
    for plugin in plugins:
        payload = by_plugin.get(plugin, {})
        outcome = str(payload.get("sonar_outcome", "missing"))
        passed = outcome == "success"
        if not passed:
            all_passed = False
        status = "passed" if passed else "failed"
        status_emoji = "✅" if passed else "❌"
        sonar_url = f"{host}dashboard?id={owner}_{plugin}"
        if pr_number > 0:
            sonar_url = f"{sonar_url}&pullRequest={pr_number}"
        rows.append(
            {
                "plugin": plugin,
                "status": status,
                "status_emoji": status_emoji,
                "outcome": outcome,
                "url": sonar_url,
                "has_issues": not passed,
            }
        )
    rows.sort(key=lambda r: (not r["has_issues"], r["plugin"]))

    header = "## ✅ SonarQube Quality Gate - All Passed" if all_passed else "## ❌ SonarQube Quality Gate - Issues Found"
    lines = [
        header,
        "",
        "| Plugin | Quality Gate Status | Analysis |",
        "|--------|---------------------|----------|",
    ]
    for row in rows:
        status_text = "Passed" if row["status"] == "passed" else f"Failed ({row['outcome']})"
        lines.append(
            f"| `{row['plugin']}` | {row['status_emoji']} {status_text} | "
            f"[See analysis details on SonarQube]({row['url']}) |"
        )
    lines += [
        "",
        "---",
        "*Quality gate checks are run for each modified plugin. Click the SonarQube links above for detailed analysis.*",
    ]
    return all_passed, rows, "\n".join(lines)


def _build_unit_report(
    plugins: list[str],
    by_plugin: dict[str, dict[str, Any]],
) -> tuple[bool, list[dict[str, Any]], list[str], list[str], str]:
    all_passed = True
    rows: list[dict[str, Any]] = []
    failing_plugins: list[str] = []
    missing_plugins: list[str] = []

    for plugin in plugins:
        payload = by_plugin.get(plugin, {})
        status = str(payload.get("tests_status", "missing"))
        is_issue = status not in {"passed", "skipped"}
        if is_issue:
            all_passed = False
            failing_plugins.append(plugin)
        if status == "missing":
            missing_plugins.append(plugin)
        rows.append(
            {
                "plugin": plugin,
                "status": status,
                "junit_exists": payload.get("junit_exists") is True,
                "coverage_exists": payload.get("coverage_exists") is True,
                "test_outcome": str(payload.get("test_outcome", "missing")),
                "has_issues": is_issue,
            }
        )

    rows.sort(key=lambda r: (not r["has_issues"], r["plugin"]))

    header = "## ✅ Unit Tests - All Passed" if all_passed else "## ❌ Unit Tests - Issues Found"
    lines = [
        header,
        "",
        f"- Failing plugins: {len(failing_plugins)}",
        f"- Missing payloads: {len(missing_plugins)}",
        "",
        "| Plugin | Test Status | Step Outcome | JUnit | Coverage |",
        "|--------|-------------|--------------|-------|----------|",
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
            f"| `{row['plugin']}` | {status_text} | {row['test_outcome']} | "
            f"{'Yes' if row['junit_exists'] else 'No'} | {'Yes' if row['coverage_exists'] else 'No'} |"
        )
    return all_passed, rows, failing_plugins, missing_plugins, "\n".join(lines)


def main() -> int:
    check_type = os.getenv("CHECK_TYPE", "").strip().lower()
    if check_type not in {"sonarqube", "unit-tests"}:
        print(f"Unsupported CHECK_TYPE: {check_type}", file=sys.stderr)
        return 2

    plugins_json_raw = os.getenv("PLUGINS_JSON", "[]")
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
    event_head_sha = str(event.get("pull_request", {}).get("head", {}).get("sha") or "")
    if event_head_sha:
        # For pull_request workflows, use PR head SHA (not merge SHA) so check runs appear on the PR.
        head_sha = event_head_sha

    try:
        raw_plugins = json.loads(plugins_json_raw)
    except Exception:
        raw_plugins = []
    plugins = _normalize_plugins(raw_plugins)
    by_plugin = _collect_result_payloads(results_dir)
    print(f"Loaded {len(by_plugin)} plugin payload(s) from {results_dir}")

    if check_type == "sonarqube":
        check_name = check_name_input or "SonarQube Quality Gate"
        comment_marker = marker_input or "SonarQube Quality Gate"
        all_passed, rows, report_markdown = _build_sonar_report(
            plugins=plugins,
            by_plugin=by_plugin,
            owner=owner,
            pr_number=pr_number,
            sonar_host_url=sonar_host_url,
        )
        failing_plugins: list[str] = []
        missing_plugins: list[str] = []
        title = "SonarQube Quality Gate Passed" if all_passed else "SonarQube Quality Gate Failed"
        issue_count = sum(1 for row in rows if row.get("has_issues"))
        check_output_summary = (
            f"All {len(rows)} plugin(s) passed SonarQube quality gate."
            if all_passed
            else f"{issue_count} of {len(rows)} plugin(s) have SonarQube quality-gate issues."
        )
    else:
        check_name = check_name_input or "Unit Tests"
        comment_marker = marker_input or "Unit Tests - Issues Found"
        all_passed, rows, failing_plugins, missing_plugins, report_markdown = _build_unit_report(
            plugins=plugins,
            by_plugin=by_plugin,
        )
        title = "Unit Tests Passed" if all_passed else "Unit Tests Failed"
        check_output_summary = (
            f"All {len(rows)} plugin(s) passed unit tests."
            if all_passed
            else f"{len(failing_plugins)} of {len(rows)} plugin(s) have unit-test issues."
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
    _write_output("plugin_results", json.dumps(rows))
    _write_output("failing_plugins", json.dumps(failing_plugins))
    _write_output("missing_plugins", json.dumps(missing_plugins))
    _write_output("report_markdown", report_markdown)

    if comment_update_error:
        print(f"Error: failed to publish PR comment for {check_name}: {comment_update_error}")
        return 2

    if check_update_error:
        print(f"Error: failed to publish check-run for {check_name}: {check_update_error}")
        return 2

    if fail_on_issues and not all_passed:
        print(f"{check_name} found issues in one or more plugins.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
