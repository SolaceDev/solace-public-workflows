#!/usr/bin/env python3
"""Prepare FOSSA diff-mode targets for project aggregation on PRs."""

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

from github_reporting import write_output  # type: ignore  # noqa: E402


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


def main() -> int:
    projects_json_raw = os.getenv("PROJECTS_JSON", "[]")
    repo_owner = os.getenv("REPO_OWNER", "").strip()
    head_ref = os.getenv("HEAD_REF", "").strip()
    base_sha = os.getenv("BASE_SHA", "").strip()
    licensing_block_on = os.getenv("LICENSING_BLOCK_ON", "policy_conflict").strip()
    vulnerability_block_on = os.getenv("VULNERABILITY_BLOCK_ON", "critical,high").strip()

    repository = os.getenv("GITHUB_REPOSITORY", "")
    if "/" in repository and not repo_owner:
        repo_owner = repository.split("/", 1)[0]

    try:
        raw_projects = json.loads(projects_json_raw)
    except Exception:
        raw_projects = []
    projects = _normalize_projects(raw_projects)

    targets: list[dict[str, Any]] = []
    for project in projects:
        project_id = f"{repo_owner}_{project}"
        targets.append(
            {
                "project": project,
                "project_id": project_id,
                "category": "licensing",
                "block_on": licensing_block_on,
                "branch": "PR",
                "revision": head_ref,
                "diff_base_revision_sha": base_sha,
            }
        )
        targets.append(
            {
                "project": project,
                "project_id": project_id,
                "category": "vulnerability",
                "block_on": vulnerability_block_on,
                "branch": "PR",
                "revision": head_ref,
                "diff_base_revision_sha": base_sha,
            }
        )

    write_output("targets_json", json.dumps(targets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
