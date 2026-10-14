# Guardian Container Scan and Sync

Scans a container image, uploads the results to Guardian, and runs Guardian's DB and Jira sync, in one step:

1. Scans with Prisma Cloud and uploads the results ([`prisma-cloud-scan`](../prisma-cloud-scan/)).
2. Optionally scans with Trivy and uploads those results to the same Guardian scan.
3. Runs the sync ([`guardian-db-sync`](../guardian-db-sync/)) for every scanner that uploaded successfully.
4. Reports the open Guardian findings for the build in the job summary and, optionally, a "Guardian Scan" check run. See [Guardian report](#guardian-report).

The nested actions run at the same commit as this action.

## Requirements

- The image is already pushed, and the job is logged in to its registry (or the image is local and `skip_image_pull: "true"`).
- A Docker daemon on the runner.
- `checks: write` for the Guardian check run (optional; without it the check run is skipped with a notice).
- Enough free disk for Trivy's vulnerability database when `run_trivy` is `true`.

## Inputs

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| `image_registry` | yes | | Image registry. |
| `image_repo` | no | repository name | Image repository. |
| `image_tag` | yes | | Image tag to scan. |
| `pcc_console_url` | yes | | Prisma Cloud Console URL. |
| `pcc_user` | yes | | Prisma Cloud access key ID. |
| `pcc_pass` | yes | | Prisma Cloud secret key. |
| `guardian_url` | yes | | Guardian API base URL. |
| `guardian_key` | yes | | Guardian API token. |
| `guardian_product_name` | no | `image_repo` | Guardian product name. |
| `guardian_product_version` | no | default branch | Guardian product version. Should match the product's trunk branch in Guardian. |
| `guardian_product_full_version` | no | `image_tag` | Guardian product full version. |
| `run_trivy` | no | `false` | Also scan with Trivy and sync its findings. |
| `trivy_version` | no | `v0.69.2` | Trivy version. |
| `show_detailed_logs` | no | by visibility | Show per-finding detail. See [Public repositories](#public-repositories). |
| `twistcli_publish` | no | `false` | Publish Prisma results to the Prisma Cloud Console. |
| `bypass_blocking` | no | `true` | Never fail on Prisma findings. |
| `skip_image_pull` | no | `false` | Use a local image instead of pulling. |
| `create_status_check` | no | `true` | Post the "Guardian Scan" check run. Skipped with a notice when the token lacks `checks: write`. |
| `guardian_dashboard_url` | no | | Guardian dashboard URL, used for links in the report. |
| `jira_base_url` | no | `https://sol-jira.atlassian.net` | Jira URL, used for issue links in the report. |
| `jira_dry_run` | no | `false` | Run Guardian's Jira reporting in dry-run mode. |
| `upload_logs` | no | `false` | Upload the sync logs as an artifact. |

## Outputs

| Output | Description |
| --- | --- |
| `prisma_scan_passed` | Prisma policy result (`true`/`false`). |
| `prisma_vuln_critical` / `_high` / `_medium` / `_low` | Prisma vulnerability counts. |
| `prisma_console_link` | Link to the Prisma Cloud results. |
| `trivy_status` | `success`, `failure` or `skipped`. |
| `trivy_vuln_critical` / `_high` / `_medium` / `_low` / `_unknown` | Trivy vulnerability counts. |
| `unifiers` | Scanners included in the sync (`prisma` or `prisma,trivy`). |
| `product_name`, `product_version`, `response_json` | Sync results from `guardian-db-sync`. |
| `guardian_blocking_count` / `guardian_pending_count` | Open findings with a fix that are past / within their SLA. |
| `guardian_check_run_url` | URL of the Guardian check run, when one was posted. |

## Guardian report

After the sync, the action reads the build's open findings that have a fix available from Guardian and writes a report to the job summary. With `create_status_check` on and `checks: write` granted, it also posts the report as a "Guardian Scan" check run on the commit. The report never fails the job: the check concludes `success` when nothing is past its SLA and `neutral` otherwise.

The Prisma and Trivy scans don't post their own check runs or job summaries.

With details shown (see [Public repositories](#public-repositories)), the report has one row per Jira issue, grouping that issue's CVEs for a component, with severity, package and version, the earliest version that fixes all of them, when it's due, the scanners that found it, and a short description. Issues and CVEs link to Jira and to the Guardian dashboard (when `guardian_dashboard_url` is set). With details hidden, the report shows only counts by severity.

## Credentials

The action masks the Guardian URL, the Guardian token and the Prisma credentials for all of its own steps. GitHub logs an action's inputs before its first step runs, though, so pass these as secrets (as in the example) to keep them out of that input list as well.

## Trivy failures

If `run_trivy` is `true` but Trivy produces no report or its upload fails, the sync still runs with Prisma only, and the action then fails. Prisma findings stay current, and the failure is visible. Findings reported only by Trivy are left unchanged until a later sync that includes Trivy.

## Public repositories

`show_detailed_logs` defaults to `false` for public repositories, and when visibility can't be determined. With it off, the job summary and the Guardian check run show only severity counts, Prisma finding details are hidden from logs, and the raw Trivy report is not uploaded as an artifact. Set it to `"true"` to include them.

## Example

```yaml
permissions:
  contents: read
  checks: write

steps:
  # ... log in to the image registry ...

  - name: Scan and sync with Guardian
    id: guardian
    uses: SolaceDev/solace-public-workflows/guardian-container-scan-and-sync@<sha>
    with:
      image_registry: ${{ steps.login.outputs.registry }}
      image_repo: my-image
      image_tag: ${{ env.VERSION }}
      pcc_console_url: ${{ secrets.PRISMACLOUD_CONSOLE_URL }}
      pcc_user: ${{ secrets.PRISMACLOUD_ACCESS_KEY_ID }}
      pcc_pass: ${{ secrets.PRISMACLOUD_SECRET_KEY }}
      guardian_url: ${{ secrets.GUARDIAN_API_URL }}
      guardian_key: ${{ secrets.GUARDIAN_API_TOKEN }}
      guardian_product_version: develop
      guardian_dashboard_url: https://guardian-dashboard.example.com
      run_trivy: "true"
```

## Tests

```bash
python3 -m unittest discover -s guardian-container-scan-and-sync/tests
```
