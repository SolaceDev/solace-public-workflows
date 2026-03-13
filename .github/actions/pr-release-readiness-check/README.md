# PR Release Readiness Check

Reusable action that performs release-readiness aggregation for PRs with one unified output:

- SonarQube hotspots (main/base branch view)
- FOSSA licensing
- FOSSA vulnerabilities
- One markdown report used for:
  - step summary
  - PR comment (optional)
  - unified check-run details (optional)

It also returns a pass/fail conclusion and can fail the job when issues exist.

## Usage

```yaml
jobs:
  release-readiness:
    runs-on: ubuntu-latest
    permissions:
      checks: write
      pull-requests: write
      contents: read
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: pypa/hatch@install

      - name: Run release readiness check
        uses: SolaceDev/solace-public-workflows/.github/actions/pr-release-readiness-check@main
        with:
          pr_number: ${{ github.event.pull_request.number }}
          github_token: ${{ secrets.GITHUB_TOKEN }}
          fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
          sonarqube_token: ${{ secrets.SONARQUBE_TOKEN }}
          sonarqube_host_url: ${{ secrets.SONARQUBE_HOST_URL }}
          base_branch: main
          fail_on_issues: "true"
```

## Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `pr_number` | no | auto | PR number for comment/check targeting |
| `github_token` | no | `${{ github.token }}` | Token for checks/comments |
| `fossa_api_key` | yes | - | FOSSA API key |
| `sonarqube_token` | yes | - | SonarQube token |
| `sonarqube_host_url` | yes | - | SonarQube host URL |
| `repo_owner` | no | repo owner | Prefix for Sonar/FOSSA project IDs |
| `base_branch` | no | `main` | Baseline branch for diff and branch checks |
| `check_name` | no | `Release Readiness` | Unified check run name |
| `comment_marker` | no | `Release Readiness Check Results` | PR comment upsert marker |
| `update_pr_comment` | no | `true` | Create/update PR comment |
| `update_check_details` | no | `true` | Create/update unified check-run |
| `fail_on_issues` | no | `true` | Fail action if issues are found |
| `docker_image` | no | `ghcr.io/solacedev/maas-build-actions:latest` | Image containing `fossa_guard.py` |
| `licensing_block_on` | no | `policy_conflict` | FOSSA licensing block rules |
| `vulnerability_block_on` | no | `critical,high` | FOSSA vulnerability block rules |

## Outputs

| Output | Description |
|---|---|
| `conclusion` | `success` or `failure` |
| `summary` | Short summary string |
| `projects_with_issues` | JSON list of plugin names with issues |
| `report_markdown` | Full rendered markdown report |
| `report_file` | Path to generated markdown report in workspace |

When `update_check_details` is `true`, the action fails if it cannot create/update the unified `Release Readiness` check run. This ensures the check is always visible on the PR.
When `update_pr_comment` is `true`, the action fails if comment creation/update fails.

## Permissions

Recommended workflow permissions:

```yaml
permissions:
  checks: write
  pull-requests: write
  contents: read
```
