# PR FOSSA Diff Report

Reusable action that aggregates per-plugin FOSSA Guard diff results from build payloads, then publishes one aggregated report:

- step summary markdown
- optional PR comment (single updatable bot comment)
- optional status check details update
- optional job failure when new issues are introduced

Implementation note: this action does not execute FOSSA Guard. It expects
`ci-plugin-result-*.json` artifacts (produced by plugin build jobs) to be downloaded first.

## Usage

```yaml
- name: Aggregate FOSSA diff report
  uses: SolaceDev/solace-public-workflows/.github/actions/pr-fossa-diff-report@main
  with:
    plugins_json: ${{ needs.label-pr.outputs.all_plugins }}
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
| `plugins_json` | yes | - | JSON list of plugins to evaluate |
| `fossa_api_key` | no | `""` | Deprecated (ignored) |
| `repo_owner` | no | repo owner | Prefix for FOSSA project IDs (`{repo_owner}_{plugin}`) |
| `head_ref` | no | from PR event | PR revision used for diff mode |
| `base_sha` | no | from PR event | Deprecated (ignored) |
| `results_dir` | no | `ci-plugin-results` | Directory containing `ci-plugin-result-*.json` payloads |
| `docker_image` | no | `ghcr.io/solacedev/maas-build-actions:latest` | Image containing `fossa_guard.py` |
| `licensing_block_on` | no | `policy_conflict` | Licensing block rules |
| `vulnerability_block_on` | no | `critical,high` | Vulnerability block rules |
| `github_token` | no | `${{ github.token }}` | Token for comments/check updates |
| `check_name` | no | `FOSSA Report` | Check-run name for details update |
| `comment_on_pr` | no | `true` | Create/update PR comment |
| `comment_marker` | no | `FOSSA Guard (PR Diff)` | Marker used for comment upsert |
| `update_check_details` | no | `true` | Update current check-run output |
| `fail_on_issues` | no | `true` | Fail action when new issues exist |

When `update_check_details` is `true`, the action fails if the `FOSSA Report` check run cannot be created or updated. This prevents silent success without a visible status check.
When `comment_on_pr` is `true`, the action fails if comment creation/update fails.

## Outputs

| Output | Description |
|---|---|
| `has_issues` | `true` if any plugin has new diff issues |
| `projects_with_issues` | JSON list of plugin names with issues |
| `results_json` | JSON list of per-plugin aggregation details |
| `report_markdown` | Full rendered markdown report |

## Permissions

Recommended workflow permissions:

```yaml
permissions:
  pull-requests: write
  checks: write
  actions: read
```

If `comment_on_pr` is `false`, `pull-requests: write` is not required.
