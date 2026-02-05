# Workflow Config Loader Action

A reusable GitHub Action that loads and parses JSON workflow configuration files from `.github/workflow-config.json`. This action centralizes configuration management for container scanning and other workflows, reducing workflow complexity and improving maintainability.

## Key Benefits

- **Reduced Workflow Complexity**: 6 runtime inputs instead of 15+ (60% reduction)
- **Configuration Reusability**: One config file shared across multiple workflows
- **Version Control**: Config files are versioned and discoverable in repositories
- **Team Flexibility**: Customize scanning policies without modifying workflows
- **Vault Integration**: Automatic secret management for private repositories
- **Backward Compatible**: Works alongside existing workflow inputs

## Quick Start

### For Private Repositories (with Vault)

Create `.github/workflow-config.json`:

```json
{
  "container_scanning": {
    "secrets": {
      "vault": {
        "secret_path": "/path/to/secret",
        "aws_role": "/path/to/aws/role"
      }
    },
    "fossa": {
      "policy": {
        "mode": "REPORT",
        "block_on": ["policy_conflict"]
      },
      "vulnerability": {
        "mode": "BLOCK",
        "block_on": ["critical", "high"]
      },
      "team": "Platform Team",
      "labels": ["production", "container"]
    }
  },
  "slack_channel": "#team-notifications"
}
```

Use in workflow:

```yaml
- name: Load Workflow Configuration
  id: config
  uses: SolaceDev/solace-public-workflows/workflow-config-loader@main
  with:
    config_file: .github/workflow-config.json
    config_type: container_scanning

- name: Use Configuration Values
  run: |
    echo "Vault Path: ${{ steps.config.outputs.vault_secret_path }}"
    echo "FOSSA Team: ${{ steps.config.outputs.fossa_team }}"
    echo "Licensing Mode: ${{ steps.config.outputs.fossa_licensing_mode }}"
```

### For Public Repositories (with GitHub Secrets)

No config file needed - pass secrets directly to workflows.

## Inputs

| Input | Required | Description |
|-------|----------|-------------|
| `config_file` | Yes | Path to JSON configuration file (e.g., `.github/workflow-config.json`) |
| `config_type` | Yes | Type of configuration to parse: `container_scanning`, `sca_scanning`, etc. |

## Outputs

### Vault Configuration
| Output | Description |
|--------|-------------|
| `vault_url` | Vault URL (typically from `vars.GCP_VAULT_ADDR`) |
| `vault_secret_path` | Vault secret path for API keys |
| `vault_aws_role` | Vault AWS STS role path for ECR authentication |

### FOSSA Configuration
| Output | Description |
|--------|-------------|
| `fossa_licensing_mode` | Licensing check mode: `BLOCK` or `REPORT` |
| `fossa_licensing_block_on` | Comma-separated licensing issues to block on |
| `fossa_vulnerability_mode` | Vulnerability check mode: `BLOCK` or `REPORT` |
| `fossa_vulnerability_block_on` | Comma-separated vulnerability severities to block on |
| `fossa_project_id` | FOSSA project ID override |
| `fossa_team` | FOSSA team name for project assignment |
| `fossa_labels` | Comma-separated FOSSA project labels |

### General Configuration
| Output | Description |
|--------|-------------|
| `config_json` | Raw configuration JSON (for advanced use cases) |
| `slack_channel` | Slack notification channel |

## Configuration Schema

The action parses JSON configuration with the following structure:

```json
{
  "container_scanning": {
    "secrets": {
      "vault": {
        "secret_path": "string",
        "aws_role": "string"
      }
    },
    "fossa": {
      "policy": {
        "mode": "BLOCK | REPORT",
        "block_on": ["policy_conflict", "policy_flag"]
      },
      "vulnerability": {
        "mode": "BLOCK | REPORT",
        "block_on": ["critical", "high", "medium", "low"]
      },
      "project_id": "string or null",
      "team": "string",
      "labels": ["string"]
    }
  },
  "slack_channel": "string"
}
```

### Configuration Defaults

When fields are not specified, the action uses these defaults:

| Field | Default Value |
|-------|---------------|
| `vault_secret_path` | `/path/to/secret` |
| `slack_channel` | `#your-slack-channel` |
| `fossa.policy.mode` | `REPORT` |
| `fossa.policy.block_on` | `["policy_conflict"]` |
| `fossa.vulnerability.mode` | `REPORT` |
| `fossa.vulnerability.block_on` | `["critical", "high"]` |

## Examples

### Basic Container Scanning Configuration

```json
{
  "container_scanning": {
    "fossa": {
      "policy": {
        "mode": "REPORT"
      },
      "vulnerability": {
        "mode": "BLOCK",
        "block_on": ["critical", "high"]
      }
    }
  }
}
```

### Advanced Configuration with Teams and Labels

```json
{
  "container_scanning": {
    "secrets": {
      "vault": {
        "secret_path": "/path/to/secret",
        "aws_role": "/path/to/aws/role"
      }
    },
    "fossa": {
      "policy": {
        "mode": "BLOCK",
        "block_on": ["policy_conflict", "policy_flag"]
      },
      "vulnerability": {
        "mode": "BLOCK",
        "block_on": ["critical", "high"]
      },
      "team": "Platform Engineering",
      "labels": ["production", "container", "critical-path"],
      "project_id": "custom_SolaceDev_my-project"
    }
  },
  "slack_channel": "#platform-alerts"
}
```

### Multi-Workflow Configuration

```json
{
  "squad": "Platform Team",
  "service_name": "my-service",
  "slack_channel": "#team-notifications",
  "container_scanning": {
    "fossa": {
      "team": "Platform Team",
      "labels": ["production"]
    }
  },
  "sca_scanning": {
    "enabled": true
  }
}
```

## Usage in Workflows

### Container Scan and Guard Workflow

```yaml
name: Container Security Scan

on:
  pull_request:
  push:
    branches: [main]

jobs:
  scan:
    uses: SolaceDev/solace-public-workflows/.github/workflows/container-scan-and-guard.yaml@main
    with:
      container_image: "my-registry/my-image:${{ github.sha }}"
      use_vault: true
      vault_url: ${{ vars.GCP_VAULT_ADDR }}
      config_file: ".github/workflow-config.json"
```

The workflow will automatically:
1. Load configuration from `.github/workflow-config.json`
2. Retrieve secrets from Vault using the configured paths
3. Apply FOSSA policies and team assignments
4. Send notifications to the configured Slack channel

### Custom Workflow Integration

```yaml
jobs:
  custom_scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Load Config
        id: config
        uses: SolaceDev/solace-public-workflows/workflow-config-loader@main
        with:
          config_file: .github/workflow-config.json
          config_type: container_scanning

      - name: Use Config Values
        run: |
          echo "Team: ${{ steps.config.outputs.fossa_team }}"
          echo "Labels: ${{ steps.config.outputs.fossa_labels }}"

          if [ "${{ steps.config.outputs.fossa_licensing_mode }}" = "BLOCK" ]; then
            echo "Licensing violations will block the build"
          fi
```

## How It Works

1. **Loads JSON File**: Reads and validates `.github/workflow-config.json`
2. **Parses Configuration**: Extracts values for the specified `config_type`
3. **Applies Defaults**: Uses sensible defaults for missing optional fields
4. **Outputs Values**: Makes all configuration available as action outputs
5. **Logs Summary**: Displays parsed configuration for transparency

## Error Handling

The action will fail with clear error messages if:

- **Config file not found**: `❌ Configuration file not found: .github/workflow-config.json`
- **Invalid JSON**: `❌ Invalid JSON syntax in .github/workflow-config.json`
- **Missing required fields**: Specific error indicating which field is required

## Migration Guide

### Migrating from Workflow Inputs to Config File

**Before (15+ workflow inputs):**
```yaml
- uses: SolaceDev/solace-public-workflows/.github/workflows/container-scan-and-guard.yaml@main
  with:
    container_image: "my-image:tag"
    fossa_licensing_mode: "BLOCK"
    fossa_licensing_block_on: "policy_conflict"
    fossa_vulnerability_mode: "BLOCK"
    fossa_vulnerability_block_on: "critical,high"
    vault_secret_path: "/path/to/secret"
    vault_aws_role: "/path/to/aws/role"
    slack_channel: "#your-slack-channel"
    # ... many more inputs
```

**After (6 workflow inputs):**
```yaml
- uses: SolaceDev/solace-public-workflows/.github/workflows/container-scan-and-guard.yaml@main
  with:
    container_image: "my-image:tag"
    use_vault: true
    vault_url: ${{ vars.GCP_VAULT_ADDR }}
    config_file: ".github/workflow-config.json"
```

All policy and team configuration moves to `.github/workflow-config.json`.

## Related Documentation

- **Full Schema Reference**: See the comprehensive schema documentation in this directory
- **Container Scanning Framework**: [container/container-scan/README.md](../container/container-scan/README.md)
- **FOSSA Integration**: [container/fossa-scan/README.md](../container/fossa-scan/README.md)
- **Architecture Design**: [Container Scan Architecture](https://github.com/SolaceDev/cicd-processes-docs/blob/main/processes/security-scanning/design/container-scan-config-architecture.md)

## Support

For questions or issues:
- Report bugs in the [solace-public-workflows](https://github.com/SolaceDev/solace-public-workflows) repository
- Refer to schema documentation for configuration options
- Check workflow logs for detailed parsing output
