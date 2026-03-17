#!/usr/bin/env python3
"""Aggregate per-project FOSSA Guard diff results into one report/check."""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
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


def _collect_project_payloads(results_dir: Path) -> dict[str, dict[str, Any]]:
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


def _build_row(
    *,
    project: str,
    payload: dict[str, Any],
    repo_owner: str,
    head_ref: str,
) -> dict[str, Any]:
    project_id = str(payload.get("fossa_project_id") or f"{repo_owner}_{project}")
    locator = urllib.parse.quote(f"custom+48578/{project_id}", safe="")
    branch = str(payload.get("fossa_branch", "PR")).strip() or "PR"
    revision = str(payload.get("fossa_revision") or head_ref).strip() or head_ref
    encoded_branch = urllib.parse.quote(branch, safe="")
    encoded_revision = urllib.parse.quote(revision, safe="")

    lic_total = safe_int(payload.get("fossa_licensing_total_issues"))
    lic_blocking = safe_int(payload.get("fossa_licensing_blocking_issues"))
    lic_outcome = str(payload.get("fossa_licensing_outcome", "missing")).strip().lower()

    vul_total = safe_int(payload.get("fossa_vulnerability_total_issues"))
    vul_blocking = safe_int(payload.get("fossa_vulnerability_blocking_issues"))
    vul_outcome = str(payload.get("fossa_vulnerability_outcome", "missing")).strip().lower()

    licensing_passed = (
        bool(payload)
        and lic_blocking == 0
        and (lic_outcome in {"success", "skipped"} or lic_total == 0)
    )
    vulnerability_passed = (
        bool(payload)
        and vul_blocking == 0
        and (vul_outcome in {"success", "skipped"} or vul_total == 0)
    )
    report_url = str(
        payload.get("fossa_report_url")
        or f"https://app.fossa.com/projects/{locator}/refs/branch/{encoded_branch}/{encoded_revision}"
    )
    return {
        "project": project,
        "project_id": project_id,
        "licensing_total_issues": lic_total,
        "licensing_blocking_issues": lic_blocking,
        "licensing_outcome": lic_outcome,
        "licensing_passed": licensing_passed,
        "vulnerability_total_issues": vul_total,
        "vulnerability_blocking_issues": vul_blocking,
        "vulnerability_outcome": vul_outcome,
        "vulnerability_passed": vulnerability_passed,
        "report_url": report_url,
        "has_issues": (not licensing_passed) or (not vulnerability_passed),
    }


def _summarize_failed_issues(results: list[dict[str, Any]]) -> tuple[int, int]:
    total_licensing_issues = 0
    total_vulnerability_issues = 0
    for row in results:
        if not bool(row.get("licensing_passed")):
            total_licensing_issues += max(
                safe_int(row.get("licensing_total_issues")),
                safe_int(row.get("licensing_blocking_issues")),
                1,
            )
        if not bool(row.get("vulnerability_passed")):
            total_vulnerability_issues += max(
                safe_int(row.get("vulnerability_total_issues")),
                safe_int(row.get("vulnerability_blocking_issues")),
                1,
            )
    return total_licensing_issues, total_vulnerability_issues


def _render_report(
    *,
    results: list[dict[str, Any]],
    with_issues: list[str],
    missing_payload_projects: list[str],
) -> str:
    total_licensing_issues, total_vulnerability_issues = _summarize_failed_issues(results)
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
        f"| FOSSA Vulnerabilities | Per-Project (PR Diff) | {overall_vulnerability} |",
        f"| License Check | Per-Project (PR Diff) | {overall_licensing} |",
        "",
        "### Projects With New Issues",
    ]
    lines += [f"- `{project}`" for project in with_issues] or ["- None"]
    lines += [
        "",
        "| Project | FOSSA Vulnerabilities | License Check | FOSSA Report |",
        "|---------|-----------------------|---------------|--------------|",
    ]

    for row in results:
        licensing_passed = bool(row.get("licensing_passed"))
        vulnerability_passed = bool(row.get("vulnerability_passed"))
        licensing_issues = max(
            safe_int(row.get("licensing_total_issues")),
            safe_int(row.get("licensing_blocking_issues")),
            0 if licensing_passed else 1,
        )
        vulnerability_issues = max(
            safe_int(row.get("vulnerability_total_issues")),
            safe_int(row.get("vulnerability_blocking_issues")),
            0 if vulnerability_passed else 1,
        )
        licensing_text = "✅ Passed" if licensing_passed else f"❌ {licensing_issues} Issues"
        vulnerability_text = "✅ Passed" if vulnerability_passed else f"❌ {vulnerability_issues} Issues"
        lines.append(
            f"| `{row['project']}` | {vulnerability_text} | {licensing_text} | [View report]({row['report_url']}) |"
        )

    lines += ["", "---", "*Only newly introduced issues are shown in this report.*"]
    if missing_payload_projects:
        missing = ", ".join(f"`{project}`" for project in missing_payload_projects)
        lines += ["", f"⚠️ Missing project result payloads for: {missing}"]
    return "\n".join(lines)


def _resolve_repository() -> tuple[str, str]:
    repository = os.getenv("GITHUB_REPOSITORY", "")
    if "/" not in repository:
        raise ValueError(f"Invalid GITHUB_REPOSITORY: {repository}")
    return repository.split("/", 1)


def _resolve_pr_number(
    *,
    owner: str,
    repo: str,
    token: str,
    head_ref: str,
    explicit_pr_number: str,
) -> tuple[int, dict[str, Any], str]:
    event = read_json_file(Path(os.getenv("GITHUB_EVENT_PATH", "")), {})
    event = event if isinstance(event, dict) else {}
    pr_number = normalize_pr_number(event, explicit_value=explicit_pr_number)
    resolved_head_ref = head_ref or str(event.get("pull_request", {}).get("head", {}).get("ref") or os.getenv("GITHUB_HEAD_REF", ""))
    if pr_number <= 0:
        pr_number = resolve_pr_number_by_head(owner, repo, token, resolved_head_ref)
    return pr_number, event, resolved_head_ref


def _update_comment_if_enabled(
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
        return "comment_on_pr=true but no github_token was provided."
    try:
        upsert_pr_comment(owner=owner, repo=repo, token=token, pr_number=pr_number, marker=marker, body=body)
        return None
    except Exception as err:
        return str(err)


def _update_check_if_enabled(
    *,
    enabled: bool,
    owner: str,
    repo: str,
    token: str,
    run_id: str,
    head_sha: str,
    check_name: str,
    body: str,
    has_issues: bool,
    results_count: int,
    issue_count: int,
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
                "title": f"{check_name} Passed" if not has_issues else f"{check_name} Failed",
                "summary": (
                    f"No newly introduced FOSSA issues across {results_count} project(s)."
                    if not has_issues
                    else f"New FOSSA issues were introduced in {issue_count} of {results_count} project(s)."
                ),
                "text": body,
            }
        }
        if created_check:
            payload.update(
                {
                    "status": "completed",
                    "conclusion": "success" if not has_issues else "failure",
                    "completed_at": utc_now_iso(),
                }
            )
        check_url = f"https://api.github.com/repos/{owner}/{repo}/check-runs/{check_run_id}"
        github_api("PATCH", check_url, token, payload)
        return None
    except Exception as err:
        return str(err)


def main() -> int:
    projects_json_raw = os.getenv("PROJECTS_JSON", "[]")
    repo_owner = os.getenv("REPO_OWNER", "").strip()
    head_ref = os.getenv("HEAD_REF", "").strip()
    results_dir = Path(os.getenv("RESULTS_DIR", "ci-plugin-results"))
    github_token = os.getenv("GITHUB_TOKEN", "").strip()
    check_name = os.getenv("CHECK_NAME", "FOSSA Report").strip()
    comment_marker = os.getenv("COMMENT_MARKER", "FOSSA Guard (PR Diff)").strip()
    comment_on_pr = to_bool(os.getenv("COMMENT_ON_PR"), default=True)
    update_check_details = to_bool(os.getenv("UPDATE_CHECK_DETAILS"), default=True)
    fail_on_issues = to_bool(os.getenv("FAIL_ON_ISSUES"), default=True)

    try:
        owner, repo = _resolve_repository()
    except ValueError as err:
        print(str(err), file=sys.stderr)
        return 2
    if not repo_owner:
        repo_owner = owner

    pr_number, event, head_ref = _resolve_pr_number(
        owner=owner,
        repo=repo,
        token=github_token,
        head_ref=head_ref,
        explicit_pr_number=os.getenv("PR_NUMBER", ""),
    )
    run_id = os.getenv("GITHUB_RUN_ID", "")
    head_sha = str(event.get("pull_request", {}).get("head", {}).get("sha") or os.getenv("GITHUB_SHA", ""))

    try:
        raw_projects = json.loads(projects_json_raw)
    except Exception:
        raw_projects = []
    projects = _normalize_projects(raw_projects)
    payloads_by_project = _collect_project_payloads(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    missing_payload_projects: list[str] = []
    for project in projects:
        payload = payloads_by_project.get(project, {})
        if not payload:
            missing_payload_projects.append(project)
        results.append(
            _build_row(
                project=project,
                payload=payload,
                repo_owner=repo_owner,
                head_ref=head_ref,
            )
        )

    results.sort(key=lambda row: (not row["has_issues"], row["project"]))
    with_issues = [row["project"] for row in results if row["has_issues"]]
    has_issues = bool(with_issues)
    body = _render_report(results=results, with_issues=with_issues, missing_payload_projects=missing_payload_projects)

    append_job_summary(body)
    (results_dir / "results.json").write_text(json.dumps({"results": results}, indent=2), encoding="utf-8")

    comment_error = _update_comment_if_enabled(
        enabled=comment_on_pr,
        owner=owner,
        repo=repo,
        token=github_token,
        pr_number=pr_number,
        marker=comment_marker,
        body=body,
        check_name=check_name,
    )
    check_error = _update_check_if_enabled(
        enabled=update_check_details,
        owner=owner,
        repo=repo,
        token=github_token,
        run_id=run_id,
        head_sha=head_sha,
        check_name=check_name,
        body=body,
        has_issues=has_issues,
        results_count=len(results),
        issue_count=len(with_issues),
    )

    write_output("has_issues", "true" if has_issues else "false")
    write_output("results_json", json.dumps(results))
    write_output("projects_with_issues", json.dumps(with_issues))
    write_output("report_markdown", body)

    if comment_error:
        print(f"Error: failed to publish PR comment for {check_name}: {comment_error}")
        return 2
    if check_error:
        print(f"Error: failed to publish check-run for {check_name}: {check_error}")
        return 2
    if fail_on_issues and has_issues:
        print(f"FOSSA diff report found issues in {len(with_issues)} project(s).")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
