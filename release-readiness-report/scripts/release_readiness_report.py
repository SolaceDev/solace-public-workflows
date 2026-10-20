#!/usr/bin/env python3
"""Write one consolidated release readiness report.

Three parts, in this order:

1. The verdict: the caller's decision, with its reasons and context lines.
2. Licensing: one row per FOSSA project (counts by issue type, the caller's
   gate result, a link to the revision's licensing issues in FOSSA) and
   recommendations for the issue types that block. Individual issues are not
   listed; FOSSA is where they are resolved, so each count links to the
   revision's active issues of that type in FOSSA.
3. Guardian: guardian-container-scan-and-sync's overview and severity counts,
   built with its code, and a compact table with one row per Jira issue. A
   single CVE links to its dashboard page, several to the component in the
   dashboard; without a dashboard, to the CVE's advisory.

The verdict's header links the caller's `links` (commit, image...), each FOSSA
revision, the scans Guardian recorded (Prisma) and the Guardian product page.

Reporting never fails the action: a FOSSA or Guardian error becomes a warning
and a reduced section.
"""

import json
import os
import sys
import urllib.parse
from pathlib import Path

# The Guardian section is guardian-container-scan-and-sync's report; importing it keeps the two
# from drifting. Actions from this repository run from one checkout, so the sibling is present.
sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "guardian-container-scan-and-sync" / "scripts")
)
import guardian_report  # noqa: E402

FOSSA_API = "https://app.fossa.com/api"
FOSSA_APP = "https://app.fossa.com/projects"
FOSSA_PAGE_SIZE = 1000
DEFAULT_GUIDE_URL = (
    "https://sol-jira.atlassian.net/wiki/spaces/DevOps/pages/6542262516/"
    "Resolving+License+Compliance+Issues+in+FOSSA"
)

# FOSSA's licensing issue types, in the order the table shows them.
ISSUE_TYPES = {
    "policy_conflict": "denied by policy",
    "unlicensed_dependency": "unlicensed",
    "unconcluded_dependency": "unconcluded",
    "policy_flag": "flagged",
    "multi_license_concluded": "multi-licence",
}
RECOMMENDATIONS = {
    "policy_conflict": (
        "**Denied by policy.** Upgrade or replace the dependency. If our use is permitted "
        "(an operating-system package out of scope of the policy, a dual-licensed package used "
        "under its approved licence), conclude or ignore it in FOSSA with the justification the "
        "guide asks for."
    ),
    "unlicensed_dependency": (
        "**Unlicensed.** FOSSA found no licence. Conclude the correct one in FOSSA, adding the "
        "licence text when it is missing; Solace's own packages are concluded as Solace's."
    ),
    "unconcluded_dependency": (
        "**Unconcluded.** FOSSA could not decide between candidate licences. Conclude the one "
        "that applies in FOSSA."
    ),
    "policy_flag": (
        "**Flagged.** The licence needs a review against how we use the package. Conclude or "
        "ignore it in FOSSA with the guide's justification."
    ),
    "multi_license_concluded": (
        "**Multi-licence.** Confirm the licence we use the package under in FOSSA."
    ),
}
RESULT_LABELS = {
    "success": "✅ passed",
    "failure": "❌ failed",
    "cancelled": "⚪ cancelled",
    "skipped": "⚪ skipped",
}

env = guardian_report.env
bool_env = guardian_report.bool_env
warn = guardian_report.warn
cell = guardian_report.cell


# ------------------------------------------------------------------------- inputs


def split_lines(value: str) -> list[str]:
    return [line.strip() for line in (value or "").splitlines() if line.strip()]


def block_on_types() -> list[str]:
    raw = env("FOSSA_BLOCK_ON") or "policy_conflict,unlicensed_dependency"
    return [item.strip() for item in raw.split(",") if item.strip()]


def fossa_projects() -> list[dict]:
    raw = env("FOSSA_PROJECTS")
    if not raw:
        return []
    try:
        projects = json.loads(raw)
    except ValueError as exc:
        warn(f"fossa_projects is not JSON ({exc}); the licensing section is omitted.")
        return []
    if not isinstance(projects, list):
        warn("fossa_projects must be a JSON list; the licensing section is omitted.")
        return []
    return [p for p in projects if isinstance(p, dict) and p.get("project")]


# -------------------------------------------------------------------------- fossa


def locator(org_id: str, project: str) -> str:
    return project if project.startswith(("custom+", "sbom+")) else f"{org_id}/{project}"


def fossa_issue_counts(token: str, project_locator: str, revision: str) -> dict[str, int]:
    """Licensing issue counts by type for one revision, across every page."""
    counts: dict[str, int] = {}
    page = 1
    while True:
        query = urllib.parse.urlencode(
            {
                "category": "licensing",
                "scope[type]": "project",
                "scope[id]": project_locator,
                "scope[revision]": revision,
                "page": page,
                "count": FOSSA_PAGE_SIZE,
            }
        )
        payload = guardian_report.fetch_json("GET", f"{FOSSA_API}/v2/issues?{query}", token) or {}
        issues = payload.get("issues") or []
        for issue in issues:
            kind = issue.get("type") or "other"
            counts[kind] = counts.get(kind, 0) + 1
        if len(issues) < FOSSA_PAGE_SIZE:
            return counts
        page += 1


def fossa_policy(token: str, project_locator: str) -> str:
    encoded = urllib.parse.quote(project_locator, safe="")
    payload = guardian_report.fetch_json("GET", f"{FOSSA_API}/projects/{encoded}", token) or {}
    return ((payload.get("policy") or {}).get("title")) or ""


def fossa_revision_scan_id(token: str, project_locator: str, revision: str) -> int | None:
    """The revision's latest scan, which pins an issues link to the scan the counts came from."""
    encoded = urllib.parse.quote(f"{project_locator}${revision}", safe="")
    payload = guardian_report.fetch_json("GET", f"{FOSSA_API}/revisions/{encoded}", token) or {}
    scan_id = payload.get("latestRevisionScanId")
    return scan_id if isinstance(scan_id, int) else None


def fossa_link(project_locator: str, branch: str, revision: str) -> str:
    base = f"{FOSSA_APP}/{urllib.parse.quote(project_locator, safe='')}"
    if branch and revision:
        return (
            f"{base}/refs/branch/{urllib.parse.quote(branch, safe='')}"
            f"/{urllib.parse.quote(revision, safe='')}/issues/licensing"
        )
    return base


def fossa_issues_link(revision_link: str, kind: str, scan_id: int | None) -> str:
    """FOSSA's licensing issues page for one revision, filtered to one issue type."""
    query = {
        "page": 1,
        "count": 20,
        "sort": "issue_count_desc",
        "grouping": "revision",
        "status": "active",
        "filter[type][0]": kind,
    }
    if scan_id is not None:
        query["revisionScanId"] = scan_id
    return f"{revision_link}?{urllib.parse.urlencode(query)}"


def describe_counts(counts: dict[str, int], kinds, link=None) -> str:
    """`N type` for each kind present, each linked to its issues when `link(kind)` gives a URL."""
    parts = []
    for kind in kinds:
        if not counts.get(kind):
            continue
        text = f"{counts[kind]} {ISSUE_TYPES.get(kind, kind)}"
        url = link(kind) if link else None
        parts.append(f"[{text}]({url})" if url else text)
    return ", ".join(parts) or "—"


def build_licensing(projects: list[dict], token: str, org_id: str, block_on: list[str]) -> tuple[list[str], int]:
    lines = ["### 📜 Licensing (FOSSA)", ""]
    lines.append(
        "Blocks on: " + ", ".join(f"`{ISSUE_TYPES.get(k, k)}`" for k in block_on) + "."
    )
    lines.append("")
    lines.append("| Scope | FOSSA project | Policy | Result | Blocking | Not blocking |")
    lines.append("| --- | --- | --- | --- | --- | --- |")

    total_blocking = 0
    blocking_kinds: set[str] = set()
    other_kinds: set[str] = set()
    for project in projects:
        project_locator = locator(org_id, str(project["project"]))
        name = project_locator.split("/", 1)[-1]
        branch = str(project.get("branch") or "")
        revision = str(project.get("revision") or "")
        link = fossa_link(project_locator, branch, revision)
        result = RESULT_LABELS.get(str(project.get("result") or ""), cell(project.get("result")))

        counts, policy, scan_id = None, "", None
        if token and revision:
            try:
                counts = fossa_issue_counts(token, project_locator, revision)
                policy = fossa_policy(token, project_locator)
            except Exception as exc:  # noqa: BLE001 - reporting must not fail the action
                warn(f"Could not read FOSSA issues for {name}@{revision}: {exc}")
            if counts is not None:
                try:
                    scan_id = fossa_revision_scan_id(token, project_locator, revision)
                except Exception as exc:  # noqa: BLE001 - the links still work without it
                    warn(f"Could not read FOSSA's scan of {name}@{revision}; issue links show its latest: {exc}")

        # Only a revision page can be filtered; without branch and revision the counts stay plain.
        def issues_link(kind: str, link=link) -> str | None:
            return fossa_issues_link(link, kind, scan_id) if branch and revision else None

        if counts is None:
            blocking_cell, other_cell = "—", "could not be read"
        else:
            blocking = sum(counts.get(k, 0) for k in block_on)
            total_blocking += blocking
            blocking_kinds.update(k for k in block_on if counts.get(k))
            other = [k for k in counts if k not in block_on]
            other_kinds.update(other)
            blocking_cell = f"**{describe_counts(counts, block_on, issues_link)}**" if blocking else "0"
            other_cell = describe_counts(
                counts,
                [k for k in ISSUE_TYPES if k in other] + [k for k in other if k not in ISSUE_TYPES],
                issues_link,
            )

        lines.append(
            f"| {cell(project.get('label') or name)} | [{cell(name)}]({link}) "
            f"| {cell(policy)} | {result} | {blocking_cell} | {other_cell} |"
        )

    guide = env("FOSSA_GUIDE_URL") or DEFAULT_GUIDE_URL
    lines.append("")
    if blocking_kinds:
        lines.append("**To unblock**, open each blocking count in the table, which lists those issues in FOSSA, and resolve each one:")
        lines.append("")
        lines.extend(f"- {RECOMMENDATIONS[k]}" for k in ISSUE_TYPES if k in blocking_kinds)
        lines.append("")
    elif other_kinds:
        lines.append("Nothing blocks. The issues counted as not blocking are worth a review in FOSSA.")
        lines.append("")
    lines.append(f"📘 How to resolve licence issues: [Resolving License Compliance Issues in FOSSA]({guide})")
    return lines, total_blocking


# ----------------------------------------------------------------------- guardian

NVD_URL = "https://nvd.nist.gov/vuln/detail/{}"
GHSA_URL = "https://github.com/advisories/{}"
SCANNER_LABELS = {"prisma": "Prisma scan", "trivy": "Trivy scan"}


def source_url(cve: str, cve_urls: dict) -> str | None:
    """The advisory Guardian recorded for the CVE, else NVD or GitHub by its id."""
    if cve_urls.get(cve):
        return cve_urls[cve]
    if cve.upper().startswith("CVE-"):
        return NVD_URL.format(cve)
    if cve.upper().startswith("GHSA-"):
        return GHSA_URL.format(cve)
    return None


def guardian_cve_urls(base: str, token: str, product: str) -> dict[str, str]:
    query = urllib.parse.urlencode({"product_name": product})
    payload = guardian_report.fetch_json("GET", f"{base}/api/v1/vulnerabilities?{query}", token) or {}
    return {
        record["cve_id"]: record["cve_url"]
        for record in payload.get("vulnerabilities") or []
        if record.get("cve_id") and record.get("cve_url")
    }


def cves_cell(row: dict, links: dict, cve_urls: dict) -> str:
    """One CVE links to itself; several link to the component in the dashboard, or to the first
    CVE's advisory when there is no dashboard."""
    cves = row["cves"]
    if not cves:
        return "—"
    if len(cves) == 1:
        if links.get("dashboard"):
            return guardian_report.cve_link(cves[0], links)
        url = source_url(cves[0], cve_urls)
        return f"[{cves[0]}]({url})" if url else cves[0]
    search = links.get("search")
    if search:
        component = row["component"].split(", ")[0]
        return f"[{len(cves)} CVEs]({search}&q={urllib.parse.quote(component, safe='')})"
    url = source_url(cves[0], cve_urls)
    first = f"[{cves[0]}]({url})" if url else cves[0]
    return f"{first} +{len(cves) - 1} more"


def build_issue_table(rows: list[dict], links: dict, cve_urls: dict, max_rows: int) -> list[str]:
    """guardian_report's rows in fewer, narrower columns: no descriptions, scanners or CVSS."""
    if not rows:
        return ["No open findings with a fix for this build."]
    lines = [
        f"#### Jira issues ({len(rows)})",
        "",
        "| Jira | Severity | Package | Version | Fix | Due | CVEs |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows[:max_rows]:
        lines.append(
            f"| {guardian_report.jira_link(row['jira_key'], links)} "
            f"| {guardian_report.SEVERITY_ICONS[row['severity']]} {row['severity']} "
            f"| {cell(row['component'])} | {cell(row['version'])} | {cell(row['fix'])} "
            f"| {guardian_report.due_label(row)} | {cves_cell(row, links, cve_urls)} |"
        )
    if len(rows) > max_rows:
        lines.append("")
        lines.append(f"_Showing {max_rows} of {len(rows)} issues._")
    return lines


def scan_links(gate_result: dict | None) -> list[tuple[str, str]]:
    """The scan pages Guardian recorded for the build's findings, one per scanner (not FOSSA,
    whose projects the licensing section links)."""
    seen: dict[str, str] = {}
    for key in ("vulnerabilities", "vulnerabilities_pending", "vulnerabilities_excluded"):
        for hit in (gate_result or {}).get(key) or []:
            for scanner, url in (hit.get("scan_urls") or {}).items():
                if scanner in SCANNER_LABELS and url and scanner not in seen:
                    seen[scanner] = url
    return [(SCANNER_LABELS[s], seen[s]) for s in SCANNER_LABELS if s in seen]


def read_guardian() -> dict:
    """Reads the gate and the dashboard context once; build_guardian renders it."""
    base = env("GUARDIAN_URL").rstrip("/")
    token = env("GUARDIAN_KEY")
    product = env("GUARDIAN_PRODUCT_NAME")
    full_version = env("GUARDIAN_FULL_VERSION")
    try:
        sync = json.loads(env("GUARDIAN_SYNC_RESPONSE") or "{}")
    except ValueError:
        sync = {}
    ctx = {
        "product": product,
        "product_version": env("GUARDIAN_PRODUCT_VERSION"),
        "full_version": full_version,
        "unifiers": env("GUARDIAN_UNIFIERS") or "fossa,prisma",
        "prisma_status": "",
        "trivy_status": "skipped",
        "sync": sync if isinstance(sync, dict) else {},
    }

    gate_result = None
    try:
        gate = guardian_report.guardian_gate(base, token, product, full_version)
        results = gate.get("results") or []
        gate_result = next((r for r in results if r.get("repository") == product), None)
        if gate_result is None:
            gate_result = results[0] if results else {}
    except Exception as exc:  # noqa: BLE001 - reporting must not fail the action
        warn(f"Could not read Guardian findings for the report: {exc}")

    links: dict = {}
    jira_base = env("JIRA_BASE_URL").rstrip("/")
    if jira_base:
        links["jira"] = jira_base
    dashboard = env("GUARDIAN_DASHBOARD_URL").rstrip("/")
    if dashboard and gate_result is not None:
        links["dashboard"] = dashboard
        try:
            squad = guardian_report.guardian_squad(base, token, product)
        except Exception as exc:  # noqa: BLE001
            squad = None
            warn(f"Could not resolve the product's squad for dashboard links: {exc}")
        if squad:
            product_path = (
                f"/squads/{urllib.parse.quote(squad, safe='')}"
                f"/products/{urllib.parse.quote(product, safe='')}"
            )
            page = f"{product_path}/{urllib.parse.quote(ctx['product_version'], safe='')}"
            links["scope"] = page
            links["product_page"] = dashboard + page
            links["search"] = (
                f"{dashboard}{product_path}?"
                + urllib.parse.urlencode({"squad": squad, "product": product})
            )

    cve_urls: dict = {}
    if gate_result is not None and bool_env("SHOW_DETAILS") and not links.get("dashboard"):
        try:
            cve_urls = guardian_cve_urls(base, token, product)
        except Exception as exc:  # noqa: BLE001
            warn(f"Could not read CVE advisory links for the report: {exc}")
    return {"ctx": ctx, "gate": gate_result, "links": links, "cve_urls": cve_urls}


def build_guardian(data: dict) -> tuple[list[str], int | None]:
    try:
        max_rows = int(env("MAX_ROWS") or guardian_report.DEFAULT_MAX_ROWS)
    except ValueError:
        max_rows = guardian_report.DEFAULT_MAX_ROWS
    gate_result, links = data["gate"], data["links"]
    overview = guardian_report.build_overview(data["ctx"], gate_result, links)
    overview[0] = "### 🛡️ Guardian"
    if gate_result is None:
        return overview, None

    rows = guardian_report.group_issues(
        gate_result.get("vulnerabilities") or [],
        gate_result.get("vulnerabilities_pending") or [],
        {},
    )
    if bool_env("SHOW_DETAILS"):
        detail = build_issue_table(rows, links, data["cve_urls"], max_rows)
    else:
        detail = [
            "Per-issue details are hidden for this repository. "
            'Set `show_details: "true"` to include them.'
        ]
    return overview + [""] + detail, len(gate_result.get("vulnerabilities") or [])


# ------------------------------------------------------------------------ verdict


def caller_links() -> list[tuple[str, str]]:
    """`links` input lines, `Label | URL` each."""
    pairs = []
    for line in split_lines(env("LINKS")):
        label, sep, url = line.rpartition("|")
        if sep and label.strip() and url.strip():
            pairs.append((label.strip(), url.strip()))
        else:
            warn(f"Ignoring links line without `Label | URL`: {line}")
    return pairs


def build_verdict(header_links: list[tuple[str, str]]) -> list[str]:
    ready = env("STATUS").lower() == "ready"
    title = env("TITLE") or "Release readiness"
    lines = [f"## {'✅' if ready else '❌'} {title} — {'ready' if ready else 'blocked'}", ""]
    if header_links:
        lines.append(" · ".join(f"[{label}]({url})" for label, url in header_links))
        lines.append("")
    lines.extend(f"- {line}" for line in split_lines(env("CONTEXT")))
    reasons = split_lines(env("REASONS"))
    if reasons:
        lines.append("")
        lines.append("**Blocked by:**")
        lines.append("")
        lines.extend(f"- {reason}" for reason in reasons)
    notes = split_lines(env("NOTES"))
    if notes:
        lines.append("")
        lines.extend(f"> {note}" for note in notes)
    return lines


# --------------------------------------------------------------------------- main


def main() -> int:
    org_id = env("FOSSA_ORG_ID") or "custom+48578"
    header_links = caller_links()
    sections = []

    licensing_blocking = ""
    projects = fossa_projects()
    if projects:
        licensing, count = build_licensing(projects, env("FOSSA_API_KEY"), org_id, block_on_types())
        sections.append(licensing)
        licensing_blocking = str(count)
        for project in projects:
            project_locator = locator(org_id, str(project["project"]))
            branch = str(project.get("branch") or "")
            revision = str(project.get("revision") or "")
            url = fossa_link(project_locator, branch, revision).removesuffix("/issues/licensing")
            header_links.append((f"FOSSA {project.get('label') or project_locator.split('/', 1)[-1]}", url))

    guardian_blocking = ""
    if env("GUARDIAN_URL") and env("GUARDIAN_PRODUCT_NAME"):
        data = read_guardian()
        header_links.extend(scan_links(data["gate"]))
        if data["links"].get("product_page"):
            header_links.append(("Guardian", data["links"]["product_page"]))
        guardian, count = build_guardian(data)
        sections.append(guardian)
        guardian_blocking = "" if count is None else str(count)

    sections.insert(0, build_verdict(header_links))
    report = "\n\n".join("\n".join(section) for section in sections) + "\n"
    report_path = Path(env("RUNNER_TEMP") or ".") / "release-readiness-report.md"
    report_path.write_text(report, encoding="utf-8")
    if bool_env("WRITE_STEP_SUMMARY", default=True) and env("GITHUB_STEP_SUMMARY"):
        with open(env("GITHUB_STEP_SUMMARY"), "a", encoding="utf-8") as handle:
            handle.write(report)

    guardian_report.write_outputs(
        {
            "report_path": str(report_path),
            "licensing_blocking": licensing_blocking,
            "guardian_blocking": guardian_blocking,
        }
    )
    print(
        f"Release readiness report written to {report_path} "
        f"(licensing blocking: {licensing_blocking or 'n/a'}, Guardian past SLA: {guardian_blocking or 'n/a'})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
