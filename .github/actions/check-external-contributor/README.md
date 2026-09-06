# Check External Contributor Action

Automatically labels pull requests created by users who are not members of a specified GitHub team.

## Usage

```yaml
- uses: SolaceDev/solace-public-workflows/check-external-contributor@main
  with:
    github_team_slug: solace-ai
    label_name: "external contributor"
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

## Inputs

| Input | Description | Required | Default |
|-------|-------------|----------|---------|
| `github_team_slug` | GitHub team slug to check membership against (e.g., `solace-ai`) | Yes | - |
| `label_name` | Label to add to PR if creator is not in the team | No | `"external contributor"` |
| `github-token` | GitHub token for API access | Yes | - |

## How it Works

1. Checks if the PR creator is a member of the specified GitHub team
2. If not a member, adds the specified label to the PR
3. Logs the results for debugging

## Workflow Trigger

This action is designed to work with `pull_request_target` to safely handle external contributors:

```yaml
on:
  pull_request_target:
    types: [opened, reopened]

jobs:
  check-external:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
      issues: write
```

## Examples

### Basic Example

```yaml
name: Check External Contributor
on:
  pull_request_target:
    types: [opened, reopened]

jobs:
  check:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
      issues: write
    steps:
      - uses: SolaceDev/solace-public-workflows/check-external-contributor@main
        with:
          github_team_slug: my-team
          label_name: "external contributor"
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

## Permissions Required

The GitHub token must have the following permissions:
- `pull-requests: write` - To access PR information
- `issues: write` - To add labels to PRs

## Notes

- Use `pull_request_target` instead of `pull_request` for security when running workflows on external PRs
- The action gracefully handles errors when checking team membership
- If the label doesn't exist, GitHub will automatically create it when adding it to the PR
