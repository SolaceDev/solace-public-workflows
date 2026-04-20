#!/usr/bin/env python3
"""Shared GitHub reporting helpers for workflow scripts."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def github_api(
    method: str,
    url: str,
    token: str,
    payload: dict[str, Any] | None = None,
    user_agent: str = "solace-public-workflows/github-reporting",
) -> dict[str, Any] | list[Any]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10",
        "User-Agent": user_agent,
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


def write_output(name: str, value: str) -> None:
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


def append_summary(markdown: str) -> None:
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    with Path(summary_path).open("a", encoding="utf-8") as handle:
        handle.write(markdown)
        if not markdown.endswith("\n"):
            handle.write("\n")


def normalize_pr_number(
    event: dict[str, Any],
    explicit_value: str = "",
    env_var_name: str = "PR_NUMBER",
) -> int:
    candidates = [
        explicit_value,
        event.get("pull_request", {}).get("number"),
        event.get("number"),
        os.getenv(env_var_name),
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


def resolve_pr_number_by_head(
    owner: str,
    repo: str,
    token: str,
    head_ref: str,
    user_agent: str = "solace-public-workflows/github-reporting",
) -> int:
    if not token or not head_ref:
        return 0
    api_base = os.getenv("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    head = urllib.parse.quote(f"{owner}:{head_ref}", safe=":")
    url = f"{api_base}/repos/{owner}/{repo}/pulls?state=open&head={head}&per_page=1"
    try:
        payload = github_api("GET", url, token, user_agent=user_agent)
    except Exception:
        return 0
    pulls = payload if isinstance(payload, list) else []
    if not pulls:
        return 0
    try:
        return int(pulls[0].get("number") or 0)
    except Exception:
        return 0


def create_check_run(
    owner: str,
    repo: str,
    token: str,
    head_sha: str,
    check_name: str,
    initial_summary: str,
    user_agent: str = "solace-public-workflows/github-reporting",
) -> int | None:
    if not token or not head_sha:
        return None
    api_base = os.getenv("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    url = f"{api_base}/repos/{owner}/{repo}/check-runs"
    payload = {
        "name": check_name,
        "head_sha": head_sha,
        "status": "in_progress",
        "started_at": utc_now_iso(),
        "output": {
            "title": check_name,
            "summary": initial_summary,
        },
    }
    try:
        created = github_api("POST", url, token, payload, user_agent=user_agent)
        return int(created.get("id"))
    except Exception:
        return None


def resolve_check_run_id(
    owner: str,
    repo: str,
    token: str,
    run_id: str,
    head_sha: str,
    check_name: str,
    user_agent: str = "solace-public-workflows/github-reporting",
) -> int | None:
    api_base = os.getenv("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    try:
        jobs_url = f"{api_base}/repos/{owner}/{repo}/actions/runs/{run_id}/jobs?per_page=100"
        jobs_resp = github_api("GET", jobs_url, token, user_agent=user_agent)
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
        checks_url = f"{api_base}/repos/{owner}/{repo}/commits/{head_sha}/check-runs?per_page=100"
        checks_resp = github_api("GET", checks_url, token, user_agent=user_agent)
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


def upsert_pr_comment(
    owner: str,
    repo: str,
    token: str,
    pr_number: int,
    marker: str,
    body: str,
    user_agent: str = "solace-public-workflows/github-reporting",
) -> None:
    if pr_number <= 0:
        return
    api_base = os.getenv("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    list_url = f"{api_base}/repos/{owner}/{repo}/issues/{pr_number}/comments?per_page=100"
    comments_resp = github_api("GET", list_url, token, user_agent=user_agent)
    comments = comments_resp if isinstance(comments_resp, list) else []
    marker_token = f"<!-- {marker} -->"
    normalized_body = body if marker in body or marker_token in body else f"{marker_token}\n{body}"
    existing_ids: list[int] = []
    for comment in comments:
        comment_body = str(comment.get("body", ""))
        user = comment.get("user", {}) if isinstance(comment, dict) else {}
        user_type = str(user.get("type", "")).strip().lower()
        user_login = str(user.get("login", "")).strip().lower()
        is_bot_author = user_type == "bot" or user_login.endswith("[bot]")
        if is_bot_author and (marker in comment_body or marker_token in comment_body):
            existing_ids.append(int(comment["id"]))

    # Always replace prior bot comments for this marker with a fresh one.
    for comment_id in existing_ids:
        delete_url = f"{api_base}/repos/{owner}/{repo}/issues/comments/{comment_id}"
        github_api("DELETE", delete_url, token, user_agent=user_agent)

    create_url = f"{api_base}/repos/{owner}/{repo}/issues/{pr_number}/comments"
    github_api("POST", create_url, token, {"body": normalized_body}, user_agent=user_agent)

