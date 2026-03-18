# Monorepo FOSSA Diff Report

Aggregates per-project FOSSA diff results into one report for a PR.

The action expects project CI payload artifacts (produced by `monorepo-project-ci-report`) and does **not** execute FOSSA scans itself.

## What it publishes

- Job summary markdown
- Optional PR comment (upserted by marker)
- Optional check-run details update
- Optional failing exit code when new issues are introduced

## How aggregation works

For each changed project from `projects_json`, the action:

1. Loads the project's CI payload from `results_dir`.
2. Reads FOSSA normalized fields:
   - `fossa_licensing_total_issues`
   - `fossa_licensing_blocking_issues`
   - `fossa_licensing_outcome`
   - `fossa_vulnerability_total_issues`
   - `fossa_vulnerability_blocking_issues`
   - `fossa_vulnerability_outcome`
3. Marks project as failing if either licensing or vulnerability check did not pass.
4. Builds one markdown table plus overall totals for the PR.

## Usage

```yaml
- name: Aggregate FOSSA diff report
  uses: SolaceDev/solace-public-workflows/monorepo-fossa-diff-report@main
  with:
    projects_json: ${{ needs.label-pr.outputs.all_plugins }}
    results_dir: ci-plugin-results
    repo_owner: ${{ github.repository_owner }}
    head_ref: ${{ github.head_ref }}
    github_token: ${{ secrets.GITHUB_TOKEN }}
    check_name: "FOSSA Report"
    comment_on_pr: "true"
    fail_on_issues: "true"
```

## Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `projects_json` | no | `""` | JSON list of changed projects |
| `repo_owner` | no | repo owner | Prefix for FOSSA project IDs (`{repo_owner}_{project}`) |
| `head_ref` | no | from PR event | Revision used for diff reporting |
| `results_dir` | no | `ci-plugin-results` | Directory containing project payloads |
| `github_token` | no | `${{ github.token }}` | Token for comments/check updates |
| `check_name` | no | `FOSSA Report` | Check run name |
| `comment_on_pr` | no | `true` | Create/update PR comment |
| `comment_marker` | no | `FOSSA Guard (PR Diff)` | Marker for comment upsert |
| `pr_number` | no | `""` | Explicit PR number override |
| `update_check_details` | no | `true` | Create/update check-run details |
| `fail_on_issues` | no | `true` | Fail action when issues are found |

## Outputs

| Output | Description |
|---|---|
| `has_issues` | `true` if any project has new FOSSA issues |
| `projects_with_issues` | JSON list of failing projects |
| `results_json` | JSON list of per-project aggregation rows |
| `report_markdown` | Full rendered markdown report |

## Permissions

Recommended job permissions:

```yaml
permissions:
  pull-requests: write
  checks: write
  contents: read
```

- `pull-requests: write` is required when `comment_on_pr: true`.
- `checks: write` is required when `update_check_details: true`.
