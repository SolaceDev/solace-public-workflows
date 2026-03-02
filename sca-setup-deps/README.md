# SCA Setup Dependencies

Composite action for setting up build environments before SCA scanning. Supports Java/Maven, Node/NPM, Python, .NET, and custom scripts via a JSON-driven configuration.

**Action Path**: [`action.yml`](action.yml)

## Overview

The `sca-setup-deps` action prepares the build environment so that FOSSA can accurately resolve all project dependencies during a scan. It uses a `setup_actions` JSON array to selectively run only the steps your project needs.

## Usage

Pass `setup_actions` as a JSON array of steps to execute. Steps run in the order they are listed.

```yaml
jobs:
  sca-scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/sca-scan-and-guard.yaml@main
    with:
      setup_actions: '["setup-java", "maven-settings", "maven-build"]'
      use_vault: true
```

## Supported Actions

| Action | Description |
|--------|-------------|
| `setup-java` | Install Java (Temurin distribution) |
| `maven-settings` | Generate `~/.m2/settings.xml` with repositories and servers |
| `maven-build` | Run Maven build command |
| `setup-node` | Install Node.js |
| `npm-config` | Configure `.npmrc` auth and run NPM install |
| `setup-python` | Install Python |
| `python-install` | Run pip install command |
| `setup-uv` | Install uv (Astral's fast Python package manager) |
| `setup-dotnet` | Install .NET SDK |
| `dotnet-nuget-config` | Add NuGet source with optional auth |
| `dotnet-restore` | Run dotnet restore |
| `custom-script` | Run arbitrary bash commands |

## Inputs

### Core

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `setup_actions` | No | `'["setup-java", "maven-settings"]'` | JSON array of setup steps to run |
| `custom_setup_script` | No | (empty) | Bash script content to run when `custom-script` is in `setup_actions` |

### Java / Maven

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `java_version` | No | `"17"` | Java version to install |
| `java_distribution` | No | `"temurin"` | Java distribution |
| `maven_settings_repositories` | No | (empty) | Maven repositories JSON configuration |
| `maven_settings_servers` | No | (empty) | Maven servers JSON configuration |
| `maven_build_command` | No | `"mvn clean install -DskipTests"` | Maven command to run |

### Node / NPM

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `node_version` | No | `"20"` | Node.js version to install |
| `npm_registry_url` | No | `"https://npm.pkg.github.com"` | NPM registry URL |
| `npm_auth_token` | No | (empty) | Auth token for the NPM registry |
| `npm_install_command` | No | `"npm install"` | NPM install command to run |

### Python

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `python_version` | No | `"3.10"` | Python version to install |
| `python_install_command` | No | `"pip install -r requirements.txt"` | Install command to run |

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
| `dotnet_restore_command` | No | `"dotnet restore"` | Restore command to run |

## Examples

### Java / Maven (Default)

No extra configuration needed — Maven is the default:

```yaml
jobs:
  sca-scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/sca-scan-and-guard.yaml@main
    with:
      use_vault: true
      # setup_actions defaults to '["setup-java", "maven-settings"]'
```

### Java with Private Repository

Use `maven_settings_repositories` and `maven_settings_servers` to configure access to a private Nexus/Artifactory:

```yaml
jobs:
  sca-scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/sca-scan-and-guard.yaml@main
    with:
      use_vault: true
      setup_actions: '["setup-java", "maven-settings", "maven-build"]'
      maven_settings_repositories: |
        [{"id": "central", "url": "https://nexus.example.com/repository/maven-central"}]
      maven_settings_servers: |
        [{"id": "central", "username": "${env.NEXUS_USERNAME}", "password": "${env.NEXUS_PASSWORD}"}]
      vault_secrets: |
        secret/data/nexus NEXUS_USER | NEXUS_USERNAME
        secret/data/nexus NEXUS_PASS | NEXUS_PASSWORD
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
      npm_install_command: "npm ci"
```

### Node with Private GitHub Packages Registry

The `npm_auth_token` is automatically set to `GITHUB_TOKEN` by the workflow:

```yaml
jobs:
  sca-scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/sca-scan-and-guard.yaml@main
    with:
      use_vault: true
      setup_actions: '["setup-node", "npm-config"]'
      npm_registry_url: "https://npm.pkg.github.com"
```

### Python

```yaml
jobs:
  sca-scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/sca-scan-and-guard.yaml@main
    with:
      use_vault: true
      setup_actions: '["setup-python", "python-install"]'
      python_version: "3.11"
      python_install_command: "pip install -r requirements.txt"
```

### .NET

```yaml
jobs:
  sca-scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/sca-scan-and-guard.yaml@main
    with:
      use_vault: true
      setup_actions: '["setup-dotnet", "dotnet-nuget-config", "dotnet-restore"]'
      dotnet_versions: "8.0.x"
      nuget_source_url: "https://nuget.pkg.github.com/SolaceDev/index.json"
```

### Python with uv

Install uv and use `custom-script` to export a `requirements.txt` before FOSSA scans. FOSSA requires a `requirements.txt` to resolve Python dependencies; `uv export` generates one from your `uv.lock` without installing packages:

```yaml
jobs:
  sca-scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/sca-scan-and-guard.yaml@main
    with:
      use_vault: true
      setup_actions: '["setup-uv", "custom-script"]'
      custom_setup_script: |
        uv export --format requirements-txt --no-dev --output-file requirements.txt
```

Pin a specific uv version if needed:

```yaml
    with:
      setup_actions: '["setup-uv", "custom-script"]'
      uv_version: "0.6.0"
      custom_setup_script: |
        uv export --format requirements-txt --no-dev --output-file requirements.txt
```

### Custom Setup Script

For edge cases not covered by the built-in actions:

```yaml
jobs:
  sca-scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/sca-scan-and-guard.yaml@main
    with:
      use_vault: true
      setup_actions: '["setup-java", "maven-settings", "custom-script"]'
      custom_setup_script: |
        echo "Generating protobuf sources..."
        mvn generate-sources -pl proto-module
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

Secrets retrieved via `secret_mappings` are injected as environment variables before build steps run, making them available to Maven settings, `.npmrc`, and other configuration files.

## Step Execution Order

Steps always execute in this fixed order regardless of the order specified in `setup_actions`:

1. `setup-java`
2. `maven-settings`
3. `maven-build`
4. `setup-node`
5. `npm-config` (runs NPM install)
6. `setup-python`
7. `python-install`
8. `setup-uv`
9. `setup-dotnet`
10. `dotnet-nuget-config`
11. `dotnet-restore`
12. `custom-script`

## Related Documentation

- [SCA Scan and Guard Workflow](../.github/workflows/docs/sca-scan-and-guard.md)
- [Workflow Config Schema](../workflow-config-loader/workflow-config-schema.md)
- [Workflow Config Loader](../workflow-config-loader/README.md)
