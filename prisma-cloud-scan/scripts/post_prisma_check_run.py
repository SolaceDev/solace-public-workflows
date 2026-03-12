#!/usr/bin/env python3
"""Post Prisma Cloud check run details to GitHub Checks API.

This script mirrors the previous inline JavaScript implementation from action.yml
to keep behavior the same while improving maintainability.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any
from urllib import error, request


def norm(value: Any) -> str:
    return str(value or "").strip()


def to_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return fallback


def md_escape(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\r\n", " ").replace("\n", " ").strip()


def truncate(value: Any, max_len: int = 140) -> str:
    text = md_escape(value)
    return text if len(text) <= max_len else f"{text[: max_len - 3]}..."


def normalize_severity(value: Any) -> str:
    return norm(value).lower()


def as_date_string(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).strftime("%Y-%m-%d")
        except (OverflowError, OSError, ValueError):
            return str(value)
    text = str(value)
    parsed = parse_datetime_to_epoch(text)
    if parsed is not None:
        return datetime.fromtimestamp(parsed, tz=timezone.utc).strftime("%Y-%m-%d")
    return text


def parse_datetime_to_epoch(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        number = int(value)
        # Prisma can return milliseconds in some places.
        return number // 1000 if number > 1_000_000_000_000 else number

    text = str(value).strip()
    if not text:
        return None

    # Support ISO timestamps with trailing "Z".
    iso_text = text.replace("Z", "+00:00") if text.endswith("Z") else text
    try:
        return int(datetime.fromisoformat(iso_text).timestamp())
    except ValueError:
        pass

    # Fallback to YYYY-MM-DD.
    try:
        return int(datetime.strptime(text.split("T", 1)[0], "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    except ValueError:
        return None


def bool_env(name: str, default: bool = False) -> bool:
    raw = norm(os.getenv(name))
    if not raw:
        return default
    return raw.lower() == "true"


def to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    raw = norm(value).lower()
    if not raw:
        return default
    return raw == "true"


def get_env(name: str, default: str = "") -> str:
    return norm(os.getenv(name, default))


def read_scan_results() -> dict[str, Any]:
    with open("pcc_scan_results.json", "r", encoding="utf-8") as handle:
        return json.load(handle)


def read_analysis_results() -> dict[str, Any]:
    path = get_env("ANALYSIS_FILE", "pcc_scan_analysis.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            parsed = json.load(handle)
            return parsed if isinstance(parsed, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def build_detailed_text(
    *,
    detailed_tables_enabled: bool,
    repo_visibility: str,
    show_detailed_logs: bool,
    target_url: str,
    grace_days: int,
    block_on_compliance: bool,
) -> str:
    severity_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    details_lines: list[str] = []

    grace_period_seconds = max(grace_days, 0) * 86400
    now_seconds = int(datetime.now(tz=timezone.utc).timestamp())

    def is_blocking_vulnerability(vulnerability: dict[str, Any]) -> bool:
        severity = normalize_severity(vulnerability.get("severity"))
        if severity not in {"critical", "high"}:
            return False
        if grace_period_seconds <= 0:
            return True
        published_epoch = parse_datetime_to_epoch(vulnerability.get("publishedDate"))
        if published_epoch is None:
            # Keep same fail-safe behavior as previous implementation.
            return True
        return published_epoch < (now_seconds - grace_period_seconds)

    def is_blocking_compliance(compliance_issue: dict[str, Any]) -> bool:
        if not block_on_compliance:
            return False
        severity = normalize_severity(compliance_issue.get("severity"))
        return severity in {"critical", "high"}

    if detailed_tables_enabled:
        if not os.path.exists("pcc_scan_results.json"):
            details_lines.append("Detailed issue tables unavailable because `pcc_scan_results.json` was not found.")
            return "\n".join(details_lines)

        try:
            parsed_scan_data = read_scan_results()
            result = {}
            if isinstance(parsed_scan_data, dict):
                results = parsed_scan_data.get("results")
                if isinstance(results, list) and results:
                    first = results[0]
                    if isinstance(first, dict):
                        result = first

            vulnerabilities = result.get("vulnerabilities", []) if isinstance(result, dict) else []
            compliances = result.get("compliances", []) if isinstance(result, dict) else []
            vulnerabilities = vulnerabilities if isinstance(vulnerabilities, list) else []
            compliances = compliances if isinstance(compliances, list) else []

            vulnerabilities.sort(
                key=lambda vuln: (
                    -(severity_rank.get(normalize_severity(vuln.get("severity")), 0)),
                    -float(vuln.get("cvss") or 0),
                )
            )
            compliances.sort(
                key=lambda issue: (-(severity_rank.get(normalize_severity(issue.get("severity")), 0)))
            )

            max_vulnerability_rows = 25
            max_compliance_rows = 15

            details_lines.append("### Vulnerability Issues (quick view)")
            details_lines.append(
                "| CVE | Severity | CVSS | Package | Version | Status | Published | Discovered | Description | Triggered Failure |"
            )
            details_lines.append("| --- | --- | ---: | --- | --- | --- | --- | --- | --- | --- |")
            if not vulnerabilities:
                details_lines.append("| _None_ | - | - | - | - | - | - | - | No vulnerabilities reported. | - |")
            else:
                for vulnerability in vulnerabilities[:max_vulnerability_rows]:
                    details_lines.append(
                        "| "
                        + " | ".join(
                            [
                                truncate(vulnerability.get("id") or vulnerability.get("cve") or "-", 60),
                                truncate(vulnerability.get("severity") or "-", 12),
                                truncate(vulnerability.get("cvss", "-"), 8),
                                truncate(vulnerability.get("packageName") or "-", 30),
                                truncate(vulnerability.get("packageVersion") or "-", 20),
                                truncate(vulnerability.get("status") or "-", 36),
                                truncate(as_date_string(vulnerability.get("publishedDate")) or "-", 20),
                                truncate(as_date_string(vulnerability.get("discoveredDate")) or "-", 20),
                                truncate(vulnerability.get("description") or "-", 150),
                                "Yes" if is_blocking_vulnerability(vulnerability) else "No",
                            ]
                        )
                        + " |"
                    )

                if len(vulnerabilities) > max_vulnerability_rows:
                    details_lines.append("")
                    details_lines.append(
                        f"_Showing {max_vulnerability_rows} of {len(vulnerabilities)} vulnerability issues._"
                    )

            details_lines.append("")
            details_lines.append("### Compliance Issues (quick view)")
            details_lines.append("| ID / Title | Severity | Description | Triggered Failure |")
            details_lines.append("| --- | --- | --- | --- |")
            if not compliances:
                details_lines.append("| _None_ | - | No compliance issues reported. | - |")
            else:
                for compliance_issue in compliances[:max_compliance_rows]:
                    issue_id = compliance_issue.get("id")
                    issue_title = compliance_issue.get("title")
                    if issue_id:
                        compliance_id_or_title = f"{issue_id}{f' - {issue_title}' if issue_title else ''}"
                    else:
                        compliance_id_or_title = issue_title or "-"
                    details_lines.append(
                        "| "
                        + " | ".join(
                            [
                                truncate(compliance_id_or_title, 80),
                                truncate(compliance_issue.get("severity") or "-", 12),
                                truncate(compliance_issue.get("description") or "-", 180),
                                "Yes" if is_blocking_compliance(compliance_issue) else "No",
                            ]
                        )
                        + " |"
                    )
                if len(compliances) > max_compliance_rows:
                    details_lines.append("")
                    details_lines.append(
                        f"_Showing {max_compliance_rows} of {len(compliances)} compliance issues._"
                    )
        except Exception as render_error:  # noqa: BLE001
            details_lines.append(f"Unable to render detailed issue tables: {md_escape(render_error)}")
    else:
        details_lines.append("Detailed issue rows are hidden.")
        if repo_visibility == "public":
            details_lines.append("Repository visibility is `public` and detailed mode is hidden by default.")
        if not show_detailed_logs:
            details_lines.append('Set `show_detailed_logs: "true"` to include quick issue tables in this check run.')
        details_lines.append(
            f"Use [Prisma Console results]({target_url}) and the uploaded artifacts for full details."
        )

    return "\n".join(details_lines)


def post_check_run(payload: dict[str, Any]) -> None:
    token = get_env("GITHUB_TOKEN")
    repository = get_env("GITHUB_REPOSITORY")
    api_url = get_env("GITHUB_API_URL", "https://api.github.com")

    if not token:
        raise RuntimeError("GITHUB_TOKEN is required to create a check run.")
    if not repository or "/" not in repository:
        raise RuntimeError("GITHUB_REPOSITORY is missing or invalid.")

    owner, repo = repository.split("/", 1)
    endpoint = f"{api_url}/repos/{owner}/{repo}/check-runs"

    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    with request.urlopen(req) as response:  # noqa: S310 (GitHub API URL from env in runner context)
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"GitHub API returned status {response.status}")


def main() -> int:
    analysis = read_analysis_results()

    scan_passed = to_bool(analysis.get("scan_passed"), default=bool_env("SCAN_PASSED", default=False))
    conclusion = "success" if scan_passed else "failure"

    vuln_critical = to_int(analysis.get("vuln_critical"), to_int(os.getenv("VULN_CRITICAL")))
    vuln_high = to_int(analysis.get("vuln_high"), to_int(os.getenv("VULN_HIGH")))
    vuln_medium = to_int(analysis.get("vuln_medium"), to_int(os.getenv("VULN_MEDIUM")))
    vuln_low = to_int(analysis.get("vuln_low"), to_int(os.getenv("VULN_LOW")))

    compliance_critical = to_int(analysis.get("compliance_critical"), to_int(os.getenv("COMPLIANCE_CRITICAL")))
    compliance_high = to_int(analysis.get("compliance_high"), to_int(os.getenv("COMPLIANCE_HIGH")))
    compliance_medium = to_int(analysis.get("compliance_medium"), to_int(os.getenv("COMPLIANCE_MEDIUM")))
    compliance_low = to_int(analysis.get("compliance_low"), to_int(os.getenv("COMPLIANCE_LOW")))

    blocking_vuln_critical = to_int(
        analysis.get("blocking_vuln_critical"), to_int(os.getenv("BLOCKING_VULN_CRITICAL"))
    )
    blocking_vuln_high = to_int(analysis.get("blocking_vuln_high"), to_int(os.getenv("BLOCKING_VULN_HIGH")))
    blocking_compliance_critical = to_int(
        analysis.get("blocking_compliance_critical"), to_int(os.getenv("BLOCKING_COMPLIANCE_CRITICAL"))
    )
    blocking_compliance_high = to_int(
        analysis.get("blocking_compliance_high"), to_int(os.getenv("BLOCKING_COMPLIANCE_HIGH"))
    )
    blocking_total = to_int(
        analysis.get("blocking_total", os.getenv("BLOCKING_TOTAL")),
        blocking_vuln_critical + blocking_vuln_high + blocking_compliance_critical + blocking_compliance_high,
    )

    scan_exit_code = get_env("SCAN_EXIT_CODE", "unknown")
    image_name = get_env("IMAGE_NAME")
    repo_visibility = get_env("REPO_VISIBILITY", "private")
    show_detailed_logs = bool_env("SHOW_DETAILED_LOGS", default=False)
    detailed_tables_enabled = show_detailed_logs and repo_visibility != "public"
    grace_days = to_int(analysis.get("grace_days"), to_int(os.getenv("GRACE_DAYS"), 7))
    block_on_compliance = to_bool(
        analysis.get("block_on_compliance"), default=bool_env("BLOCK_ON_COMPLIANCE", default=False)
    )

    runner_os = get_env("RUNNER_OS")
    runner_arch = get_env("RUNNER_ARCH")
    system_label = "/".join(part for part in [runner_os, runner_arch] if part)
    target_sha = get_env("TARGET_SHA") or get_env("PR_HEAD_SHA") or get_env("GITHUB_SHA")
    check_name = f"Prisma Image Scan ({system_label})" if system_label else "Prisma Image Scan"

    target_url = get_env("CONSOLE_LINK")
    if not target_url:
        pcc_console_url = get_env("PCC_CONSOLE_URL")
        target_url = f"{pcc_console_url}/compute?computeState=/monitor/vulnerabilities/images/ci"

    fallback_image = get_env("FALLBACK_IMAGE")
    vulnerability_total = vuln_critical + vuln_high + vuln_medium + vuln_low
    compliance_total = compliance_critical + compliance_high + compliance_medium + compliance_low
    blocking_vuln_total = blocking_vuln_critical + blocking_vuln_high
    blocking_compliance_total = blocking_compliance_critical + blocking_compliance_high

    summary_markdown = "\n".join(
        [
            "### Prisma Image Scan Overview",
            f"- **Result:** {'PASS' if scan_passed else 'FAIL'}",
            f"- **System:** `{md_escape(system_label or 'unknown')}`",
            f"- **Image:** `{md_escape(image_name or fallback_image)}`",
            f"- **Blocking issues:** **{blocking_total}**",
            f"- **Check SHA:** `{md_escape(target_sha)}`",
            f"- **twistcli exit code:** `{md_escape(scan_exit_code)}`",
            f"- **Prisma results:** [Open full results in Prisma Cloud]({target_url})",
            "",
            "| Category | Critical | High | Medium | Low | Total | Blocking |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            f"| Vulnerabilities | {vuln_critical} | {vuln_high} | {vuln_medium} | {vuln_low} | {vulnerability_total} | {blocking_vuln_total} |",
            f"| Compliance | {compliance_critical} | {compliance_high} | {compliance_medium} | {compliance_low} | {compliance_total} | {blocking_compliance_total} |",
            f"| **Combined** | **{vuln_critical + compliance_critical}** | **{vuln_high + compliance_high}** | **{vuln_medium + compliance_medium}** | **{vuln_low + compliance_low}** | **{vulnerability_total + compliance_total}** | **{blocking_total}** |",
            "",
            f"Policy settings: `block_on_compliance={str(block_on_compliance).lower()}`, `vulnerability_grace_period_days={grace_days}`",
        ]
    )

    details_text = build_detailed_text(
        detailed_tables_enabled=detailed_tables_enabled,
        repo_visibility=repo_visibility,
        show_detailed_logs=show_detailed_logs,
        target_url=target_url,
        grace_days=grace_days,
        block_on_compliance=block_on_compliance,
    )

    payload = {
        "name": check_name,
        "head_sha": target_sha,
        "status": "completed",
        "conclusion": conclusion,
        "details_url": target_url,
        "output": {
            "title": "Prisma Image Scan passed" if scan_passed else "Prisma Image Scan failed",
            "summary": summary_markdown,
            "text": details_text,
        },
    }

    try:
        post_check_run(payload)
        print(f"✅ Posted check run: {conclusion}")
        return 0
    except error.HTTPError as http_err:
        message = http_err.reason
        try:
            body = http_err.read().decode("utf-8")
            parsed = json.loads(body) if body else {}
            message = parsed.get("message") or message
        except Exception:  # noqa: BLE001
            pass
        print(
            f"Failed to create dedicated Prisma check run: {message}. "
            "Ensure workflow token has `checks: write` permission.",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:  # noqa: BLE001
        print(
            f"Failed to create dedicated Prisma check run: {exc}. "
            "Ensure workflow token has `checks: write` permission.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
