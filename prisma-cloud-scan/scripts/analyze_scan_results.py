#!/usr/bin/env python3
"""Analyze Prisma scan JSON, emit outputs, and enforce blocking policy."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any


ANALYSIS_FILE = "pcc_scan_analysis.json"
RESULTS_FILE = "pcc_scan_results.json"
SEVERITIES = ("critical", "high", "medium", "low")
SUMMARY_SEPARATOR = "=========================================="


def norm(value: Any) -> str:
    return str(value or "").strip()


def to_int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def to_bool(value: Any, default: bool = False) -> bool:
    raw = norm(value).lower()
    if raw == "":
        return default
    return raw == "true"


def write_output(key: str, value: Any) -> None:
    output_path = os.getenv("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as handle:
        handle.write(f"{key}={value}\n")


def write_outputs(values: dict[str, Any]) -> None:
    for key, value in values.items():
        write_output(key, value)


def write_analysis_file(values: dict[str, Any]) -> None:
    with open(ANALYSIS_FILE, "w", encoding="utf-8") as handle:
        json.dump(values, handle, indent=2, sort_keys=True)


def severity_count(items: list[dict[str, Any]], severity: str) -> int:
    target = severity.lower()
    return sum(1 for item in items if norm(item.get("severity")).lower() == target)


def parse_string_date_to_epoch(date_text: str) -> int | None:
    normalized = norm(date_text)
    if not normalized:
        return None
    date_part = normalized.split("T", 1)[0]
    try:
        dt = datetime.strptime(date_part, "%Y-%m-%d")
        return int(dt.replace(tzinfo=timezone.utc).timestamp())
    except ValueError:
        return None


def parse_published_date_to_epoch(published_date: Any) -> int:
    if isinstance(published_date, (int, float)):
        # Preserve existing behavior from jq logic: compare numeric value as-is.
        return int(published_date)
    parsed = parse_string_date_to_epoch(str(published_date))
    if parsed is None:
        raise ValueError(f"Unable to parse publishedDate: {published_date}")
    return parsed


def compute_blocking_vulnerability_count(
    vulnerabilities: list[dict[str, Any]],
    severity: str,
    threshold_epoch: int,
    fallback_count: int,
) -> int:
    try:
        count = 0
        for vulnerability in vulnerabilities:
            if norm(vulnerability.get("severity")).lower() != severity:
                continue
            published_epoch = parse_published_date_to_epoch(vulnerability.get("publishedDate", 0))
            if published_epoch < threshold_epoch:
                count += 1
        return count
    except Exception:  # noqa: BLE001
        # Match previous shell+jq behavior: if parsing fails, fall back to total count.
        return fallback_count


def load_scan_json() -> dict[str, Any]:
    with open(RESULTS_FILE, "r", encoding="utf-8") as handle:
        return json.load(handle)


def empty_counts() -> dict[str, int]:
    return {f"{category}_{severity}": 0 for category in ("vuln", "compliance") for severity in SEVERITIES}


def main() -> int:
    print("📊 Analyzing Prisma Cloud scan results...")

    block_on_compliance = to_bool(os.getenv("BLOCK_ON_COMPLIANCE"), default=False)
    grace_period_days = to_int(os.getenv("GRACE_PERIOD_DAYS"), default=7)
    guardian_managed_vulnerabilities = to_bool(os.getenv("GUARDIAN_ENABLED"), default=False)
    grace_period_seconds = grace_period_days * 86400
    current_timestamp = int(datetime.now(tz=timezone.utc).timestamp())
    console_link = norm(os.getenv("CONSOLE_LINK"))
    if not console_link:
        console_link = norm(os.getenv("PCC_CONSOLE_URL"))

    print("Configuration:")
    print(f"  Block on compliance: {str(block_on_compliance).lower()}")
    print(f"  Vulnerability grace period: {grace_period_days} days")
    print(
        "  Vulnerability blocking delegated to Guardian: "
        f"{str(guardian_managed_vulnerabilities).lower()}"
    )

    if not os.path.exists(RESULTS_FILE):
        print(f"❌ Error: {RESULTS_FILE} not found", file=sys.stderr)
        baseline = {
            "scan_passed": False,
            "block_on_compliance": block_on_compliance,
            "grace_days": grace_period_days,
            "blocking_total": 0,
            **empty_counts(),
            "blocking_vuln_critical": 0,
            "blocking_vuln_high": 0,
            "blocking_compliance_critical": 0,
            "blocking_compliance_high": 0,
            "guardian_managed_vulnerabilities": guardian_managed_vulnerabilities,
            "error": "results_file_missing",
        }
        write_analysis_file(baseline)
        write_outputs({"scan_passed": "false"})
        return 1

    try:
        scan_data = load_scan_json()
    except json.JSONDecodeError:
        print("❌ Error: Invalid JSON in scan results file", file=sys.stderr)
        baseline = {
            "scan_passed": False,
            "block_on_compliance": block_on_compliance,
            "grace_days": grace_period_days,
            "blocking_total": 0,
            **empty_counts(),
            "blocking_vuln_critical": 0,
            "blocking_vuln_high": 0,
            "blocking_compliance_critical": 0,
            "blocking_compliance_high": 0,
            "guardian_managed_vulnerabilities": guardian_managed_vulnerabilities,
            "error": "invalid_json",
        }
        write_analysis_file(baseline)
        write_outputs({"scan_passed": "false"})
        return 1
    except OSError as err:
        print(f"❌ Error reading {RESULTS_FILE}: {err}", file=sys.stderr)
        baseline = {
            "scan_passed": False,
            "block_on_compliance": block_on_compliance,
            "grace_days": grace_period_days,
            "blocking_total": 0,
            **empty_counts(),
            "blocking_vuln_critical": 0,
            "blocking_vuln_high": 0,
            "blocking_compliance_critical": 0,
            "blocking_compliance_high": 0,
            "guardian_managed_vulnerabilities": guardian_managed_vulnerabilities,
            "error": "read_error",
        }
        write_analysis_file(baseline)
        write_outputs({"scan_passed": "false"})
        return 1

    results = scan_data.get("results")
    first_result = results[0] if isinstance(results, list) and results and isinstance(results[0], dict) else {}
    vulnerabilities = first_result.get("vulnerabilities")
    compliances = first_result.get("compliances")
    vulnerabilities = vulnerabilities if isinstance(vulnerabilities, list) else []
    compliances = compliances if isinstance(compliances, list) else []

    vuln_counts = {severity: severity_count(vulnerabilities, severity) for severity in SEVERITIES}
    compliance_counts = {severity: severity_count(compliances, severity) for severity in SEVERITIES}

    # Match existing fallback behavior.
    if (
        vuln_counts["critical"] == 0
        and vuln_counts["high"] == 0
        and compliance_counts["critical"] == 0
        and compliance_counts["high"] == 0
    ):
        vulnerability_distribution = first_result.get("vulnerabilityDistribution", {})
        compliance_distribution = first_result.get("complianceDistribution", {})
        if not isinstance(vulnerability_distribution, dict):
            vulnerability_distribution = {}
        if not isinstance(compliance_distribution, dict):
            compliance_distribution = {}

        for severity in SEVERITIES:
            vuln_counts[severity] = to_int(vulnerability_distribution.get(severity), default=0)
            compliance_counts[severity] = to_int(compliance_distribution.get(severity), default=0)

    blocking_vuln_critical = 0
    blocking_vuln_high = 0
    grace_vuln_critical = 0
    grace_vuln_high = 0

    if guardian_managed_vulnerabilities:
        blocking_vuln_critical = 0
        blocking_vuln_high = 0
        grace_vuln_critical = 0
        grace_vuln_high = 0
    elif grace_period_days > 0:
        threshold_epoch = current_timestamp - grace_period_seconds
        blocking_vuln_critical = compute_blocking_vulnerability_count(
            vulnerabilities, "critical", threshold_epoch, vuln_counts["critical"]
        )
        blocking_vuln_high = compute_blocking_vulnerability_count(
            vulnerabilities, "high", threshold_epoch, vuln_counts["high"]
        )
        grace_vuln_critical = vuln_counts["critical"] - blocking_vuln_critical
        grace_vuln_high = vuln_counts["high"] - blocking_vuln_high
    else:
        blocking_vuln_critical = vuln_counts["critical"]
        blocking_vuln_high = vuln_counts["high"]

    blocking_compliance_critical = compliance_counts["critical"] if block_on_compliance else 0
    blocking_compliance_high = compliance_counts["high"] if block_on_compliance else 0

    blocking_total = (
        blocking_vuln_critical
        + blocking_vuln_high
        + blocking_compliance_critical
        + blocking_compliance_high
    )
    blocking_issues = blocking_total > 0

    print(SUMMARY_SEPARATOR)
    print("Prisma Cloud Scan Results Summary")
    print(SUMMARY_SEPARATOR)
    print("Vulnerabilities:")
    print(
        f"  Critical: {vuln_counts['critical']} "
        f"(blocking: {blocking_vuln_critical}, in grace period: {grace_vuln_critical})"
    )
    print(
        f"  High:     {vuln_counts['high']} "
        f"(blocking: {blocking_vuln_high}, in grace period: {grace_vuln_high})"
    )
    print(f"  Medium:   {vuln_counts['medium']}")
    print(f"  Low:      {vuln_counts['low']}")
    print("")
    print(f"Compliance Issues (block_on_compliance={str(block_on_compliance).lower()}):")
    print(f"  Critical: {compliance_counts['critical']}")
    print(f"  High:     {compliance_counts['high']}")
    print(f"  Medium:   {compliance_counts['medium']}")
    print(f"  Low:      {compliance_counts['low']}")
    print(SUMMARY_SEPARATOR)

    if guardian_managed_vulnerabilities:
        print("🛡️ Guardian upload is configured; vulnerability blocking is delegated to Guardian.")
        if vuln_counts["critical"] > 0 or vuln_counts["high"] > 0:
            print(
                f"   Reported critical/high vulnerabilities: "
                f"{vuln_counts['critical']} critical, {vuln_counts['high']} high"
            )
    elif blocking_vuln_critical > 0:
        print(
            f"❌ BLOCKING: Found {blocking_vuln_critical} critical vulnerabilities "
            f"past {grace_period_days}-day grace period"
        )
    if blocking_vuln_high > 0:
        print(
            f"❌ BLOCKING: Found {blocking_vuln_high} high severity vulnerabilities "
            f"past {grace_period_days}-day grace period"
        )
    if block_on_compliance:
        if blocking_compliance_critical > 0:
            print(f"❌ BLOCKING: Found {blocking_compliance_critical} critical compliance issues")
        if blocking_compliance_high > 0:
            print(f"❌ BLOCKING: Found {blocking_compliance_high} high severity compliance issues")
    elif compliance_counts["critical"] > 0 or compliance_counts["high"] > 0:
        print("⚠️ WARNING: Found compliance issues but blocking is disabled (block_on_compliance=false)")

    if grace_vuln_critical > 0 or grace_vuln_high > 0:
        print("")
        print(
            f"ℹ️ INFO: {grace_vuln_critical} critical and {grace_vuln_high} high vulnerabilities "
            f"are within the {grace_period_days}-day grace period"
        )
        print("   These will become blocking after the grace period expires.")

    outputs = {
        "scan_passed": "false" if blocking_issues else "true",
        "vuln_critical": str(vuln_counts["critical"]),
        "vuln_high": str(vuln_counts["high"]),
        "vuln_medium": str(vuln_counts["medium"]),
        "vuln_low": str(vuln_counts["low"]),
        "compliance_critical": str(compliance_counts["critical"]),
        "compliance_high": str(compliance_counts["high"]),
        "compliance_medium": str(compliance_counts["medium"]),
        "compliance_low": str(compliance_counts["low"]),
        "blocking_vuln_critical": str(blocking_vuln_critical),
        "blocking_vuln_high": str(blocking_vuln_high),
        "blocking_compliance_critical": str(blocking_compliance_critical),
        "blocking_compliance_high": str(blocking_compliance_high),
        "blocking_total": str(blocking_total),
        "guardian_managed_vulnerabilities": str(guardian_managed_vulnerabilities).lower(),
    }
    write_outputs(outputs)

    analysis = {
        "scan_passed": not blocking_issues,
        "vuln_critical": vuln_counts["critical"],
        "vuln_high": vuln_counts["high"],
        "vuln_medium": vuln_counts["medium"],
        "vuln_low": vuln_counts["low"],
        "compliance_critical": compliance_counts["critical"],
        "compliance_high": compliance_counts["high"],
        "compliance_medium": compliance_counts["medium"],
        "compliance_low": compliance_counts["low"],
        "blocking_vuln_critical": blocking_vuln_critical,
        "blocking_vuln_high": blocking_vuln_high,
        "blocking_compliance_critical": blocking_compliance_critical,
        "blocking_compliance_high": blocking_compliance_high,
        "blocking_total": blocking_total,
        "grace_days": grace_period_days,
        "block_on_compliance": block_on_compliance,
        "guardian_managed_vulnerabilities": guardian_managed_vulnerabilities,
    }
    write_analysis_file(analysis)

    if blocking_issues:
        print("")
        print("🚫 Release blocked due to critical or high severity security issues.")
        print("Please review and resolve the issues before proceeding with the release.")
        if console_link:
            print("")
            print(f"View detailed results in Prisma Cloud Console: {console_link}")
        print("Or check pcc_scan_results.json for full details")
        print("")
        print("For debugging, here's the JSON structure:")
        print(", ".join(scan_data.keys()) if isinstance(scan_data, dict) else "Could not parse JSON keys")
        return 1

    print("✅ No blocking issues found. Scan passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
