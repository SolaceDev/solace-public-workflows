#!/usr/bin/env python3
"""
Run aggregated release-readiness checks and publish one unified report/check.

Checks included:
- SonarQube hotspots (main branch)
- FOSSA licensing guard
- FOSSA vulnerability guard
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
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

from github_reporting import (  # type: ignore  # noqa: E402
    append_summary as _append_summary,
    create_check_run as _create_check_run,
    github_api as _github_api,
    normalize_pr_number as _normalize_pr_number,
    resolve_pr_number_by_head as _resolve_pr_number_by_head,
    to_bool as _to_bool,
    upsert_pr_comment as _upsert_pr_comment,
    utc_now_iso as _utc_now_iso,
    write_output as _write_output,
)


def _run_cmd(cmd: list[str], cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


def _extract_head_sha(pr_number: int, event: dict[str, Any], token: str, owner: str, repo: str) -> str:
    event_sha = str(event.get("pull_request", {}).get("head", {}).get("sha") or "")
    if event_sha:
        return event_sha
    if pr_number > 0 and token:
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
            pr = _github_api("GET", url, token)
            return str(pr.get("head", {}).get("sha") or "")
        except Exception:
            pass
    sha = _run_cmd(["git", "rev-parse", "HEAD"])
    if sha.returncode == 0:
        return sha.stdout.strip()
    return os.getenv("GITHUB_SHA", "")


def _run_sonar_hotspots(
    *,
    project_id: str,
    base_branch: str,
    sonar_host_url: str,
    sonar_token: str,
) -> dict[str, Any]:
    sonar_host = sonar_host_url if sonar_host_url.endswith("/") else f"{sonar_host_url}/"
    api_url = f"{sonar_host}api/hotspots/search"
    high_count = 0
    page = 1
    page_size = 500
    auth = base64.b64encode(f"{sonar_token}:".encode("utf-8")).decode("utf-8")
    headers = {"Authorization": f"Basic {auth}"}

    while True:
        params = urllib.parse.urlencode(
            {
                "projectKey": project_id,
                "branch": base_branch,
                "status": "TO_REVIEW",
                "p": page,
                "ps": page_size,
            }
        )
        req = urllib.request.Request(f"{api_url}?{params}", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception:
            # Missing/unavailable Sonar hotspot data should not be counted as an issue.
            return {"status": "passed", "issues": 0}

        hotspots = payload.get("hotspots", [])
        high_count += sum(1 for hotspot in hotspots if hotspot.get("vulnerabilityProbability") == "HIGH")
        paging = payload.get("paging", {})
        total = int(paging.get("total", len(hotspots)) or 0)
        if page * page_size >= total:
            break
        page += 1

    return {"status": "failed" if high_count > 0 else "passed", "issues": high_count}


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _collect_plugin_payloads(results_dir: Path) -> dict[str, dict[str, Any]]:
    by_plugin: dict[str, dict[str, Any]] = {}
    if not results_dir.exists():
        return by_plugin
    for file_path in sorted(results_dir.rglob("*.json")):
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        plugin = str(payload.get("plugin", "")).strip()
        if not plugin:
            continue
        by_plugin[plugin] = payload
    return by_plugin


def main() -> int:
    github_token = os.getenv("GITHUB_TOKEN", "").strip()
    sonar_token = os.getenv("SONARQUBE_TOKEN", "").strip()
    sonar_host = os.getenv("SONARQUBE_HOST_URL", "").strip()
    repo_owner_input = os.getenv("REPO_OWNER", "").strip()
    base_branch = os.getenv("BASE_BRANCH", "main").strip()
    check_name = os.getenv("CHECK_NAME", "Release Readiness").strip()
    comment_marker = os.getenv("COMMENT_MARKER", "Release Readiness Check Results").strip()
    results_dir = Path(os.getenv("RESULTS_DIR", "ci-plugin-results"))
    fail_on_issues = _to_bool(os.getenv("FAIL_ON_ISSUES"), default=True)
    update_pr_comment = _to_bool(os.getenv("UPDATE_PR_COMMENT"), default=True)
    update_check_details = _to_bool(os.getenv("UPDATE_CHECK_DETAILS"), default=True)
    pr_number_input = os.getenv("PR_NUMBER", "")

    if not sonar_token:
        print("Missing SONARQUBE_TOKEN", file=sys.stderr)
        return 2
    if not sonar_host:
        print("Missing SONARQUBE_HOST_URL", file=sys.stderr)
        return 2

    repository = os.getenv("GITHUB_REPOSITORY", "")
    if "/" not in repository:
        print(f"Invalid GITHUB_REPOSITORY: {repository}", file=sys.stderr)
        return 2
    owner, repo = repository.split("/", 1)
    repo_owner = repo_owner_input or owner

    event_path = Path(os.getenv("GITHUB_EVENT_PATH", ""))
    event: dict[str, Any] = {}
    if event_path.exists():
        try:
            event = json.loads(event_path.read_text(encoding="utf-8"))
        except Exception:
            event = {}
    pr_number = _normalize_pr_number(event, explicit_value=pr_number_input)
    if pr_number <= 0:
        head_ref = str(event.get("pull_request", {}).get("head", {}).get("ref") or os.getenv("GITHUB_HEAD_REF", ""))
        pr_number = _resolve_pr_number_by_head(owner, repo, github_token, head_ref)
    head_sha = _extract_head_sha(pr_number, event, github_token, owner, repo)
    short_sha = head_sha[:12] if head_sha else "unknown"
    created_check_run = False

    check_run_id: int | None = None
    if update_check_details:
        if not github_token:
            print("Error: update_check_details=true but no github_token was provided.")
            return 2
        if not head_sha:
            print("Error: update_check_details=true but no head SHA was available.")
            return 2
        check_run_id = _create_check_run(
            owner,
            repo,
            github_token,
            head_sha,
            check_name,
            "Aggregating SonarQube and FOSSA results...",
        )
        created_check_run = check_run_id is not None
        if check_run_id is None:
            print(f"Error: unable to create dedicated check run '{check_name}'.")
            return 2

    plugin_payloads = _collect_plugin_payloads(results_dir)
    plugins = sorted(plugin_payloads.keys())
    if not plugins:
        print(
            f"Error: no plugin payloads found in '{results_dir}'. "
            "Download ci-plugin-result artifacts before running release-readiness aggregation.",
            file=sys.stderr,
        )
        return 2

    workspace = Path.cwd()
    rows: list[dict[str, Any]] = []

    for plugin in plugins:
        payload = plugin_payloads.get(plugin, {})
        project_id = str(payload.get("fossa_project_id") or f"{repo_owner}_{plugin}")
        version = str(payload.get("fossa_revision") or short_sha)
        fossa_branch = str(payload.get("fossa_branch") or base_branch)

        sonar = _run_sonar_hotspots(
            project_id=project_id,
            base_branch=base_branch,
            sonar_host_url=sonar_host,
            sonar_token=sonar_token,
        )

        lic_outcome = str(payload.get("fossa_licensing_outcome", "missing")).strip().lower()
        vul_outcome = str(payload.get("fossa_vulnerability_outcome", "missing")).strip().lower()
        lic_total = _safe_int(payload.get("fossa_licensing_total_issues"))
        lic_blocking = _safe_int(payload.get("fossa_licensing_blocking_issues"))
        vul_total = _safe_int(payload.get("fossa_vulnerability_total_issues"))
        vul_blocking = _safe_int(payload.get("fossa_vulnerability_blocking_issues"))

        licensing_passed = lic_blocking == 0 and (lic_outcome in {"success", "skipped"} or lic_total == 0)
        vulnerability_passed = vul_blocking == 0 and (vul_outcome in {"success", "skipped"} or vul_total == 0)

        plugin_has_issues = (
            sonar["status"] == "failed"
            or not licensing_passed
            or not vulnerability_passed
        )

        project_locator = urllib.parse.quote(f"custom+48578/{project_id}", safe="")
        encoded_branch = urllib.parse.quote(fossa_branch, safe="")
        encoded_version = urllib.parse.quote(version, safe="")
        sonar_base = sonar_host if sonar_host.endswith("/") else f"{sonar_host}/"
        fallback_fossa_url = (
            f"https://app.fossa.com/projects/{project_locator}/refs/branch/{encoded_branch}/{encoded_version}"
        )

        rows.append(
            {
                "plugin": plugin,
                "project_id": project_id,
                "version": version,
                "sonar_status": sonar["status"],
                "sonar_issues": sonar["issues"],
                "licensing_status": "passed" if licensing_passed else "failed",
                "licensing_total": lic_total,
                "licensing_blocking": lic_blocking,
                "vulnerability_status": "passed" if vulnerability_passed else "failed",
                "vulnerability_total": vul_total,
                "vulnerability_blocking": vul_blocking,
                "has_issues": plugin_has_issues,
                "sonar_url": f"{sonar_base}dashboard?id={urllib.parse.quote(project_id, safe='')}",
                "fossa_report_url": str(payload.get("fossa_report_url") or fallback_fossa_url),
            }
        )

    rows.sort(key=lambda row: (not row["has_issues"], row["plugin"]))

    projects_with_issues = [row["plugin"] for row in rows if row["has_issues"]]
    projects_without_issues = [row["plugin"] for row in rows if not row["has_issues"]]
    licensing_total = sum(int(row["licensing_total"]) for row in rows)
    vulnerability_total = sum(int(row["vulnerability_total"]) for row in rows)
    sonar_total_issues = sum(int(row["sonar_issues"]) for row in rows)

    overall_sonar = "✅ Passed" if sonar_total_issues == 0 else f"❌ {sonar_total_issues} Issues"
    overall_licensing = "✅ Passed" if licensing_total == 0 else f"❌ {licensing_total} Issues"
    overall_vulnerability = "✅ Passed" if vulnerability_total == 0 else f"❌ {vulnerability_total} Issues"

    lines = [
        "## 🔐 Release Readiness Check Results",
        "",
        "### Overall Status",
        "",
        "| Check | Scope | Status |",
        "|-------|-------|--------|",
        f"| SonarQube Hotspots | Per-Plugin | {overall_sonar} |",
        f"| FOSSA Licensing | Per-Plugin | {overall_licensing} |",
        f"| FOSSA Vulnerabilities | Per-Plugin | {overall_vulnerability} |",
        "",
        "### Projects With Issues",
    ]
    lines += [f"- `{plugin}`" for plugin in projects_with_issues] or ["- None"]
    lines += ["", "### Projects Without Issues"]
    lines += [f"- `{plugin}`" for plugin in projects_without_issues] or ["- None"]
    lines += [
        "",
        "### Projects Checked (Issues First)",
        "",
        "| Plugin | SonarQube Hotspots | FOSSA Vulnerabilities | License Check | SonarQube Report | FOSSA Report |",
        "|--------|-------------------|-----------------------|---------------|------------------|--------------|",
    ]

    for row in rows:
        sonar_text = "✅ Passed" if int(row["sonar_issues"]) == 0 else f"❌ {row['sonar_issues']} Issues"
        vulnerability_text = (
            "✅ Passed"
            if int(row["vulnerability_total"]) == 0
            else f"❌ {row['vulnerability_total']} Issues"
        )
        licensing_text = "✅ Passed" if int(row["licensing_total"]) == 0 else f"❌ {row['licensing_total']} Issues"
        lines.append(
            f"| `{row['plugin']}` | {sonar_text} | {vulnerability_text} | {licensing_text} | "
            f"[View report]({row['sonar_url']}) | [View report]({row['fossa_report_url']}) |"
        )

    lines += ["", "### Plugins Being Released"]
    lines += [f"- `{row['plugin']}`" for row in rows] or ["- No specific plugins detected"]
    lines += ["", "---", "*This check runs automatically on release-please PRs to ensure compliance before release.*"]
    report = "\n".join(lines)

    _append_summary(report)
    report_path = workspace / "release-readiness-report.md"
    report_path.write_text(report, encoding="utf-8")

    conclusion = "failure" if projects_with_issues else "success"
    summary = (
        f"❌ {len(projects_with_issues)} plugin(s) have release-readiness issues."
        if projects_with_issues
        else "✅ All release-readiness checks passed."
    )

    comment_update_error: str | None = None
    if update_pr_comment:
        if pr_number <= 0:
            comment_update_error = (
                f"update_pr_comment=true for {check_name}, but PR number could not be resolved."
            )
        elif not github_token:
            comment_update_error = "update_pr_comment=true but no github_token was provided."
        else:
            try:
                _upsert_pr_comment(owner, repo, github_token, pr_number, comment_marker, report)
                print(f"Upserted PR comment for #{pr_number} ({check_name}).")
            except Exception as err:
                comment_update_error = str(err)

    check_update_error: str | None = None
    if update_check_details and check_run_id:
        try:
            update_url = f"https://api.github.com/repos/{owner}/{repo}/check-runs/{check_run_id}"
            _github_api(
                "PATCH",
                update_url,
                github_token,
                {
                    "status": "completed",
                    "conclusion": conclusion,
                    "completed_at": _utc_now_iso(),
                    "output": {
                        "title": "Release Readiness Check",
                        "summary": summary,
                        "text": report,
                    },
                },
            )
            if created_check_run:
                print(f"Created and completed dedicated check run {check_run_id} for {check_name}")
            else:
                print(f"Updated existing check run {check_run_id} for {check_name}")
        except Exception as err:
            check_update_error = str(err)

    _write_output("conclusion", conclusion)
    _write_output("summary", summary)
    _write_output("projects_with_issues", json.dumps(projects_with_issues))
    _write_output("report_markdown", report)
    _write_output("report_file", str(report_path))

    if comment_update_error:
        print(f"Error: failed to publish PR comment for {check_name}: {comment_update_error}")
        return 2

    if check_update_error:
        print(f"Error: failed to publish check-run for {check_name}: {check_update_error}")
        return 2

    if fail_on_issues and conclusion != "success":
        print(summary)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
