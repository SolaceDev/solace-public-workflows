# Generate GitHub Release Notes

A Docker-based GitHub Action that generates formatted release notes using GitHub's API with optional Jira issue tracking integration and conventional commit format support.

## Features

- 🔄 **Conventional Commits**: Supports conventional commit format parsing
- 🎯 **Issue Tracking**: Conditionally extracts and links issue references (only when configured)
- 📝 **Clean Formatting**: Removes issue prefixes from commit messages for clean output
- 🏷️ **Type Categorization**: Groups commits by type (Features, Bug Fixes, etc.)
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

## Inputs

| Input          | Description                                                                       | Required | Default            |
| -------------- | --------------------------------------------------------------------------------- | -------- | ------------------ |
| `from-ref`     | Starting git reference (tag, commit, branch). If empty, generates for all commits | No       | `main`             |
| `to-ref`       | Ending git reference (tag, commit, branch)                                        | No       | `HEAD`             |
| `output-file`  | Output file path for release notes                                                | No       | `RELEASE_NOTES.md` |
| `github-token` | GitHub token for API access                                                       | Yes      | -                  |

## Outputs

| Output               | Description                              |
| -------------------- | ---------------------------------------- |
| `release-notes-path` | Path to the generated release notes file |
| `total-commits`      | Total number of commits processed        |

## Configuration

The action supports configuration via a `.versionrc.json` file in your repository root.

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
  "issueUrlFormat": "https://sol-jira.atlassian.net/browse/{{prefix}}{{id}}"
}
```

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

```markdown
## Features

- [`abc1234`](https://github.com/org/repo/commit/abc1234) Add user authentication ([#45](https://github.com/org/repo/pull/45)) ([DATAGO-123](https://jira.com/browse/DATAGO-123))

## Bug Fixes

- [`def5678`](https://github.com/org/repo/commit/def5678) Fix login issue ([MRE-456](https://jira.com/browse/MRE-456))

## Chores

- [`ghi9012`](https://github.com/org/repo/commit/ghi9012) Update dependencies ([#67](https://github.com/org/repo/pull/67))
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
