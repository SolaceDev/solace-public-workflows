# SCA Scan and Guard Workflow

Software Composition Analysis (SCA) scanning for source code dependencies with policy and vulnerability enforcement.

## Overview

The SCA scan and guard workflow provides automated security scanning of source code dependencies using FOSSA. It supports both pull request (diff-based) and release (full) scanning contexts with configurable policy enforcement.

**Workflow Path**: [`../.github/workflows/sca-scan-and-guard.yaml`](../sca-scan-and-guard.yaml)

## Features

- **FOSSA SCA scanning** with licensing and vulnerability checks
- **Context-aware scanning**: PR (diff-based) vs Release (full scan)
- **Config-driven policy enforcement** via workflow-config.json
- **Monorepo support** with path filtering
- **Split emergency gates** for policy and vulnerability concerns
- **Vault integration** for private repositories
- **Privacy mode** auto-enabled for public repositories
- **Dashboard links** with correct Solace organization {org_id}

## Usage

### Basic Usage (Public Repository)

```yaml
name: SCA Scan

on:
  pull_request:
  push:
    branches: [main]

jobs:
  sca-scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/sca-scan-and-guard.yaml@main
    secrets:
      FOSSA_API_KEY: ${{ secrets.FOSSA_API_KEY }}
```

### Config-Driven Usage (Private Repository)

```yaml
name: SCA Scan

on:
  pull_request:
  push:
    tags: ['*']

jobs:
  sca-scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/sca-scan-and-guard.yaml@main
    with:
      use_vault: true
      config_file: '.github/workflow-config.json'
    secrets:
      VAULT_ROLE: ${{ secrets.VAULT_ROLE }}  # Optional
```

### Monorepo Support

```yaml
jobs:
  scan-plugin:
    uses: SolaceDev/solace-public-workflows/.github/workflows/sca-scan-and-guard.yaml@main
    with:
      use_vault: true
      config_file: 'plugins/my-plugin/workflow-config.json'
      additional_scan_params: |
        fossa.only_path=plugins/my-plugin
```

### Monorepo Matrix Scanning

```yaml
jobs:
  scan:
    strategy:
      matrix:
        plugin: [plugin-a, plugin-b, plugin-c]
    uses: SolaceDev/solace-public-workflows/.github/workflows/sca-scan-and-guard.yaml@main
    with:
      use_vault: true
      config_file: 'plugins/${{ matrix.plugin }}/workflow-config.json'
      additional_scan_params: |
        fossa.only_path=plugins/${{ matrix.plugin }}
```

## Inputs

### Core Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `git_ref` | No | (empty) | Git ref to checkout (e.g., `0.0.269` for releases). Leave empty for PR context. |
| `skip_policy_gate` | No | `false` | EMERGENCY: Skip policy/licensing gate (requires admin permission) |
| `skip_vulnerability_gate` | No | `false` | EMERGENCY: Skip vulnerability gate (requires admin permission) |
| `bypass_justification` | No | (empty) | REQUIRED if either bypass gate is used: Justification for emergency bypass |
| `use_vault` | No | `false` | Retrieve FOSSA API key from Vault (true for private repos) |
| `config_file` | No | `.github/workflow-config.json` | Path to workflow configuration file |
| `additional_scan_params` | No | (empty) | Additional scanner-specific parameters (see below) |

### Dependency Setup Inputs

These inputs configure the build environment before FOSSA runs. See [SCA Setup Dependencies](../../../sca-setup-deps/README.md) for full documentation.

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `setup_actions` | No | `'["setup-java", "maven-settings"]'` | JSON array of setup steps to run |
| `vault_secrets` | No | (empty) | Multiline Vault secret mappings (`secret/path KEY \| ENV_VAR`) |
| `custom_setup_script` | No | (empty) | Custom bash script to run before the scan |
| `java_version` | No | `"17"` | Java version |
| `node_version` | No | `"20"` | Node.js version |
| `python_version` | No | `"3.10"` | Python version |
| `dotnet_versions` | No | `"6.0.x"` | .NET SDK versions |
| `maven_build_command` | No | `"mvn clean install -DskipTests"` | Maven build command |
| `maven_settings_repositories` | No | (empty) | Maven repositories configuration (JSON) |
| `maven_settings_servers` | No | (empty) | Maven servers configuration (JSON) |
| `npm_install_command` | No | `"npm install"` | NPM install command |
| `python_install_command` | No | `"pip install -r requirements.txt"` | Python install command |
| `dotnet_restore_command` | No | `"dotnet restore"` | .NET restore command |

## Secrets

| Secret | Required | Description |
|--------|----------|-------------|
| `FOSSA_API_KEY` | Conditional | Required if `use_vault` is `false` |
| `VAULT_ROLE` | No | Vault role for JWT authentication (defaults to `cicd-workflows-secret-read-role`) |

## Configuration File

Create `.github/workflow-config.json`:

```json
{
  "secrets": {
    "vault": {
      "url": "https://vault.example.com:8200",
      "role": "github-actions-role",
      "secret_path": "secret/data/path/to/secrets"
    }
  },
  "sca_scanning": {
    "enabled": true,
    "fossa": {
      "policy": {
        "mode": "BLOCK",
        "block_on": ["policy_conflict"]
      },
      "vulnerability": {
        "mode": "REPORT",
        "block_on": ["critical", "high"]
      },
      "project_id": "SolaceDev_my-project",
      "team": "Platform Team",
      "labels": ["production", "critical"]
    }
  }
}
```

**See**: [Workflow Config Schema Documentation](../../../workflow-config-loader/workflow-config-schema.md)

### Configuration Fields

#### FOSSA Policy

- **`mode`**: `"BLOCK"` (fail on violations) or `"REPORT"` (report only)
- **`block_on`**: Array of issues to block on
  - `"policy_conflict"` - License policy violations
  - `"policy_flag"` - Flagged licenses

#### FOSSA Vulnerability

- **`mode`**: `"BLOCK"` or `"REPORT"`
- **`block_on`**: Array of severities to block on
  - `"critical"`, `"high"`, `"medium"`, `"low"`

## Additional Scan Parameters

Use `additional_scan_params` for FOSSA-specific options:

```yaml
additional_scan_params: |
  fossa.debug=true
  fossa.team=Platform Team
  fossa.only_path=packages/my-package
  fossa.project_label=critical,backend
```

**Common Parameters**:
- `fossa.debug` - Enable debug logging
- `fossa.path` - Base directory to scan
- `fossa.only_path` - Only scan specific paths (monorepo)
- `fossa.config` - Path to `.fossa.yml`
- `fossa.team` - FOSSA team name
- `fossa.project_label` - Comma-separated labels
- `fossa.privacy_mode` - Override privacy mode detection

**See**: [FOSSA Scan Action](../../../.github/actions/sca/fossa-scan/README.md) for full parameter list

## Dependency Setup

Before FOSSA scans your project, the workflow runs the `sca-setup-deps` composite action to prepare the build environment so that all dependencies are resolvable. You control which setup steps run via the `setup_actions` JSON array.

**Full documentation**: [SCA Setup Dependencies](../../../sca-setup-deps/README.md)

### Java / Maven (Default)

Maven setup runs by default with no extra configuration:

```yaml
jobs:
  sca-scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/sca-scan-and-guard.yaml@main
    with:
      use_vault: true
      # setup_actions defaults to '["setup-java", "maven-settings"]'
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
```

### Custom Setup Script

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

### Retrieving Build Credentials from Vault

Use `vault_secrets` to inject credentials needed for private registries or repositories:

```yaml
jobs:
  sca-scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/sca-scan-and-guard.yaml@main
    with:
      use_vault: true
      setup_actions: '["setup-java", "maven-settings", "maven-build"]'
      vault_secrets: |
        secret/data/nexus USERNAME | NEXUS_USERNAME
        secret/data/nexus PASSWORD | NEXUS_PASSWORD
      maven_settings_servers: |
        [{"id": "central", "username": "${env.NEXUS_USERNAME}", "password": "${env.NEXUS_PASSWORD}"}]
```

Alternatively, configure `secret_mappings` in your `workflow-config.json` to avoid passing `vault_secrets` each time. See [SCA Setup Dependencies](../../../sca-setup-deps/README.md#vault-secret-mappings) for details.

## Scan Contexts

The workflow automatically detects the scan context:

### PR Context

Triggered by pull requests:
- Branch: `PR`
- Scans diff against base branch
- Comments results on PR

### Release Context

Triggered when `git_ref` is provided:
- Branch: Derived from git ref (e.g., `main`)
- Full scan of all dependencies
- Posts results to commit status

### Manual Context

Run when a caller workflow is manually triggered via `workflow_dispatch`:
- Branch: Current branch
- Full scan

## Emergency Bypass Gates

The workflow provides split bypass gates for emergencies:

### Skip Policy Gate

```yaml
with:
  skip_policy_gate: true
  bypass_justification: "JIRA-123: Emergency hotfix for production incident"
```

Skips licensing/policy enforcement while still checking vulnerabilities.

### Skip Vulnerability Gate

```yaml
with:
  skip_vulnerability_gate: true
  bypass_justification: "JIRA-456: Known false positive, fix pending"
```

Skips vulnerability enforcement while still checking licensing.

**Requirements**:
- Caller must have **admin** repository permissions
- Must provide `bypass_justification`
- Bypass is logged and visible in workflow output

## Privacy Mode

Privacy mode prevents FOSSA from exposing internal dependency information.

**Automatic Detection**:
- Public repositories: Privacy mode enabled
- Private repositories: Privacy mode disabled

**Manual Override**:

```yaml
additional_scan_params: |
  fossa.privacy_mode=false  # Force disable for public repo
```

## Outputs

The workflow posts results to:

1. **PR Comments** (PR context)
   - Summary of scan results
   - Link to FOSSA dashboard
   - Policy and vulnerability findings

2. **Commit Status** (Release context)
   - Pass/fail status
   - Link to FOSSA dashboard

3. **Job Summary**
   - Detailed scan results
   - Configuration used
   - Links to FOSSA dashboard

## FOSSA Dashboard Links

Dashboard URLs use Solace's organization ID:

```
https://app.fossa.com/projects/custom%2B{org_id}%2F{project_id}
```

**Format**: `custom+{org_id}/SolaceDev_{project_name}`

## Troubleshooting

### Configuration File Not Found

**Error**: `❌ Configuration file not found: .github/workflow-config.json`

**Solution**: Create the config file or specify correct path via `config_file` input

### FOSSA Bypass Denied

**Error**: `❌ FOSSA bypass denied: User X does not have admin permissions`

**Solution**: Only repository admins can use emergency bypass gates

### Vault Authentication Failed

**Error**: `Failed to authenticate to Vault`

**Solution**:
- Verify `VAULT_ROLE` secret is set (or use default role)
- Check Vault URL in config file
- Verify Vault permissions for the role

### Dashboard Link Broken

**Error**: FOSSA dashboard returns 404

**Solution**:
- Verify project ID format: `custom+{org_id}/SolaceDev_{project_name}`
- Check that FOSSA scan completed successfully
- Verify organization ID is {org_id}

### Debug Mode

Enable debug logging:

```yaml
additional_scan_params: |
  fossa.debug=true
```

## Examples

### Basic PR and Main Branch Scanning

```yaml
name: SCA Scan

on:
  pull_request:
  push:
    branches: [main]

jobs:
  sca-scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/sca-scan-and-guard.yaml@main
    secrets:
      FOSSA_API_KEY: ${{ secrets.FOSSA_API_KEY }}
```

### Release Scanning on Tags

```yaml
name: SCA Release Scan

on:
  push:
    tags: ['*']

jobs:
  sca-scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/sca-scan-and-guard.yaml@main
    with:
      git_ref: ${{ github.ref_name }}
      use_vault: true
      config_file: '.github/workflow-config.json'
```

### Custom FOSSA Team and Labels

```yaml
jobs:
  sca-scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/sca-scan-and-guard.yaml@main
    with:
      use_vault: true
      additional_scan_params: |
        fossa.team=Backend Team
        fossa.project_label=critical,production,backend
```

### Monorepo with Per-Package Config

```yaml
jobs:
  scan-packages:
    strategy:
      matrix:
        package:
          - path: packages/core
            project: core
          - path: packages/plugins
            project: plugins
    uses: SolaceDev/solace-public-workflows/.github/workflows/sca-scan-and-guard.yaml@main
    with:
      use_vault: true
      config_file: '${{ matrix.package.path }}/workflow-config.json'
      additional_scan_params: |
        fossa.only_path=${{ matrix.package.path }}
        fossa.project=SolaceDev_my-app-${{ matrix.package.project }}
```

## Related Documentation

- [SCA Setup Dependencies](../../../sca-setup-deps/README.md)
- [Workflow Config Loader](../../../workflow-config-loader/README.md)
- [SCA Scan Action](../../../.github/actions/sca/sca-scan/README.md)
- [FOSSA Scan Action](../../../.github/actions/sca/fossa-scan/README.md)
- [FOSSA Guard Action](../../../.github/actions/fossa-guard/README.md)
- [FOSSA CLI Documentation](https://github.com/fossas/fossa-cli)

## Support

- **Issues**: [GitHub Issues](https://github.com/SolaceDev/solace-public-workflows/issues)
