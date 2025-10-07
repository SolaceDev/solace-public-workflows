# GitHub Permissions Guide

This document provides detailed information about the GitHub token permissions required for the Generate GitHub Release Notes action.

## Quick Fix for Common Issues

If you're seeing this error:

```
Resource not accessible by integration
```

**Solution**: Add the required permissions to your workflow:

```yaml
jobs:
  generate-changelog:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: read
      metadata: read
    steps:
      # ... your steps
```

## Required Permissions Explained

### Why These Permissions Are Needed

| Permission      | Scope  | Purpose                                        |
| --------------- | ------ | ---------------------------------------------- |
| `contents`      | `read` | Access repository content, commits, and tags   |
| `pull-requests` | `read` | Link commits to their associated pull requests |
| `metadata`      | `read` | Access basic repository information            |

### What Happens Without These Permissions

| Missing Permission    | Error                                    | Impact                                        |
| --------------------- | ---------------------------------------- | --------------------------------------------- |
| `contents: read`      | Cannot access repository                 | Action fails completely                       |
| `pull-requests: read` | "Resource not accessible by integration" | PR links missing from output                  |
| `metadata: read`      | Cannot access repository metadata        | Action may fail or produce incomplete results |

## Implementation Examples

### Example 1: Basic Workflow (Recommended)

```yaml
name: Generate Changelog

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pull-requests: read
  metadata: read

jobs:
  generate-changelog:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Generate Release Notes
        uses: SolaceDev/solace-public-workflows/generate-github-release-notes@main
        with:
          from-ref: "v1.0.0"
          to-ref: "v1.1.0"
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

### Example 2: Job-Level Permissions

```yaml
name: Generate Changelog

on:
  workflow_dispatch:

jobs:
  generate-changelog:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: read
      metadata: read
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Generate Release Notes
        uses: SolaceDev/solace-public-workflows/generate-github-release-notes@main
        with:
          from-ref: ${{ inputs.from_ref }}
          to-ref: ${{ inputs.to_ref }}
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

### Example 3: Using Personal Access Token

If you need broader permissions or cross-repository access:

```yaml
jobs:
  generate-changelog:
    runs-on: ubuntu-latest
    steps:
      - name: Generate Release Notes
        uses: SolaceDev/solace-public-workflows/generate-github-release-notes@main
        with:
          from-ref: "v1.0.0"
          to-ref: "v1.1.0"
          github-token: ${{ secrets.PERSONAL_ACCESS_TOKEN }}
```

**PAT Requirements:**

- `repo` scope (for private repositories)
- `public_repo` scope (for public repositories)

## Troubleshooting

### Error: "Resource not accessible by integration"

**Cause**: Missing `pull-requests: read` permission

**Solution**: Add the permission to your workflow:

```yaml
permissions:
  pull-requests: read
```

### Error: "Bad credentials" or "Not Found"

**Cause**: Invalid or insufficient token

**Solutions**:

1. Verify `GITHUB_TOKEN` is correctly passed
2. Check if repository is private (may need PAT)
3. Ensure token has required scopes

### Error: "API rate limit exceeded"

**Cause**: Too many API requests

**Solutions**:

1. Use `GITHUB_TOKEN` instead of PAT (higher rate limits)
2. Add delays between workflow runs
3. Consider using GitHub App token

### Organization Restrictions

Some organizations restrict token permissions. If you encounter issues:

1. **Check organization settings**: Security → Actions → General
2. **Contact your admin**: They may need to allow the required permissions
3. **Use GitHub App**: Create an app with necessary permissions
4. **Use PAT**: Personal Access Token with broader scopes

## Security Considerations

### Principle of Least Privilege

The action only requests the minimum permissions needed:

- `read` access only (no write permissions)
- Specific scopes (not broad `repo` access)
- No access to secrets or sensitive data

### Token Security

- **GITHUB_TOKEN**: Automatically provided, scoped to the repository
- **PAT**: Store as encrypted secret, never in plain text
- **GitHub App**: Most secure for organization-wide usage

### What the Action Can Access

With the required permissions, the action can:

- ✅ Read commit history and metadata
- ✅ Access pull request information
- ✅ Read repository tags and branches

The action **cannot**:

- ❌ Write to the repository
- ❌ Access other repositories (unless using PAT/App)
- ❌ Access secrets or sensitive data
- ❌ Modify issues or pull requests

## Migration Guide

### From Basic GITHUB_TOKEN

If your current workflow uses:

```yaml
github-token: ${{ secrets.GITHUB_TOKEN }}
```

Add permissions:

```yaml
permissions:
  contents: read
  pull-requests: read
  metadata: read
# ... rest of workflow
```

### From Personal Access Token

If you're using a PAT, you can either:

1. **Keep using PAT** (no changes needed)
2. **Switch to GITHUB_TOKEN** with permissions (more secure)

### From GitHub App

GitHub App tokens work without additional configuration, as they typically have the necessary permissions.

## FAQ

**Q: Why not use `repo` scope for everything?**
A: Following security best practices, we request only the minimum permissions needed.

**Q: Can I use this action in a private repository?**
A: Yes, with proper permissions. Use `GITHUB_TOKEN` with permissions or a PAT with `repo` scope.

**Q: What if my organization doesn't allow these permissions?**
A: Contact your GitHub organization admin or use a Personal Access Token.

**Q: Does this work with GitHub Enterprise?**
A: Yes, the same permissions apply to GitHub Enterprise Server and GitHub Enterprise Cloud.

**Q: Can I run this action on a fork?**
A: Yes, but the token needs access to the target repository. PRs from forks may have limited permissions.

## Support

If you continue to experience permission issues:

1. Check the [GitHub Actions documentation](https://docs.github.com/en/actions/security-guides/automatic-token-authentication)
2. Review your organization's security settings
3. Consider using a Personal Access Token or GitHub App
4. Open an issue in the repository with your workflow configuration (remove sensitive information)
