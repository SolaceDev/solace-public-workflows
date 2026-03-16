#!/usr/bin/env python3
"""Prepare FOSSA diff-mode targets for PR plugin aggregation."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


def main() -> int:
    plugins_json_raw = os.getenv("PLUGINS_JSON", "[]")
    repo_owner = os.getenv("REPO_OWNER", "").strip()
    head_ref = os.getenv("HEAD_REF", "").strip()
    base_sha = os.getenv("BASE_SHA", "").strip()
    licensing_block_on = os.getenv("LICENSING_BLOCK_ON", "policy_conflict").strip()
    vulnerability_block_on = os.getenv("VULNERABILITY_BLOCK_ON", "critical,high").strip()

    repository = os.getenv("GITHUB_REPOSITORY", "")
    if "/" in repository and not repo_owner:
        repo_owner = repository.split("/", 1)[0]

    try:
        raw_plugins = json.loads(plugins_json_raw)
    except Exception:
        raw_plugins = []
    plugins = _normalize_plugins(raw_plugins)

    targets: list[dict[str, Any]] = []
    for plugin in plugins:
        project_id = f"{repo_owner}_{plugin}"
        targets.append(
            {
                "plugin": plugin,
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
                "plugin": plugin,
                "project_id": project_id,
                "category": "vulnerability",
                "block_on": vulnerability_block_on,
                "branch": "PR",
                "revision": head_ref,
                "diff_base_revision_sha": base_sha,
            }
        )

    _write_output("targets_json", json.dumps(targets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
