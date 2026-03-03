# SCA Setup Dependencies

Composite action for setting up build environments before SCA scanning. Supports Java/Maven, Node/NPM, Python, .NET, and custom scripts via a JSON-driven configuration.

**Action Path**: [`action.yml`](action.yml)

## Overview

The `sca-setup-deps` action prepares the build environment so that FOSSA can accurately resolve all project dependencies during a scan. It uses a `setup_actions` JSON array to selectively run only the setup steps your project needs.

Build and install commands are intentionally not built-in — use `custom_setup_script` to run them. This keeps the action focused on environment setup while giving you full control over build steps.

`custom_setup_script` runs automatically whenever it is non-empty; you do not need to add anything to `setup_actions` for it to execute.

## Usage

Pass `setup_actions` as a JSON array of environment setup steps, and optionally provide `custom_setup_script` for build or install commands:

```yaml
jobs:
  sca-scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/sca-scan-and-guard.yaml@main
    with:
      use_vault: true
      setup_actions: '["setup-java", "maven-settings"]'
      custom_setup_script: |
        mvn clean install -DskipTests
```

## Supported Actions

| Action | Description |
|--------|-------------|
| `setup-java` | Install Java (Temurin distribution) |
| `maven-settings` | Generate `~/.m2/settings.xml` with repositories and servers |
| `setup-node` | Install Node.js |
| `npm-config` | Configure `.npmrc` auth token |
| `setup-python` | Install Python |
| `setup-uv` | Install uv (Astral's fast Python package manager) |
| `setup-dotnet` | Install .NET SDK |
| `dotnet-nuget-config` | Add NuGet source with optional auth |

## Inputs

### Core

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `setup_actions` | No | `'["setup-java", "maven-settings"]'` | JSON array of setup steps to run |
| `custom_setup_script` | No | (empty) | Bash script for build/install commands. Runs automatically when non-empty. |

### Java / Maven

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `java_version` | No | `"17"` | Java version to install |
| `java_distribution` | No | `"temurin"` | Java distribution |
| `maven_settings_repositories` | No | (empty) | Maven repositories JSON configuration |
| `maven_settings_servers` | No | (empty) | Maven servers JSON configuration |

### Node / NPM

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `node_version` | No | `"20"` | Node.js version to install |
| `npm_registry_url` | No | `"https://npm.pkg.github.com"` | NPM registry URL |
| `npm_auth_token` | No | (empty) | Auth token for the NPM registry |

### Python

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `python_version` | No | `"3.10"` | Python version to install |

### uv

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `uv_version` | No | `""` (latest) | uv version to install (e.g. `"0.6.0"`). Leave empty for latest. |

### .NET

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `dotnet_versions` | No | `"6.0.x"` | .NET SDK versions to install |
| `nuget_source_url` | No | (empty) | NuGet source URL to add |
| `nuget_auth_token` | No | (empty) | Auth token for NuGet source |

## Examples

### Java / Maven (Default)

Maven setup is the default. Provide `custom_setup_script` if FOSSA needs the project built to resolve dependencies:

```yaml
jobs:
  sca-scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/sca-scan-and-guard.yaml@main
    with:
      use_vault: true
      setup_actions: '["setup-java", "maven-settings"]'
      custom_setup_script: |
        mvn clean install -DskipTests
```

If FOSSA can resolve dependencies from `pom.xml` alone, omit `custom_setup_script`:

```yaml
    with:
      use_vault: true
      # setup_actions defaults to '["setup-java", "maven-settings"]'
```

### Java with Private Repository

```yaml
jobs:
  sca-scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/sca-scan-and-guard.yaml@main
    with:
      use_vault: true
      setup_actions: '["setup-java", "maven-settings"]'
      maven_settings_repositories: |
        [{"id": "central", "url": "https://nexus.example.com/repository/maven-central"}]
      maven_settings_servers: |
        [{"id": "central", "username": "${env.NEXUS_USERNAME}", "password": "${env.NEXUS_PASSWORD}"}]
      vault_secrets: |
        secret/data/nexus NEXUS_USER | NEXUS_USERNAME
        secret/data/nexus NEXUS_PASS | NEXUS_PASSWORD
      custom_setup_script: |
        mvn clean install -DskipTests
```

### Node / NPM

```yaml
jobs:
  sca-scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/sca-scan-and-guard.yaml@main
    with:
      use_vault: true
      setup_actions: '["setup-node", "npm-config"]'
      node_version: "18"
      custom_setup_script: |
        npm ci
```

### Node with Private GitHub Packages Registry

`npm_auth_token` defaults to `GITHUB_TOKEN` automatically. The `npm-config` action writes it to `.npmrc`:

```yaml
jobs:
  sca-scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/sca-scan-and-guard.yaml@main
    with:
      use_vault: true
      setup_actions: '["setup-node", "npm-config"]'
      npm_registry_url: "https://npm.pkg.github.com"
      custom_setup_script: |
        npm ci
```

### Python

```yaml
jobs:
  sca-scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/sca-scan-and-guard.yaml@main
    with:
      use_vault: true
      setup_actions: '["setup-python"]'
      python_version: "3.11"
      custom_setup_script: |
        pip install -r requirements.txt
```

### Python with uv

Install uv and use `custom_setup_script` to export a `requirements.txt` before FOSSA scans. FOSSA requires a `requirements.txt` to resolve Python dependencies; `uv export` generates one from your `uv.lock` without installing packages:

```yaml
jobs:
  sca-scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/sca-scan-and-guard.yaml@main
    with:
      use_vault: true
      setup_actions: '["setup-uv"]'
      custom_setup_script: |
        uv export --format requirements-txt --no-dev --output-file requirements.txt
```

Pin a specific uv version if needed:

```yaml
    with:
      setup_actions: '["setup-uv"]'
      uv_version: "0.6.0"
      custom_setup_script: |
        uv export --format requirements-txt --no-dev --output-file requirements.txt
```

### .NET

```yaml
jobs:
  sca-scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/sca-scan-and-guard.yaml@main
    with:
      use_vault: true
      setup_actions: '["setup-dotnet", "dotnet-nuget-config"]'
      dotnet_versions: "8.0.x"
      nuget_source_url: "https://nuget.pkg.github.com/SolaceDev/index.json"
      custom_setup_script: |
        dotnet restore
```

### Mixed Language (Java + Node)

```yaml
jobs:
  sca-scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/sca-scan-and-guard.yaml@main
    with:
      use_vault: true
      setup_actions: '["setup-java", "maven-settings", "setup-node", "npm-config"]'
      java_version: "21"
      node_version: "20"
      custom_setup_script: |
        mvn clean install -DskipTests
        npm ci
```

## Vault Secret Mappings

For build tools that need credentials retrieved from Vault, use the `vault_secrets` input or configure `secret_mappings` in your `workflow-config.json`.

### Via Workflow Input

```yaml
with:
  vault_secrets: |
    secret/data/nexus USERNAME | NEXUS_USERNAME
    secret/data/nexus PASSWORD | NEXUS_PASSWORD
```

### Via Config File

```json
{
  "secrets": {
    "vault": {
      "url": "https://vault.example.com:8200",
      "role": "github-actions-role",
      "secret_path": "secret/data/fossa",
      "secret_mappings": [
        "secret/data/nexus USERNAME | NEXUS_USERNAME",
        "secret/data/nexus PASSWORD | NEXUS_PASSWORD"
      ]
    }
  }
}
```

Secrets retrieved via `secret_mappings` are injected as environment variables before `custom_setup_script` runs, making them available to Maven settings, `.npmrc`, and other configuration files.

## Step Execution Order

Steps always execute in this fixed order regardless of the order specified in `setup_actions`. `custom_setup_script` always runs last when non-empty:

1. `setup-java`
2. `maven-settings`
3. `setup-node`
4. `npm-config` (writes `.npmrc` auth token)
5. `setup-python`
6. `setup-uv`
7. `setup-dotnet`
8. `dotnet-nuget-config`
9. `custom_setup_script` (runs when non-empty)

## Related Documentation

- [SCA Scan and Guard Workflow](../.github/workflows/docs/sca-scan-and-guard.md)
- [Workflow Config Schema](../workflow-config-loader/workflow-config-schema.md)
- [Workflow Config Loader](../workflow-config-loader/README.md)
