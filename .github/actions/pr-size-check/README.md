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

- **Success**: PR size is within the limit - the action passes
- **Failure**: PR size exceeds the limit - the action fails with an error message showing the actual size and the limit

## Error Message Format

When a PR exceeds the limit, the action will fail with:

```
PR size (600 lines) exceeds maximum allowed limit (500 lines)
```
