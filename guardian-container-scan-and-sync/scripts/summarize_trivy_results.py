#!/usr/bin/env python3
"""Summarize a Trivy JSON image report for the GitHub job.

Writes severity counts to GITHUB_OUTPUT and an overview panel to
GITHUB_STEP_SUMMARY. The per-finding table is only included when
SHOW_DETAILS is true, so public repositories do not publish the full
vulnerability list by default.

A missing or unreadable report is not an error here: it is reported as
scan_ok=false so the action can still sync the other scanners before failing.
"""

import json
import os
from pathlib import Path

SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN")
DEFAULT_MAX_ROWS = 200


def bool_env(name: str, default: bool = False) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    return value == "true"


def load_report(path: str):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def collect_findings(report: dict) -> list[dict]:
    """Unique findings keyed on (id, package, installed version).

    Trivy can report the same vulnerability for several targets in one image;
    counting each would inflate the totals.
    """
    seen = set()
    findings = []
    for result in report.get("Results") or []:
        for vuln in result.get("Vulnerabilities") or []:
            key = (
                vuln.get("VulnerabilityID", ""),
                vuln.get("PkgName", ""),
                vuln.get("InstalledVersion", ""),
            )
            if key in seen:
                continue
            seen.add(key)
            severity = str(vuln.get("Severity", "UNKNOWN")).upper()
            if severity not in SEVERITIES:
                severity = "UNKNOWN"
            findings.append(
                {
                    "id": key[0],
                    "package": key[1],
                    "installed": key[2],
                    "fixed": vuln.get("FixedVersion", "") or "",
                    "severity": severity,
                }
            )
    return findings


def count_by_severity(findings: list[dict]) -> dict[str, int]:
    counts = {severity: 0 for severity in SEVERITIES}
    for finding in findings:
        counts[finding["severity"]] += 1
    return counts


def cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ") or "—"


def build_summary(
    image: str,
    trivy_version: str,
    counts: dict[str, int] | None,
    findings: list[dict],
    show_details: bool,
    visibility: str,
    max_rows: int,
) -> str:
    lines = ["### Trivy Image Scan Overview"]
    if image:
        lines.append(f"- **Image:** `{image}`")
    if trivy_version:
        lines.append(f"- **Trivy:** `{trivy_version}`")
    lines.append("")

    if counts is None:
        lines.append("⚠️ Trivy did not produce a readable report; its findings were not synced.")
        return "\n".join(lines) + "\n"

    total = sum(counts.values())
    lines.extend(
        [
            "| Category | 🔴 Critical | 🟠 High | 🟡 Medium | 🔵 Low | ⚪ Unknown | Total |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            "| Vulnerabilities | "
            + " | ".join(str(counts[s]) for s in SEVERITIES)
            + f" | {total} |",
            "",
        ]
    )

    if not show_details:
        lines.append(
            f"> Detailed findings are hidden (repository visibility: `{visibility or 'unknown'}`). "
            'Set `show_detailed_logs: "true"` to include them.'
        )
        return "\n".join(lines) + "\n"

    if not findings:
        return "\n".join(lines) + "\n"

    rank = {severity: i for i, severity in enumerate(SEVERITIES)}
    ordered = sorted(findings, key=lambda f: (rank[f["severity"]], f["id"], f["package"]))
    shown = ordered[:max_rows]
    lines.extend(
        [
            f"<details><summary>Vulnerabilities ({total})</summary>",
            "",
            "| ID | Severity | Package | Installed | Fixed |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for f in shown:
        lines.append(
            f"| {cell(f['id'])} | {f['severity']} | {cell(f['package'])} "
            f"| {cell(f['installed'])} | {cell(f['fixed'])} |"
        )
    if len(ordered) > len(shown):
        lines.append("")
        lines.append(f"_Showing the first {len(shown)} of {len(ordered)} findings._")
    lines.extend(["", "</details>"])
    return "\n".join(lines) + "\n"


def write_outputs(path: str, values: dict[str, str]) -> None:
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def main() -> int:
    report = load_report(os.environ.get("TRIVY_FILE", ""))
    show_details = bool_env("SHOW_DETAILS")
    try:
        max_rows = int(os.environ.get("MAX_ROWS", DEFAULT_MAX_ROWS))
    except ValueError:
        max_rows = DEFAULT_MAX_ROWS

    if isinstance(report, dict):
        findings = collect_findings(report)
        counts = count_by_severity(findings)
        outputs = {"scan_ok": "true"}
    else:
        findings, counts = [], None
        outputs = {"scan_ok": "false"}

    effective = counts or {severity: 0 for severity in SEVERITIES}
    for severity in SEVERITIES:
        outputs[f"vuln_{severity.lower()}"] = str(effective[severity])
    outputs["vuln_total"] = str(sum(effective.values()))
    write_outputs(os.environ.get("GITHUB_OUTPUT", ""), outputs)

    summary = build_summary(
        image=os.environ.get("IMAGE_DISPLAY", ""),
        trivy_version=os.environ.get("TRIVY_VERSION", ""),
        counts=counts,
        findings=findings,
        show_details=show_details,
        visibility=os.environ.get("REPO_VISIBILITY", ""),
        max_rows=max_rows,
    )
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if summary_path and bool_env("WRITE_STEP_SUMMARY", default=True):
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write(summary)

    if counts is None:
        print("Trivy report missing or unreadable.")
    else:
        print(
            "Trivy findings: "
            + ", ".join(f"{s.lower()}={counts[s]}" for s in SEVERITIES)
            + f", total={sum(counts.values())}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
