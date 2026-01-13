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
| `enable_pr_comment` | `false` | Enable PR commenting (`true`/`false`) |
| `enable_status_check` | `false` | Enable GitHub status checks (`true`/`false`) |
| `status_check_name` | `FOSSA Guard` | Custom name for status checks |
| `pr_comment_max_violations` | `5` | Max violations shown in PR comment |
| `enable_diff_mode` | `false` | Enable diff mode to show only new issues (`true`/`false`) |
| `diff_base_revision_sha` | (auto-detect) | Base revision SHA to compare against (optional - auto-detects default branch) |
| `enable_license_enrichment` | `true` | Show declared/discovered license indicators (`true`/`false`) |

### Issue Types Explained
- **policy_conflict**: There is a known explicit policy violation (FOSSA terminology). This means the license or dependency is denied in your FOSSA policy and should block the build.
- **policy_flag**: The license needs to be reviewed or is unknown (FOSSA terminology). This means the license or dependency is flagged for review or is uncategorized in your FOSSA policy and may require manual attention.

> **Note:**
> The FOSSA project ID can be specified in your `.fossa.yml` file. If not present, use the format `custom+48578/SolaceDev_solace-agent-mesh-enterprise` and drop the `custom+48578/` prefix, so the project ID is just `SolaceDev_solace-agent-mesh-enterprise`.

---

## Supported Modes

| Mode   | Description                                                                                   |
|--------|-----------------------------------------------------------------------------------------------|
| BLOCK  | Fails the build if violations matching `block_on` are found (exit code 2). PR comments show violations. Status checks fail. Prints a Markdown/HTML summary.  |
| REPORT | Shows violations in PR comments and status checks (marked as failed), but build passes (exit code 0). Useful for gradual rollout. Also sends Slack reports if configured. |
| BLOCK,REPORT | Combines both actions - blocks on violations AND sends Slack reports. Exit code 2 if blocking violations found (Slack failure won't affect exit code). Exit code 0 if no blocking violations. |

### Mode Behavior Clarification

**Important**: PR comments and status checks work identically in both BLOCK and REPORT modes. The only difference is:
- **REPORT mode**: Shows violations in status check (failure), but build passes (exit 0)
- **BLOCK mode**: Shows violations in status check (failure), and build fails (exit 2)

This allows you to enable PR integration in REPORT mode first for visibility without blocking builds, then switch to BLOCK mode when ready to enforce compliance.

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

## Pull Request Workflow Examples

### Basic PR Integration

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

### With Diff Mode (Recommended for PRs)

Diff mode shows only newly introduced issues, making PR reviews more focused:

```yaml
name: FOSSA PR Check with Diff Mode

on:
  pull_request:
    branches: [main, master]

permissions:
  pull-requests: write  # For PR comments
  checks: write         # For status checks
  issues: write         # For PR comments

jobs:
  fossa-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: FOSSA Guard - Licensing (Diff Mode)
        uses: SolaceDev/solace-public-workflows/.github/actions/fossa-guard@main
        with:
          fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
          fossa_project_id: ${{ secrets.FOSSA_PROJECT_ID }}
          fossa_category: licensing
          fossa_mode: BLOCK
          fossa_branch: PR
          fossa_revision: ${{ github.event.pull_request.head.ref }}
          block_on: policy_conflict
          # Diff mode - auto-detects base branch
          enable_diff_mode: true
          # PR Integration
          github_token: ${{ github.token }}
          enable_pr_comment: true
          enable_status_check: true

      - name: FOSSA Guard - Vulnerabilities (Diff Mode)
        uses: SolaceDev/solace-public-workflows/.github/actions/fossa-guard@main
        with:
          fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
          fossa_project_id: ${{ secrets.FOSSA_PROJECT_ID }}
          fossa_category: vulnerability
          fossa_mode: BLOCK
          fossa_branch: PR
          fossa_revision: ${{ github.event.pull_request.head.ref }}
          block_on: critical,high
          # Diff mode
          enable_diff_mode: true
          # PR Integration
          github_token: ${{ github.token }}
          enable_pr_comment: true
          enable_status_check: true
```

### REPORT Mode Example (Non-Blocking)

Use REPORT mode for gradual rollout - violations are shown but don't fail the build:

```yaml
- name: FOSSA Guard (Report Mode - Non-Blocking)
  uses: SolaceDev/solace-public-workflows/.github/actions/fossa-guard@main
  with:
    fossa_api_key: ${{ secrets.FOSSA_API_KEY }}
    fossa_project_id: ${{ secrets.FOSSA_PROJECT_ID }}
    fossa_category: licensing
    fossa_mode: REPORT  # Show violations but don't fail build
    block_on: policy_conflict,policy_flag
    enable_diff_mode: true
    github_token: ${{ github.token }}
    enable_pr_comment: true
    enable_status_check: true  # Status shows failure but build passes
```

### Branch Protection Setup

To enforce FOSSA checks before merging:

1. Repository Settings → Branches → Add protection rule
2. Enable "Require status checks to pass before merging"
3. Add required checks:
   - `FOSSA Guard (licensing)`
   - `FOSSA Guard (vulnerability)` (if applicable)

---

## Diff Mode

Diff mode compares the PR branch against the base branch to show only newly introduced issues, making PR reviews more focused.

### How It Works

- Compares current scan results against base branch scan results
- Shows "X new, Y total (Z in base)" in PR comments for clarity
- Auto-detects default branch (main/master) if `diff_base_revision_sha` not provided
- Uses three-tier matching strategy for accurate comparison

### Requirements

- Base branch must have been scanned by FOSSA for comparison to work
- Best used with PR workflows to focus on newly introduced issues

### Usage

```yaml
with:
  enable_diff_mode: true
  # Optional - will auto-detect if not provided
  diff_base_revision_sha: ${{ github.event.pull_request.base.sha }}
```

---

## PR Comment Features

- **Smart deduplication**: One comment per category (licensing/vulnerability) - updates existing, doesn't duplicate
- **Top N violations**: Shows top N violations (default: 5, configurable via `pr_comment_max_violations`)
- **Clear explanations**: Shows what's blocking vs what needs review
- **Direct links**: Links to full scan report and FOSSA dashboard
- **Blocking status**: For vulnerabilities, shows actual blocking status (e.g., "✅ No blocking issues found (configured to block on: HIGH)")
- **Diff mode support**: Shows "X new, Y total (Z in base)" when diff mode is enabled

---

## Status Check Behavior

- Status checks show **failure** when violations exist matching `block_on` rules (regardless of mode)
- Status checks show **success** when no violations found or all issues are non-blocking
- Can be used with branch protection rules to enforce compliance
- Works in both BLOCK and REPORT modes (only exit code differs)

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
- `enable_pr_comment` is not set to `false`

### Status Check Not Appearing

**Check:**
- Workflow has `checks: write` permission
- Using PR head SHA: `fossa_revision: ${{ github.event.pull_request.head.ref || github.sha }}`
- `enable_status_check` is not set to `false`

### Diff Mode Not Working

**Check:**
- The PR branch revision has been scanned by FOSSA (ensure FOSSA scan runs before FOSSA Guard)
- The base branch revision exists in FOSSA scan history
- `enable_diff_mode` is set to `true`
- FOSSA project exists and has scan data for both revisions

### Token Permission Errors

Add to workflow:
```yaml
permissions:
  pull-requests: write
  checks: write
  issues: write
```

---


## Reference Links

- **Implementation PR**: https://github.com/SolaceDev/maas-build-actions/pull/581
- **Live Example**: https://github.com/SolaceDev/solace-agent-mesh-enterprise/pull/458
- **Full Documentation**: See maas-build-actions repository `scripts/fossa-guard/fossa-guard-usage.md`
