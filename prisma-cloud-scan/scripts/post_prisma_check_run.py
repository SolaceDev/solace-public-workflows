#!/usr/bin/env python3
"""Post Prisma Cloud check run details to GitHub Checks API.

This script mirrors the previous inline JavaScript implementation from action.yml
to keep behavior the same while improving maintainability.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _bootstrap_common_module() -> None:
    script_path = Path(__file__).resolve()
    for parent in script_path.parents:
        # Current repository layout keeps shared helpers in `common/`.
        current_candidate = parent / "common" / "github_reporting.py"
        if current_candidate.exists():
            sys.path.insert(0, str(current_candidate.parent))
            return

        # Backward compatibility for older layouts.
        legacy_candidate = parent / ".github" / "scripts" / "common" / "github_reporting.py"
        if legacy_candidate.exists():
            sys.path.insert(0, str(legacy_candidate.parent))
            return


_bootstrap_common_module()

from github_reporting import github_api  # type: ignore  # noqa: E402


def norm(value: Any) -> str:
    return str(value or "").strip()


def to_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return fallback


def to_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(str(value).strip())
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


def append_step_summary(markdown: str) -> None:
    summary_path = get_env("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    with open(summary_path, "a", encoding="utf-8") as handle:
        handle.write(markdown.rstrip())
        handle.write("\n")


def md_code(value: Any) -> str:
    text = md_escape(value).replace("`", "'")
    return f"`{text or '-'}`"


def severity_emoji(value: Any) -> str:
    return {
        "critical": "🔴",
        "high": "🟠",
        "medium": "🟡",
        "low": "🔵",
    }.get(normalize_severity(value), "⚪")


def severity_label(value: Any) -> str:
    normalized = normalize_severity(value)
    if not normalized:
        return "-"
    return f"{severity_emoji(normalized)} {normalized.capitalize()}"


def format_fix_status(value: Any) -> str:
    text = md_escape(value)
    if not text:
        return "-"
    prefix = "fixed in "
    if text.lower().startswith(prefix):
        suffix = text[len(prefix) :]
        parts = [part.strip() for part in suffix.split(",")]
        rendered_parts = []
        for part in parts:
            if not part:
                continue
            if part == "...":
                rendered_parts.append("...")
            else:
                rendered_parts.append(md_code(part))
        if rendered_parts:
            return prefix + ", ".join(rendered_parts)
    return text


def parse_image_reference(image_ref: str) -> tuple[str, str, str, str]:
    raw = norm(image_ref)
    if not raw:
        return "", "", "", ""

    name_part = raw
    digest = ""
    if "@" in raw:
        name_part, digest = raw.split("@", 1)

    last_slash = name_part.rfind("/")
    last_colon = name_part.rfind(":")
    tag = ""
    if last_colon > last_slash:
        tag = name_part[last_colon + 1 :]
        name_part = name_part[:last_colon]

    if "/" not in name_part:
        return "", name_part, tag, digest

    registry, repository = name_part.split("/", 1)
    return registry, repository, tag, digest


def build_ecr_image_url(registry: str, repository: str, image_digest: str) -> str:
    match = re.match(r"^(?P<account>\d+)\.dkr\.ecr\.(?P<region>[a-z0-9-]+)\.amazonaws\.com(?:\.cn)?$", registry)
    if not match or not repository or not image_digest:
        return ""
    account = match.group("account")
    region = match.group("region")
    return (
        f"https://{region}.console.aws.amazon.com/ecr/repositories/private/"
        f"{account}/{repository}/_/image/{image_digest}/details?region={region}"
    )


def build_commit_url(target_sha: str) -> str:
    server_url = get_env("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
    repository = get_env("GITHUB_REPOSITORY")
    if not server_url or not repository or not target_sha:
        return ""
    return f"{server_url}/{repository}/commit/{target_sha}"


def build_image_markdown(image_ref: str, image_digest: str) -> tuple[str, str]:
    registry, repository, tag, embedded_digest = parse_image_reference(image_ref)
    resolved_digest = norm(image_digest) or embedded_digest

    if registry and repository:
        if tag:
            image_label = md_code(f"{repository}:{tag}")
        elif resolved_digest:
            image_label = md_code(f"{repository}@{resolved_digest}")
        else:
            image_label = md_code(repository)
    else:
        image_label = md_code(image_ref or "unknown")

    image_url = build_ecr_image_url(registry, repository, resolved_digest)
    image_markdown = f"[{image_label}]({image_url})" if image_url else image_label
    return image_markdown, md_code(registry) if registry else "-"


def read_github_event() -> dict[str, Any]:
    event_path = get_env("GITHUB_EVENT_PATH")
    if not event_path or not os.path.exists(event_path):
        return {}
    try:
        with open(event_path, "r", encoding="utf-8") as handle:
            parsed = json.load(handle)
            return parsed if isinstance(parsed, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def resolve_target_sha() -> str:
    event_payload = read_github_event()
    pull_request = event_payload.get("pull_request") if isinstance(event_payload, dict) else None
    if isinstance(pull_request, dict):
        head = pull_request.get("head")
        if isinstance(head, dict):
            pull_request_head_sha = norm(head.get("sha"))
            if pull_request_head_sha:
                return pull_request_head_sha
    return get_env("TARGET_SHA") or get_env("PR_HEAD_SHA") or get_env("GITHUB_SHA")


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
    guardian_managed_vulnerabilities: bool,
) -> str:
    severity_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    details_lines: list[str] = []

    grace_period_seconds = max(grace_days, 0) * 86400
    now_seconds = int(datetime.now(tz=timezone.utc).timestamp())

    def is_blocking_vulnerability(vulnerability: dict[str, Any]) -> bool:
        if guardian_managed_vulnerabilities:
            return False
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
                    0 if is_blocking_vulnerability(vuln) else 1,
                    -(severity_rank.get(normalize_severity(vuln.get("severity")), 0)),
                    -to_float(vuln.get("cvss"), 0.0),
                )
            )
            compliances.sort(
                key=lambda issue: (
                    0 if is_blocking_compliance(issue) else 1,
                    -(severity_rank.get(normalize_severity(issue.get("severity")), 0)),
                )
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
                                truncate(severity_label(vulnerability.get("severity") or "-"), 16),
                                truncate(vulnerability.get("cvss", "-"), 8),
                                truncate(vulnerability.get("packageName") or "-", 30),
                                truncate(md_code(vulnerability.get("packageVersion") or "-"), 32),
                                truncate(format_fix_status(vulnerability.get("status") or "-"), 72),
                                truncate(as_date_string(vulnerability.get("publishedDate")) or "-", 20),
                                truncate(as_date_string(vulnerability.get("discoveredDate")) or "-", 20),
                                truncate(vulnerability.get("description") or "-", 150),
                                "🚫 Yes" if is_blocking_vulnerability(vulnerability) else "✅ No",
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
                                truncate(severity_label(compliance_issue.get("severity") or "-"), 16),
                                truncate(compliance_issue.get("description") or "-", 180),
                                "🚫 Yes" if is_blocking_compliance(compliance_issue) else "✅ No",
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


def post_check_run(payload: dict[str, Any]) -> dict[str, Any]:
    token = get_env("GITHUB_TOKEN")
    repository = get_env("GITHUB_REPOSITORY")
    api_url = get_env("GITHUB_API_URL", "https://api.github.com")

    if not token:
        raise RuntimeError("GITHUB_TOKEN is required to create a check run.")
    if not repository or "/" not in repository:
        raise RuntimeError("GITHUB_REPOSITORY is missing or invalid.")

    owner, repo = repository.split("/", 1)
    endpoint = f"{api_url}/repos/{owner}/{repo}/check-runs"
    response = github_api(
        "POST",
        endpoint,
        token,
        payload=payload,
        user_agent="solace-public-workflows/prisma-cloud-scan",
    )
    return response if isinstance(response, dict) else {}


def main() -> int:
    analysis = read_analysis_results()

    scan_passed = to_bool(analysis.get("scan_passed"), default=bool_env("SCAN_PASSED", default=False))
    conclusion = "success" if scan_passed else "failure"
    guardian_managed_vulnerabilities = to_bool(
        analysis.get("guardian_managed_vulnerabilities"),
        default=bool_env("GUARDIAN_ENABLED", default=False),
    )

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

    image_name = get_env("IMAGE_NAME")
    image_digest = get_env("IMAGE_DIGEST")
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
    target_sha = resolve_target_sha()
    check_name = f"Prisma Image Scan ({system_label})" if system_label else "Prisma Image Scan"

    target_url = get_env("CONSOLE_LINK")
    if not target_url:
        pcc_console_url = get_env("PCC_CONSOLE_URL")
        target_url = f"{pcc_console_url}/compute?computeState=/monitor/vulnerabilities/images/ci"

    fallback_image = get_env("FALLBACK_IMAGE")
    resolved_image = image_name or fallback_image
    image_markdown, registry_markdown = build_image_markdown(resolved_image, image_digest)
    commit_url = build_commit_url(target_sha)
    sha_markdown = f"[{md_code(target_sha)}]({commit_url})" if commit_url else md_code(target_sha)
    vulnerability_total = vuln_critical + vuln_high + vuln_medium + vuln_low
    compliance_total = compliance_critical + compliance_high + compliance_medium + compliance_low
    blocking_vuln_total = blocking_vuln_critical + blocking_vuln_high
    blocking_compliance_total = blocking_compliance_critical + blocking_compliance_high

    overall_scan_status = "✅ Passed" if scan_passed else "❌ Failed"
    if guardian_managed_vulnerabilities:
        vulnerability_policy_status = "🛡️ Guardian-managed"
    elif blocking_vuln_total > 0:
        vulnerability_policy_status = f"❌ {blocking_vuln_total} blocking"
    else:
        vulnerability_policy_status = "✅ No blocking vulnerabilities"

    if block_on_compliance:
        if blocking_compliance_total > 0:
            compliance_policy_status = f"❌ {blocking_compliance_total} blocking"
        else:
            compliance_policy_status = "✅ No blocking compliance issues"
    else:
        compliance_policy_status = "⚪ Report only"

    summary_lines = [
        "### Prisma Image Scan Overview",
        f"- **Prisma results:** [Open full results in Prisma Cloud]({target_url})",
        f"- **Image:** {image_markdown}",
        f"- **Container Registry:** {registry_markdown}",
        f"- **Scanned SHA:** {sha_markdown}",
        "",
        "| Check | Status |",
        "| --- | --- |",
        f"| Overall scan | {overall_scan_status} |",
        f"| Vulnerability blocking | {vulnerability_policy_status} |",
        f"| Compliance blocking | {compliance_policy_status} |",
        "",
        "| Category | 🔴 Critical | 🟠 High | 🟡 Medium | 🔵 Low | Total | 🚫 Blocking |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        f"| Vulnerabilities | {vuln_critical} | {vuln_high} | {vuln_medium} | {vuln_low} | {vulnerability_total} | {blocking_vuln_total} |",
        f"| Compliance | {compliance_critical} | {compliance_high} | {compliance_medium} | {compliance_low} | {compliance_total} | {blocking_compliance_total} |",
        f"| **Combined** | **{vuln_critical + compliance_critical}** | **{vuln_high + compliance_high}** | **{vuln_medium + compliance_medium}** | **{vuln_low + compliance_low}** | **{vulnerability_total + compliance_total}** | **{blocking_total}** |",
    ]
    if guardian_managed_vulnerabilities:
        summary_lines.extend(
            [
                "",
                "> 🛡️ Guardian manages vulnerability thresholds for this scan. Prisma findings are reported here, but vulnerability blocking is delegated to Guardian.",
            ]
        )
    else:
        summary_lines.extend(
            [
                "",
                f"> Local vulnerability policy: critical and high findings block after a `{grace_days}`-day grace period.",
            ]
        )
    if not block_on_compliance:
        summary_lines.append(
            "> Compliance findings are reported for visibility only because `block_on_compliance=false`."
        )
    summary_markdown = "\n".join(summary_lines)

    details_text = build_detailed_text(
        detailed_tables_enabled=detailed_tables_enabled,
        repo_visibility=repo_visibility,
        show_detailed_logs=show_detailed_logs,
        target_url=target_url,
        grace_days=grace_days,
        block_on_compliance=block_on_compliance,
        guardian_managed_vulnerabilities=guardian_managed_vulnerabilities,
    )

    append_step_summary(summary_markdown)

    payload = {
        "name": check_name,
        "head_sha": target_sha,
        "status": "completed",
        "conclusion": conclusion,
        "details_url": target_url,
        "output": {
            "title": "✅ Prisma Image Scan passed" if scan_passed else "❌ Prisma Image Scan failed",
            "summary": summary_markdown,
            "text": details_text,
        },
    }

    try:
        posted_check_run = post_check_run(payload) or {}
        posted_check_url = norm(posted_check_run.get("html_url"))
        print(f"✅ Posted check run: {conclusion} (sha={target_sha})")
        if posted_check_url:
            print(f"🔗 Check run URL: {posted_check_url}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(
            f"Failed to create dedicated Prisma check run: {exc}. "
            "Ensure workflow token has `checks: write` permission.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
