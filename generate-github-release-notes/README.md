# Generate GitHub Release Notes

A Docker-based GitHub Action that generates formatted release notes using GitHub's API with optional Jira issue tracking integration and conventional commit format support.

## Features

- 🔄 **Conventional Commits**: Supports conventional commit format parsing
- 🎯 **Issue Tracking**: Conditionally extracts and links issue references (only when configured)
- 📝 **Clean Formatting**: Removes issue prefixes from commit messages for clean output
- 🏷️ **Type Categorization**: Groups commits by type (Features, Bug Fixes, etc.)
- 🎨 **UI Changes Detection**: Automatically detects and groups UI-related commits with version ranges
- ⚙️ **Configurable**: Supports custom configuration via `.versionrc.json`
- 🔗 **Repository Agnostic**: Works with any GitHub repository
- 🐳 **Docker-based**: Consistent execution environment across platforms
- 🔒 **Security-First**: No hardcoded issue URLs or prefixes - only uses what you configure
- 🚀 **GitHub API**: Uses GitHub's release notes API instead of git commands for better performance

## Usage

### Basic Usage

```yaml
- name: Generate Release Notes
  uses: SolaceDev/maas-build-actions/generate-github-release-notes@main
  with:
    from-ref: "v1.0.0"
    to-ref: "v1.1.0"
    output-file: "RELEASE_NOTES.md"
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

### Advanced Usage

```yaml
- name: Generate Release Notes
  uses: SolaceDev/maas-build-actions/generate-github-release-notes@main
  with:
    from-ref: "v1.0.0"
    to-ref: "HEAD"
    output-file: "release-notes.md"
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

### Generate Notes for All Commits

```yaml
- name: Generate Complete Release Notes
  uses: SolaceDev/maas-build-actions/generate-github-release-notes@main
  with:
    from-ref: "main" # Will include all commits from main
    to-ref: "HEAD"
    output-file: "CHANGELOG.md"
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

### Using Custom Configuration File

```yaml
- name: Generate Release Notes with Custom Config
  uses: SolaceDev/maas-build-actions/generate-github-release-notes@main
  with:
    from-ref: "v1.0.0"
    to-ref: "v1.1.0"
    output-file: "RELEASE_NOTES.md"
    config-file: ".github/release-config.json"
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

## Required Permissions

This action requires specific GitHub token permissions to function properly. The token must have access to:

### Minimum Required Permissions

For the action to work, your GitHub token needs:

- **Contents**: `read` - To access repository content and commits
- **Metadata**: `read` - To access basic repository information
- **Pull requests**: `read` - To access pull request information linked to commits

### Setting Up Permissions

#### Option 1: Using Default GITHUB_TOKEN (Recommended)

For most use cases, you can use the default `GITHUB_TOKEN` with enhanced permissions:

```yaml
jobs:
  generate-release-notes:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: read
      metadata: read
    steps:
      - name: Generate Release Notes
        uses: SolaceDev/solace-public-workflows/generate-github-release-notes@main
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          # ... other inputs
```

#### Option 2: Using Personal Access Token (PAT)

If you need additional permissions or are using this across repositories:

1. Create a Personal Access Token with these scopes:

   - `repo` (Full control of private repositories) OR
   - `public_repo` (Access public repositories) + `read:org` (if needed)

2. Add the token as a repository secret (e.g., `RELEASE_NOTES_TOKEN`)

3. Use it in your workflow:

```yaml
- name: Generate Release Notes
  uses: SolaceDev/solace-public-workflows/generate-github-release-notes@main
  with:
    github-token: ${{ secrets.RELEASE_NOTES_TOKEN }}
    # ... other inputs
```

#### Option 3: Using GitHub App Token

For organization-wide usage, consider using a GitHub App:

```yaml
- name: Generate App Token
  id: app-token
  uses: actions/create-github-app-token@v1
  with:
    app-id: ${{ vars.APP_ID }}
    private-key: ${{ secrets.APP_PRIVATE_KEY }}
    repositories: ${{ github.repository }}

- name: Generate Release Notes
  uses: SolaceDev/solace-public-workflows/generate-github-release-notes@main
  with:
    github-token: ${{ steps.app-token.outputs.token }}
    # ... other inputs
```

### Troubleshooting Permission Issues

If you encounter errors like:

```
Resource not accessible by integration
```

This typically means:

1. **Missing pull-requests permission**: The token cannot access PR information
2. **Insufficient repository access**: The token doesn't have read access to the repository
3. **Organization restrictions**: Your organization may have restrictions on token permissions

**Solutions:**

- Ensure your workflow has the `pull-requests: read` permission
- Verify the token has access to the target repository
- Check organization security settings for token restrictions
- Consider using a PAT or GitHub App token with broader permissions

## Inputs

| Input          | Description                                                                       | Required | Default            |
| -------------- | --------------------------------------------------------------------------------- | -------- | ------------------ |
| `from-ref`     | Starting git reference (tag, commit, branch). If empty, generates for all commits | No       | `main`             |
| `to-ref`       | Ending git reference (tag, commit, branch)                                        | No       | `HEAD`             |
| `output-file`  | Output file path for release notes                                                | No       | `RELEASE_NOTES.md` |
| `config-file`  | Path to configuration file                                                        | No       | `.versionrc.json`  |
| `github-token` | GitHub token for API access (see Required Permissions above)                      | Yes      | -                  |

## Outputs

| Output               | Description                              |
| -------------------- | ---------------------------------------- |
| `release-notes-path` | Path to the generated release notes file |
| `total-commits`      | Total number of commits processed        |

## Configuration

The action supports configuration via a `.versionrc.json` file in your repository root, or you can specify a custom configuration file path using the `config-file` input parameter.

### Security Note

**Issue tracking is completely optional and secure by default.** The action will only:

- Extract issue references if `issuePrefixes` is configured
- Generate issue URLs if both `issuePrefixes` and `issueUrlFormat` are configured
- No hardcoded issue prefixes or URLs are included for security

### Example Configuration

```json
{
  "types": [
    { "type": "feat", "section": "Features" },
    { "type": "fix", "section": "Bug Fixes" },
    { "type": "ci", "section": "Continuous Integration" },
    { "type": "deps", "section": "Dependencies" },
    { "type": "chore", "section": "Chores" },
    { "type": "build", "section": "Build" },
    { "type": "docs", "section": "Documentation" },
    { "type": "style", "section": "Style" },
    { "type": "refactor", "section": "Refactoring" },
    { "type": "perf", "section": "Performance" },
    { "type": "test", "section": "Tests" }
  ],
  "issuePrefixes": [
    "DATAGO-",
    "MRE-",
    "DATAGOOPS-",
    "EBP-",
    "COE-",
    "SOL-",
    "AI-",
    "DOC-",
    "CICDSOL-"
  ],
  "issueUrlFormat": "https://sol-jira.atlassian.net/browse/{{prefix}}{{id}}",
  "uiChanges": {
    "enabled": true,
    "tagPrefix": "ui-v",
    "pathPatterns": ["client/webui/frontend/**"],
    "bumpCommitPattern": "bump version to ui-v.*\\[skip ci\\]"
  }
}
```

### UI Changes Detection

The action can automatically detect and group UI-related commits separately from main repository changes. This is useful for repositories that have separate UI versioning (e.g., `ui-v1.0.0` tags).

#### Configuration Options

| Option              | Description                                     | Default                                 | Required |
| ------------------- | ----------------------------------------------- | --------------------------------------- | -------- |
| `enabled`           | Enable UI changes detection                     | `false`                                 | No       |
| `tagPrefix`         | Prefix for UI version tags                      | `"ui-v"`                                | No       |
| `pathPatterns`      | Array of path patterns that indicate UI changes | `["client/webui/frontend/**"]`          | No       |
| `bumpCommitPattern` | Regex pattern to match UI version bump commits  | `"bump version to ui-v.*\\[skip ci\\]"` | No       |

#### How It Works

1. **Detects UI bump commits**: Finds commits that match the `bumpCommitPattern`
2. **Extracts version ranges**: Parses version changes from bump commits (e.g., `ui-v0.9.0` → `ui-v0.9.1`)
3. **Groups preceding commits**: Identifies commits that modified `pathPatterns` before each bump
4. **Categorizes by type**: Groups UI commits by their conventional commit type
5. **Excludes bump commits**: Removes the actual bump commits from the output

#### Example Workflow

Given these commits in chronological order:

1. `fix: auto add files after precommit hook run (#352)` (modifies `client/webui/frontend/`)
2. `ci: bump version to ui-v0.9.1 [skip ci]` (UI bump commit)
3. `feat: add new backend feature` (main repo change)

The output will be:

- **Main sections**: Contains the backend feature
- **UI Changes ui-v0.9.0 → ui-v0.9.1**: Contains the UI fix, categorized under "Bug Fixes"
- **Excluded**: The bump commit itself is not shown

## Supported Commit Formats

The action supports conventional commit format:

- `type: subject (#PR)`
- `type(scope): subject (#PR)`
- `type(ISSUE-123): subject (#PR)`

## Issue Reference Handling

The action intelligently extracts and cleans issue references:

**Input:**

```
feat(DATAGO-123): DATAGO-456: add new feature
```

**Output:**

```
* [`abc1234`](commit-url) add new feature ([DATAGO-123](jira-url), [DATAGO-456](jira-url))
```

## Example Output

### Standard Output

```markdown
## Features

- [`abc1234`](https://github.com/org/repo/commit/abc1234) Add user authentication ([#45](https://github.com/org/repo/pull/45)) ([DATAGO-123](https://jira.com/browse/DATAGO-123))

## Bug Fixes

- [`def5678`](https://github.com/org/repo/commit/def5678) Fix login issue ([MRE-456](https://jira.com/browse/MRE-456))

## Chores

- [`ghi9012`](https://github.com/org/repo/commit/ghi9012) Update dependencies ([#67](https://github.com/org/repo/pull/67))
```

### With UI Changes Detection

When `uiChanges` is enabled, UI-related commits are grouped separately:

```markdown
## Features

- [`abc1234`](https://github.com/org/repo/commit/abc1234) Add user authentication ([#45](https://github.com/org/repo/pull/45))

## Bug Fixes

- [`def5678`](https://github.com/org/repo/commit/def5678) Fix login issue ([MRE-456](https://jira.com/browse/MRE-456))

## UI Changes ui-v0.9.0 → ui-v0.9.1

### Bug Fixes

- [`be94294`](https://github.com/org/repo/commit/be94294) auto add files after precommit hook run ([#352](https://github.com/org/repo/pull/352)) (Raman Gupta)

### Features

- [`xyz9876`](https://github.com/org/repo/commit/xyz9876) add new UI component ([#353](https://github.com/org/repo/pull/353)) (Jane Doe)
```

## Workflow Examples

### Release Workflow

```yaml
name: Create Release

on:
  push:
    tags:
      - "v*"

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Get Previous Tag
        id: prev-tag
        run: |
          PREV_TAG=$(git describe --tags --abbrev=0 HEAD~1 2>/dev/null || echo "")
          echo "prev-tag=$PREV_TAG" >> $GITHUB_OUTPUT

      - name: Generate Release Notes
        uses: SolaceDev/maas-build-actions/generate-github-release-notes@main
        with:
          from-ref: ${{ steps.prev-tag.outputs.prev-tag }}
          to-ref: ${{ github.ref_name }}
          output-file: "RELEASE_NOTES.md"
          github-token: ${{ secrets.GITHUB_TOKEN }}

      - name: Create GitHub Release
        uses: actions/create-release@v1
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          tag_name: ${{ github.ref_name }}
          release_name: Release ${{ github.ref_name }}
          body_path: RELEASE_NOTES.md
```

### Manual Release Notes Generation

```yaml
name: Generate Release Notes

on:
  workflow_dispatch:
    inputs:
      from_tag:
        description: "From tag (e.g., v1.0.0)"
        required: true
      to_tag:
        description: "To tag (e.g., v1.1.0)"
        required: true
        default: "HEAD"

jobs:
  generate-notes:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Generate Release Notes
        uses: SolaceDev/maas-build-actions/generate-github-release-notes@main
        with:
          from-ref: ${{ github.event.inputs.from_tag }}
          to-ref: ${{ github.event.inputs.to_tag }}
          output-file: "release-notes-${{ github.event.inputs.to_tag }}.md"
          github-token: ${{ secrets.GITHUB_TOKEN }}

      - name: Upload Release Notes
        uses: actions/upload-artifact@v4
        with:
          name: release-notes
          path: "release-notes-*.md"
```

## Development

### Local Testing

You can test the action locally using Docker:

```bash
# Build the Docker image
docker build -t generate-release-notes .

# Run with test parameters
docker run --rm -v $(pwd):/github/workspace \
  generate-release-notes main HEAD test-output.md
```

### Requirements

- Git repository with conventional commits
- Docker runtime
- Optional: `.versionrc.json` configuration file

## License

This action is part of the Solace MaaS Build Actions and follows the same licensing terms.
