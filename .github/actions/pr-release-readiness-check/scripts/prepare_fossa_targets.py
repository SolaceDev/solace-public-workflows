#!/usr/bin/env python3
"""Prepare release-readiness FOSSA targets from changed plugins."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _run_cmd(cmd: list[str], cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


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


def main() -> int:
    repository = os.getenv("GITHUB_REPOSITORY", "")
    if "/" not in repository:
        print(f"Invalid GITHUB_REPOSITORY: {repository}", file=sys.stderr)
        return 2
    owner, _repo = repository.split("/", 1)
    repo_owner = (os.getenv("REPO_OWNER", "").strip() or owner).strip()

    base_branch = os.getenv("BASE_BRANCH", "main").strip()
    licensing_block_on = os.getenv("LICENSING_BLOCK_ON", "policy_conflict").strip()
    vulnerability_block_on = os.getenv("VULNERABILITY_BLOCK_ON", "critical,high").strip()
    sha = os.getenv("GITHUB_SHA", "").strip()
    short_sha = sha[:12] if sha else "unknown"

    fetch_main = _run_cmd(["git", "fetch", "origin", base_branch])
    if fetch_main.returncode != 0:
        if fetch_main.stdout:
            print(fetch_main.stdout)
        if fetch_main.stderr:
            print(fetch_main.stderr)

    changed_files = _run_cmd(["git", "diff", "--name-only", f"origin/{base_branch}...HEAD"])
    changed = changed_files.stdout.splitlines() if changed_files.returncode == 0 else []
    plugins = sorted({line.split("/", 1)[0] for line in changed if line.startswith("sam-") and "/" in line})

    plugin_versions: list[dict[str, Any]] = []
    targets: list[dict[str, Any]] = []
    for plugin in plugins:
        project_id = f"{repo_owner}_{plugin}"
        version_cmd = _run_cmd(["hatch", "version"], cwd=plugin)
        if version_cmd.returncode == 0 and version_cmd.stdout.strip():
            version = version_cmd.stdout.strip().splitlines()[-1].strip()
        else:
            version = short_sha

        plugin_versions.append(
            {
                "plugin": plugin,
                "project_id": project_id,
                "version": version,
            }
        )
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

    plugin_versions_file = Path("release-readiness-plugin-versions.json")
    plugin_versions_file.write_text(json.dumps({"plugins": plugin_versions}, indent=2), encoding="utf-8")

    targets_json = json.dumps(targets)
    _write_output("targets_json", targets_json)
    _write_output("plugin_versions_file", str(plugin_versions_file))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
