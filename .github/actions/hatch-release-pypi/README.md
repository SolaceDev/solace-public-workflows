# Hatch Release to PyPI Action

A composite action for releasing Python packages to PyPI using [Trusted Publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/).

## Features

- Version bumping using Hatch
- Skips version bump if last commit was already a version bump
- Builds Python package distribution
- Publishes to PyPI using Trusted Publishing (no API token required)
- Commits and pushes version bump
- Creates GitHub Release with wheel artifacts
- Generates and updates release notes

## Prerequisites

1. **PyPI Trusted Publisher Configuration**: Configure your repository as a trusted publisher on PyPI:
   - Go to [PyPI Project Settings](https://pypi.org/manage/project/YOUR_PROJECT/settings/publishing/)
   - Add a new trusted publisher with your repository details
   - Set the workflow name and optionally the environment name (`pypi`)

2. **Repository Permissions**: The calling job must have these permissions:
   ```yaml
   permissions:
     id-token: write    # Required for Trusted Publishing
     contents: write    # Required for pushing commits and creating releases
   ```

3. **SSH Key for Pushing**: The repository must be checked out with an SSH key that has push access.

## Usage

```yaml
jobs:
  release:
    runs-on: ubuntu-latest
    environment: pypi  # Recommended for Trusted Publishing
    permissions:
      id-token: write
      contents: write
    steps:
      - name: Checkout
        uses: actions/checkout@v5
        with:
          fetch-depth: 0
          ssh-key: ${{ secrets.COMMIT_KEY }}

      # Add any project-specific build steps here (e.g., npm build for frontend)

      - name: Release to PyPI
        id: release
        uses: SolaceDev/solace-public-workflows/.github/actions/hatch-release-pypi@main
        with:
          version: patch  # or minor, major
          github_token: ${{ secrets.GITHUB_TOKEN }}
```

## Inputs

| Input | Description | Required | Default |
|-------|-------------|----------|---------|
| `version` | Version bump type (patch, minor, major) | Yes | - |
| `github_token` | GitHub token for creating releases | Yes | - |

## Outputs

| Output | Description |
|--------|-------------|
| `new_version` | The new version that was released |
| `commit_hash` | The commit hash for the version bump commit |
| `current_version` | The version before bumping |

## Example: Full Release Workflow

```yaml
name: Release
on:
  workflow_dispatch:
    inputs:
      version:
        type: choice
        required: true
        description: "Version bump type"
        options:
          - patch
          - minor
          - major

permissions:
  id-token: write
  contents: write

jobs:
  # Optional: Run security checks first
  security-checks:
    uses: SolaceDev/solace-public-workflows/.github/workflows/hatch_release_security_checks.yml@main
    with:
      whitesource_project_name: my-project
      whitesource_product_name: my-product
    secrets:
      WHITESOURCE_API_KEY: ${{ secrets.WHITESOURCE_API_KEY }}
      # ... other secrets

  release:
    needs: security-checks
    runs-on: ubuntu-latest
    environment: pypi
    outputs:
      new_version: ${{ steps.release.outputs.new_version }}
      commit_hash: ${{ steps.release.outputs.commit_hash }}
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0
          ssh-key: ${{ secrets.COMMIT_KEY }}

      - name: Release to PyPI
        id: release
        uses: SolaceDev/solace-public-workflows/.github/actions/hatch-release-pypi@main
        with:
          version: ${{ github.event.inputs.version }}
          github_token: ${{ secrets.GITHUB_TOKEN }}

  # Optional: Build Docker image after release
  docker:
    needs: release
    runs-on: ubuntu-latest
    steps:
      - run: echo "Building Docker image for version ${{ needs.release.outputs.new_version }}"
```

## Security Benefits

Using Trusted Publishing instead of API tokens provides:

- **No long-lived secrets**: OIDC tokens are short-lived and scoped to specific workflows
- **Workflow-specific**: Only the exact workflow can publish
- **Environment protection**: Using GitHub environments allows additional protection rules
- **Audit trail**: All publishes are tied to specific GitHub Actions runs

See [PyPI Trusted Publishers Security Model](https://docs.pypi.org/trusted-publishers/security-model/) for more details.
