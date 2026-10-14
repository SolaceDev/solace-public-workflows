#!/usr/bin/env python3
"""Report the Guardian result for the scanned build.

Reads the open, fixable findings for the build from Guardian's vulnerability
gate, groups them into one row per Jira issue (Guardian files one issue per
component), and writes the report to the job summary and, when the token can,
to a "Guardian Scan" check run.

The per-issue table (with descriptions and dashboard links) is only rendered
when SHOW_DETAILS is true; otherwise the report carries counts only.

Reporting never fails the action: the scans are already synced by the time this
runs, so any error here is surfaced as a warning and a reduced report.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

SEVERITIES = ("Critical", "High", "Medium", "Low", "Unknown")
SEVERITY_ICONS = {
    "Critical": "🔴",
    "High": "🟠",
    "Medium": "🟡",
    "Low": "🔵",
    "Unknown": "⚪",
}
DEFAULT_MAX_ROWS = 50
DESCRIPTION_LIMIT = 140
# GitHub rejects check-run summary/text fields longer than this.
CHECK_FIELD_LIMIT = 65000
HTTP_TIMEOUT = 120


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def bool_env(name: str, default: bool = False) -> bool:
    value = env(name).lower()
    return default if not value else value == "true"


def warn(message: str) -> None:
    print(f"::warning::{message}")


def normalize_severity(value) -> str:
    text = str(value or "").strip().capitalize()
    return text if text in SEVERITIES else "Unknown"


def severity_rank(severity: str) -> int:
    return SEVERITIES.index(normalize_severity(severity))


# --------------------------------------------------------------------- versions


def version_key(version: str) -> tuple:
    """Loose ordering key for package versions (semver, distro, epoch)."""
    parts = []
    for token in re.split(r"[.\-+_~:]", str(version)):
        if not token:
            continue
        for piece in re.findall(r"\d+|[A-Za-z]+", token):
            parts.append((0, int(piece)) if piece.isdigit() else (1, piece.lower()))
    return tuple(parts)


def earliest_fix(installed: str, fixes: list[str]) -> str | None:
    """Lowest fix version above the installed one (else the lowest fix)."""
    fixes = [f for f in fixes if f]
    if not fixes:
        return None
    above = [f for f in fixes if version_key(f) > version_key(installed)]
    return min(above or fixes, key=version_key)


# ------------------------------------------------------------------------- http


def fetch_json(method: str, url: str, token: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/json")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
        return json.loads(response.read().decode() or "null")


def guardian_gate(base: str, token: str, product: str, full_version: str) -> dict:
    body = {"repositories": [{"product": product, "version": full_version}]}
    run_url = run_link()
    if run_url:
        body["triggered_by"] = run_url
    return fetch_json("POST", f"{base}/api/v1/vulnerability_gate", token, body)


def guardian_descriptions(base: str, token: str, product: str) -> dict:
    """(cve, component, version) -> {description, cvss} for the product's live findings."""
    query = urllib.parse.urlencode({"product_name": product})
    payload = fetch_json("GET", f"{base}/api/v1/vulnerabilities?{query}", token) or {}
    lookup = {}
    for record in payload.get("vulnerabilities") or []:
        key = (
            record.get("cve_id"),
            record.get("component_name"),
            record.get("component_version"),
        )
        lookup[key] = {
            "description": record.get("description") or "",
            "cvss": record.get("cvss_score"),
        }
    return lookup


def guardian_squad(base: str, token: str, product: str) -> str | None:
    payload = fetch_json("GET", f"{base}/api/v1/configs/squads", token) or {}
    for squad in payload.get("squads") or []:
        for entry in squad.get("products") or []:
            if entry.get("name") == product:
                return squad.get("name")
    return None


def run_link() -> str:
    server, repo, run_id = env("GITHUB_SERVER_URL"), env("GITHUB_REPOSITORY"), env("GITHUB_RUN_ID")
    return f"{server}/{repo}/actions/runs/{run_id}" if server and repo and run_id else ""


# ---------------------------------------------------------------------- grouping


def group_issues(blocking: list[dict], pending: list[dict], details: dict) -> list[dict]:
    """One row per Jira issue; findings without a ticket group by component@version."""
    groups: dict[str, dict] = {}
    for hits, is_blocking in ((blocking, True), (pending, False)):
        for hit in hits:
            component = hit.get("component_name") or "unknown"
            version = hit.get("component_version") or ""
            key = hit.get("jira_key") or f"{component}@{version}"
            row = groups.setdefault(
                key,
                {
                    "jira_key": hit.get("jira_key"),
                    "components": [],
                    "versions": [],
                    "hits": [],
                    "blocking": False,
                    "days_until_blocking": None,
                    "scanners": set(),
                },
            )
            row["hits"].append(hit)
            if component not in row["components"]:
                row["components"].append(component)
            if version and version not in row["versions"]:
                row["versions"].append(version)
            row["scanners"].update(s for s in hit.get("scanners") or [] if s)
            if is_blocking:
                row["blocking"] = True
            else:
                days = hit.get("days_until_blocking")
                if days is not None and (
                    row["days_until_blocking"] is None or days < row["days_until_blocking"]
                ):
                    row["days_until_blocking"] = days

    rows = []
    for row in groups.values():
        hits = row["hits"]
        worst = min(hits, key=lambda h: severity_rank(h.get("severity")))
        per_cve_fix = [
            earliest_fix(h.get("component_version") or "", h.get("fix_versions") or [])
            for h in hits
        ]
        per_cve_fix = [f for f in per_cve_fix if f]
        cves = []
        for h in sorted(hits, key=lambda h: severity_rank(h.get("severity"))):
            if h.get("cve_id") and h["cve_id"] not in cves:
                cves.append(h["cve_id"])
        cvss_values = []
        for h in hits:
            info = details.get((h.get("cve_id"), h.get("component_name"), h.get("component_version")))
            if info and isinstance(info.get("cvss"), (int, float)):
                cvss_values.append(float(info["cvss"]))
        worst_info = details.get(
            (worst.get("cve_id"), worst.get("component_name"), worst.get("component_version"))
        ) or {}
        rows.append(
            {
                "jira_key": row["jira_key"],
                "severity": normalize_severity(worst.get("severity")),
                "cvss": max(cvss_values) if cvss_values else None,
                "component": ", ".join(row["components"]),
                "version": ", ".join(row["versions"]),
                # The fix that clears every CVE in the issue is the highest of the
                # per-CVE earliest fixes.
                "fix": max(per_cve_fix, key=version_key) if per_cve_fix else None,
                "blocking": row["blocking"],
                "days_until_blocking": row["days_until_blocking"],
                "cves": cves,
                "scanners": sorted(row["scanners"]),
                "description": worst_info.get("description") or "",
            }
        )

    rows.sort(
        key=lambda r: (
            0 if r["blocking"] else 1,
            r["days_until_blocking"] if r["days_until_blocking"] is not None else 10**6,
            severity_rank(r["severity"]),
            r["component"],
        )
    )
    return rows


def count_by_severity(hits: list[dict]) -> dict[str, int]:
    counts = {severity: 0 for severity in SEVERITIES}
    for hit in hits:
        counts[normalize_severity(hit.get("severity"))] += 1
    return counts


# --------------------------------------------------------------------- rendering


def cell(value) -> str:
    text = re.sub(r"\s+", " ", str(value if value is not None else "")).strip()
    return text.replace("|", "\\|") or "—"


def truncate(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def plain_description(text: str) -> str:
    """Advisory text is often Markdown; drop headings and emphasis so it reads inline in a cell."""
    text = re.sub(r"(?m)^\s*#+\s*", "", text or "")
    return re.sub(r"\*\*|__|`", "", text)


def due_label(row: dict) -> str:
    if row["blocking"]:
        return "🚨 now"
    days = row["days_until_blocking"]
    return "—" if days is None else f"⏳ {days}d"


def cve_link(cve: str, links: dict) -> str:
    dashboard = links.get("dashboard")
    if not dashboard:
        return cve
    url = f"{dashboard}/vulnerabilities/{urllib.parse.quote(cve, safe='')}"
    scope = links.get("scope")
    if scope:
        url += "?from=" + urllib.parse.quote(scope, safe="")
    return f"[{cve}]({url})"


def jira_link(key: str | None, links: dict) -> str:
    if not key:
        return "—"
    base = links.get("jira")
    return f"[{key}]({base}/browse/{key})" if base else key


def build_overview(ctx: dict, gate_result: dict | None, links: dict) -> list[str]:
    lines = ["### Guardian Scan Overview"]
    lines.append(
        f"- **Product:** `{ctx['product']}` · `{ctx['product_version']}` · build `{ctx['full_version']}`"
    )
    scanners = ctx["unifiers"].replace(",", ", ")
    if ctx["trivy_status"] == "failure":
        scanners += " (Trivy requested but not synced)"
    lines.append(f"- **Scanners synced:** {scanners}")

    sync = ctx.get("sync") or {}
    summary = (sync.get("db_synch") or {}).get("summary") or {}
    jira_close = sync.get("jira_close") or {}
    if summary or jira_close:
        parts = [f"{summary.get(k, 0)} {k}" for k in ("new", "resolved", "resurfaced")]
        closed = jira_close.get("closed", 0)
        if isinstance(closed, list):
            closed = len(closed)
        lines.append(f"- **Sync:** {' · '.join(parts)} · Jira closed: {closed}")
    if links.get("product_page"):
        lines.append(f"- **Dashboard:** [{ctx['product']}:{ctx['product_version']}]({links['product_page']})")
    lines.append("")

    if gate_result is None:
        lines.append("⚠️ Guardian findings could not be retrieved for this build; see the job log.")
        return lines

    blocking = gate_result.get("vulnerabilities") or []
    pending = gate_result.get("vulnerabilities_pending") or []
    header_icons = " | ".join(f"{SEVERITY_ICONS[s]} {s}" for s in SEVERITIES)
    lines.append(f"| Open findings with a fix | {header_icons} | Total |")
    lines.append("| --- |" + " ---: |" * (len(SEVERITIES) + 1))
    for label, hits in (("🚨 Past SLA", blocking), ("⏳ Within SLA", pending)):
        counts = count_by_severity(hits)
        lines.append(
            f"| {label} | " + " | ".join(str(counts[s]) for s in SEVERITIES) + f" | {len(hits)} |"
        )
    extras = []
    excluded = len(gate_result.get("vulnerabilities_excluded") or [])
    parent_owned = len(gate_result.get("vulnerabilities_parent_owned") or [])
    if excluded:
        extras.append(f"{excluded} excluded")
    if parent_owned:
        extras.append(f"{parent_owned} vendor-owned")
    if extras:
        lines.append("")
        lines.append(f"Not counted above: {', '.join(extras)}.")
    return lines


def build_table(rows: list[dict], links: dict, max_rows: int) -> list[str]:
    if not rows:
        return ["No open findings with a fix for this build."]
    lines = [
        f"#### Jira issues ({len(rows)})",
        "",
        "| Jira | Severity | CVSS | Package | Version | Status | Due | CVEs | Scanners | Description |",
        "| --- | --- | ---: | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows[:max_rows]:
        cves = row["cves"]
        shown = ", ".join(cve_link(c, links) for c in cves[:3])
        if len(cves) > 3:
            shown += f" +{len(cves) - 3} more"
        cvss = f"{row['cvss']:.1f}" if row["cvss"] is not None else "—"
        status = f"fixed in {row['fix']}" if row["fix"] else "—"
        lines.append(
            f"| {jira_link(row['jira_key'], links)} "
            f"| {SEVERITY_ICONS[row['severity']]} {row['severity']} "
            f"| {cvss} | {cell(row['component'])} | {cell(row['version'])} "
            f"| {cell(status)} | {due_label(row)} | {shown or '—'} "
            f"| {cell(', '.join(row['scanners']))} "
            f"| {cell(truncate(plain_description(row['description']), DESCRIPTION_LIMIT))} |"
        )
    if len(rows) > max_rows:
        lines.append("")
        lines.append(f"_Showing {max_rows} of {len(rows)} issues._")
    return lines


def fit(text: str) -> str:
    if len(text) <= CHECK_FIELD_LIMIT:
        return text
    return text[: CHECK_FIELD_LIMIT - 40].rsplit("\n", 1)[0] + "\n\n_Report truncated._"


# ------------------------------------------------------------------- check run


def post_check_run(payload: dict) -> str | None:
    """Create the check run; returns its URL, or None when the token can't."""
    token, repository = env("GITHUB_TOKEN"), env("GITHUB_REPOSITORY")
    api = env("GITHUB_API_URL", "https://api.github.com")
    if not token or "/" not in repository:
        print("::notice::Guardian check run skipped: no GitHub token or repository.")
        return None
    request = urllib.request.Request(
        f"{api}/repos/{repository}/check-runs",
        data=json.dumps(payload).encode(),
        method="POST",
    )
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("Content-Type", "application/json")
    request.add_header("User-Agent", "solace-public-workflows/guardian-container-scan-and-sync")
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            return (json.loads(response.read().decode() or "{}") or {}).get("html_url")
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 404):
            print("::notice::Guardian check run skipped: the token does not have `checks: write`.")
            return None
        raise


# ------------------------------------------------------------------------- main


def write_outputs(values: dict) -> None:
    path = env("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            for key, value in values.items():
                handle.write(f"{key}={value}\n")


def main() -> int:
    base = env("GUARDIAN_URL").rstrip("/")
    token = env("GUARDIAN_KEY")
    show_details = bool_env("SHOW_DETAILS")
    try:
        max_rows = int(env("MAX_ROWS") or DEFAULT_MAX_ROWS)
    except ValueError:
        max_rows = DEFAULT_MAX_ROWS
    try:
        sync = json.loads(env("SYNC_RESPONSE") or "{}")
    except ValueError:
        sync = {}
    ctx = {
        "product": env("PRODUCT_NAME"),
        "product_version": env("PRODUCT_VERSION"),
        "full_version": env("FULL_VERSION"),
        "unifiers": env("UNIFIERS") or "prisma",
        "trivy_status": env("TRIVY_STATUS"),
        "sync": sync if isinstance(sync, dict) else {},
    }

    gate_result = None
    try:
        gate = guardian_gate(base, token, ctx["product"], ctx["full_version"])
        results = gate.get("results") or []
        gate_result = next((r for r in results if r.get("repository") == ctx["product"]), None)
        if gate_result is None and results:
            gate_result = results[0]
        if gate_result is None:
            gate_result = {}
    except Exception as exc:  # noqa: BLE001 - reporting must not fail the action
        warn(f"Could not read Guardian findings for the report: {exc}")

    links: dict = {}
    details: dict = {}
    if show_details and gate_result is not None:
        dashboard = env("DASHBOARD_URL").rstrip("/")
        jira_base = env("JIRA_BASE_URL").rstrip("/")
        if jira_base:
            links["jira"] = jira_base
        if dashboard:
            links["dashboard"] = dashboard
            try:
                squad = guardian_squad(base, token, ctx["product"])
            except Exception as exc:  # noqa: BLE001
                squad = None
                warn(f"Could not resolve the product's squad for dashboard links: {exc}")
            if squad:
                page = (
                    f"/squads/{urllib.parse.quote(squad, safe='')}"
                    f"/products/{urllib.parse.quote(ctx['product'], safe='')}"
                    f"/{urllib.parse.quote(ctx['product_version'], safe='')}"
                )
                links["scope"] = page
                links["product_page"] = dashboard + page
        try:
            details = guardian_descriptions(base, token, ctx["product"])
        except Exception as exc:  # noqa: BLE001
            warn(f"Could not read finding descriptions for the report: {exc}")

    overview = build_overview(ctx, gate_result, links)
    rows = []
    if gate_result is not None:
        rows = group_issues(
            gate_result.get("vulnerabilities") or [],
            gate_result.get("vulnerabilities_pending") or [],
            details,
        )
    if show_details and gate_result is not None:
        detail_lines = build_table(rows, links, max_rows)
    else:
        detail_lines = [
            "Per-issue details are hidden for this repository. "
            'Set `show_detailed_logs: "true"` to include them.'
        ]

    summary_md = "\n".join(overview) + "\n"
    detail_md = "\n".join(detail_lines) + "\n"
    if bool_env("WRITE_STEP_SUMMARY", default=True) and env("GITHUB_STEP_SUMMARY"):
        with open(env("GITHUB_STEP_SUMMARY"), "a", encoding="utf-8") as handle:
            handle.write(summary_md + "\n" + detail_md)

    blocking_rows = sum(1 for r in rows if r["blocking"])
    blocking_count = len((gate_result or {}).get("vulnerabilities") or [])
    pending_count = len((gate_result or {}).get("vulnerabilities_pending") or [])
    if gate_result is None:
        title = "Guardian report unavailable"
    elif blocking_rows:
        title = f"⚠️ {blocking_rows} Jira issue(s) past SLA"
    else:
        title = "✅ No issues past SLA"

    check_url = ""
    if bool_env("CREATE_CHECK", default=True):
        payload = {
            "name": env("CHECK_NAME") or "Guardian Scan",
            "head_sha": env("TARGET_SHA") or env("GITHUB_SHA"),
            "status": "completed",
            # Report-only: the release gate decides blocking, so this never turns red.
            "conclusion": "success" if gate_result is not None and not blocking_rows else "neutral",
            "output": {"title": title, "summary": fit(summary_md), "text": fit(detail_md)},
        }
        if links.get("product_page"):
            payload["details_url"] = links["product_page"]
        try:
            check_url = post_check_run(payload) or ""
            if check_url:
                print(f"Posted Guardian check run: {check_url}")
        except Exception as exc:  # noqa: BLE001
            warn(f"Could not post the Guardian check run: {exc}")

    write_outputs(
        {
            "report_status": "ok" if gate_result is not None else "unavailable",
            "blocking_count": blocking_count,
            "pending_count": pending_count,
            "blocking_issues": blocking_rows,
            "check_run_url": check_url,
        }
    )
    print(f"Guardian report: {title} ({blocking_count} past SLA, {pending_count} within SLA)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
