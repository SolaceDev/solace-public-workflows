# PR Plugin Check Report

Reusable action that aggregates plugin-level CI payloads and publishes a compact markdown report for:

- SonarQube quality gate (`check_type: sonarqube`)
- Unit tests (`check_type: unit-tests`)

It reads `ci-plugin-result-*.json` artifacts (downloaded into `results_dir`), writes a step summary, optionally updates a PR comment, optionally updates the current check-run details, and can fail the job when issues are found.

## Usage

```yaml
- name: Download plugin result artifacts
  uses: actions/download-artifact@v4
  with:
    pattern: ci-plugin-result-*
    merge-multiple: true
    path: ci-plugin-results

- name: Aggregate SonarQube report
  uses: SolaceDev/solace-public-workflows/.github/actions/pr-plugin-check-report@main
  with:
    check_type: sonarqube
    plugins_json: ${{ needs.label-pr.outputs.all_plugins }}
    results_dir: ci-plugin-results
    sonarqube_host_url: ${{ secrets.SONARQUBE_HOST_URL }}
    github_token: ${{ secrets.GITHUB_TOKEN }}
    comment_on_pr: "true"
    check_name: "SonarQube Quality Gate"
    fail_on_issues: "true"
```

```yaml
- name: Aggregate Unit Tests report
  uses: SolaceDev/solace-public-workflows/.github/actions/pr-plugin-check-report@main
  with:
    check_type: unit-tests
    plugins_json: ${{ needs.label-pr.outputs.all_plugins }}
    results_dir: ci-plugin-results
    github_token: ${{ secrets.GITHUB_TOKEN }}
    comment_on_pr: "false"
    check_name: "Unit Tests"
    fail_on_issues: "true"
```

## Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `check_type` | yes | - | `sonarqube` or `unit-tests` |
| `plugins_json` | yes | - | JSON list of plugins to aggregate |
| `results_dir` | no | `ci-plugin-results` | Directory with downloaded JSON payload artifacts |
| `github_token` | no | `${{ github.token }}` | Token for PR comment/check-run updates |
| `sonarqube_host_url` | no | `https://sonarq.solace.com` | Sonar dashboard base URL (`sonarqube` mode only) |
| `check_name` | no | mode-specific | Target check-run name for details update |
| `comment_on_pr` | no | `false` | Create/update PR comment |
| `comment_marker` | no | mode-specific | Marker used to find existing bot comment |
| `update_check_details` | no | `true` | Update current check-run output summary |
| `fail_on_issues` | no | `true` | Fail action if aggregated result has issues |

When `update_check_details` is `true`, the action will fail if it cannot create or update the named check run. This guarantees the status check is always published (or the workflow fails loudly).

## Outputs

| Output | Description |
|---|---|
| `all_passed` | `true` if all plugins passed |
| `plugin_results` | JSON array of per-plugin rows |
| `failing_plugins` | JSON list (unit-tests mode) |
| `missing_plugins` | JSON list (unit-tests mode) |
| `report_markdown` | Full rendered markdown report |

## Permissions

Recommended workflow permissions for full functionality:

```yaml
permissions:
  checks: write
  pull-requests: write
  actions: read
```

If `comment_on_pr` is `false`, `pull-requests: write` is not required.
