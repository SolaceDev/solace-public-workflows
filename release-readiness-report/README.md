# Release Readiness Report

Writes one job summary for a release readiness check, in three parts:

1. **The verdict.** The caller's decision (`ready` or `blocked`), a line of links (the caller's, such as the commit and the image, then each FOSSA revision, the Prisma scan Guardian recorded, and the Guardian product page), its reasons and context lines.
2. **Licensing (FOSSA).** One row per FOSSA project: policy, the caller's gate result, blocking and non-blocking issue counts by type, and a link to the revision's licensing issues in FOSSA. Individual issues are not listed. When something blocks, the section recommends what to do for each blocking issue type and links the guide to resolving licence issues in FOSSA.
3. **Guardian.** The overview and severity counts [`guardian-container-scan-and-sync`](../guardian-container-scan-and-sync/#guardian-report) writes, built with its code: product and build, scanners synced, sync counts, and open findings with a fix by severity, past and within SLA. Then a compact table with one row per Jira issue: severity, package, version, fix, due date and CVEs. One CVE links to its dashboard page and several to the component's findings in the dashboard (`N CVEs`). Without `guardian_dashboard_url`, CVEs link to the advisory Guardian recorded (NVD, Ubuntu, Red Hat...).

The action only reports. It never fails, and a FOSSA or Guardian error becomes a warning and a reduced section; the caller decides readiness.

## One summary for the whole run

Every scan and Guardian action this report summarises writes its own job summary unless told not to. Turn them off in the jobs that run them, and run this action in the job that decides:

| Action or workflow | Input |
| --- | --- |
| [`sca-scan-and-guard.yaml`](../.github/workflows/sca-scan-and-guard.yaml) | `write_step_summary: false` |
| [`fossa-guard`](../.github/actions/fossa-guard/) | `write_step_summary: "false"` |
| [`prisma-cloud-scan`](../prisma-cloud-scan/) | `write_step_summary: "false"` |
| [`guardian-db-sync`](../guardian-db-sync/) | `write-step-summary: "false"` |
| [`guardian-vulnerability-gate`](../guardian-vulnerability-gate/) | `write-step-summary: "false"` |

## Inputs

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| `status` | yes | | `ready` or `blocked`. |
| `title` | no | `Release readiness` | Heading, e.g. ``Release readiness: `1.4.0-rc.3` ``. |
| `links` | no | | Links under the heading, one `Label \| URL` per line, e.g. the commit and the image. |
| `reasons` | no | | Why the release is blocked, one per line. |
| `context` | no | | Bullets under the verdict, one per line, Markdown allowed. |
| `notes` | no | | Quoted notes under the verdict, e.g. an admin bypass. |
| `fossa_api_key` | no | | FOSSA API key. Pass it as a secret. |
| `fossa_org_id` | no | `custom+48578` | FOSSA organisation locator prefix. |
| `fossa_projects` | no | | JSON list of projects; empty omits the licensing section. See below. |
| `fossa_block_on` | no | `policy_conflict,unlicensed_dependency` | Issue types that block, as given to `fossa-guard`. |
| `fossa_guide_url` | no | the Confluence guide | Guide linked for resolving licence issues. |
| `guardian_url` | no | | Guardian API base URL; empty omits the Guardian section. |
| `guardian_key` | no | | Guardian API token. Pass it as a secret. |
| `guardian_product_name` | no | | Guardian product. |
| `guardian_product_version` | no | | Product version (stream), for the dashboard link. |
| `guardian_full_version` | no | | The build the gate is read for. |
| `guardian_unifiers` | no | `fossa,prisma` | Scanners synced, as shown in the overview. |
| `guardian_sync_response` | no | | `guardian-db-sync`'s `response_json`, for the sync counts. |
| `guardian_dashboard_url` | no | | Guardian dashboard base URL, for CVE and product links. Not the API URL, which is masked and would print as `***`. |
| `jira_base_url` | no | `https://sol-jira.atlassian.net` | Jira base URL. |
| `show_details` | no | by visibility | List the Jira issues with descriptions. Defaults to `true` for private and internal repositories. |
| `max_rows` | no | `50` | Most Jira issues listed. |
| `write_step_summary` | no | `true` | With `false`, the report is only written to `report_path`. |

Each `fossa_projects` entry:

| Key | Description |
| --- | --- |
| `label` | Row name, e.g. `Source` or `Container (amd64)`. |
| `project` | FOSSA project id, with or without the organisation prefix. |
| `branch`, `revision` | The FOSSA branch and revision the scan recorded. |
| `result` | The caller's licensing gate result: `success`, `failure`, `cancelled` or `skipped`. |

Blocking counts use FOSSA's issue types, the same rule `fossa-guard` blocks on.

## Outputs

| Output | Description |
| --- | --- |
| `report_path` | The report as a Markdown file, e.g. for a Slack or PR comment. |
| `licensing_blocking` | Blocking licensing issues across the projects; empty when not read. |
| `guardian_blocking` | Guardian findings past their SLA; empty when not read. |

## Example

```yaml
- name: Release readiness report
  if: ${{ always() }}
  uses: SolaceDev/solace-public-workflows/release-readiness-report@<sha>
  with:
    title: "Release readiness: `${{ inputs.version }}`"
    status: ${{ steps.decide.outputs.status }}
    reasons: ${{ steps.decide.outputs.reasons }}
    links: |
      Commit `${{ inputs.git_ref }}` | ${{ github.server_url }}/${{ github.repository }}/commit/${{ inputs.git_ref }}
    fossa_api_key: ${{ steps.vault.outputs.FOSSA_API_KEY }}
    fossa_projects: >-
      [{"label": "Source", "project": "SolaceDev_my-repo", "branch": "main",
        "revision": "${{ inputs.version }}", "result": "${{ needs.source.result }}"}]
    guardian_url: https://guardian.solacedev.ca
    guardian_key: ${{ steps.vault.outputs.GUARDIAN_API_TOKEN }}
    guardian_product_name: my-product
    guardian_product_version: main
    guardian_full_version: ${{ inputs.version }}
    guardian_dashboard_url: https://guardian-dashboard.solacedev.ca
```

## Tests

```bash
python3 -m unittest discover -s release-readiness-report/tests
```
