#!/usr/bin/env python3
"""Prepare release-readiness FOSSA targets from changed plugins."""

from __future__ import annotations

import json
import os
import subprocess
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


def _run_cmd(cmd: list[str], cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, check=False, capture_output=True, text=True)


def _resolve_repo_owner(repository: str, repo_owner: str) -> str:
    owner, _ = repository.split("/", 1)
    return (repo_owner.strip() or owner).strip()


def _fetch_base_branch(base_branch: str) -> None:
    fetch_cmd = _run_cmd(["git", "fetch", "origin", base_branch])
    if fetch_cmd.returncode != 0:
        if fetch_cmd.stdout:
            print(fetch_cmd.stdout)
        if fetch_cmd.stderr:
            print(fetch_cmd.stderr)


def _changed_plugins(base_branch: str) -> list[str]:
    changed_cmd = _run_cmd(["git", "diff", "--name-only", f"origin/{base_branch}...HEAD"])
    if changed_cmd.returncode != 0:
        return []
    changed_files = changed_cmd.stdout.splitlines()
    return sorted({line.split("/", 1)[0] for line in changed_files if line.startswith("sam-") and "/" in line})


def _resolve_plugin_version(plugin: str, fallback_version: str) -> str:
    version_cmd = _run_cmd(["hatch", "version"], cwd=plugin)
    if version_cmd.returncode == 0 and version_cmd.stdout.strip():
        return version_cmd.stdout.strip().splitlines()[-1].strip()
    return fallback_version


def _build_targets(
    *,
    plugins: list[str],
    repo_owner: str,
    base_branch: str,
    licensing_block_on: str,
    vulnerability_block_on: str,
    fallback_version: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    plugin_versions: list[dict[str, Any]] = []
    targets: list[dict[str, Any]] = []

    for plugin in plugins:
        project_id = f"{repo_owner}_{plugin}"
        version = _resolve_plugin_version(plugin, fallback_version)
        plugin_versions.append({"plugin": plugin, "project_id": project_id, "version": version})
        targets.append(
            {
                "plugin": plugin,
                "project_id": project_id,
                "category": "licensing",
                "block_on": licensing_block_on,
                "branch": base_branch,
                "revision": version,
            }
        )
        targets.append(
            {
                "plugin": plugin,
                "project_id": project_id,
                "category": "vulnerability",
                "block_on": vulnerability_block_on,
                "branch": base_branch,
                "revision": version,
            }
        )
    return plugin_versions, targets


def main() -> int:
    repository = os.getenv("GITHUB_REPOSITORY", "")
    if "/" not in repository:
        print(f"Invalid GITHUB_REPOSITORY: {repository}", file=sys.stderr)
        return 2

    repo_owner = _resolve_repo_owner(repository, os.getenv("REPO_OWNER", ""))
    base_branch = os.getenv("BASE_BRANCH", "main").strip()
    licensing_block_on = os.getenv("LICENSING_BLOCK_ON", "policy_conflict").strip()
    vulnerability_block_on = os.getenv("VULNERABILITY_BLOCK_ON", "critical,high").strip()
    sha = os.getenv("GITHUB_SHA", "").strip()
    fallback_version = sha[:12] if sha else "unknown"

    _fetch_base_branch(base_branch)
    plugins = _changed_plugins(base_branch)
    plugin_versions, targets = _build_targets(
        plugins=plugins,
        repo_owner=repo_owner,
        base_branch=base_branch,
        licensing_block_on=licensing_block_on,
        vulnerability_block_on=vulnerability_block_on,
        fallback_version=fallback_version,
    )

    plugin_versions_file = Path("release-readiness-plugin-versions.json")
    plugin_versions_file.write_text(json.dumps({"plugins": plugin_versions}, indent=2), encoding="utf-8")

    write_output("targets_json", json.dumps(targets))
    write_output("plugin_versions_file", str(plugin_versions_file))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
