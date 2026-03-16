#!/usr/bin/env python3
"""Aggregate per-plugin FOSSA Guard diff results into one report/check."""

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
    plugins_json_raw = os.getenv("PLUGINS_JSON", "[]")
    repo_owner = os.getenv("REPO_OWNER", "").strip()
    head_ref = os.getenv("HEAD_REF", "").strip()
    results_dir = Path(os.getenv("RESULTS_DIR", "ci-plugin-results"))
    github_token = os.getenv("GITHUB_TOKEN", "").strip()
    check_name = os.getenv("CHECK_NAME", "FOSSA Report").strip()
    comment_marker = os.getenv("COMMENT_MARKER", "FOSSA Guard (PR Diff)").strip()
    comment_on_pr = _to_bool(os.getenv("COMMENT_ON_PR"), default=True)
    update_check_details = _to_bool(os.getenv("UPDATE_CHECK_DETAILS"), default=True)
    fail_on_issues = _to_bool(os.getenv("FAIL_ON_ISSUES"), default=True)

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
    pr_number = _normalize_pr_number(event)
    if not head_ref:
        head_ref = str(event.get("pull_request", {}).get("head", {}).get("ref") or os.getenv("GITHUB_HEAD_REF", ""))
    if pr_number <= 0:
        pr_number = _resolve_pr_number_by_head(owner, repo, github_token, head_ref)
    run_id = os.getenv("GITHUB_RUN_ID", "")
    head_sha = str(event.get("pull_request", {}).get("head", {}).get("sha") or os.getenv("GITHUB_SHA", ""))

    try:
        raw_plugins = json.loads(plugins_json_raw)
    except Exception:
        raw_plugins = []
    plugins = _normalize_plugins(raw_plugins)
    by_plugin = _collect_plugin_payloads(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    missing_payload_plugins: list[str] = []
    for plugin in plugins:
        payload = by_plugin.get(plugin, {})
        if not payload:
            missing_payload_plugins.append(plugin)
        project_id = str(payload.get("fossa_project_id") or f"{repo_owner}_{plugin}")
        locator = urllib.parse.quote(f"custom+48578/{project_id}", safe="")
        branch = str(payload.get("fossa_branch", "PR")).strip() or "PR"
        revision = str(payload.get("fossa_revision") or head_ref).strip() or head_ref
        encoded_branch = urllib.parse.quote(branch, safe="")
        encoded_revision = urllib.parse.quote(revision, safe="")

        lic_total = _safe_int(payload.get("fossa_licensing_total_issues"))
        lic_blocking = _safe_int(payload.get("fossa_licensing_blocking_issues"))
        lic_outcome = str(payload.get("fossa_licensing_outcome", "missing")).strip().lower()

        vul_total = _safe_int(payload.get("fossa_vulnerability_total_issues"))
        vul_blocking = _safe_int(payload.get("fossa_vulnerability_blocking_issues"))
        vul_outcome = str(payload.get("fossa_vulnerability_outcome", "missing")).strip().lower()

        licensing_url = (
            f"https://app.fossa.com/projects/{locator}/refs/branch/{encoded_branch}/{encoded_revision}/issues/licensing"
            "?page=1&count=20&sort=issue_count_desc&grouping=revision&status=active"
        )
        vulnerability_url = (
            f"https://app.fossa.com/projects/{locator}/refs/branch/{encoded_branch}/{encoded_revision}/issues/vulnerability"
            "?page=1&count=20&sort=issue_count_desc&grouping=revision&status=active"
        )
        report_url = str(
            payload.get("fossa_report_url")
            or f"https://app.fossa.com/projects/{locator}/refs/branch/{encoded_branch}/{encoded_revision}"
        )

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
        has_issues = (not licensing_passed) or (not vulnerability_passed)

        results.append(
            {
                "plugin": plugin,
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
                "licensing_url": licensing_url,
                "vulnerability_url": vulnerability_url,
                "has_issues": has_issues,
            }
        )

    results.sort(key=lambda r: (not r["has_issues"], r["plugin"]))
    with_issues = [r["plugin"] for r in results if r["has_issues"]]

    total_licensing_issues = 0
    total_vulnerability_issues = 0
    for row in results:
        if not bool(row.get("licensing_passed")):
            total_licensing_issues += max(
                _safe_int(row.get("licensing_total_issues")),
                _safe_int(row.get("licensing_blocking_issues")),
                1,
            )
        if not bool(row.get("vulnerability_passed")):
            total_vulnerability_issues += max(
                _safe_int(row.get("vulnerability_total_issues")),
                _safe_int(row.get("vulnerability_blocking_issues")),
                1,
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
        licensing_passed = bool(row.get("licensing_passed"))
        vulnerability_passed = bool(row.get("vulnerability_passed"))
        licensing_issues = max(
            _safe_int(row.get("licensing_total_issues")),
            _safe_int(row.get("licensing_blocking_issues")),
            0 if licensing_passed else 1,
        )
        vulnerability_issues = max(
            _safe_int(row.get("vulnerability_total_issues")),
            _safe_int(row.get("vulnerability_blocking_issues")),
            0 if vulnerability_passed else 1,
        )

        licensing_text = "✅ Passed" if licensing_passed else f"❌ {licensing_issues} Issues"
        vulnerability_text = "✅ Passed" if vulnerability_passed else f"❌ {vulnerability_issues} Issues"
        lines.append(
            f"| `{row['plugin']}` | {vulnerability_text} | {licensing_text} | [View report]({row['report_url']}) |"
        )

    lines += ["", "---", "*Only newly introduced issues are shown in this report.*"]
    if missing_payload_plugins:
        lines += [
            "",
            f"⚠️ Missing plugin result payloads for: {', '.join(f'`{p}`' for p in missing_payload_plugins)}",
        ]
    body = "\n".join(lines)

    _append_summary(body)
    (results_dir / "results.json").write_text(json.dumps({"results": results}, indent=2), encoding="utf-8")

    has_issues = len(with_issues) > 0

    comment_update_error: str | None = None
    if comment_on_pr:
        if pr_number <= 0:
            comment_update_error = (
                f"comment_on_pr=true for {check_name}, but PR number could not be resolved from event payload."
            )
        elif not github_token:
            comment_update_error = "comment_on_pr=true but no github_token was provided."
        else:
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

                title = f"{check_name} Passed" if not has_issues else f"{check_name} Failed"
                check_output_summary = (
                    f"No newly introduced FOSSA issues across {len(results)} plugin(s)."
                    if not has_issues
                    else f"New FOSSA issues were introduced in {len(with_issues)} of {len(results)} plugin(s)."
                )
                check_url = f"https://api.github.com/repos/{owner}/{repo}/check-runs/{check_run_id}"
                payload: dict[str, Any] = {
                    "output": {
                        "title": title,
                        "summary": check_output_summary,
                        "text": body,
                    }
                }
                if created_check_run:
                    payload.update(
                        {
                            "status": "completed",
                            "conclusion": "success" if not has_issues else "failure",
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

    _write_output("has_issues", "true" if has_issues else "false")
    _write_output("results_json", json.dumps(results))
    _write_output("projects_with_issues", json.dumps(with_issues))
    _write_output("report_markdown", body)

    if comment_update_error:
        print(f"Error: failed to publish PR comment for {check_name}: {comment_update_error}")
        return 2

    if check_update_error:
        print(f"Error: failed to publish check-run for {check_name}: {check_update_error}")
        return 2

    if fail_on_issues and has_issues:
        print(f"FOSSA diff report found issues in {len(with_issues)} plugin(s).")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
