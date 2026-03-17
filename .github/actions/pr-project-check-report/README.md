# PR Project Check Report

Reusable action that aggregates project-level CI payloads and publishes a compact markdown report for:

- SonarQube quality gate (`check_type: sonarqube`)
- Unit tests (`check_type: unit-tests`)

It reads CI result artifacts from `results_dir`, writes a step summary, optionally updates a PR comment, optionally updates check-run details, and can fail the job when issues are found.

## Usage

```yaml
- name: Aggregate SonarQube report
  uses: SolaceDev/solace-public-workflows/.github/actions/pr-project-check-report@main
  with:
    check_type: sonarqube
    projects_json: ${{ needs.label-pr.outputs.all_plugins }}
    results_dir: ci-plugin-results
    sonarqube_host_url: ${{ secrets.SONARQUBE_HOST_URL }}
    github_token: ${{ secrets.GITHUB_TOKEN }}
    comment_on_pr: "true"
    check_name: "SonarQube Quality Gate"
    fail_on_issues: "true"
```

```yaml
- name: Aggregate Unit Tests report
  uses: SolaceDev/solace-public-workflows/.github/actions/pr-project-check-report@main
  with:
    check_type: unit-tests
    projects_json: ${{ needs.label-pr.outputs.all_plugins }}
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
| `projects_json` | no | `""` | JSON list of projects to aggregate |
| `plugins_json` | no | `""` | Deprecated alias for `projects_json` |
| `results_dir` | no | `ci-plugin-results` | Directory with downloaded JSON payload artifacts |
| `github_token` | no | `${{ github.token }}` | Token for PR comment/check-run updates |
| `sonarqube_host_url` | no | `https://sonarq.solace.com` | Sonar dashboard base URL (`sonarqube` mode only) |
| `check_name` | no | mode-specific | Target check-run name for details update |
| `comment_on_pr` | no | `false` | Create/update PR comment |
| `comment_marker` | no | mode-specific | Marker used to find existing bot comment |
| `update_check_details` | no | `true` | Update current check-run output summary |
| `fail_on_issues` | no | `true` | Fail action if aggregated result has issues |

## Outputs

| Output | Description |
|---|---|
| `all_passed` | `true` if all projects passed |
| `project_results` | JSON array of per-project rows |
| `failing_projects` | JSON list (unit-tests mode) |
| `missing_projects` | JSON list (unit-tests mode) |
| `report_markdown` | Full rendered markdown report |

Backward-compat outputs (`plugin_results`, `failing_plugins`, `missing_plugins`) are still emitted.
