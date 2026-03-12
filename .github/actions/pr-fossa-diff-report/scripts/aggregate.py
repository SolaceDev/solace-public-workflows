#!/usr/bin/env python3
"""
Run per-plugin FOSSA Guard diff checks and publish a compact aggregated report.
"""

from __future__ import annotations

import json
import os
import re
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
        "User-Agent": "solace-public-workflows/pr-fossa-diff-report",
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


def _resolve_check_run_id(
    owner: str,
    repo: str,
    token: str,
    run_id: str,
    head_sha: str,
    check_name: str,
) -> int | None:
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


def _run_guard(
    *,
    workspace: Path,
    fossa_api_key: str,
    project_id: str,
    category: str,
    block_on: str,
    head_ref: str,
    base_sha: str,
    docker_image: str,
) -> tuple[int, dict[str, Any]]:
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
        "FOSSA_BRANCH=PR",
        "-e",
        f"FOSSA_REVISION={head_ref}",
        "-e",
        "ENABLE_DIFF_MODE=true",
        "-e",
        f"DIFF_BASE_REVISION_SHA={base_sha}",
        "-v",
        f"{workspace}:/workspace",
        "-w",
        "/workspace",
        docker_image,
        "/bin/sh",
        "-c",
        "source /maas-build-actions/venv/bin/activate && python3 /maas-build-actions/scripts/fossa-guard/fossa_guard.py",
    ]
    completed = subprocess.run(cmd, check=False)
    report_data: dict[str, Any] = {}
    if report_path.exists():
        try:
            report_data = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:
            report_data = {}
    return completed.returncode, report_data


def _summary_counts(report: dict[str, Any]) -> tuple[int, int]:
    summary = report.get("summary", {}) if isinstance(report, dict) else {}
    total = int(summary.get("total_issues", 0) or 0)
    blocking = int(summary.get("blocking_issues", 0) or 0)
    return total, blocking


def main() -> int:
    plugins_json_raw = os.getenv("PLUGINS_JSON", "[]")
    fossa_api_key = os.getenv("FOSSA_API_KEY", "").strip()
    repo_owner = os.getenv("REPO_OWNER", "").strip()
    head_ref = os.getenv("HEAD_REF", "").strip()
    base_sha = os.getenv("BASE_SHA", "").strip()
    results_dir = Path(os.getenv("RESULTS_DIR", "fossa-report"))
    docker_image = os.getenv("DOCKER_IMAGE", "ghcr.io/solacedev/maas-build-actions:latest").strip()
    licensing_block_on = os.getenv("LICENSING_BLOCK_ON", "policy_conflict").strip()
    vulnerability_block_on = os.getenv("VULNERABILITY_BLOCK_ON", "critical,high").strip()
    github_token = os.getenv("GITHUB_TOKEN", "").strip()
    check_name = os.getenv("CHECK_NAME", "FOSSA Report").strip()
    comment_marker = os.getenv("COMMENT_MARKER", "FOSSA Guard (PR Diff)").strip()
    comment_on_pr = _to_bool(os.getenv("COMMENT_ON_PR"), default=True)
    update_check_details = _to_bool(os.getenv("UPDATE_CHECK_DETAILS"), default=True)
    fail_on_issues = _to_bool(os.getenv("FAIL_ON_ISSUES"), default=True)

    if not fossa_api_key:
        print("Missing FOSSA_API_KEY", file=sys.stderr)
        return 2

    repository = os.getenv("GITHUB_REPOSITORY", "")
    if "/" not in repository:
        print(f"Invalid GITHUB_REPOSITORY: {repository}", file=sys.stderr)
        return 2
    owner, repo = repository.split("/", 1)
    if not repo_owner:
        repo_owner = owner

    event_path = Path(os.getenv("GITHUB_EVENT_PATH", ""))
    event: dict[str, Any] = {}
    if event_path.exists():
        try:
            event = json.loads(event_path.read_text(encoding="utf-8"))
        except Exception:
            event = {}
    pr_number = int(event.get("pull_request", {}).get("number") or 0)
    if not head_ref:
        head_ref = str(event.get("pull_request", {}).get("head", {}).get("ref") or os.getenv("GITHUB_HEAD_REF", ""))
    if not base_sha:
        base_sha = str(event.get("pull_request", {}).get("base", {}).get("sha") or "")
    run_id = os.getenv("GITHUB_RUN_ID", "")
    head_sha = str(event.get("pull_request", {}).get("head", {}).get("sha") or os.getenv("GITHUB_SHA", ""))

    try:
        raw_plugins = json.loads(plugins_json_raw)
    except Exception:
        raw_plugins = []
    plugins = _normalize_plugins(raw_plugins)
    workspace = Path.cwd()
    results_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for plugin in plugins:
        project_id = f"{repo_owner}_{plugin}"
        locator = urllib.parse.quote(f"custom+48578/{project_id}", safe="")
        encoded_revision = urllib.parse.quote(head_ref, safe="")

        lic_rc, lic_report = _run_guard(
            workspace=workspace,
            fossa_api_key=fossa_api_key,
            project_id=project_id,
            category="licensing",
            block_on=licensing_block_on,
            head_ref=head_ref,
            base_sha=base_sha,
            docker_image=docker_image,
        )
        lic_total, lic_blocking = _summary_counts(lic_report)
        (results_dir / f"{plugin}-licensing.json").write_text(json.dumps(lic_report, indent=2), encoding="utf-8")

        vul_rc, vul_report = _run_guard(
            workspace=workspace,
            fossa_api_key=fossa_api_key,
            project_id=project_id,
            category="vulnerability",
            block_on=vulnerability_block_on,
            head_ref=head_ref,
            base_sha=base_sha,
            docker_image=docker_image,
        )
        vul_total, vul_blocking = _summary_counts(vul_report)
        (results_dir / f"{plugin}-vulnerability.json").write_text(json.dumps(vul_report, indent=2), encoding="utf-8")

        licensing_url = (
            f"https://app.fossa.com/projects/{locator}/refs/branch/PR/{encoded_revision}/issues/licensing"
            "?page=1&count=20&sort=issue_count_desc&grouping=revision&status=active"
        )
        vulnerability_url = (
            f"https://app.fossa.com/projects/{locator}/refs/branch/PR/{encoded_revision}/issues/vulnerability"
            "?page=1&count=20&sort=issue_count_desc&grouping=revision&status=active"
        )
        report_url = f"https://app.fossa.com/projects/{locator}/refs/branch/PR/{encoded_revision}"

        has_issues = (
            lic_blocking > 0
            or vul_blocking > 0
            or lic_rc != 0
            or vul_rc != 0
        )

        results.append(
            {
                "plugin": plugin,
                "project_id": project_id,
                "licensing_total_issues": lic_total,
                "licensing_blocking_issues": lic_blocking,
                "licensing_exit_code": lic_rc,
                "vulnerability_total_issues": vul_total,
                "vulnerability_blocking_issues": vul_blocking,
                "vulnerability_exit_code": vul_rc,
                "report_url": report_url,
                "licensing_url": licensing_url,
                "vulnerability_url": vulnerability_url,
                "has_issues": has_issues,
            }
        )

    results.sort(key=lambda r: (not r["has_issues"], r["plugin"]))
    with_issues = [r["plugin"] for r in results if r["has_issues"]]

    total_licensing_issues = sum(
        max(
            int(r.get("licensing_total_issues", 0) or 0),
            int(r.get("licensing_blocking_issues", 0) or 0),
            0 if int(r.get("licensing_exit_code", 1) or 1) == 0 else 1,
        )
        for r in results
    )
    total_vulnerability_issues = sum(
        max(
            int(r.get("vulnerability_total_issues", 0) or 0),
            int(r.get("vulnerability_blocking_issues", 0) or 0),
            0 if int(r.get("vulnerability_exit_code", 1) or 1) == 0 else 1,
        )
        for r in results
    )

    overall_licensing = "✅ Passed" if total_licensing_issues == 0 else f"❌ {total_licensing_issues} Issues"
    overall_vulnerability = "✅ Passed" if total_vulnerability_issues == 0 else f"❌ {total_vulnerability_issues} Issues"

    header = (
        "## ✅ FOSSA Guard (PR Diff) - No New Issues Introduced"
        if not with_issues
        else "## ❌ FOSSA Guard (PR Diff) - New Issues Introduced"
    )

    lines = [
        header,
        "",
        "_Diff mode compares PR head against base revision and reports only newly introduced issues._",
        "",
        "| Check | Scope | Status |",
        "|-------|-------|--------|",
        f"| FOSSA Vulnerabilities | Per-Plugin (PR Diff) | {overall_vulnerability} |",
        f"| License Check | Per-Plugin (PR Diff) | {overall_licensing} |",
        "",
        "### Projects With New Issues",
    ]
    lines += [f"- `{plugin}`" for plugin in with_issues] or ["- None"]
    lines += [
        "",
        "| Plugin | FOSSA Vulnerabilities | License Check | FOSSA Report |",
        "|--------|-----------------------|---------------|--------------|",
    ]

    for row in results:
        licensing_passed = int(row["licensing_exit_code"]) == 0 and int(row["licensing_blocking_issues"]) == 0
        vulnerability_passed = int(row["vulnerability_exit_code"]) == 0 and int(row["vulnerability_blocking_issues"]) == 0

        licensing_issues = max(
            int(row["licensing_total_issues"]),
            int(row["licensing_blocking_issues"]),
            0 if int(row["licensing_exit_code"]) == 0 else 1,
        )
        vulnerability_issues = max(
            int(row["vulnerability_total_issues"]),
            int(row["vulnerability_blocking_issues"]),
            0 if int(row["vulnerability_exit_code"]) == 0 else 1,
        )

        licensing_text = "✅ Passed" if licensing_passed else f"❌ {licensing_issues} Issues"
        vulnerability_text = "✅ Passed" if vulnerability_passed else f"❌ {vulnerability_issues} Issues"
        lines.append(
            f"| `{row['plugin']}` | {vulnerability_text} | {licensing_text} | [View report]({row['report_url']}) |"
        )

    lines += ["", "---", "*Only newly introduced issues are shown in this report.*"]
    body = "\n".join(lines)

    _append_summary(body)
    (results_dir / "results.json").write_text(json.dumps({"results": results}, indent=2), encoding="utf-8")

    has_issues = len(with_issues) > 0

    if github_token and comment_on_pr and pr_number > 0:
        try:
            _upsert_pr_comment(
                owner=owner,
                repo=repo,
                token=github_token,
                pr_number=pr_number,
                marker=comment_marker,
                body=body,
            )
        except Exception as err:
            print(f"Warning: failed to upsert FOSSA PR comment: {err}")

    if github_token and update_check_details:
        try:
            check_run_id = _resolve_check_run_id(
                owner=owner,
                repo=repo,
                token=github_token,
                run_id=run_id,
                head_sha=head_sha,
                check_name=check_name,
            )
            if check_run_id:
                title = "FOSSA Report Passed" if not has_issues else "FOSSA Report Failed"
                check_url = f"https://api.github.com/repos/{owner}/{repo}/check-runs/{check_run_id}"
                _github_api(
                    "PATCH",
                    check_url,
                    github_token,
                    {
                        "output": {
                            "title": title,
                            "summary": body,
                        }
                    },
                )
                print(f"Updated check run {check_run_id} for {check_name}")
            else:
                print(f"No check run found for {check_name}; skipping check details update")
        except Exception as err:
            print(f"Warning: failed to update FOSSA check-run details: {err}")

    _write_output("has_issues", "true" if has_issues else "false")
    _write_output("results_json", json.dumps(results))
    _write_output("projects_with_issues", json.dumps(with_issues))
    _write_output("report_markdown", body)

    if fail_on_issues and has_issues:
        print(f"FOSSA diff report found issues in {len(with_issues)} plugin(s).")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
