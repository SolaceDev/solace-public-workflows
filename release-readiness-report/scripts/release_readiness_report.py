#!/usr/bin/env python3
"""Write one consolidated release readiness report.

Three parts, in this order:

1. The verdict: the caller's decision, with its reasons and context lines.
2. Licensing: one row per FOSSA project (counts by issue type, the caller's
   gate result, a link to the revision's licensing issues in FOSSA) and
   recommendations for the issue types that block. Individual issues are not
   listed; FOSSA is where they are resolved.
3. Guardian: the report guardian-container-scan-and-sync writes (overview,
   severity counts, one row per Jira issue), built with the same code.

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


def fossa_link(project_locator: str, branch: str, revision: str) -> str:
    base = f"{FOSSA_APP}/{urllib.parse.quote(project_locator, safe='')}"
    if branch and revision:
        return (
            f"{base}/refs/branch/{urllib.parse.quote(branch, safe='')}"
            f"/{urllib.parse.quote(revision, safe='')}/issues/licensing"
        )
    return base


def describe_counts(counts: dict[str, int], kinds) -> str:
    parts = [f"{counts[k]} {ISSUE_TYPES.get(k, k)}" for k in kinds if counts.get(k)]
    return ", ".join(parts) or "—"


def build_licensing(projects: list[dict], token: str, org_id: str, block_on: list[str]) -> tuple[list[str], int]:
    lines = ["### 📜 Licensing (FOSSA)", ""]
    lines.append(
        "Blocks on: " + ", ".join(f"`{ISSUE_TYPES.get(k, k)}`" for k in block_on) + "."
    )
    lines.append("")
    lines.append("| Scope | FOSSA project | Revision | Policy | Result | Blocking | Not blocking |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")

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

        counts, policy = None, ""
        if token and revision:
            try:
                counts = fossa_issue_counts(token, project_locator, revision)
                policy = fossa_policy(token, project_locator)
            except Exception as exc:  # noqa: BLE001 - reporting must not fail the action
                warn(f"Could not read FOSSA issues for {name}@{revision}: {exc}")

        if counts is None:
            blocking_cell, other_cell = "—", "could not be read"
        else:
            blocking = sum(counts.get(k, 0) for k in block_on)
            total_blocking += blocking
            blocking_kinds.update(k for k in block_on if counts.get(k))
            other = [k for k in counts if k not in block_on]
            other_kinds.update(other)
            blocking_cell = f"**{describe_counts(counts, block_on)}**" if blocking else "0"
            other_cell = describe_counts(counts, [k for k in ISSUE_TYPES if k in other] + [k for k in other if k not in ISSUE_TYPES])

        lines.append(
            f"| {cell(project.get('label') or name)} | [{cell(name)}]({link}) | `{cell(revision)}` "
            f"| {cell(policy)} | {result} | {blocking_cell} | {other_cell} |"
        )

    guide = env("FOSSA_GUIDE_URL") or DEFAULT_GUIDE_URL
    lines.append("")
    if blocking_kinds:
        lines.append("**To unblock**, open the project's issues from the table and resolve each one:")
        lines.append("")
        lines.extend(f"- {RECOMMENDATIONS[k]}" for k in ISSUE_TYPES if k in blocking_kinds)
        lines.append("")
    elif other_kinds:
        lines.append("Nothing blocks. The issues counted as not blocking are worth a review in FOSSA.")
        lines.append("")
    lines.append(f"📘 How to resolve licence issues: [Resolving License Compliance Issues in FOSSA]({guide})")
    return lines, total_blocking


# ----------------------------------------------------------------------- guardian


def build_guardian() -> tuple[list[str], int | None]:
    """guardian-container-scan-and-sync's report, under this report's heading."""
    base = env("GUARDIAN_URL").rstrip("/")
    token = env("GUARDIAN_KEY")
    product = env("GUARDIAN_PRODUCT_NAME")
    full_version = env("GUARDIAN_FULL_VERSION")
    show_details = bool_env("SHOW_DETAILS")
    try:
        max_rows = int(env("MAX_ROWS") or guardian_report.DEFAULT_MAX_ROWS)
    except ValueError:
        max_rows = guardian_report.DEFAULT_MAX_ROWS
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
    except Exception as exc:  # noqa: BLE001
        warn(f"Could not read Guardian findings for the report: {exc}")

    links: dict = {}
    details: dict = {}
    if show_details and gate_result is not None:
        dashboard = env("GUARDIAN_DASHBOARD_URL").rstrip("/")
        jira_base = env("JIRA_BASE_URL").rstrip("/")
        if jira_base:
            links["jira"] = jira_base
        if dashboard:
            links["dashboard"] = dashboard
            try:
                squad = guardian_report.guardian_squad(base, token, product)
            except Exception as exc:  # noqa: BLE001
                squad = None
                warn(f"Could not resolve the product's squad for dashboard links: {exc}")
            if squad:
                page = (
                    f"/squads/{urllib.parse.quote(squad, safe='')}"
                    f"/products/{urllib.parse.quote(product, safe='')}"
                    f"/{urllib.parse.quote(ctx['product_version'], safe='')}"
                )
                links["scope"] = page
                links["product_page"] = dashboard + page
        try:
            details = guardian_report.guardian_descriptions(base, token, product)
        except Exception as exc:  # noqa: BLE001
            warn(f"Could not read finding descriptions for the report: {exc}")

    overview = guardian_report.build_overview(ctx, gate_result, links)
    overview[0] = "### 🛡️ Guardian"
    if gate_result is None:
        return overview, None

    rows = guardian_report.group_issues(
        gate_result.get("vulnerabilities") or [],
        gate_result.get("vulnerabilities_pending") or [],
        details,
    )
    if show_details:
        detail = guardian_report.build_table(rows, links, max_rows)
    else:
        detail = [
            "Per-issue details are hidden for this repository. "
            'Set `show_details: "true"` to include them.'
        ]
    return overview + [""] + detail, len(gate_result.get("vulnerabilities") or [])


# ------------------------------------------------------------------------ verdict


def build_verdict() -> list[str]:
    ready = env("STATUS").lower() == "ready"
    title = env("TITLE") or "Release readiness"
    lines = [f"## {'✅' if ready else '❌'} {title} — {'ready' if ready else 'blocked'}", ""]
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
    sections = [build_verdict()]

    licensing_blocking = ""
    projects = fossa_projects()
    if projects:
        licensing, count = build_licensing(
            projects, env("FOSSA_API_KEY"), env("FOSSA_ORG_ID") or "custom+48578", block_on_types()
        )
        sections.append(licensing)
        licensing_blocking = str(count)

    guardian_blocking = ""
    if env("GUARDIAN_URL") and env("GUARDIAN_PRODUCT_NAME"):
        guardian, count = build_guardian()
        sections.append(guardian)
        guardian_blocking = "" if count is None else str(count)

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
