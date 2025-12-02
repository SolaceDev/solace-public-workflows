# Hatch Release to PyPI Actions

Composite actions for releasing Python packages to PyPI using [Trusted Publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/).

## Why Two Actions?

According to the [PyPI publish action documentation](https://github.com/marketplace/actions/pypi-publish):

> Invoking `pypi-publish` from composite actions is unsupported.

Therefore, the release process is split into two composite actions with the PyPI publish step directly in the caller workflow:

1. **`hatch-release-prep`** - Prepares the release (setup, version bump, commit, build)
2. **PyPI publish step** - Must be directly in the workflow (not in a composite action)
3. **`hatch-release-post`** - Finalizes the release (push commit, create GitHub release, release notes)

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
    outputs:
      new_version: ${{ steps.prep.outputs.new_version }}
      commit_hash: ${{ steps.prep.outputs.commit_hash }}
    steps:
      - name: Checkout
        uses: actions/checkout@v5
        with:
          fetch-depth: 0
          ssh-key: ${{ secrets.COMMIT_KEY }}

      # Add any project-specific build steps here (e.g., npm build for frontend)

      - name: Prepare Release
        id: prep
        uses: SolaceDev/solace-public-workflows/.github/actions/hatch-release-prep@main
        with:
          version: patch  # or minor, major

      # PyPI publish MUST be directly in the workflow, not in a composite action
      - name: Publish package distributions to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          verbose: true

      - name: Finalize Release
        uses: SolaceDev/solace-public-workflows/.github/actions/hatch-release-post@main
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          new_version: ${{ steps.prep.outputs.new_version }}
          current_version: ${{ steps.prep.outputs.current_version }}
          skip_bump: ${{ steps.prep.outputs.skip_bump }}
```

## Action Inputs/Outputs

### hatch-release-prep

**Inputs:**
| Input | Description | Required |
|-------|-------------|----------|
| `version` | Version bump type (patch, minor, major) | Yes |

**Outputs:**
| Output | Description |
|--------|-------------|
| `new_version` | The new version that was released |
| `commit_hash` | The commit hash for the version bump commit |
| `current_version` | The version before bumping |
| `skip_bump` | Whether version bump was skipped (1 if skipped, 0 if not) |

### hatch-release-post

**Inputs:**
| Input | Description | Required |
|-------|-------------|----------|
| `github_token` | GitHub token for creating releases | Yes |
| `new_version` | The new version that was released | Yes |
| `current_version` | The version before bumping (for release notes) | Yes |
| `skip_bump` | Whether version bump was skipped | No (default: "0") |

## Full Example with Security Checks

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
  checks: write
  pull-requests: read

jobs:
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
      new_version: ${{ steps.prep.outputs.new_version }}
      commit_hash: ${{ steps.prep.outputs.commit_hash }}
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0
          ssh-key: ${{ secrets.COMMIT_KEY }}

      - name: Prepare Release
        id: prep
        uses: SolaceDev/solace-public-workflows/.github/actions/hatch-release-prep@main
        with:
          version: ${{ github.event.inputs.version }}

      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          verbose: true

      - name: Finalize Release
        uses: SolaceDev/solace-public-workflows/.github/actions/hatch-release-post@main
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          new_version: ${{ steps.prep.outputs.new_version }}
          current_version: ${{ steps.prep.outputs.current_version }}
          skip_bump: ${{ steps.prep.outputs.skip_bump }}
```

## Security Benefits

Using Trusted Publishing instead of API tokens provides:

- **No long-lived secrets**: OIDC tokens are short-lived and scoped to specific workflows
- **Workflow-specific**: Only the exact workflow can publish
- **Environment protection**: Using GitHub environments allows additional protection rules
- **Audit trail**: All publishes are tied to specific GitHub Actions runs

See [PyPI Trusted Publishers Security Model](https://docs.pypi.org/trusted-publishers/security-model/) for more details.
