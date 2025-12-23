# fossa-guard GitHub Action Usage Guide

The `fossa-guard` GitHub Action integrates with the FOSSA API to fetch and process licensing or vulnerability issues for a given project. It is designed for CI/CD pipelines (such as GitHub Actions) to enforce open source compliance and security policies.

---

## Usage

```yaml
  uses: SolaceDev/solace-public-workflows/.github/actions/fossa-guard@main
  with:
    fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
    fossa_project_id: <your_fossa_project_id>
    fossa_category: licensing # or vulnerability
    fossa_mode: BLOCK        # Optional, default is BLOCK. Use REPORT for reporting only.
    block_on: policy_conflict,policy_flag # Optional, comma-separated list of issue types to block on
```

---

## Inputs

| Name                  | Required | Description                                                                 |
|-----------------------|----------|-----------------------------------------------------------------------------|
| `fossa_api_key`       | Yes      | API key for FOSSA.                                                          |
| `fossa_project_id`    | Yes      | Project ID in FOSSA. Can be specified in `.fossa.yml`. If not, use the format `custom+48578/SolaceDev_solace-agent-mesh-enterprise` and drop the `custom+48578/` prefix. |
| `fossa_category`      | Yes      | Issue category: `licensing` or `vulnerability`.                             |
| `fossa_mode`          | No       | Comma-separated list of actions: `BLOCK`, `REPORT`, or both (e.g., `BLOCK,REPORT`). Default: `BLOCK`.|
| `block_on`            | No       | Comma-separated list of issue types to block on. For licensing: `policy_conflict,policy_flag`. For vulnerability: `critical,high,medium,low`. Default: `policy_conflict`.|
| `fossa_branch`        | No       | Specify a branch name to query issues for that branch (e.g., 'main', 'develop', 'feature/xyz'). |
| `fossa_revision`      | No       | Specify a commit SHA to filter issues for a specific revision. Can be used alone or with `fossa_branch` for better context. |
| `fossa_revision_scan_id` | No    | Specify a revision scan ID for more granular filtering (advanced usage).     |
| `fossa_release`       | No       | Specify a release group ID to filter issues for a release group (advanced usage). |
| `fossa_release_scan_id` | No    | Specify a release scan ID for release group filtering (advanced usage).      |
| `slack_token`         | No       | Slack bot token for posting messages (optional).                             |
| `slack_channel`       | No       | Slack channel ID to post to (optional).                                      |
| `slack_thread_ts`     | No       | Slack thread timestamp to reply to an existing thread (optional).            |
| `github_repository`   | No       | GitHub repository name for links (optional).                                 |
| `github_run_id`       | No       | GitHub Actions run ID for build links (optional).                            |
| `github_server_url`   | No       | GitHub server URL (default: https://github.com) (optional).                  |

### PR Integration Inputs (Optional)

| Input | Default | Description |
|-------|---------|-------------|
| `github_token` | `${{ github.token }}` | GitHub token for PR comments and status checks |
| `enable_pr_comment` | `true` | Enable PR commenting (`true`/`false`) |
| `enable_status_check` | `true` | Enable GitHub status checks (`true`/`false`) |
| `status_check_name` | `FOSSA Guard` | Custom name for status checks |
| `pr_comment_max_violations` | `5` | Max violations shown in PR comment |

### Issue Types Explained
- **policy_conflict**: There is a known explicit policy violation (FOSSA terminology). This means the license or dependency is denied in your FOSSA policy and should block the build.
- **policy_flag**: The license needs to be reviewed or is unknown (FOSSA terminology). This means the license or dependency is flagged for review or is uncategorized in your FOSSA policy and may require manual attention.

> **Note:**
> The FOSSA project ID can be specified in your `.fossa.yml` file. If not present, use the format `custom+48578/SolaceDev_solace-agent-mesh-enterprise` and drop the `custom+48578/` prefix, so the project ID is just `SolaceDev_solace-agent-mesh-enterprise`.

---

## Supported Modes

| Mode   | Description                                                                                   |
|--------|-----------------------------------------------------------------------------------------------|
| BLOCK  | Fails the build if violations matching `block_on` are found. Prints a Markdown/HTML summary.  |
| REPORT | Generates and sends Slack reports (requires `slack_token` and `slack_channel`). Prints a Markdown/HTML summary. Intended for reporting only. Exit code 1 if Slack reporting fails and REPORT is the only action. |
| BLOCK,REPORT | Combines both actions - blocks on violations AND sends Slack reports. Exit code 2 if blocking violations found (Slack failure won't affect exit code). Exit code 0 if no blocking violations. |

---

## Business Logic

- Fetches issues from FOSSA for the specified project and category.
- All violations are always reported in the summary, regardless of blocking rules.
- The `block_on` flag determines which issue types (e.g., `policy_conflict`, `policy_flag`) will cause the build to fail in BLOCK mode.
- If `block_on` is empty, no violations will block the build, but all will be reported.
- Supports both licensing and vulnerability categories, with clear, formatted output for each.
- In REPORT mode, the script is intended for informational/reporting purposes and will not fail the build.

---

## Example Workflow Usage

```yaml
jobs:
  fossa_guard:
    runs-on: ubuntu-latest
    steps:
      - name: Run FOSSA Guard (Block mode)
        uses: SolaceDev/solace-public-workflows/.github/actions/fossa-guard@main
        with:
          fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
          fossa_project_id: ${{ secrets.FOSSA_PROJECT_ID }}
          fossa_category: licensing
          fossa_mode: BLOCK
          block_on: policy_conflict,policy_flag

      - name: Run FOSSA Guard (Report only, for Slack)
        uses: SolaceDev/solace-public-workflows/.github/actions/fossa-guard@main
        continue-on-error: true
        with:
          fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
          fossa_project_id: ${{ secrets.FOSSA_PROJECT_ID }}
          fossa_category: licensing
          fossa_mode: REPORT
          block_on: policy_conflict,policy_flag
```

> **Note:**
> If you want to use REPORT mode for Slack reporting and do not want the CI to fail on violations, set `continue-on-error: true` on the step.

---

## Pull Request Workflow Example

```yaml
name: FOSSA PR Check

on:
  pull_request:
    branches: [main]

permissions:
  pull-requests: write  # For PR comments
  checks: write         # For status checks
  issues: write         # For PR comments

jobs:
  fossa-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: FOSSA Guard with PR Integration
        uses: SolaceDev/solace-public-workflows/.github/actions/fossa-guard@main
        with:
          fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
          fossa_project_id: ${{ secrets.FOSSA_PROJECT_ID }}
          fossa_category: licensing
          fossa_mode: BLOCK
          fossa_branch: ${{ github.event.pull_request.number && 'PR' || github.event.repository.default_branch }}
          fossa_revision: ${{ github.event.pull_request.head.ref || github.sha }}
          block_on: policy_conflict,policy_flag
          # PR features (auto-enabled)
          github_token: ${{ github.token }}
          enable_pr_comment: true
          enable_status_check: true
```

### Branch Protection Setup

To enforce FOSSA checks before merging:

1. Repository Settings → Branches → Add protection rule
2. Enable "Require status checks to pass before merging"
3. Add required checks:
   - `FOSSA Guard (licensing)`
   - `FOSSA Guard (vulnerability)` (if applicable)

---

## Notes
- The action prints a Markdown summary to the GitHub Actions log.
- If the `GITHUB_STEP_SUMMARY` environment variable is set, the summary is also written to the step summary for rich UI display.
- In BLOCK mode, the script exits with code 2 if blocking violations are found, causing the GitHub Action to fail.
- Advanced parameters (`fossa_branch`, `fossa_revision`, `fossa_revision_scan_id`, `fossa_release`, `fossa_release_scan_id`) allow targeting issues for a specific branch, tag, commit, or release group. If unset, the script defaults to the latest scan for the project.
- Slack integration parameters (`slack_token`, `slack_channel`, `slack_thread_ts`) allow posting formatted reports to Slack channels or threads.
- GitHub context parameters (`github_repository`, `github_run_id`, `github_server_url`) allow linking reports to specific repositories and builds.
- For more details, see the script source and comments.

---

## Troubleshooting

### PR Comment Not Appearing

**Check:**
- `github_token` input is set (defaults to `${{ github.token }}`)
- Workflow has `pull-requests: write` and `issues: write` permissions
- Running in `pull_request` event (not `push`)

### Status Check Not Appearing

**Check:**
- Workflow has `checks: write` permission
- Using PR head SHA: `fossa_revision: ${{ github.event.pull_request.head.ref || github.sha }}`

### Token Permission Errors

Add to workflow:
```yaml
permissions:
  pull-requests: write
  checks: write
  issues: write
```
