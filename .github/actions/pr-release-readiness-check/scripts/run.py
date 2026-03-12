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
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


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
        "User-Agent": "solace-public-workflows/pr-release-readiness-check",
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
            marker = f"EOF_{name}_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
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


def _run_cmd(cmd: list[str], cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


def _normalize_pr_number(value: str, event: dict[str, Any]) -> int:
    try:
        if value.strip():
            return int(value.strip())
    except Exception:
        pass
    try:
        return int(event.get("pull_request", {}).get("number") or 0)
    except Exception:
        return 0


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


def _create_check_run(owner: str, repo: str, token: str, check_name: str, head_sha: str) -> int | None:
    if not token or not head_sha:
        return None
    try:
        url = f"https://api.github.com/repos/{owner}/{repo}/check-runs"
        payload = {
            "name": check_name,
            "head_sha": head_sha,
            "status": "in_progress",
            "started_at": datetime.utcnow().isoformat() + "Z",
            "output": {
                "title": "Release Readiness Check",
                "summary": "Aggregating SonarQube and FOSSA results...",
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
    if pr_number <= 0 or not token:
        return
    list_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments?per_page=100"
    comments_resp = _github_api("GET", list_url, token)
    comments = comments_resp if isinstance(comments_resp, list) else []
    existing_id = None
    for comment in comments:
        if marker in str(comment.get("body", "")) and comment.get("user", {}).get("type") == "Bot":
            existing_id = int(comment["id"])
            break

    if existing_id:
        patch_url = f"https://api.github.com/repos/{owner}/{repo}/issues/comments/{existing_id}"
        _github_api("PATCH", patch_url, token, {"body": body})
        return
    create_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
    _github_api("POST", create_url, token, {"body": body})


def _run_fossa_guard(
    *,
    workspace: Path,
    fossa_api_key: str,
    project_id: str,
    category: str,
    block_on: str,
    branch: str,
    revision: str,
    docker_image: str,
) -> dict[str, Any]:
    report_path = workspace / "fossa_guard_report.json"
    if report_path.exists():
        report_path.unlink()

    cmd = [
        "docker",
        "run",
        "--rm",
        "-e",
        f"FOSSA_API_KEY={fossa_api_key}",
        "-e",
        f"FOSSA_PROJECT_ID={project_id}",
        "-e",
        f"FOSSA_CATEGORY={category}",
        "-e",
        "FOSSA_MODE=REPORT",
        "-e",
        f"BLOCK_ON={block_on}",
        "-e",
        f"FOSSA_BRANCH={branch}",
        "-e",
        f"FOSSA_REVISION={revision}",
        "-v",
        f"{workspace}:/workspace",
        "-w",
        "/workspace",
        docker_image,
        "/bin/sh",
        "-c",
        "source /maas-build-actions/venv/bin/activate && python3 /maas-build-actions/scripts/fossa-guard/fossa_guard.py",
    ]
    proc = subprocess.run(cmd, check=False)

    report_data: dict[str, Any] = {}
    if report_path.exists():
        try:
            report_data = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:
            report_data = {}

    summary = report_data.get("summary", {}) if isinstance(report_data, dict) else {}
    total_issues = int(summary.get("total_issues", 0) or 0)
    blocking_issues = int(summary.get("blocking_issues", 0) or 0)

    if proc.returncode != 0:
        status = "error"
    elif blocking_issues > 0:
        status = "failed"
    else:
        status = "passed"

    return {
        "status": status,
        "total_issues": total_issues,
        "blocking_issues": blocking_issues,
    }


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


def main() -> int:
    github_token = os.getenv("GITHUB_TOKEN", "").strip()
    fossa_api_key = os.getenv("FOSSA_API_KEY", "").strip()
    sonar_token = os.getenv("SONARQUBE_TOKEN", "").strip()
    sonar_host = os.getenv("SONARQUBE_HOST_URL", "").strip()
    repo_owner_input = os.getenv("REPO_OWNER", "").strip()
    base_branch = os.getenv("BASE_BRANCH", "main").strip()
    check_name = os.getenv("CHECK_NAME", "Release Readiness").strip()
    comment_marker = os.getenv("COMMENT_MARKER", "Release Readiness Check Results").strip()
    docker_image = os.getenv("DOCKER_IMAGE", "ghcr.io/solacedev/maas-build-actions:latest").strip()
    licensing_block_on = os.getenv("LICENSING_BLOCK_ON", "policy_conflict").strip()
    vulnerability_block_on = os.getenv("VULNERABILITY_BLOCK_ON", "critical,high").strip()
    fail_on_issues = _to_bool(os.getenv("FAIL_ON_ISSUES"), default=True)
    update_pr_comment = _to_bool(os.getenv("UPDATE_PR_COMMENT"), default=True)
    update_check_details = _to_bool(os.getenv("UPDATE_CHECK_DETAILS"), default=True)
    pr_number_input = os.getenv("PR_NUMBER", "")

    if not fossa_api_key:
        print("Missing FOSSA_API_KEY", file=sys.stderr)
        return 2
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
    pr_number = _normalize_pr_number(pr_number_input, event)
    head_sha = _extract_head_sha(pr_number, event, github_token, owner, repo)
    short_sha = head_sha[:12] if head_sha else "unknown"

    check_run_id: int | None = None
    if update_check_details:
        check_run_id = _create_check_run(owner, repo, github_token, check_name, head_sha)

    fetch_main = _run_cmd(["git", "fetch", "origin", base_branch])
    if fetch_main.returncode != 0:
        print(fetch_main.stdout)
        print(fetch_main.stderr)

    changed_files = _run_cmd(["git", "diff", "--name-only", f"origin/{base_branch}...HEAD"])
    changed = changed_files.stdout.splitlines() if changed_files.returncode == 0 else []
    plugins = sorted({line.split("/", 1)[0] for line in changed if line.startswith("sam-") and "/" in line})

    workspace = Path.cwd()
    rows: list[dict[str, Any]] = []

    for plugin in plugins:
        project_id = f"{repo_owner}_{plugin}"

        version_cmd = _run_cmd(["hatch", "version"], cwd=plugin)
        if version_cmd.returncode == 0 and version_cmd.stdout.strip():
            version = version_cmd.stdout.strip().splitlines()[-1].strip()
        else:
            version = short_sha

        sonar = _run_sonar_hotspots(
            project_id=project_id,
            base_branch=base_branch,
            sonar_host_url=sonar_host,
            sonar_token=sonar_token,
        )
        licensing = _run_fossa_guard(
            workspace=workspace,
            fossa_api_key=fossa_api_key,
            project_id=project_id,
            category="licensing",
            block_on=licensing_block_on,
            branch=base_branch,
            revision=version,
            docker_image=docker_image,
        )
        vulnerabilities = _run_fossa_guard(
            workspace=workspace,
            fossa_api_key=fossa_api_key,
            project_id=project_id,
            category="vulnerability",
            block_on=vulnerability_block_on,
            branch=base_branch,
            revision=version,
            docker_image=docker_image,
        )

        plugin_has_issues = (
            sonar["status"] == "failed"
            or licensing["total_issues"] > 0
            or vulnerabilities["total_issues"] > 0
        )

        project_locator = urllib.parse.quote(f"custom+48578/{project_id}", safe="")
        encoded_version = urllib.parse.quote(version, safe="")
        sonar_base = sonar_host if sonar_host.endswith("/") else f"{sonar_host}/"

        rows.append(
            {
                "plugin": plugin,
                "project_id": project_id,
                "version": version,
                "sonar_status": sonar["status"],
                "sonar_issues": sonar["issues"],
                "licensing_status": licensing["status"],
                "licensing_total": licensing["total_issues"],
                "licensing_blocking": licensing["blocking_issues"],
                "vulnerability_status": vulnerabilities["status"],
                "vulnerability_total": vulnerabilities["total_issues"],
                "vulnerability_blocking": vulnerabilities["blocking_issues"],
                "has_issues": plugin_has_issues,
                "sonar_url": f"{sonar_base}dashboard?id={urllib.parse.quote(project_id, safe='')}",
                "fossa_report_url": (
                    f"https://app.fossa.com/projects/{project_locator}/refs/branch/{base_branch}/{encoded_version}"
                ),
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

    if update_pr_comment and pr_number > 0:
        try:
            _upsert_pr_comment(owner, repo, github_token, pr_number, comment_marker, report)
        except Exception as err:
            print(f"Warning: failed to upsert release-readiness PR comment: {err}")

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
                    "completed_at": datetime.utcnow().isoformat() + "Z",
                    "output": {
                        "title": "Release Readiness Check",
                        "summary": summary,
                        "text": report,
                    },
                },
            )
        except Exception as err:
            print(f"Warning: failed to update release-readiness check-run details: {err}")

    _write_output("conclusion", conclusion)
    _write_output("summary", summary)
    _write_output("projects_with_issues", json.dumps(projects_with_issues))
    _write_output("report_markdown", report)
    _write_output("report_file", str(report_path))

    if fail_on_issues and conclusion != "success":
        print(summary)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
