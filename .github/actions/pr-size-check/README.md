# PR Size Check Action

A GitHub composite action that validates pull request size against a configurable maximum line limit.

## Usage

Add this action to your workflow file (e.g., `.github/workflows/pr-checks.yml`):

**Required Permissions:** The workflow must have `statuses: write` and `pull-requests: read` permissions to post status checks.

```yaml
name: PR Checks

on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  pr-size-check:
    name: Check PR Size
    runs-on: ubuntu-latest
    permissions:
      statuses: write
      pull-requests: read
    steps:
      - name: Validate PR Size
        uses: SolaceDev/solace-public-workflows/.github/actions/pr-size-check@main
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          max-lines: 500  # optional, defaults to 500
```

## Inputs

| Input | Description | Required | Default |
|-------|-------------|----------|---------|
| `max-lines` | Maximum PR size (additions + deletions) | No | `500` |
| `github-token` | GitHub token for API access (needs `repo:status` scope) | Yes | N/A |

## Outputs

| Output | Description |
|--------|-------------|
| `pr-size` | Total PR size (additions + deletions) |
| `size-exceeded` | Whether the PR size exceeds the limit (`true` or `false`) |

## Examples

### Basic usage with default limit (500 lines)

```yaml
- uses: SolaceDev/solace-public-workflows/.github/actions/pr-size-check@main
  with:
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

### Custom limit

```yaml
- uses: SolaceDev/solace-public-workflows/.github/actions/pr-size-check@main
  with:
    github-token: ${{ secrets.GITHUB_TOKEN }}
    max-lines: 1000
```

### Using outputs

```yaml
- name: Check PR Size
  id: size-check
  uses: SolaceDev/solace-public-workflows/.github/actions/pr-size-check@main
  with:
    github-token: ${{ secrets.GITHUB_TOKEN }}
    max-lines: 500

- name: Comment on large PRs
  if: steps.size-check.outputs.size-exceeded == 'true'
  run: |
    echo "PR is too large: ${{ steps.size-check.outputs.pr-size }} lines"
```

## Behavior

The action **always succeeds** (workflow passes) but posts a commit status check that shows success or failure:

- **Success**: PR size ≤ limit → Status check `PR Validation / Size Check` shows SUCCESS ✅
- **Failure**: PR size > limit → Status check `PR Validation / Size Check` shows FAILURE ❌

The workflow itself does not fail. Enforcement happens through branch protection rules (see below).

## Status Check

The action posts a commit status with context name: **`PR Validation / Size Check`**

When a PR exceeds the limit, the status check shows:
```
PR size exceeds maximum allowed limit: 600 lines (max: 500)
```

When within the limit:
```
PR size is within acceptable limits: 300 lines (max: 500)
```

## Enforcing PR Size Limits

To **block merges** for oversized PRs, add the status check as a required check in your branch protection rules:

1. Go to: **Settings** → **Branches** → **Branch protection rules**
2. Edit the rule for your main branch (e.g., `main`)
3. Enable: **Require status checks to pass before merging**
4. Search for and select: **`PR Validation / Size Check`**
5. Save changes

Once configured, PRs exceeding the limit cannot be merged until reduced in size.
